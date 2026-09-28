// ==UserScript==
// @name         AI Chat Export Recorder
// @namespace    local.ai-chat-recorder
// @version      2.22
// @description  Captures chat JSON responses; exports clean SaveAI-format chat files.
// @match        *://*/*
// @run-at       document-start
// @grant        none
// ==/UserScript==

(function () {
    "use strict";

    var MAX_RESPONSES = 500;
    var USER_ROLES = ["user", "human", "me"];
    var ASSISTANT_ROLES = ["assistant", "bot", "model", "ai"];
    var ROLE_KEYS = ["role", "sender", "from", "author"];
    var TEXT_KEYS = ["contents", "content", "text", "parts", "message", "body",
                     "content_blocks", "fragments", "content_list", "blocks"];
    var TEXT_FIELD_KEYS = ["text", "content", "value", "body", "part", "parts"];
    var TEXT_MARKERS = ["text", "output_text", "markdown", "request", "response"];
    var TIME_KEYS = ["created_at", "create_time", "created", "createTime",
                     "createdAt", "inserted_at", "timestamp"];
    var MODEL_KEYS = ["displayModel", "display_model", "modelName", "model",
                      "modelId"];

    var buffer = [];
    var button = null;

    function isDict(v) {
        return v !== null && typeof v === "object" && !Array.isArray(v);
    }

    function getRole(node) {
        for (var i = 0; i < ROLE_KEYS.length; i++) {
            var value = node[ROLE_KEYS[i]];
            if (typeof value === "string" && value.trim()) {
                return value.trim().toLowerCase();
            }
            if (isDict(value) && typeof value.role === "string"
                    && value.role.trim()) {
                return value.role.trim().toLowerCase();
            }
        }
        return "";
    }

    function collectText(node, out) {
        if (typeof node === "string") {
            if (node) out.push(node);
        } else if (Array.isArray(node)) {
            for (var i = 0; i < node.length; i++) collectText(node[i], out);
        } else if (isDict(node)) {
            var phase = node.phase;
            if (typeof phase === "string"
                    && phase.toLowerCase().indexOf("thinking") !== -1) {
                return;
            }
            var marker = node.type !== undefined ? node.type : node.content_type;
            if (typeof marker === "string"
                    && TEXT_MARKERS.indexOf(marker.toLowerCase()) === -1) {
                return;
            }
            for (var j = 0; j < TEXT_FIELD_KEYS.length; j++) {
                if (TEXT_FIELD_KEYS[j] in node) {
                    collectText(node[TEXT_FIELD_KEYS[j]], out);
                }
            }
        }
    }

    function getText(node) {
        for (var i = 0; i < TEXT_KEYS.length; i++) {
            var key = TEXT_KEYS[i];
            if (!(key in node)) continue;
            var parts = [];
            collectText(node[key], parts);
            var text = "";
            for (var j = 0; j < parts.length; j++) {
                if (parts[j]) text += (text ? "\n" : "") + parts[j];
            }
            text = text.trim();
            if (text) return text;
        }
        return "";
    }

    function coerceTime(value) {
        if (value instanceof Date) {
            return isNaN(value.getTime()) ? null : value;
        }
        if (typeof value === "number" && isFinite(value)) {
            var seconds = value > 1e11 ? value / 1000 : value;
            if (seconds >= 1e9 && seconds < 4e9) {
                var d = new Date(seconds * 1000);
                if (!isNaN(d.getTime())) return d;
            }
            return null;
        }
        if (typeof value === "string" && value.trim()) {
            var s = value.trim();
            var t = Date.parse(s.replace(" ", "T").replace("Z", "+00:00"));
            if (isNaN(t)) t = Date.parse(s);
            if (!isNaN(t)) return new Date(t);
        }
        return null;
    }

    function pad2(n) { return (n < 10 ? "0" : "") + n; }

    function formatWhen(d) {
        return d.getFullYear() + "-" + pad2(d.getMonth() + 1) + "-" + pad2(d.getDate())
            + " " + pad2(d.getHours()) + ":" + pad2(d.getMinutes())
            + ":" + pad2(d.getSeconds());
    }

    function getWhen(node) {
        for (var i = 0; i < TIME_KEYS.length; i++) {
            var key = TIME_KEYS[i];
            if (key in node) {
                var d = coerceTime(node[key]);
                if (d) return d;
            }
        }
        return null;
    }

    function getModel(node) {
        for (var i = 0; i < MODEL_KEYS.length; i++) {
            var v = node[MODEL_KEYS[i]];
            if (typeof v === "string" && v.trim()) return v.trim();
        }
        return "";
    }

    function parseMessage(node) {
        var role = getRole(node);
        if (!role) return null;
        var text = getText(node);
        if (!text) return null;
        return {
            role: role,
            text: text,
            when: getWhen(node),
            model: getModel(node),
            id: typeof node.id === "string" ? node.id : ""
        };
    }

    function walkMessages(node, out) {
        if (Array.isArray(node)) {
            for (var i = 0; i < node.length; i++) walkMessages(node[i], out);
        } else if (isDict(node)) {
            var m = parseMessage(node);
            if (m) { out.push(m); return; }
            for (var key in node) {
                if (Object.prototype.hasOwnProperty.call(node, key)) {
                    walkMessages(node[key], out);
                }
            }
        }
    }

    function isGeminiId(s) {
        return typeof s === "string" && s.length > 12
            && (s.indexOf("c_") === 0 || s.indexOf("r_") === 0);
    }

    function findGeminiTurns(node, out) {
        if (Array.isArray(node)) {
            if (node.length >= 4 && Array.isArray(node[0]) && node[0].length === 2
                    && isGeminiId(node[0][0]) && isGeminiId(node[0][1])
                    && Array.isArray(node[2]) && Array.isArray(node[3])) {
                collectGeminiTurn(node, out);
                return;
            }
            for (var i = 0; i < node.length; i++) findGeminiTurns(node[i], out);
        } else if (node && typeof node === "object") {
            for (var key in node) {
                if (Object.prototype.hasOwnProperty.call(node, key)) {
                    findGeminiTurns(node[key], out);
                }
            }
        }
    }

    function collectGeminiTurn(turn, out) {
        var userEl = turn[2];
        var assistantEl = turn[3];
        var tsEl = turn[4];
        var when = null;
        if (Array.isArray(tsEl) && tsEl.length === 2
                && typeof tsEl[0] === "number" && typeof tsEl[1] === "number") {
            when = coerceTime(tsEl[0]);
        }
        if (Array.isArray(userEl) && Array.isArray(userEl[0])
                && typeof userEl[0][0] === "string" && userEl[0][0].trim()) {
            out.push({ role: "user", text: userEl[0][0].trim(), when: when,
                       model: "", id: "" });
        }
        if (Array.isArray(assistantEl) && Array.isArray(assistantEl[0])
                && Array.isArray(assistantEl[0][0])
                && typeof assistantEl[0][0][0] === "string"
                && assistantEl[0][0][0].indexOf("rc_") === 0
                && Array.isArray(assistantEl[0][0][1])
                && typeof assistantEl[0][0][1][0] === "string") {
            out.push({ role: "assistant", text: assistantEl[0][0][1][0],
                       when: when, model: "", id: assistantEl[0][0][0] });
        }
    }

    function parseBatchexecute(text) {
        var out = [];
        var lines = text.split("\n");
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            if (line.indexOf('[["wrb.fr"') !== 0) continue;
            var frames;
            try { frames = JSON.parse(line); } catch (e) { continue; }
            if (!Array.isArray(frames)) continue;
            for (var j = 0; j < frames.length; j++) {
                var frame = frames[j];
                if (!Array.isArray(frame) || frame.length < 3) continue;
                if (frame[0] !== "wrb.fr") continue;
                if (typeof frame[2] !== "string") continue;
                try {
                    out.push(JSON.parse(frame[2]));
                } catch (e) { /* not a JSON payload */ }
            }
        }
        return out;
    }

    function dedup(messages) {
        var seen = {};
        var out = [];
        for (var i = 0; i < messages.length; i++) {
            var m = messages[i];
            var key = m.role + "\u0000" + m.text;
            if (seen[key]) continue;
            seen[key] = true;
            out.push(m);
        }
        return out;
    }

    function order(messages) {
        if (messages.length < 2) return messages;
        for (var i = 0; i < messages.length; i++) {
            if (!messages[i].when) return messages;
        }
        return messages.slice().sort(function (a, b) {
            return Math.floor(a.when.getTime() / 1000)
                 - Math.floor(b.when.getTime() / 1000);
        });
    }

    function uuid() {
        if (window.crypto && crypto.randomUUID) {
            try { return crypto.randomUUID(); } catch (e) { /* fall through */ }
        }
        return "id-" + Date.now() + "-" + Math.random().toString(36).slice(2, 10);
    }

    function toSaveai(messages, groupId) {
        var entries = [];
        for (var i = 0; i < messages.length; i++) {
            var m = messages[i];
            var role;
            if (USER_ROLES.indexOf(m.role) !== -1) role = "user";
            else if (ASSISTANT_ROLES.indexOf(m.role) !== -1) role = "assistant";
            else continue;
            var id = m.id || uuid();
            entries.push({
                id: id,
                ids: [id],
                chatGroupId: groupId,
                role: role,
                model: m.model,
                displayModel: m.model,
                modelId: m.model,
                contents: [{ type: "text", content: m.text }],
                created_at: m.when ? formatWhen(m.when) : null,
                updated_at: 0
            });
        }
        return entries;
    }

    function extractDialog() {
        var found = [];
        for (var i = 0; i < buffer.length; i++) {
            walkMessages(buffer[i].body, found);
            findGeminiTurns(buffer[i].body, found);
        }
        return order(dedup(found));
    }

    function looksLikeChatBody(text) {
        return text.indexOf('"role"') !== -1
            || text.indexOf('"author"') !== -1
            || text.indexOf('"sender"') !== -1
            || text.indexOf(")]}'") === 0;
    }

    function capture(url, text) {
        if (buffer.length >= MAX_RESPONSES) return;
        var body;
        if (text.indexOf(")]}'") === 0) {
            var payloads = parseBatchexecute(text);
            if (!payloads.length) return;
            body = payloads;
        } else {
            try { body = JSON.parse(text); } catch (e) { return; }
        }
        buffer.push({ url: String(url), body: body });
        showButton();
    }

    function jsonTitle() {
        for (var i = 0; i < buffer.length; i++) {
            var body = buffer[i].body;
            if (isDict(body) && typeof body.title === "string"
                    && body.title.trim()) {
                return body.title.trim();
            }
            if (isDict(body) && isDict(body.data)
                    && typeof body.data.title === "string"
                    && body.data.title.trim()) {
                return body.data.title.trim();
            }
        }
        return "";
    }

    function cleanPageTitle() {
        var t = (document.title || "").trim();
        var cut = Math.max(t.lastIndexOf(" | "), t.lastIndexOf(" — "),
                           t.lastIndexOf(" - "));
        if (cut > 0) { t = t.slice(0, cut).trim(); }
        return t;
    }

    function chosenTitle() {
        return jsonTitle() || cleanPageTitle();
    }

    function slugify(text) {
        var s = String(text || "").trim().replace(/\s+/g, "-");
        s = s.replace(/[^\w\u0400-\u04FF-]/g, "");
        s = s.replace(/-{2,}/g, "-").replace(/^-+|-+$/g, "");
        return s.slice(0, 60);
    }

    function showButton() {
        if (button) { updateButton(); return; }
        if (!document.body) {
            document.addEventListener("DOMContentLoaded", showButton);
            return;
        }
        button = document.createElement("button");
        button.style.cssText = [
            "position:fixed", "right:12px", "top:calc(50% - 32px)",
            "z-index:2147483647",
            "padding:4px 8px", "border:1px solid #888", "border-radius:6px",
            "background:rgba(30,30,30,0.85)", "color:#fff", "font:12px sans-serif",
            "cursor:pointer", "box-shadow:0 2px 6px rgba(0,0,0,0.4)", "opacity:0.85"
        ].join(";");
        button.addEventListener("click", function (e) {
            if (e.shiftKey) exportRaw(); else exportClean();
        });
        button.addEventListener("contextmenu", function (e) {
            e.preventDefault();
            buffer = [];
            updateButton();
        });
        document.body.appendChild(button);
        updateButton();
    }

    function updateButton() {
        if (!button) return;
        button.textContent = "E";
        button.title = "Export — " + buffer.length + " response(s) captured.\n"
            + "Click: save a clean chat file (SaveAI format).\n"
            + "Shift+click: raw dump for diagnostics.\n"
            + "Right click: clear the buffer (start the next chat).";
    }

    function download(blob, name) {
        var link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = name;
        document.body.appendChild(link);
        link.click();
        setTimeout(function () {
            URL.revokeObjectURL(link.href);
            link.remove();
        }, 60000);
    }

    function fetchKimiChat() {
        var mId = window.location.href.match(/\/chat\/([^/?#]+)/);
        if (!mId) {
            alert("Kimi: open the chat itself (the address must "
                + "contain /chat/...) and press E again.");
            return;
        }
        // Auth: the kimi-auth cookie first (the SaveAI recipe), then
        // the access_token from localStorage (the page keeps it there
        // and refreshes it — the live proven key).
        var headers = { "Content-Type": "application/json" };
        var mAuth = document.cookie.match(/kimi-auth=([^;]+)/);
        var lsToken = null;
        try { lsToken = localStorage.getItem("access_token"); } catch (e) {}
        var token = mAuth ? mAuth[1] : lsToken;
        if (token) {
            headers["Authorization"] = "Bearer " + token;
        }
        fetch("/apiv2/kimi.gateway.chat.v1.ChatService/ListMessages", {
            method: "POST",
            headers: headers,
            body: JSON.stringify({ chat_id: mId[1] })
        }).then(function (r) { return r.text(); }).then(function (raw) {
            var text = raw;
            // Kimi returns messages NEWEST-FIRST — reverse into the
            // dialog order before parsing (the second-granularity sort
            // then keeps the site's own pair order, as with DeepSeek).
            try {
                var payload = JSON.parse(raw);
                if (payload && Array.isArray(payload.messages)) {
                    payload.messages.reverse();
                    text = JSON.stringify(payload);
                }
            } catch (e) { /* keep the raw text */ }
            capture("kimi-api",
                    "/apiv2/kimi.gateway.chat.v1.ChatService/ListMessages",
                    "application/json", text);
            var messages = extractDialog();
            if (messages.length) {
                exportClean();  // the buffer is filled now
            } else {
                var blob = new Blob([text], { type: "application/json" });
                download(blob, "kimi-response.json");
                alert("Kimi answered, the raw response is downloaded "
                    + "as kimi-response.json — send that file to the "
                    + "assistant.");
            }
        }).catch(function (e) {
            alert("Kimi request failed: " + String(e));
        });
    }

    function exportClean() {
        var messages = extractDialog();
        if (!messages.length) {
            // Kimi: its chats live behind an apiv2 endpoint the page
            // never calls — ask directly (the SaveAI recipe).
            if (location.hostname.indexOf("kimi.") !== -1) {
                fetchKimiChat();
                updateButton();
                return;
            }
            collectIndexedChats(function (chats) {
                if (!chats.length) {
                    alert("No chat messages found in the captured "
                        + "responses or the local storage.\n"
                        + "Try Shift+click for a raw dump and report it.");
                    return;
                }
                for (var i = 0; i < chats.length; i++) {
                    var found = [];
                    walkMessages(chats[i], found);
                    var msgs = order(dedup(found));
                    if (!msgs.length) continue;
                    var entries = toSaveai(msgs, uuid());
                    var blob = new Blob(
                        [JSON.stringify(entries)],
                        { type: "application/json" });
                    var stamp = "";
                    if (msgs[0].when) {
                        var day = msgs[0].when;
                        stamp = "_" + day.getFullYear() + "_"
                            + pad2(day.getMonth() + 1) + "_"
                            + pad2(day.getDate());
                    }
                    var title = typeof chats[i].title === "string"
                        ? chats[i].title : "";
                    download(blob, (slugify(title) || "chat") + stamp + ".json");
                }
            });
            updateButton();
            return;
        }
        var entries = toSaveai(messages, uuid());
        var blob = new Blob([JSON.stringify(entries)],
                            { type: "application/json" });
        var stamp = "";
        if (messages.length && messages[0].when) {
            var day = messages[0].when;
            stamp = "_" + day.getFullYear() + "_" + pad2(day.getMonth() + 1)
                + "_" + pad2(day.getDate());
        }
        download(blob, (slugify(chosenTitle()) || "chat") + stamp + ".json");
        updateButton();
    }

    function exportRaw() {
        var payload = {
            source: "ai-chat-recorder-raw",
            exported_at: new Date().toISOString(),
            title: chosenTitle(),
            response_count: buffer.length,
            responses: buffer
        };
        var blob = new Blob([JSON.stringify(payload)],
                            { type: "application/json" });
        var stamp = new Date();
        var stampText = ""
            + stamp.getFullYear() + pad2(stamp.getMonth() + 1)
            + pad2(stamp.getDate())
            + "-" + pad2(stamp.getHours()) + pad2(stamp.getMinutes())
            + pad2(stamp.getSeconds());
        download(blob, (slugify(chosenTitle()) || "chat") + "-raw-"
               + stampText + ".json");
    }

    function readAllRecords(db, storeName, cb) {
        var out = [];
        try {
            var tx = db.transaction(storeName, "readonly");
            var cursor = tx.objectStore(storeName).openCursor();
            cursor.onsuccess = function () {
                var c = cursor.result;
                if (c) { out.push(c.value); c.continue(); }
            };
            tx.oncomplete = function () { cb(out); };
            tx.onerror = function () { cb(out); };
        } catch (e) { cb(out); }
    }

    function collectIndexedChats(done) {
        if (!window.indexedDB
                || typeof indexedDB.databases !== "function") {
            done([]);
            return;
        }
        indexedDB.databases().then(function (dbs) {
            var chats = [];
            var pending = dbs.length;
            if (!pending) { done(chats); return; }
            dbs.forEach(function (dbInfo) {
                var openReq = indexedDB.open(dbInfo.name);
                openReq.onsuccess = function () {
                    var db = openReq.result;
                    var storeNames = Array.prototype.slice.call(
                        db.objectStoreNames);
                    var interesting = storeNames.filter(function (n) {
                        return /chat|message|conversation/i.test(n);
                    });
                    if (!interesting.length) { db.close(); step(); return; }
                    var left = interesting.length;
                    interesting.forEach(function (sName) {
                        readAllRecords(db, sName, function (records) {
                            for (var i = 0; i < records.length; i++) {
                                var rec = records[i];
                                if (isDict(rec)
                                        && Array.isArray(rec.messages)) {
                                    chats.push(rec);
                                }
                            }
                            left--;
                            if (!left) { db.close(); step(); }
                        });
                    });
                };
                openReq.onerror = function () { step(); };
            });
            function step() {
                pending--;
                if (pending <= 0) done(chats);
            }
        }).catch(function () { done([]); });
    }

    function bustCacheUrl(url) {
        var u = String(url);
        var fresh = u.replace(
            /([?&])(cache_version|cache_reset_at|cache_cursor)=\d+/g,
            "$1$2=0"
        );
        return fresh !== u ? fresh : null;
    }

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
                    if (ctype.indexOf("json") !== -1) {
                        response.clone().text().then(function (text) {
                            if (text && looksLikeChatBody(text)) {
                                capture(response.url, text);
                            }
                        }).catch(function () {});
                    }
                } catch (e) { /* never break the page */ }
                return response;
            });
        };
    }

    var originalOpen = XMLHttpRequest.prototype.open;
    var originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
        var busted = bustCacheUrl(url);
        if (busted) {
            arguments[1] = busted;
            this.__chatRecorderUrl = busted;
        } else {
            this.__chatRecorderUrl = url;
        }
        return originalOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
        var xhr = this;
        xhr.addEventListener("load", function () {
            try {
                var ctype = xhr.getResponseHeader("content-type") || "";
                var text = xhr.responseText;
                if (ctype.indexOf("json") !== -1 && text
                        && looksLikeChatBody(text)) {
                    capture(xhr.__chatRecorderUrl, text);
                }
            } catch (e) { /* never break the page */ }
        });
        return originalSend.apply(this, arguments);
    };

    // ── WebSocket: textual chat frames (some sites deliver the
    // history over a socket, not REST); binary (proto) frames are
    // skipped — they need a per-site decoder, not a heuristic ──
    var MAX_WS_PER_SOCKET = 50;
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
                    var data = ev.data;
                    if (typeof data === "string"
                            && looksLikeChatBody(data)) {
                        count++;
                        capture(url, data);
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

    // ── EventSource (SSE): a separate API, not fetch/XHR ──
    var OriginalES = window.EventSource;
    if (typeof OriginalES === "function") {
        window.EventSource = function (url, config) {
            var es = new OriginalES(url, config);
            try {
                es.addEventListener("message", function (ev) {
                    var data = String(ev.data || "");
                    if (looksLikeChatBody(data)) {
                        capture(url, data);
                    }
                });
            } catch (e) { /* never break the page */ }
            return es;
        };
        window.EventSource.prototype = OriginalES.prototype;
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", showButton);
    } else {
        showButton();
    }
})();
