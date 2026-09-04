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
    content = "".join(
        f"line-{i:06d} of the source document\n" for i in range(size_lines)
    )
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


# --- make_atoms: local-LLM extraction invariants ---


def _fake_llm(monkeypatch, answers: list[str]) -> list[dict]:
    """Patch httpx.post to return canned LLM answers. Returns calls.

    The last answer repeats for any extra parts: the number of parts
    depends on the split (line boundaries), tests must not hardcode
    an exact part count.
    """
    calls: list[dict] = []

    class _Resp:
        def __init__(self, content: str):
            self._content = content

        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": self._content}}]}

    def _post(url: str, json: dict, timeout: float) -> _Resp:
        calls.append(json)
        idx = min(len(calls) - 1, len(answers) - 1)
        return _Resp(answers[idx])

    monkeypatch.setattr(prepare_docs.httpx, "post", _post)
    return calls


def test_make_atoms_creates_single_file(tmp_path: Path, monkeypatch) -> None:
    """One atoms-*.md file per chat, every answer block joined in."""
    src = _make_file(tmp_path, "chat.md", 8000)  # ~230 KB -> 24 parts at 12 KB
    dest = tmp_path / "dest"
    dest.mkdir()
    _fake_llm(monkeypatch, ["ATOM-CONTENT"])
    result = prepare_docs.make_atoms(src, dest)
    assert result.name == "atoms-chat.md"
    assert result.parent == dest
    content = result.read_text(encoding="utf-8")
    # Part count is derived from part_bytes, not hardcoded: assert the
    # separator-joined structure, with a range covering split variance.
    count = content.count("ATOM-CONTENT")
    assert 20 <= count <= 28, f"unexpected part count: {count}"
    assert content.count("\n\n---\n\n") == count - 1  # separators between answers


def test_make_atoms_last_part_marked_final(tmp_path: Path, monkeypatch) -> None:
    """The last part must carry the FINAL header (dedup trigger).

    The assert checks the PART header block, not the whole content:
    the archivist prompt itself contains the word "FINAL" (delivery
    instructions), which would false-positive a whole-content check.
    """
    src = _make_file(tmp_path, "chat.md", 8000)
    dest = tmp_path / "dest"
    dest.mkdir()
    calls = _fake_llm(monkeypatch, ["a1", "a2"])
    prepare_docs.make_atoms(src, dest)
    assert len(calls) >= 2

    def _header(content: str) -> str:
        # The part header comes after the archivist prompt; the prompt
        # itself mentions "PART N/M". Anchor on the header that
        # starts a line right after a blank-line separator.
        import re

        m = re.search(r"\n(PART \d+/\d+(?:\nFINAL)?)", content)
        return m.group(1) if m else ""

    last_header = _header(calls[-1]["messages"][0]["content"])
    first_header = _header(calls[0]["messages"][0]["content"])
    assert "FINAL" in last_header, "last part must be marked FINAL"
    assert "PART" in last_header
    assert "FINAL" not in first_header, "first part must not be FINAL"


def test_make_atoms_temperature_zero(tmp_path: Path, monkeypatch) -> None:
    """Extraction must be deterministic: temperature 0.0 in payload."""
    src = _make_file(tmp_path, "chat.md", 100)
    dest = tmp_path / "dest"
    dest.mkdir()
    calls = _fake_llm(monkeypatch, ["single answer"])
    prepare_docs.make_atoms(src, dest)
    assert calls[0]["temperature"] == 0.0


def test_make_atoms_raw_source_untouched(tmp_path: Path, monkeypatch) -> None:
    """The source file is read-only for the atoms path."""
    src = _make_file(tmp_path, "chat.md", 100)
    original = src.read_bytes()
    dest = tmp_path / "dest"
    dest.mkdir()
    _fake_llm(monkeypatch, ["answer"])
    prepare_docs.make_atoms(src, dest)
    assert src.read_bytes() == original


def test_make_atoms_payload_has_no_model(tmp_path: Path, monkeypatch) -> None:
    """No model field: a single-model local server routes without it."""
    src = _make_file(tmp_path, "chat.md", 100)
    dest = tmp_path / "dest"
    dest.mkdir()
    calls = _fake_llm(monkeypatch, ["answer"])
    prepare_docs.make_atoms(src, dest)
    assert "model" not in calls[0]


def test_make_atoms_omits_model_when_name_empty(tmp_path: Path, monkeypatch) -> None:
    """No model field in the payload when the config is unreadable."""
    fake_root = tmp_path / "root"
    fake_root.mkdir()
    monkeypatch.setattr(prepare_docs, "_PROJECT_ROOT", fake_root)
    src = _make_file(tmp_path, "chat.md", 100)
    dest = tmp_path / "dest"
    dest.mkdir()
    calls = _fake_llm(monkeypatch, ["answer"])
    prepare_docs.make_atoms(src, dest)
    assert "model" not in calls[0]


# --- _needs_processing: idempotency invariants ---


def _touch_later(path: Path, offset: float) -> None:
    """Set mtime into the future/past relative to now."""
    import os

    st = path.stat()
    os.utime(path, (st.st_atime, st.st_mtime + offset))


def test_needs_processing_new_source(tmp_path: Path) -> None:
    """No outputs at all -> processing required."""
    src = _make_file(tmp_path, "new.md", 10)
    dest = tmp_path / "dest"
    dest.mkdir()
    assert prepare_docs._needs_processing(src, dest, atoms=True, split=True)


