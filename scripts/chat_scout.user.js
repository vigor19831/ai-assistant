// ==UserScript==
// @name         AI Chat Scout (diagnostic)
// @namespace    local.ai-chat-scout
// @version      1.13
// @description  Traffic + storages + Web Worker recon: requests, schemas, message samples, IndexedDB, Cache, worker fetches.
// @match        *://*/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
    "use strict";

    var MAX_ITEMS = 120;
    var MAX_MSG_SAMPLES = 10;
    var MAX_DATE_SAMPLES = 25;
    var MAX_WS_PER_SOCKET = 15;
    var MAX_LS_KEYS = 40;
    var MAX_CACHE_ENTRIES = 40;
    var MAX_DB_SAMPLES = 12;
    var MAX_WORKER_TEXT = 262144;

    var captures = [];
    var totalSeen = 0;
    var button = null;

    function shortText(s, n) {
        s = String(s);
        return s.length > n ? s.slice(0, n) + "…[" + s.length + "]" : s;
    }

    function shortValue(v) {
        var s;
        try { s = JSON.stringify(v); } catch (e) { return "?"; }
        return shortText(s, 120);
    }

    function schemaOf(node, depth) {
        if (depth > 5) return "…";
        if (node === null) return "null";
        var t = typeof node;
        if (t === "string") {
            return "str[" + node.length + "] " + shortText(node, 40);
        }
        if (t === "number" || t === "boolean") {
            return t + ":" + String(node);
        }
        if (Array.isArray(node)) {
            if (node.length === 0) return "[]";
            return "[" + node.length + "] " + schemaOf(node[0], depth + 1);
        }
        if (t === "object") {
            var keys = Object.keys(node);
            var parts = [];
            for (var i = 0; i < keys.length && i < 30; i++) {
                parts.push(keys[i] + "=" + schemaOf(node[keys[i]], depth + 1));
            }
            return "{" + keys.length + "} " + parts.join(", ");
        }
        return t;
    }

    var ROLE_KEYS = ["role", "sender", "from", "author"];

    function findMessageLike(node, out, depth) {
        if (out.length >= MAX_MSG_SAMPLES || depth > 8) return;
        if (Array.isArray(node)) {
            for (var i = 0; i < node.length && out.length < MAX_MSG_SAMPLES; i++) {
                findMessageLike(node[i], out, depth + 1);
            }
            return;
        }
        if (!node || typeof node !== "object") return;
        var hasRole = false;
        for (var k = 0; k < ROLE_KEYS.length; k++) {
            if (Object.prototype.hasOwnProperty.call(node, ROLE_KEYS[k])) {
                hasRole = true;
                break;
            }
        }
        if (hasRole) {
            var sample = {};
            var keys = Object.keys(node);
            for (var j = 0; j < keys.length; j++) {
                sample[keys[j]] = shortValue(node[keys[j]]);
            }
            out.push({ keys: keys, sample: sample });
            return;
        }
        for (var key in node) {
            if (Object.prototype.hasOwnProperty.call(node, key)) {
                findMessageLike(node[key], out, depth + 1);
            }
        }
    }

    var DATE_KEY_RE = /time|date|creat|stamp|_at\b/i;

    function findDateLike(node, out, path, depth) {
        if (out.length >= MAX_DATE_SAMPLES || depth > 8) return;
        if (Array.isArray(node)) {
            for (var i = 0; i < Math.min(node.length, 20); i++) {
                findDateLike(node[i], out, path + "[]", depth + 1);
            }
            return;
        }
        if (!node || typeof node !== "object") return;
        for (var key in node) {
            if (!Object.prototype.hasOwnProperty.call(node, key)) continue;
            if (DATE_KEY_RE.test(key)) {
                out.push({ path: path + "." + key, value: shortValue(node[key]) });
                if (out.length >= MAX_DATE_SAMPLES) return;
            }
        }
        for (var key2 in node) {
            if (!Object.prototype.hasOwnProperty.call(node, key2)) continue;
            findDateLike(node[key2], out, path + "." + key2, depth + 1);
        }
    }

    function analyze(bodyText) {
        var data;
        try { data = JSON.parse(bodyText); } catch (e) { return null; }
        var msg = [];
        findMessageLike(data, msg, 0);
        var dates = [];
        findDateLike(data, dates, "$", 0);
        return {
            schema: schemaOf(data, 0),
            messageLike: msg,
            dateLike: dates
        };
    }

    function addCapture(kind, url, ctype, bodyText) {
        totalSeen++;
        if (captures.length >= MAX_ITEMS) return;
        var entry = {
            kind: kind,
            url: shortText(url, 200),
            ctype: String(ctype || ""),
            size: bodyText.length
        };
        if (bodyText.indexOf(")]}'") === 0) {
            entry.batchexecute = shortText(bodyText, 262144);
            captures.push(entry);
            updateButton();
            return;
        }
        var analysis = analyze(bodyText);
        if (analysis) {
            entry.json = true;
            entry.schema = analysis.schema;
            if (analysis.messageLike.length) entry.messageLike = analysis.messageLike;
            if (analysis.dateLike.length) entry.dateLike = analysis.dateLike;
        } else if (/^\s*data:/m.test(bodyText)) {
            var lines = [];
            var raw = bodyText.split("\n");
            for (var i = 0; i < raw.length && lines.length < 5; i++) {
                if (raw[i].indexOf("data:") === 0) {
                    var t = raw[i].slice(5).trim();
                    var a = analyze(t);
                    lines.push(a ? a : shortText(t, 150));
                }
            }
            entry.sse = lines;
        } else {
            entry.json = false;
            entry.head = shortText(bodyText, 150);
        }
        captures.push(entry);
        updateButton();
    }

    // ── Web Worker recon: Kimi-class sites fetch their chats inside a
    // Dedicated Worker — invisible to the page. Wrap the Worker
    // constructor: a bootstrap blob importScripts the original script,
    // then patches self.fetch inside the worker; captured responses
    // are stored in a dedicated IndexedDB, which this page reads at
    // report time. The site's own message flow is never touched.
    var WORKER_DB = "scout-worker-captures";
    var WORKER_STORE = "captures";

    function workerBootstrap(originalUrl) {
        return "importScripts(" + JSON.stringify(originalUrl) + ");\n" +
            "(function () {" +
            "  var origFetch = self.fetch;" +
            "  self.fetch = function () {" +
            "    var args = arguments;" +
            "    return origFetch.apply(self, args).then(function (response) {" +
            "      try {" +
            "        var ct = response.headers.get('content-type') || '';" +
            "        if (ct.indexOf('json') !== -1) {" +
            "          response.clone().text().then(function (text) {" +
            "            try {" +
            "              var open = indexedDB.open('" + WORKER_DB + "', 1);" +
            "              open.onupgradeneeded = function () {" +
            "                open.result.createObjectStore('" + WORKER_STORE + "');" +
            "              };" +
            "              open.onsuccess = function () {" +
            "                var db = open.result;" +
            "                var tx = db.transaction('" + WORKER_STORE + "', 'readwrite');" +
            "                tx.objectStore('" + WORKER_STORE + "').put({" +
            "                  url: String(response.url)," +
            "                  text: text.slice(0, " + MAX_WORKER_TEXT + ")" +
            "                });" +
            "                tx.oncomplete = function () { db.close(); };" +
            "              };" +
            "            } catch (e) {}" +
            "          }).catch(function () {});" +
            "        }" +
            "      } catch (e) {}" +
            "      return response;" +
            "    });" +
            "  };" +
            "})();";
    }

    var OriginalWorker = window.Worker;
    if (typeof OriginalWorker === "function") {
        window.Worker = function (url, options) {
            var injectable = typeof url === "string"
                && /^https?:/i.test(url)
                && !(options && options.type === "module");
            if (injectable) {
                var blobUrl = URL.createObjectURL(new Blob(
                    [workerBootstrap(url)],
                    { type: "application/javascript" }));
                var w = new OriginalWorker(blobUrl);
                return w;
            }
            return options !== undefined
                ? new OriginalWorker(url, options)
                : new OriginalWorker(url);
        };
        window.Worker.prototype = OriginalWorker.prototype;
    }

    function collectWorkerCaptures(done) {
        // The database may not exist yet (no injected worker has run
        // so far): open() then creates it EMPTY — without the store.
        // Both states must reach done(), or the report chain hangs.
        try {
            var openReq = indexedDB.open(WORKER_DB, 1);
            openReq.onupgradeneeded = function () {
                openReq.result.createObjectStore(WORKER_STORE);
            };
            openReq.onerror = function () { done([]); };
            openReq.onsuccess = function () {
                var db = openReq.result;
                var out = [];
                if (!db.objectStoreNames.contains(WORKER_STORE)) {
                    db.close();
                    done([]);
                    return;
                }
                var tx = db.transaction(WORKER_STORE, "readonly");
                var cur = tx.objectStore(WORKER_STORE).openCursor();
                cur.onsuccess = function () {
                    var c = cur.result;
                    if (c && out.length < MAX_ITEMS) {
                        var a = analyze(c.value.text || "");
                        var rec = { url: shortText(c.value.url, 200),
                                    size: (c.value.text || "").length };
                        if (a) {
                            rec.schema = a.schema;
                            if (a.messageLike.length) {
                                rec.messageLike = a.messageLike;
                            }
                            if (a.dateLike.length) {
                                rec.dateLike = a.dateLike;
                            }
                        } else {
                            rec.head = shortText(c.value.text || "", 150);
                        }
                        out.push(rec);
                        c.continue();
                    }
                };
                tx.oncomplete = function () { done(out); };
                tx.onerror = function () { done(out); };
            };
        } catch (e) { done([]); }
    }

    // ── local storage recon ──

    function decodeInPlace(container, key) {
        var v = container[key];
        if (typeof v === "string" && v.length > 64
                && v.indexOf("eyJ") === 0) {
            try {
                var decoded = atob(v);
                try {
                    container[key] = JSON.parse(decoded);
                } catch (e) {
                    container[key] = decoded;
                }
                return true;
            } catch (e) { /* not base64 */ }
        }
        return false;
    }

    function decodeBase64Strings(node) {
        var changed = false;
        if (Array.isArray(node)) {
            for (var i = 0; i < node.length; i++) {
                if (decodeInPlace(node, i)) { changed = true; }
                else if (decodeBase64Strings(node[i])) { changed = true; }
            }
        } else if (node && typeof node === "object") {
            for (var key in node) {
                if (Object.prototype.hasOwnProperty.call(node, key)) {
                    if (decodeInPlace(node, key)) { changed = true; }
                    else if (decodeBase64Strings(node[key])) {
                        changed = true;
                    }
                }
            }
        }
        return changed;
    }

    function describeValue(v) {
        if (v instanceof ArrayBuffer) return "ArrayBuffer[" + v.byteLength + "]";
        if (typeof Blob !== "undefined" && v instanceof Blob) {
            return "Blob[" + v.size + "/" + (v.type || "?") + "]";
        }
        if (v === null) return "null";
        var t = typeof v;
        if (t === "string") {
            if (v.length > 64 && v.indexOf("eyJ") === 0) {
                try {
                    var decoded = atob(v);
                    var a = analyze(decoded);
                    if (a) return a;
                    return "b64: " + shortText(decoded, 200);
                } catch (e) { /* not valid base64 */ }
            }
            return "str: " + shortText(v, 120);
        }
        if (t === "object" || Array.isArray(v)) {
            try {
                var expanded = JSON.parse(JSON.stringify(v));
                if (decodeBase64Strings(expanded)) {
                    var a2 = analyze(JSON.stringify(expanded));
                    if (a2) return a2;
                }
            } catch (e) { /* keep the plain path */ }
        }
        if (t === "number" || t === "boolean") {
            return t + ": " + String(v);
        }
        var s;
        try { s = JSON.stringify(v); } catch (e) { return "unserializable"; }
        if (s === undefined) return "undefined";
        var a3 = analyze(s);
        return a3 || shortText(s, 200);
    }

    function describeStore(db, storeName) {
        return new Promise(function (resolve) {
            var info = { name: storeName, count: -1, samples: [] };
            try {
                var tx = db.transaction(storeName, "readonly");
                var store = tx.objectStore(storeName);
                var countReq = store.count();
                countReq.onsuccess = function () {
                    info.count = countReq.result;
                };
                var cur = store.openCursor(null, "next");
                cur.onsuccess = function () {
                    var c = cur.result;
                    if (c && info.samples.length < MAX_DB_SAMPLES) {
                        info.samples.push(describeValue(c.value));
                        c.continue();
                    }
                };
                tx.oncomplete = function () { resolve(info); };
                tx.onerror = function () { resolve(info); };
                tx.onabort = function () { resolve(info); };
            } catch (e) {
                info.error = String(e);
                resolve(info);
            }
        });
    }

    function collectIndexedDB(done) {
        if (!window.indexedDB) { done({ note: "indexedDB unavailable" }); return; }
        if (typeof indexedDB.databases !== "function") {
            done({ note: "databases() unsupported in this browser" });
            return;
        }
        indexedDB.databases().then(function (dbs) {
            if (!dbs.length) { done([]); return; }
            var out = [];
            var pending = dbs.length;
            dbs.forEach(function (dbInfo) {
                var openReq = indexedDB.open(dbInfo.name);
                openReq.onsuccess = function () {
                    var db = openReq.result;
                    var storeNames = Array.prototype.slice.call(db.objectStoreNames);
                    var rec = { name: dbInfo.name, version: dbInfo.version, stores: [] };
                    if (!storeNames.length) {
                        out.push(rec);
                        db.close();
                        finish();
                        return;
                    }
                    var tasks = storeNames.map(function (sName) {
                        return describeStore(db, sName);
                    });
                    Promise.all(tasks).then(function (stores) {
                        rec.stores = stores;
                        db.close();
                        out.push(rec);
                        finish();
                    });
                };
                openReq.onerror = function () {
                    out.push({ name: dbInfo.name, error: "open failed" });
                    finish();
                };
            });
            function finish() {
                pending--;
                if (pending <= 0) done(out);
            }
        }).catch(function (e) {
            done({ note: "databases() failed: " + String(e) });
        });
    }

    function collectStorage(storage) {
        var out = {};
        try {
            for (var i = 0; i < storage.length && i < MAX_LS_KEYS; i++) {
                var k = storage.key(i);
                out[k] = shortText(String(storage.getItem(k)), 120);
            }
        } catch (e) {
            return { error: String(e) };
        }
        return out;
    }

    var ASSET_RE =
        /\.(js|css|png|jpe?g|svg|woff2?|gif|webp|ico|mp4|wasm|ttf)(\?|$)/i;

    function collectCaches(done) {
        if (!window.caches) { done({ note: "CacheStorage unavailable" }); return; }
        caches.keys().then(function (names) {
            if (!names.length) { done([]); return; }
            var out = [];
            var pending = names.length;
            names.forEach(function (cname) {
                caches.open(cname).then(function (cache) {
                    cache.keys().then(function (requests) {
                        var rec = {
                            name: cname,
                            total_requests: requests.length,
                            entries: []
                        };
                        var interesting = requests.filter(function (r) {
                            return !ASSET_RE.test(r.url);
                        });
                        var subset = interesting.slice(0, MAX_CACHE_ENTRIES);
                        var left = subset.length;
                        if (!left) { out.push(rec); finish(); return; }
                        subset.forEach(function (req) {
                            var entry = { url: shortText(req.url, 200) };
                            cache.match(req).then(function (resp) {
                                if (!resp) { entry.note = "no match"; step(); return; }
                                var ct = resp.headers.get("content-type") || "";
                                entry.ctype = ct;
                                if (ct.indexOf("json") !== -1) {
                                    resp.text().then(function (t) {
                                        entry.size = t.length;
                                        var a = analyze(t);
                                        if (a) {
                                            entry.schema = a.schema;
                                            if (a.messageLike.length) {
                                                entry.messageLike = a.messageLike;
                                            }
                                            if (a.dateLike.length) {
                                                entry.dateLike = a.dateLike;
                                            }
                                        } else {
                                            entry.head = shortText(t, 150);
                                        }
                                        step();
                                    }).catch(function () { step(); });
                                } else {
                                    entry.note = "non-json";
                                    step();
                                }
                            }).catch(function () { step(); });
                            function step() {
                                rec.entries.push(entry);
                                left--;
                                if (!left) { out.push(rec); finish(); }
                            }
                        });
                    }).catch(function () {
                        out.push({ name: cname, error: "keys failed" });
                        finish();
                    });
                }).catch(function () {
                    out.push({ name: cname, error: "open failed" });
                    finish();
                });
            });
            function finish() {
                pending--;
                if (pending <= 0) done(out);
            }
        }).catch(function (e) {
            done({ note: "caches.keys() failed: " + String(e) });
        });
    }

    function pad2(n) { return (n < 10 ? "0" : "") + n; }

    function showButton() {
        if (button) { updateButton(); return; }
        if (!document.body) {
            document.addEventListener("DOMContentLoaded", showButton);
            return;
        }
        button = document.createElement("button");
        button.style.cssText = [
            "position:fixed", "right:12px", "top:50%",
            "z-index:2147483647",
            "padding:4px 8px", "border:2px solid #36c", "border-radius:6px",
            "background:rgba(20,30,60,0.9)", "color:#fff", "font:12px sans-serif",
            "cursor:pointer", "box-shadow:0 2px 6px rgba(0,0,0,0.4)", "opacity:0.9"
        ].join(";");
        button.addEventListener("click", dump);
        button.addEventListener("contextmenu", function (e) {
            e.preventDefault();
            captures = [];
            updateButton();
        });
        document.body.appendChild(button);
        updateButton();
    }

    function updateButton() {
        if (!button) return;
        button.textContent = "S";
        button.title = "Scout — " + captures.length + " capture(s).\n"
            + "Click: compact report (traffic + storages + workers).\n"
            + "Right click: clear.";
    }

    function dump() {
        // Recon runs at click time (fresh data).
        collectWorkerCaptures(function (workerReport) {
            collectIndexedDB(function (idbReport) {
                collectCaches(function (cachesReport) {
                    var s = new Date();
                    var stamp = ""
                        + s.getFullYear() + pad2(s.getMonth() + 1)
                        + pad2(s.getDate())
                        + "-" + pad2(s.getHours()) + pad2(s.getMinutes())
                        + pad2(s.getSeconds());
                    var payload = {
                        source: "ai-chat-scout",
                        host: location.hostname,
                        exported_at: new Date().toISOString(),
                        captures_seen: totalSeen,
                        captures_reported: captures.length,
                        captures: captures,
                        worker_captures: workerReport,
                        localStorage: collectStorage(window.localStorage),
                        sessionStorage: collectStorage(window.sessionStorage),
                        indexeddb: idbReport,
                        caches: cachesReport
                    };
                    var blob = new Blob(
                        [JSON.stringify(payload)],
                        { type: "application/json" }
                    );
                    var link = document.createElement("a");
                    link.href = URL.createObjectURL(blob);
                    link.download = "chat-scout-"
                        + location.hostname + "-" + stamp + ".json";
                    document.body.appendChild(link);
                    link.click();
                    setTimeout(function () {
                        URL.revokeObjectURL(link.href);
                        link.remove();
                    }, 5000);
                });
            });
        });
    }

    function bustCacheUrl(url) {
        var u = String(url);
        var fresh = u.replace(
            /([?&])(cache_version|cache_reset_at|cache_cursor)=\d+/g,
            "$1$2=0"
        );
        return fresh !== u ? fresh : null;
    }

    // ── fetch: every textual response ──
    var originalFetch = window.fetch;
    if (typeof originalFetch === "function") {
        window.fetch = function () {
            var self = this;
            var args = arguments;
            if (typeof args[0] === "string") {
                var busted = bustCacheUrl(args[0]);
                if (busted) args[0] = busted;
            }
            return originalFetch.apply(self, args).then(function (response) {
                try {
                    var ctype = response.headers.get("content-type") || "";
                    var isTextual = ctype.indexOf("json") !== -1
                            || ctype.indexOf("text/") === 0
                            || ctype.indexOf("event-stream") !== -1;
                    if (isTextual) {
                        response.clone().text().then(function (text) {
                            addCapture("fetch", response.url, ctype, text);
                        }).catch(function () {});
                    } else if (/api|rpc|grpc|connect|proto|chat|message/i
                            .test(response.url)) {
                        response.clone().arrayBuffer().then(function (buf) {
                            var bytes = new Uint8Array(buf.slice(0, 65536));
                            var runs = [];
                            var cur = "";
                            for (var i = 0; i < bytes.length; i++) {
                                var b = bytes[i];
                                if (b >= 32 && b < 127) {
                                    cur += String.fromCharCode(b);
                                } else {
                                    if (cur.length >= 4) runs.push(cur);
                                    cur = "";
                                }
                            }
                            if (cur.length >= 4) runs.push(cur);
                            addCapture("fetch-bin", response.url, ctype,
                                runs.length ? runs.join(" | ")
                                            : "no printable strings");
                        }).catch(function () {});
                    }
                } catch (e) { /* never break the page */ }
                return response;
            });
        };
    }

    // ── XHR: every textual response ──
    var originalOpen = XMLHttpRequest.prototype.open;
    var originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
        var busted = bustCacheUrl(url);
        if (busted) {
            arguments[1] = busted;
            this.__scoutUrl = busted;
        } else {
            this.__scoutUrl = url;
        }
        return originalOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
        var xhr = this;
        xhr.addEventListener("load", function () {
            try {
                var ctype = xhr.getResponseHeader("content-type") || "";
                if (ctype.indexOf("json") !== -1
                        || ctype.indexOf("text/") === 0) {
                    addCapture("xhr", xhr.__scoutUrl, ctype,
                               xhr.responseText || "");
                }
            } catch (e) { /* binary xhr: skip */ }
        });
        return originalSend.apply(this, arguments);
    };

    // ── EventSource (SSE): a separate API, not fetch/XHR ──
    var OriginalES = window.EventSource;
    if (typeof OriginalES === "function") {
        window.EventSource = function (url, config) {
            var es = new OriginalES(url, config);
            try {
                es.addEventListener("message", function (ev) {
                    addCapture("sse", url, "text/event-stream",
                               String(ev.data));
                });
            } catch (e) { /* never break the page */ }
            return es;
        };
        window.EventSource.prototype = OriginalES.prototype;
    }

    // ── WebSocket: first messages per socket ──
    var OriginalWS = window.WebSocket;
    if (typeof OriginalWS === "function") {
        window.WebSocket = function (url, protocols) {
            var ws = protocols !== undefined
                ? new OriginalWS(url, protocols)
                : new OriginalWS(url);
            var count = 0;
            try {
                ws.addEventListener("message", function (ev) {
                    if (count >= MAX_WS_PER_SOCKET) return;
                    count++;
                    var data = ev.data;
                    if (data instanceof ArrayBuffer) {
                        addCapture("ws", url, "websocket",
                                   "ArrayBuffer[" + data.byteLength + "]");
                    } else {
                        addCapture("ws", url, "websocket", String(data));
                    }
                });
            } catch (e) { /* never break the page */ }
            return ws;
        };
        window.WebSocket.prototype = OriginalWS.prototype;
        window.WebSocket.OPEN = OriginalWS.OPEN;
        window.WebSocket.CONNECTING = OriginalWS.CONNECTING;
        window.WebSocket.CLOSING = OriginalWS.CLOSING;
        window.WebSocket.CLOSED = OriginalWS.CLOSED;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", showButton);
    } else {
        showButton();
    }
})();
