"""Tests for scripts/prepare_docs.py — ingestion pipeline invariants.

The script feeds the vector index: a silent content loss at a seam
becomes a permanent hole in the knowledge base (fail-silently class,
cf. drift #5 — disk format must match content exactly). Tests assert
content-level invariants, not implementation details, so they survive
the planned --atoms extension.

Load path note: prepare_docs is a script, not a package module;
loaded by file path (same approach as other script-facing checks).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "prepare_docs.py"
_SPEC = importlib.util.spec_from_file_location("prepare_docs", _SCRIPT)
prepare_docs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(prepare_docs)


def _make_file(tmp_path: Path, name: str, size_lines: int) -> Path:
    """Create a source file with one known line per row."""
    src = tmp_path / "src" / name
    src.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(f"line-{i:06d} of the source document\n" for i in range(size_lines))
    src.write_text(content, encoding="utf-8")
    return src


def _run_split(tmp_path: Path, src: Path) -> list[Path]:
    dest = tmp_path / "dest"
    dest.mkdir(parents=True, exist_ok=True)
    return prepare_docs.split_file(src, dest)


# --- Invariant 1: lossless (the core guarantee) ---

def test_split_is_lossless(tmp_path: Path) -> None:
    """Concat of parts equals the original byte-for-byte.

    A line lost or duplicated at a seam becomes a permanent hole or
    duplicate in the index — invisible to any later check.
    """
    src = _make_file(tmp_path, "big.md", 8000)  # > THRESHOLD_BYTES
    parts = _run_split(tmp_path, src)
    assert len(parts) > 1, "expected a split, not a copy"
    joined = b"".join(p.read_bytes() for p in parts)
    assert joined == src.read_bytes()


# --- Invariant 2: seams at line boundaries ---

def test_parts_end_on_line_boundaries(tmp_path: Path) -> None:
    """Every part except possibly the last ends with a newline.

    Sentence integrity upstream of the chunker: a part torn mid-line
    produces corrupted chunks and embeddings.
    """
    src = _make_file(tmp_path, "big.md", 8000)
    parts = _run_split(tmp_path, src)
    for part in parts[:-1]:
        assert part.read_bytes().endswith(b"\n"), f"{part.name} torn mid-line"


# --- Invariant 3: small files pass through whole ---

def test_small_file_copied_as_is(tmp_path: Path) -> None:
    """Files under the threshold are copied, never split."""
    src = _make_file(tmp_path, "small.md", 100)  # < THRESHOLD_BYTES
    parts = _run_split(tmp_path, src)
    assert len(parts) == 1
    assert parts[0].read_bytes() == src.read_bytes()


# --- Invariant 4: watcher-visible names ---

def test_part_names_carry_md_extension(tmp_path: Path) -> None:
    """Parts keep the source suffix: watcher include is ["*.md", "*.txt"]."""
    src = _make_file(tmp_path, "big.md", 8000)
    parts = _run_split(tmp_path, src)
    assert parts, "no parts produced"
    for part in parts:
        assert part.suffix == ".md", f"{part.name} invisible to watcher"


# --- Invariant 5: threshold boundary ---

def test_threshold_boundary_not_split(tmp_path: Path) -> None:
    """A file of exactly THRESHOLD_BYTES is copied, not split."""
    data = b"x" * prepare_docs.THRESHOLD_BYTES
    src = tmp_path / "src" / "exact.md"
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(data)
    parts = _run_split(tmp_path, src)
    assert len(parts) == 1
    assert parts[0].read_bytes() == data


# --- Invariant 6: no empty parts (regression guard) ---

def test_no_empty_parts(tmp_path: Path) -> None:
    """Splitting never produces zero-length part files."""
    src = _make_file(tmp_path, "big.md", 8000)
    parts = _run_split(tmp_path, src)
    for part in parts:
        assert part.stat().st_size > 0, f"empty part: {part.name}"