def test_needs_processing_fresh_outputs_skipped(tmp_path: Path) -> None:
    """Outputs exist and are newer than the source -> skip.

    Small files are copied as-is (no part01 ever exists): the split
    marker is the copy itself — regression guard for the bug where
    part01-only markers reprocessed small files forever.
    """
    src = _make_file(tmp_path, "done.md", 10)
    dest = tmp_path / "dest"
    dest.mkdir()
    copy = dest / "done.md"
    atoms = dest / "atoms-done.md"
    copy.write_text("c", encoding="utf-8")
    atoms.write_text("a", encoding="utf-8")
    # Outputs created after the source -> their mtime is newer.
    _touch_later(copy, 60.0)
    _touch_later(atoms, 60.0)
    assert not prepare_docs._needs_processing(src, dest, atoms=True, split=True)


def test_needs_processing_stale_output_detected(tmp_path: Path) -> None:
    """Source modified after the output was written -> reprocess."""
    src = _make_file(tmp_path, "edited.md", 10)
    dest = tmp_path / "dest"
    dest.mkdir()
    copy = dest / "edited.md"
    atoms = dest / "atoms-edited.md"
    copy.write_text("c", encoding="utf-8")
    atoms.write_text("a", encoding="utf-8")
    # Source touched AFTER the outputs were written.
    _touch_later(src, 60.0)
    assert prepare_docs._needs_processing(src, dest, atoms=True, split=True)


def test_needs_processing_partial_layer_detected(tmp_path: Path) -> None:
    """Split exists but atoms missing -> only the atoms layer is stale."""
    src = _make_file(tmp_path, "half.md", 10)
    dest = tmp_path / "dest"
    dest.mkdir()
    copy = dest / "half.md"
    copy.write_text("c", encoding="utf-8")
    _touch_later(copy, 60.0)
    # Split layer fresh -> split is done; atoms layer missing -> needed.
    assert not prepare_docs._needs_processing(src, dest, atoms=False, split=True)
    assert prepare_docs._needs_processing(src, dest, atoms=True, split=False)


def test_idempotent_rerun_after_real_split(tmp_path: Path) -> None:
    """A second pass over real split_file outputs skips everything.

    Uses the real producer (split_file), not hand-crafted files:
    after a run, both a small file (as-is copy) and a big file
    (part01..NN) must be reported as up to date. The menu workflow
    depends on this: pressing the script twice must cost nothing
    the second time.
    """
    small = _make_file(tmp_path, "small.md", 100)
    big = _make_file(tmp_path, "big.md", 8000)
    dest = tmp_path / "dest"
    dest.mkdir()
    prepare_docs.split_file(small, dest)
    prepare_docs.split_file(big, dest)
    assert not prepare_docs._needs_processing(small, dest, atoms=False, split=True)
    assert not prepare_docs._needs_processing(big, dest, atoms=False, split=True)


def test_reconcile_grown_source_drops_stale_copy(tmp_path: Path) -> None:
    """A file that grew past the threshold loses its old as-is copy.

    Otherwise the watcher indexes the stale copy alongside the new
    parts — two versions of one document in the index.
    """
    src = _make_file(tmp_path, "grew.md", 100)  # small (~3.5 KB)
    dest = tmp_path / "dest"
    dest.mkdir()
    prepare_docs.split_file(src, dest)  # -> as-is copy "grew.md"
    assert (dest / "grew.md").exists()
    # Same source grows past THRESHOLD_BYTES: 20000 rows x 25 bytes
    # = 500 KB (the default _make_file row is ~12 bytes; 8000 rows
    # stay below the 150 KB threshold — this test needs the cross).
    content = "".join(f"line-{i:06d}{'x' * 18}\n" for i in range(20_000))
    src.write_text(content, encoding="utf-8")
    prepare_docs.split_file(src, dest)  # -> parts, copy must be gone
    assert not (dest / "grew.md").exists(), "stale as-is copy survived"
    parts = sorted(dest.glob("grew_part*.md"))
    assert parts, "no parts produced for the grown file"


def test_atoms_seam_caps_part_overshoot() -> None:
    """Atom parts never exceed the part_bytes budget by more than 25%.

    The seam may extend a part to the next newline (sentence
    coherence), but the extension is capped: a 17041-byte part on a
    12000-byte budget was measured in a live run (2026-09-03) —
    inside the context window, but spending the answer headroom.
    """
    # 10 lines x 400 bytes; at a 1200-byte budget the next newline is
    # 399 bytes past the budget point — beyond the 25% cap (300), so
    # the seam must cut at the budget instead of extending.
    data = (("x" * 399) + "\n") * 10
    parts = prepare_docs._split_for_atoms(data.encode("utf-8"), 1200)
    assert len(parts) > 1
    for part in parts:
        assert len(part) <= 1200 + 1200 // 4, f"overshoot: {len(part)}"
    assert b"".join(parts) == data.encode("utf-8")


def test_make_atoms_payload_contains_prompt(tmp_path, monkeypatch):
    """The archivist prompt must reach the LLM (delivery, not definition).

    Also guards the status-discipline and creative-materials clauses:
    losing them (a silent prompt edit) would reopen the measured
    drift where assistant advice was recorded as user decisions
    (2026-09-03, watch-chat atoms).
    """
    src = _make_file(tmp_path, "chat.md", 100)
    dest = tmp_path / "dest"
    dest.mkdir()
    calls = _fake_llm(monkeypatch, ["answer"])
    prepare_docs.make_atoms(src, dest)
    content = calls[0]["messages"][0]["content"]
    assert "TASK: turn a chat history" in content
    assert "THE DECISION TEST" in content
    assert "is NEVER a decision" in content
    assert "NOT creative materials" in content
