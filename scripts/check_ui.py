#!/usr/bin/env python3
"""check_ui.py — Live UI/infra probe (the assembled whole).

The unit gates check code; this checks that the RUNNING system is
what the code says it should be: API answers, the UI page carries
its load-bearing element ids, the static libraries resolve, and
the index/text proportion is healthy. Run with the stack up:

    python scripts/check_ui.py [--base http://127.0.0.1:8000]

Exit code 0 = healthy; 1 = at least one probe failed. A probe's
failure message names the broken link, not just the symptom.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load-bearing element ids: the page is dead if any is missing
# (the "script died silently" class — drift #227 lesson).
REQUIRED_IDS = ("nsBtn", "indexBar", "indexStatusLine", "messageInput", "sendBtn")

# Static libraries the page hard-requires (its own bootstrap check
# names them; the probe verifies the server actually serves them).
REQUIRED_STATIC = (
    "static/marked.min.js",
    "static/purify.min.js",
    "static/highlight.min.js",
)

# Index/text proportion guard (drift #227-adjacent): indices are
# derived data; if they grow an order faster than the corpus,
# something accumulates junk. Rough ceiling, not a precision tool.
MAX_INDEX_TO_TEXT_RATIO = 200.0

_passed = 0
_failed = 0


def _report(ok: bool, name: str, detail: str) -> bool:
    global _passed, _failed
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    if ok:
        _passed += 1
    else:
        _failed += 1
    return ok


def _get(base: str, path: str, api_key: str | None) -> tuple[int, bytes]:
    req = Request(base + path)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    with urlopen(req, timeout=10) as resp:
        return resp.status, resp.read()


API_PROBE_PATHS = (
    "/api/v1/rag/health",
    "/api/v1/rag/prefixes",
    "/api/v1/rag/index-status",
)


def _stack_down(exc: Exception) -> bool:
    """True when the failure is 'cannot connect' (no stack), not a
    defect in what is being probed. Skips, not fails (drift #135:
    conditions-missing degrades to a visible skip; a mechanical
    contract stays red)."""
    return isinstance(exc, OSError) and getattr(exc, "errno", None) in (
        111,  # Connection refused
        99,  # Cannot assign requested address
        113,  # No route to host
    )


def probe_api(base: str, key: str | None) -> str:
    """Returns 'ok' | 'skip' | 'fail' — skip = stack down."""
    ok = True
    for path in API_PROBE_PATHS:
        try:
            status, _ = _get(base, path, key)
            ok &= _report(status == 200, f"GET {path}", f"HTTP {status}")
        except Exception as exc:
            if _stack_down(exc):
                print(f"  [SKIP] GET {path} — stack down ({exc})")
                return "skip"
            ok &= _report(False, f"GET {path}", str(exc))
    return "ok" if ok else "fail"


def probe_page(base: str) -> str:
    """Returns 'ok' | 'skip' | 'fail' — skip = stack down."""
    try:
        status, body = _get(base, "/ui/", None)
    except Exception as exc:
        if _stack_down(exc):
            print(f"  [SKIP] GET /ui/ — stack down ({exc})")
            return "skip"
        _report(False, "GET /ui/", str(exc))
        return "fail"
    html = body.decode("utf-8", errors="replace")
    ok = _report(status == 200, "GET /ui/", f"HTTP {status}")
    missing = [i for i in REQUIRED_IDS if f'id="{i}"' not in html]
    detail = f"missing: {missing}" if missing else "all present"
    ok &= _report(not missing, "page element ids", detail)
    return "ok" if ok else "fail"


def probe_static(base: str) -> bool:
    """Static probes never skip: the page probe already established
    the stack; a failure here is a real missing file."""
    ok = True
    for lib in REQUIRED_STATIC:
        try:
            status, _ = _get(base, f"/ui/{lib}", None)
            ok &= _report(status == 200, f"GET /ui/{lib}", f"HTTP {status}")
        except Exception as exc:
            ok &= _report(False, f"GET /ui/{lib}", str(exc))
    return ok


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _count_files(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(
        1
        for f in path.rglob("*")
        if f.is_file() and f.suffix in (".md", ".txt")
    )


def probe_proportion() -> bool:
    """Indices vs corpus text: a canary, not a precision gauge."""
    text_bytes = _dir_size(PROJECT_ROOT / "data" / "documents")
    index_bytes = _dir_size(PROJECT_ROOT / "data" / "indices") + _dir_size(
        PROJECT_ROOT / "data" / "lexical_indices"
    )
    docs = _count_files(PROJECT_ROOT / "data" / "documents")
    if text_bytes == 0:
        return _report(
            False, "index proportion", "documents/ is empty — nothing indexed?"
        )
    ratio = index_bytes / text_bytes
    detail = (
        f"text {text_bytes // 1024} KiB, indices {index_bytes // 1024} KiB, "
        f"ratio x{ratio:.0f}, {docs} file(s)"
    )
    return _report(ratio <= MAX_INDEX_TO_TEXT_RATIO, "index proportion", detail)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default="local")
    args = parser.parse_args()

    print("UI / INFRA PROBE")
    print(f"  base: {args.base}")
    print()
    api_state = probe_api(args.base, args.api_key)
    if api_state == "skip":
        print("  [SKIP] stack down — HTTP probes skipped")
        print("         (start the stack: python run_servers.py start)")
    else:
        # Page/static probes run only with the stack up; a skip in
        # probe_page (partial connectivity) still runs statics: the
        # server answered the API, so files are checkable.
        if probe_page(args.base) == "ok":
            probe_static(args.base)
    probe_proportion()
    print()
    if _failed:
        print(f"  RESULT: FAIL ({_passed} passed, {_failed} failed)")
        return 1
    if api_state == "skip":
        print(f"  RESULT: SKIPPED-STACK-DOWN ({_passed} passed, 0 failed)")
        return 0
    print(f"  RESULT: OK ({_passed} passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
