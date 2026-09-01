"""Split large documents into RAG-indexable parts.

The watcher's reindex window is SOURCE_INDEX_TIMEOUT (300 s). On the
CPU embedder (bge-m3) the measured rate is ~4 chunks/s, so a file
larger than ~150 KB risks the timeout loop (drift #42 pattern).
This script splits oversized files into ~30 KB parts at line
boundaries before they enter data/documents/.

Usage:
  python scripts/prepare_docs.py              # everything from
                                              # data/raw_documents/
  python scripts/prepare_docs.py big_chat.md  # one file from the
                                              # source dir
  python scripts/prepare_docs.py --src DIR --dest DIR FILE
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 150 KB ≈ 300 chunks ≈ 75 s at the measured CPU rate (~4 chunks/s):
# fits the 300 s watcher window with headroom. On GPU embedding the
# threshold could be raised — see Hardware Ceiling Log for rates.
THRESHOLD_BYTES = 150_000

# 30 KB ≈ 60 chunks ≈ 15 s per part: visible per-file progress in
# app.log ("Documents indexed" per part), safe margin under any
# single-file timeout.
PART_BYTES = 30_000


def split_file(src: Path, dest_dir: Path) -> list[Path]:
    """Split src into parts of ~PART_BYTES at line boundaries.

    Returns the list of created part files. Files under the
    threshold are copied as-is (single "part").
    """
    data = src.read_bytes()
    stem = src.stem
    if len(data) <= THRESHOLD_BYTES:
        target = dest_dir / f"{stem}{src.suffix}"
        target.write_bytes(data)
        print(f"[SKIP] {src.name}: {len(data)} bytes <= threshold, copied as-is")
        return [target]

    parts: list[Path] = []
    start = 0
    idx = 1
    total = len(data)
    while start < total:
        end = min(start + PART_BYTES, total)
        if end < total:
            # Extend to the next newline so sentences stay intact.
            newline = data.find(b"\n", end)
            if newline != -1 and newline - end < PART_BYTES // 2:
                end = newline + 1
        chunk = data[start:end]
        target = dest_dir / f"{stem}_part{idx:02d}{src.suffix}"
        target.write_bytes(chunk)
        parts.append(target)
        print(f"[PART] {target.name}: {len(chunk)} bytes")
        start = end
        idx += 1
    return parts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "files",
        nargs="*",
        help="Files to split (default: everything in the source dir)",
    )
    parser.add_argument(
        "--src",
        default=str(_PROJECT_ROOT / "data" / "raw_documents"),
        help="Source directory with original documents",
    )
    parser.add_argument(
        "--dest",
        default=str(_PROJECT_ROOT / "data" / "documents"),
        help="Destination directory (default: data/documents)",
    )
    args = parser.parse_args()

    src_dir = Path(args.src)
    dest_dir = Path(args.dest)
    dest_dir.mkdir(parents=True, exist_ok=True)

    targets: list[Path] = []
    if args.files:
        for name in args.files:
            path = Path(name)
            if not path.is_absolute():
                path = src_dir / name
            targets.append(path)
    else:
        if not src_dir.exists():
            print(f"[ERROR] source dir not found: {src_dir}", file=sys.stderr)
            return 1
        targets = sorted(
            p for p in src_dir.iterdir() if p.is_file()
        )
        if not targets:
            print(f"[ERROR] no files in {src_dir}", file=sys.stderr)
            return 1

    total_parts = 0
    for src in targets:
        if not src.is_file():
            print(f"[ERROR] not a file: {src}", file=sys.stderr)
            return 1
        parts = split_file(src, dest_dir)
        total_parts += len(parts)

    print(f"[DONE] {total_parts} file(s) in {dest_dir}")
    print("[NEXT] watcher picks them up within 60 s; watch app.log for")
    print("       'Documents indexed' lines, one per part.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
