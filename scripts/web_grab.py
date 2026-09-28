"""Save a web page as clean markdown via trafilatura (drift #216).

The extraction itself is trafilatura's job — this wrapper only
removes friction: URL in, clean .md in the Downloads folder. The
page is reviewed by the owner there (delete noise, edit text)
before it is moved into data/raw_documents/ — raw_documents/ can
hold hundreds of files, so the new arrival is easier to find and
check in Downloads.

Usage:
  python scripts/web_grab.py <url>               # one page
  python scripts/web_grab.py --batch queue.txt   # one URL per line
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
# The browser-style download folder: anchored to the user profile
# (pathlib + home — cross-platform, no hardcoded absolute paths);
# created when the system's own folder is named differently.
DOWNLOAD_DIR = Path.home() / "Downloads"

# trafilatura is called as a subprocess: the tool stays swappable
# (one line to replace), never a code-level dependency.


def _slugify(title: str) -> str:
    """File-safe name from the page title, 60 chars max."""
    slug = re.sub(r"[^\w\- ]", "", title, flags=re.UNICODE).strip()
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:60].rstrip("-") or "web-page"


def _grab(url: str) -> Path | None:
    """Fetch one URL -> Downloads/<name>.md. None on failure."""
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
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    target = DOWNLOAD_DIR / f"{_slugify(title)}.md"
    counter = 2
    while target.exists():  # same-stem collision: suffix, never overwrite
        target = DOWNLOAD_DIR / f"{_slugify(title)}-{counter}.md"
        counter += 1
    target.write_text(result.stdout, encoding="utf-8")
    print(f"[DONE] {target}")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", nargs="?", help="Page URL to save")
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
    elif args.url:
        urls = [args.url]
    else:
        parser.error("provide a URL or --batch FILE")

    saved = 0
    for url in urls:
        if _grab(url):
            saved += 1
    print(f"\n[SUMMARY] {saved}/{len(urls)} page(s) saved to Downloads/")
    print("[NEXT] review the file(s) (delete noise), then move them into")
    print("       data/raw_documents/ and run prepare_docs")
    return 0 if saved == len(urls) else 1


if __name__ == "__main__":
    sys.exit(main())
