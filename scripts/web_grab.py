"""Save a web page as clean markdown via trafilatura (drift #216).

The extraction itself is trafilatura's job — this wrapper only
removes friction: URL in, clean .md in raw_documents/, with the
empty-output guard (the Pop-OS lesson: a silent empty file must
never reach raw_documents).

Usage:
  python scripts/web_grab.py <url>              # one page
  python scripts/web_grab.py --batch queue.txt   # one URL per line
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = _PROJECT_ROOT / "data" / "raw_documents"

# trafilatura is called as a subprocess: the tool stays swappable
# (one line to replace), never a code-level dependency.


def _clipboard_text() -> str:
    """Read the clipboard cross-platform (pyperclip: Linux/Win/macOS).

    On Linux pyperclip shells out to xclip/xsel/wl-paste under the
    hood — the platform package is still needed there (documented in
    the README line below the docstring); on Windows and macOS the
    native clipboard is used with no extra system packages.
    """
    try:
        import pyperclip
    except ImportError:
        sys.exit(
            "[ERROR] pyperclip is not installed: run 'pip install -e .' "
            "(project dependencies) or 'pip install pyperclip'"
        )
    try:
        text = str(pyperclip.paste())
    except pyperclip.PyperclipException as exc:
        sys.exit(
            f"[ERROR] clipboard unavailable: {exc}\n"
            "        (Linux needs the xclip or wl-clipboard system package)"
        )
    if not text.strip():
        sys.exit("[ERROR] the clipboard is empty — copy the URL first")
    return text.strip()


def _slugify(title: str) -> str:
    """File-safe name from the page title, 60 chars max."""
    slug = re.sub(r"[^\w\- ]", "", title, flags=re.UNICODE).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:60].rstrip("-") or "web-page"


def _grab(url: str) -> Path | None:
    """Fetch one URL -> raw_documents/<name>.md. None on failure."""
    print(f"[WEB] {url}")
    result = subprocess.run(
        ["trafilatura", "-u", url, "--markdown"],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0 or not result.stdout.strip():
        print(f"[ERROR] extraction failed: {url}")
        print(f"        {result.stderr.strip()[:200] or 'no output'}")
        return None
    # The Pop-OS guard: never write an empty/near-empty file.
    if len(result.stdout.strip()) < 50:
        print(f"[SKIP] too little content ({len(result.stdout.strip())} chars): {url}")
        return None
    title_match = re.search(r"^# (.+)$", result.stdout, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else url.split("/")[-1][:40]
    target = RAW_DIR / f"{_slugify(title)}.md"
    counter = 2
    while target.exists():  # same-stem collision: suffix, never overwrite
        target = RAW_DIR / f"{_slugify(title)}-{counter}.md"
        counter += 1
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(result.stdout, encoding="utf-8")
    print(f"[DONE] {target.name}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Page URL to save")
    parser.add_argument(
        "--batch", help="File with one URL per line (comments with #)"
    )
    args = parser.parse_args()

    if args.batch:
        urls = [
            line.strip()
            for line in Path(args.batch).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
    else:
        urls = [args.url]

    saved = 0
    for url in urls:
        if _grab(url):
            saved += 1
    print(f"\n[SUMMARY] {saved}/{len(urls)} page(s) saved to raw_documents/")
    print("[NEXT] run prepare_docs (runner menu [10], mode 1) to index them")
    return 0 if saved == len(urls) else 1


if __name__ == "__main__":
    sys.exit(main())
