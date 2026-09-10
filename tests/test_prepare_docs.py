"""Tests for scripts/prepare_docs.py — ingestion pipeline invariants.

The script feeds the vector index: a silent content loss at a seam
becomes a permanent hole in the knowledge base (fail-silently class,
cf. drift #5 — disk format must match content exactly). Tests assert
content-level invariants, not implementation details, so they survive
the planned --atoms extension.

The static validation section (--validate, V1-V6) covers: the atom
shapes observed in live files (inline / same-line / continuation
labels), THE DECISION TEST quote requirement, date grounding against
the source chat, chronology consistency, Creative Materials filing,
script dominance (computed over template-stripped atom content — the
first live run flipped a fully RU file via English Context values,
2026-09-08), and the documents/-vs-index identity (store
metadata.source is the file STEM, no extension).

Load path note: prepare_docs is a script, not a package module;
loaded by file path (same approach as other script-facing checks).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "prepare_docs.py"
_SPEC = importlib.util.spec_from_file_location("prepare_docs", _SCRIPT)
prepare_docs = importlib.util.module_from_spec(_SPEC)
# Register in sys.modules BEFORE exec_module: the script's dataclasses
# resolve string annotations (PEP 563, "from __future__ import
# annotations") via sys.modules[cls.__module__]; without registration
# the first @dataclass raises AttributeError (2026-09-08).
sys.modules["prepare_docs"] = prepare_docs
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
    parts: list[Path] = prepare_docs.split_file(src, dest)
    return parts


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


# --- Decision validator (drift #78) ---


class TestDecisionValidator:
    """Fabricated decisions are demoted; genuine quoted ones survive.

    Russian strings below are test DATA (chat-export fixtures) —
    the validator's subject is exactly RU quotes; RUF001 suppressed
    per drift #71 (Cyrillic in tests = data, not code).
    """

    def test_fabricated_quote_demoted(self, tmp_path: Path) -> None:
        """Decision with a quote absent from the source -> demoted."""
        src = tmp_path / "chat.md"
        src.write_text(
            "#### Вы сказали:\nкакой калибр лучше?\n",  # noqa: RUF001
            encoding="utf-8",
        )
        atoms = (
            '**[Выбор]** -- выбор сделан.\n'
            '(User said: "беру"; Status: decision)\n'  # noqa: RUF001
        )
        validated, demoted = prepare_docs._validate_decisions(atoms, src)
        assert demoted == 1
        assert "Status: decision" not in validated
        assert "Status: recommendation" in validated

    def test_genuine_quote_survives(self, tmp_path: Path) -> None:
        """Decision quoted verbatim from a user block -> kept."""
        src = tmp_path / "chat.md"
        src.write_text(
            "#### Вы сказали:\nберу эту модель\n\n"  # noqa: RUF001
            "#### ChatGPT сказал:\nок\n",  # noqa: RUF001
            encoding="utf-8",
        )
        atoms = (
            '**[Покупка]** -- покупка состоялась.\n'
            '(User said: "беру эту модель"; Status: decision)\n'  # noqa: RUF001
        )
        validated, demoted = prepare_docs._validate_decisions(atoms, src)
        assert demoted == 0
        assert "Status: decision" in validated

    def test_assistant_quote_demoted(self, tmp_path: Path) -> None:
        """Quote taken from the assistant block -> demoted."""
        src = tmp_path / "chat.md"
        src.write_text(
            "#### Вы сказали:\nчто посоветуешь?\n\n"  # noqa: RUF001
            "#### ChatGPT сказал:\nидеальное сочетание\n",  # noqa: RUF001
            encoding="utf-8",
        )
        atoms = (
            '**[Выбор]** -- выбор сделан.\n'
            '(User said: "идеальное сочетание"; Status: decision)\n'
        )
        validated, demoted = prepare_docs._validate_decisions(atoms, src)
        assert demoted == 1
        assert "Status: recommendation" in validated

    def test_no_quote_demoted(self, tmp_path: Path) -> None:
        """Decision without any quote -> demoted."""
        src = tmp_path / "chat.md"
        src.write_text(
            "#### Вы сказали:\nвопрос\n",  # noqa: RUF001
            encoding="utf-8",
        )
        atoms = '**[Выбор]** -- выбор.\n(Status: decision)\n'
        validated, demoted = prepare_docs._validate_decisions(atoms, src)
        assert demoted == 1
        assert "Status: recommendation" in validated

    def test_stated_form_demoted(self, tmp_path: Path) -> None:
        """'User stated:' (form drift) without a real quote -> demoted."""
        src = tmp_path / "chat.md"
        src.write_text(
            "#### Вы сказали:\nвопрос\n",  # noqa: RUF001
            encoding="utf-8",
        )
        atoms = (
            '**[Выбор]** -- выбор сделан.\n'
            'The user stated: "я бы выбрал" (Status: decision)\n'
        )
        validated, demoted = prepare_docs._validate_decisions(atoms, src)
        assert demoted == 1
        assert "Status: decision" not in validated

    def test_two_line_atom_genuine_quote_survives(
        self, tmp_path: Path
    ) -> None:
        """Quote in the atom body, Status on the next line.

        The live component B shape (2026-09-08): a genuine verbatim
        quote must survive even when it does not share the line with
        the Status label.
        """
        src = tmp_path / "chat.md"
        src.write_text(
            "#### Вы сказали:\nберу эту модель\n\n"  # noqa: RUF001
            "#### ChatGPT сказал:\nок\n",  # noqa: RUF001
            encoding="utf-8",
        )
        atoms = (
            "**[Покупка]** -- покупка состоялась."
            ' (User said: "беру эту модель")\n'  # noqa: RUF001
            "  (Context: 2026-09-02; Status: decision)\n"
        )
        validated, demoted = prepare_docs._validate_decisions(atoms, src)
        assert demoted == 0
        assert "Status: decision" in validated

    def test_two_line_atom_fabricated_quote_demoted(
        self, tmp_path: Path
    ) -> None:
        """Same multi-line shape, quote absent from the source:
        still demoted -- the safety direction is unchanged."""
        src = tmp_path / "chat.md"
        src.write_text(
            "#### Вы сказали:\nчто посоветуешь?\n",  # noqa: RUF001
            encoding="utf-8",
        )
        atoms = (
            "**[Покупка]** -- покупка состоялась."
            ' (User said: "беру эту модель")\n'  # noqa: RUF001
            "  (Context: 2026-09-02; Status: decision)\n"
        )
        validated, demoted = prepare_docs._validate_decisions(atoms, src)
        assert demoted == 1
        assert "Status: recommendation" in validated


# --- Static validation (--validate): fixtures in the live atom shapes ---

GOOD_RU_ATOMS = (
    "## Facts\n"
    "[Установлен ZRAM вместо swap для повышения эффективности"
    " использования памяти. (Context: 2026-09-01, Pop OS; Status: fact)]\n"
    "[Включён TRIM для накопителя NVMe."
    " (Context: 2026-09-01, Pop OS; Status: fact)]\n"
    "\n"
    "## Decisions\n"
    "No user decisions with exact quotes in this part.\n"
    "\n"
    "## Recommendations (not accepted)\n"
    "[ChatGPT предложил LXQt для экономии памяти."
    " (Context: 2026-09-01; Status: recommendation)]\n"
    "\n"
    "## Hypotheses (not verified in chat)\n"
    "No hypotheses found in this part.\n"
    "\n"
    "## Creative Materials\n"
    "**[Заголовок]** -- готовый заголовок «Молния за 59 секунд».\n"
    "  (Context: 2026-09-06; Status: creative material)\n"
    "\n"
    "## Chronology\n"
    "2026-09-01 - настройка системы - ZRAM и TRIM настроены\n"
)

GOOD_SOURCE = (
    "#### Вы сказали:\n"
    "как настроить систему? замеры от 2026-09-01\n"
    "\n"
    "#### ChatGPT сказал:\n"
    "черновики заголовков от 2026-09-06\n"
)

DECISION_NO_QUOTE = (
    "## Decisions\n"
    "**[Выбор хранилища]** -- пользователь выбрал Sprinter.\n"
    "  (Context: 2026-09-02; Status: decision)\n"
)

DECISION_QUOTE_SAID = (
    "## Decisions\n"
    "**[Выбор модели]** -- пользователь выбрал Sprinter.\n"
    "  (Context: 2026-09-02; User said: \"беру Sprinter\"; "  # noqa: RUF001
    "Status: decision)\n"
)

DECISION_QUOTE_STATED = (
    "## Decisions\n"
    "**[Выбор модели]** -- выбор сделан.\n"
    "  The user stated: \"беру Sprinter\" (Status: decision)\n"  # noqa: RUF001
)

DEMOTED_ATOM = (
    "## Recommendations (not accepted)\n"
    "**[Выбор модели]** -- пользователь выбрал Sprinter.\n"
    "  (Context: 2026-09-02; Status: recommendation)\n"
)

INLINE_DECISION_NO_QUOTE = (
    "## Decisions\n"
    "[Пользователь решил перевести сервер на Linux."
    " (Context: 2026-09-02; Status: decision)]\n"
)

DATED_FACT = (
    "## Facts\n"
    "**[Дата покупки]** -- покупка состоялась 2026-08-07.\n"
    "  (Context: 2026-08-07; Status: fact)\n"
)

SOURCE_NO_DATE = (
    "#### Вы сказали:\n"
    "когда была покупка?\n"
)

ISO_FACT = (
    "## Facts\n"
    "**[Релиз]** -- релиз состоялся 2024-05-01.\n"
    "  (Context: 2024-05-01; Status: fact)\n"
)

RU_DATED_SOURCE = (
    "#### Вы сказали:\n"
    "релиз был 1 мая 2024\n"
)

YEAR_SOURCE = (
    "#### Вы сказали:\n"
    "релиз был в 2024 году\n"
)

YEAR_FACT = (
    "## Facts\n"
    "**[Год замера]** -- замер выполнен в 2024 году.\n"
    "  (Context: 2024; Status: fact)\n"
)

FULL_DATED_SOURCE = (
    "#### Вы сказали:\n"
    "замер 2024-08-07 прошёл штатно\n"
)

CHRON_CONFLICT = (
    "## Chronology\n"
    "2026-01-01 - выбор роутера - куплен TP-Link\n"
    "2026-02-01 - выбор роутера - куплен TP-Link\n"
)

CHRON_ACROSS_BLOCKS = (
    "## Chronology\n"
    "2026-01-15 - релиз - версия 1.0\n"
    "\n---\n\n"
    "## Chronology\n"
    "2026-02-15 - релиз - версия 1.0\n"
)

CHRON_COMPATIBLE = (
    "## Chronology\n"
    "2026-01 - релиз - версия 1.0\n"
    "2026-01-15 - релиз - версия 1.0\n"
)

CHRON_BRACKETED = (
    "## Chronology\n"
    "[Aug 22] - watch criteria - candidates identified\n"
    "2024-05-22 - watch criteria - candidates identified\n"
)

CREATIVE_REC = (
    "## Creative Materials\n"
    "**[Оффер]** -- ассистент рекомендует оффер «Скидка 20%».\n"
    "  (Context: 2026-09-06; Status: recommendation)\n"
)

CREATIVE_FACT = (
    "## Creative Materials\n"
    "**[Заголовок]** -- готовый заголовок «Молния за 59 секунд».\n"
    "  (Context: 2026-09-06; Status: fact)\n"
)

EN_FILE_WITH_RU_ATOM = (
    "## Facts\n"
    "- **[Indexing rate]** -- measured ten chunks per second"
    " on the embedded GPU.\n"
    "  (Context: 2026-09-01, live corpus; Status: fact)\n"
    "\n"
    "## Facts\n"
    "- **[Tokenizer fallback]** -- the char fallback tokenizer"
    " was selected for startup safety.\n"
    "  (Context: 2026-09-05; Status: fact)\n"
    "\n"
    "## Facts\n"
    "**[Скорость индексации]** -- измерено десять чанков"
    " в секунду на GPU.\n"
    "  (Context: 2026-09-01; Status: fact)\n"
)

RU_FILE_WITH_EN_ATOM = (
    "## Facts\n"
    "**[Скорость индексации]** -- измерено десять чанков в секунду"
    " на встроенном GPU, что в семь раз"
    " быстрее процессорного варианта.\n"
    "  (Context: 2026-09-01; Status: fact)\n"
    "\n"
    "## Facts\n"
    "**[Выбор хранилища]** -- выбрано хранилище faiss"
    " для основного индекса после сравнения потребления"
    " оперативной памяти на живом корпусе.\n"
    "  (Context: 2026-09-02; Status: fact)\n"
    "\n"
    "## Facts\n"
    "**[Tokenizer fallback]** -- the char fallback tokenizer"
    " was selected for startup safety.\n"
    "  (Context: 2026-09-05; Status: fact)\n"
)

RU_FILE_WITH_CODE = (
    "## Facts\n"
    "**[Контекстное окно]** -- максимальный контекст"
    " перебалансирован до четырёх тысяч восьмисот токенов.\n"
    "  (Context: 2026-09-03; Status: fact)\n"
    "\n"
    "## Facts\n"
    "**[Конфигурация]** -- значение зафиксировано в конфиге:\n"
    "  ```\n"
    "  max_context_tokens = 4800\n"
    "  ```\n"
    "  (Context: 2026-09-03; Status: fact)\n"
)

# The first live run (2026-09-08) flipped a fully RU file into
# "EN-dominant" via English Context VALUES ("project: ...",
# "conditions: ...") -- the regression fixture below.
RU_FILE_EN_CONTEXTS = (
    "## Facts\n"
    "[Установлен ZRAM вместо swap для повышения эффективности"
    " использования памяти. (Context: 2026-09-01, project: local AI"
    " assistant with RAG, conditions: sixteen gigabytes of RAM and a"
    " four gigabyte GPU; Status: fact)]\n"
    "[Включён TRIM для накопителя NVMe. (Context: 2026-09-01,"
    " project: local AI assistant with RAG, conditions: Pop OS"
    " optimization with a long English context value; Status: fact)]\n"
    "[Ограничены потоки NumPy и OpenBLAS восемью потоками"
    " для корректной работы на этом процессоре."
    " (Context: 2026-09-01, project: local AI assistant with RAG,"
    " conditions: thread limits; Status: fact)]\n"
)

RU_FILE_EN_CHRONOLOGY = (
    "## Facts\n"
    "**[Скорость индексации]** -- измерено десять чанков в секунду"
    " на встроенном GPU, что в семь раз быстрее"
    " процессорного варианта при живом корпусе.\n"
    "  (Context: 2026-09-01; Status: fact)\n"
    "\n"
    "## Facts\n"
    "**[Замер скорости]** -- замер выполнен на живом корпусе.\n"
    "  (Context: 2026-09-02; Status: fact)\n"
    "\n"
    "## Chronology\n"
    "[Aug 22] - watch criteria - candidates identified\n"
)


def _write_store(
    index_dir: Path, namespace: str, chunks: list[dict[str, Any]]
) -> None:
    """Write a minimal {namespace}.store.json (adapter schema)."""
    store = {"dim": 8, "metric": "cosine", "chunks": chunks}
    target = index_dir / f"{namespace}.store.json"
    target.write_text(json.dumps(store, ensure_ascii=False), encoding="utf-8")


def _store_chunk(source: str, total: int, index: int = 0) -> dict[str, Any]:
    """One store chunk entry: identity is metadata.source (the stem)."""
    return {
        "id": f"chunk-{source}-{index}",
        "text": "chunk text",
        "embedding": [0.0, 1.0],
        "metadata": {
            "source": source,
            "index": index,
            "total_chunks": total,
            "custom": {},
            "original_path": None,
            "source_uri": source,
            "last_modified": None,
        },
    }


# --- Static validation: atom shapes ---


class TestAtomShapes:
    """The three live atom shapes (2026-09-08) all parse as atoms."""

    def test_all_shapes_parse(self) -> None:
        """Inline / same-line / continuation / template forms."""
        text = (
            "## Facts\n"
            "[Включён TRIM. (Context: 2026-09-01; Status: fact)]\n"
            "[Indexing measured] (Context: 2026-09-02; Status: fact)\n"
            "**[Скорость]** -- десять чанков в секунду.\n"
            "  (Context: 2026-09-03; Status: fact)\n"
            "- **[Template]** -- template form still accepted.\n"
            "  (Context: 2026-09-04; Status: fact)\n"
        )
        atoms = list(prepare_docs._iter_atoms(text))
        assert len(atoms) == 4
        assert all(section == "facts" for section, _start, _atom in atoms)
        assert [start for _section, start, _atom in atoms] == [2, 3, 4, 6]

    def test_good_ru_file_is_clean(self) -> None:
        """All five text checks pass on a live-shaped RU atoms file."""
        result = prepare_docs.validate_text(
            GOOD_RU_ATOMS, "atoms-chat.md", GOOD_SOURCE, "chat.md"
        )
        assert result == ()


class TestDecisionQuote:
    """V1: THE DECISION TEST (drift #67)."""

    def test_missing_quote_flagged(self) -> None:
        violations = prepare_docs._check_decisions(
            DECISION_NO_QUOTE, "atoms-chat.md"
        )
        assert len(violations) == 1
        assert violations[0].check == "V1"
        assert violations[0].severity == "error"
        assert violations[0].line == 2

    def test_inline_shape_flagged(self) -> None:
        """Shape "everything in one line" is an atom, not a sentinel."""
        violations = prepare_docs._check_decisions(
            INLINE_DECISION_NO_QUOTE, "atoms-chat.md"
        )
        assert len(violations) == 1
        assert violations[0].line == 2

    def test_quote_forms_accepted(self) -> None:
        """Both prompt-sanctioned forms ("said"/"stated") satisfy V1."""
        for atoms in (DECISION_QUOTE_SAID, DECISION_QUOTE_STATED):
            assert prepare_docs._check_decisions(atoms, "atoms-chat.md") == ()

    def test_demoted_recommendation_clean(self) -> None:
        """V1 is decision-only: demoted atoms are the pipeline's job."""
        assert prepare_docs._check_decisions(
            DEMOTED_ATOM, "atoms-chat.md"
        ) == ()

    def test_sentinel_lines_not_atoms(self) -> None:
        """PART-sentinels never become atoms; a quoted decision passes."""
        text = (
            "PART 1: no significant knowledge found\n"
            "\n---\n\n"
            "## Decisions\n"
            "**[Выбор]** -- выбор сделан.\n"
            "  (Context: 2026-09-02; User said: \"беру\"; Status: decision)\n"  # noqa: RUF001
        )
        assert prepare_docs._check_decisions(text, "atoms-chat.md") == ()

    def test_empty_decisions_sentinel_clean(self) -> None:
        """The "No user decisions" sentinel line is a correct result."""
        text = "## Decisions\nNo user decisions with exact quotes in this part.\n"
        assert prepare_docs._check_decisions(text, "atoms-chat.md") == ()


class TestDateGrounding:
    """V2: dates must be grounded in the source (drift #80/#81)."""

    def test_invented_date_flagged(self) -> None:
        result = prepare_docs.validate_text(
            DATED_FACT, "atoms-chat.md", SOURCE_NO_DATE, "chat.md"
        )
        assert len(result) == 2  # statement line + Context line
        assert all(v.check == "V2" and v.severity == "error" for v in result)
        assert all("2026-08-07" in v.message for v in result)

    def test_grounded_across_formats(self) -> None:
        """ISO in the atom is grounded by "1 мая 2024" in the source."""
        result = prepare_docs.validate_text(
            ISO_FACT, "atoms-chat.md", RU_DATED_SOURCE, "chat.md"
        )
        assert result == ()

    def test_precision_escalation_flagged(self) -> None:
        """A full date is not grounded by a bare year in the source."""
        result = prepare_docs.validate_text(
            ISO_FACT, "atoms-chat.md", YEAR_SOURCE, "chat.md"
        )
        assert all(v.check == "V2" for v in result)
        assert len(result) == 2

    def test_bare_year_covered_by_precise_source(self) -> None:
        result = prepare_docs.validate_text(
            YEAR_FACT, "atoms-chat.md", FULL_DATED_SOURCE, "chat.md"
        )
        assert result == ()

    def test_missing_source_warns(self) -> None:
        """No source: provenance unchecked is a warning, not an error."""
        result = prepare_docs.validate_text(
            DATED_FACT, "atoms-x.md", None, "x.md"
        )
        assert len(result) == 1
        assert result[0].check == "V2"
        assert result[0].severity == "warn"
        assert "source not found" in result[0].message

    def test_extraction_forms(self) -> None:
        """ISO, dotted, RU and EN month names, bare years all extract."""
        text = "2026-08-07 01.05.2024 1 мая 2024 May 1, 2024 May 2024 2026"
        tokens = tuple(
            token for _, token in prepare_docs._parse_date_tokens(text)
        )
        assert tokens == (
            prepare_docs.DateToken(2026, 8, 7),
            prepare_docs.DateToken(2024, 5, 1),
            prepare_docs.DateToken(2024, 5, 1),
            prepare_docs.DateToken(2024, 5, 1),
            prepare_docs.DateToken(2024, 5, None),
            prepare_docs.DateToken(2026, None, None),
        )

    def test_unix_date_format_extracted(self) -> None:
        """Terminal transcripts carry 'Fri Aug 7 08:20:28 2026' -- a
        complete date (nastroyka corpus, 2026-09-08)."""
        tokens = tuple(
            token
            for _, token in prepare_docs._parse_date_tokens(
                "Fri Aug 7 08:20:28 2026"
            )
        )
        assert tokens == (prepare_docs.DateToken(2026, 8, 7),)

    def test_unix_format_grounds_atom_date(self) -> None:
        """A terminal-timestamp source date grounds the atom's date:
        13 false V2 flags on nastroyka before the fix (2026-09-08)."""
        result = prepare_docs.validate_text(
            "**[Факт]** -- факт с датой Aug 7 2026.\n"  # noqa: RUF001
            "  (Context: Aug 7 2026; Status: fact)\n",
            "atoms-chat.md",
            "Fri Aug 7 08:20:28 2026\n#### Вы сказали:\nвопрос\n",  # noqa: RUF001
            "chat.md",
        )
        assert result == ()

    def test_covers_semantics(self) -> None:
        """Source precision must cover atom precision, not vice versa."""
        covers = prepare_docs._covers
        token = prepare_docs.DateToken
        assert covers(token(2026, 8, 7), token(2026, None, None))
        assert covers(token(2026, 5, 1), token(2026, 5, 1))
        assert not covers(token(2026, None, None), token(2026, 8, 7))
        assert not covers(token(2025, 5, 1), token(2026, 5, 1))

    def test_conflicts_semantics(self) -> None:
        """Compatible precision is not a conflict; disagreeing parts are."""
        conflicts = prepare_docs._conflicts
        token = prepare_docs.DateToken
        assert not conflicts(token(2026, 8, 7), token(2026, 8, None))
        assert not conflicts(token(2026, None, None), token(2026, 5, 1))
        assert conflicts(token(2026, 8, 7), token(2026, 9, 7))


class TestChronologyConsistency:
    """V3: one topic -- one date."""

    def test_conflicting_dates_flagged(self) -> None:
        violations = prepare_docs._check_chronology(
            CHRON_CONFLICT, "atoms-chat.md"
        )
        assert len(violations) == 1
        assert violations[0].check == "V3"
        assert "2026-01-01" in violations[0].message
        assert "2026-02-01" in violations[0].message

    def test_conflict_across_blocks_flagged(self) -> None:
        """The drift #80 shape: different dates for one topic per part."""
        violations = prepare_docs._check_chronology(
            CHRON_ACROSS_BLOCKS, "atoms-chat.md"
        )
        assert len(violations) == 1
        assert violations[0].check == "V3"

    def test_compatible_precisions_clean(self) -> None:
        """"2026-01" and "2026-01-15" for one topic are the same date."""
        assert prepare_docs._check_chronology(
            CHRON_COMPATIBLE, "atoms-chat.md"
        ) == ()

    def test_distinct_topics_clean(self) -> None:
        text = (
            "## Chronology\n"
            "2025-05-01 - первая кампания - запуск\n"
            "2026-05-01 - вторая кампания - запуск\n"
        )
        assert prepare_docs._check_chronology(text, "atoms-chat.md") == ()

    def test_bracketed_date_conflict_flagged(self) -> None:
        """Live shape: "[Aug 22] - ..." chronology lines parse."""
        violations = prepare_docs._check_chronology(
            CHRON_BRACKETED, "atoms-chat.md"
        )
        assert len(violations) == 1
        assert "Aug 22" in violations[0].message
        assert "2024-05-22" in violations[0].message


class TestCreativeMaterials:
    """V4: the section holds texts, not recommendations."""

    def test_recommendation_flagged(self) -> None:
        violations = prepare_docs._check_creative(
            CREATIVE_REC, "atoms-chat.md"
        )
        assert len(violations) == 1
        assert violations[0].check == "V4"

    def test_fact_in_creative_clean(self) -> None:
        assert prepare_docs._check_creative(
            CREATIVE_FACT, "atoms-chat.md"
        ) == ()

    def test_recommendation_section_clean(self) -> None:
        """Recommendations belong in their own section."""
        assert prepare_docs._check_creative(
            DEMOTED_ATOM, "atoms-chat.md"
        ) == ()


class TestScriptDominance:
    """V5: script consistency (drift #67)."""

    def test_ru_atom_in_en_file_flagged(self) -> None:
        violations = prepare_docs._check_script(
            EN_FILE_WITH_RU_ATOM, "atoms-chat.md"
        )
        assert len(violations) == 1
        assert violations[0].check == "V5"
        assert "Cyrillic" in violations[0].message

    def test_en_atom_in_ru_file_flagged(self) -> None:
        """Mirror case: an EN atom in an RU file (#67 residual)."""
        violations = prepare_docs._check_script(
            RU_FILE_WITH_EN_ATOM, "atoms-chat.md"
        )
        assert len(violations) == 1
        assert violations[0].check == "V5"
        assert "Latin" in violations[0].message

    def test_english_context_values_do_not_flip_dominance(self) -> None:
        """Regression (first live run, 2026-09-08): English Context
        VALUES ("project: ...", "conditions: ...") inside RU atoms must
        not make the file EN-dominant."""
        assert prepare_docs._check_script(
            RU_FILE_EN_CONTEXTS, "atoms-chat.md"
        ) == ()

    def test_chronology_not_language_checked(self) -> None:
        """Chronology lines are entries, not atoms: no flags, no votes."""
        assert prepare_docs._check_script(
            RU_FILE_EN_CHRONOLOGY, "atoms-chat.md"
        ) == ()

    def test_template_and_code_ignored(self) -> None:
        """Label lines and fenced code are skeleton, not language."""
        assert prepare_docs._check_script(
            RU_FILE_WITH_CODE, "atoms-chat.md"
        ) == ()

    def test_small_file_skipped(self) -> None:
        """Below the letter floor the dominant script is undecidable."""
        text = "## Facts\n[A] ok.\n(Context: 2026-09-01; Status: fact)\n"
        assert prepare_docs._check_script(text, "atoms-a.md") == ()


class TestIndexCoverage:
    """V6: documents/ vs store identity and completeness (#82-open)."""

    def _dirs(self, tmp_path: Path) -> tuple[Path, Path]:
        dest = tmp_path / "documents"
        index = tmp_path / "indices"
        dest.mkdir()
        index.mkdir()
        return dest, index

    def test_stem_identity_clean(self, tmp_path: Path) -> None:
        """Regression (live index, 2026-09-08): store ids are STEMS
        ("chat" covers documents/chat.md), not posix paths."""
        dest, index = self._dirs(tmp_path)
        (dest / "chat.md").write_text("doc", encoding="utf-8")
        (dest / "atoms-chat.md").write_text("atoms", encoding="utf-8")
        _write_store(index, "default", [
            _store_chunk("chat", 1),
            _store_chunk("atoms-chat", 1),
        ])
        assert prepare_docs.check_index_coverage(
            dest, index, "default"
        ) == ()

    def test_orphan_flagged(self, tmp_path: Path) -> None:
        dest, index = self._dirs(tmp_path)
        (dest / "chat.md").write_text("doc", encoding="utf-8")
        _write_store(index, "default", [
            _store_chunk("chat", 1),
            _store_chunk("bench-ae4737db", 1),  # pre-#82 residue shape
        ])
        violations = prepare_docs.check_index_coverage(dest, index, "default")
        assert len(violations) == 1
        assert violations[0].check == "V6"
        assert violations[0].severity == "warn"
        assert "orphan" in violations[0].message

    def test_missing_document_flagged(self, tmp_path: Path) -> None:
        dest, index = self._dirs(tmp_path)
        (dest / "chat.md").write_text("doc", encoding="utf-8")
        (dest / "new.md").write_text("new", encoding="utf-8")
        _write_store(index, "default", [_store_chunk("chat", 1)])
        violations = prepare_docs.check_index_coverage(dest, index, "default")
        assert len(violations) == 1
        assert "new.md" in violations[0].file
        assert "no chunks" in violations[0].message

    def test_partial_chunks_flagged(self, tmp_path: Path) -> None:
        """The drift #82 gap: a partial restore loses chunks."""
        dest, index = self._dirs(tmp_path)
        (dest / "chat.md").write_text("doc", encoding="utf-8")
        _write_store(index, "default", [
            _store_chunk("chat", 3, index=0),
            _store_chunk("chat", 3, index=1),
        ])
        violations = prepare_docs.check_index_coverage(dest, index, "default")
        assert len(violations) == 1
        assert "2 of 3" in violations[0].message

    def test_no_store_warns(self, tmp_path: Path) -> None:
        dest, index = self._dirs(tmp_path)
        (dest / "chat.md").write_text("doc", encoding="utf-8")
        violations = prepare_docs.check_index_coverage(dest, index, "default")
        assert len(violations) == 1
        assert "no store" in violations[0].message


class TestValidateCli:
    """--validate mode wiring and exit codes."""

    def test_reports_errors_and_returns_one(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        dest = tmp_path / "documents"
        src = tmp_path / "raw_documents"
        index = tmp_path / "indices"
        for directory in (dest, src, index):
            directory.mkdir()
        (dest / "atoms-chat.md").write_text(
            DECISION_NO_QUOTE, encoding="utf-8"
        )
        (src / "chat.md").write_text(SOURCE_NO_DATE, encoding="utf-8")
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "prepare_docs.py", "--validate",
                "--dest", str(dest), "--src", str(src), "--index", str(index),
            ],
        )
        assert prepare_docs.main() == 1
        out = capsys.readouterr().out
        assert "[V1]" in out
        assert "[DONE] 1 file(s) checked" in out

    def test_clean_run_returns_zero(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        dest = tmp_path / "documents"
        src = tmp_path / "raw_documents"
        index = tmp_path / "indices"
        for directory in (dest, src, index):
            directory.mkdir()
        (dest / "atoms-chat.md").write_text(GOOD_RU_ATOMS, encoding="utf-8")
        (src / "chat.md").write_text(GOOD_SOURCE, encoding="utf-8")
        _write_store(index, "default", [_store_chunk("atoms-chat", 1)])
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "prepare_docs.py", "--validate",
                "--dest", str(dest), "--src", str(src), "--index", str(index),
            ],
        )
        assert prepare_docs.main() == 0
        out = capsys.readouterr().out
        assert "[DONE] 1 file(s) checked: 0 error(s), 0 warning(s)" in out

    def test_mutual_exclusion_rejected(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        monkeypatch.setattr(
            sys, "argv", ["prepare_docs.py", "--validate", "--atoms"]
        )
        assert prepare_docs.main() == 1
        assert "[ERROR]" in capsys.readouterr().err

    def test_validate_file_resolves_source(self, tmp_path: Path) -> None:
        """atoms-<name> maps to <name> in the source dir (make_atoms)."""
        dest = tmp_path / "documents"
        src = tmp_path / "raw_documents"
        dest.mkdir()
        src.mkdir()
        (dest / "atoms-chat.md").write_text(DATED_FACT, encoding="utf-8")
        (src / "chat.md").write_text(SOURCE_NO_DATE, encoding="utf-8")
        violations = prepare_docs.validate_file(dest / "atoms-chat.md", src)
        assert any(
            v.check == "V2" and v.severity == "error" for v in violations
        )


class TestFullRunSummary:
    """Mode [2]: no per-atom wall, only a run-total error summary."""

    def test_error_total_and_check_hint(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Defective atoms: end-of-run total + pointer to mode [3]."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "chat.md").write_text(
            "#### Вы сказали:\nвопрос\n",  # noqa: RUF001
            encoding="utf-8",
        )
        dest = tmp_path / "dest"
        dest.mkdir()
        answer = (
            "**[Релиз]** -- релиз состоялся 2026-08-07.\n"
            "  (Context: 2026-08-07; Status: fact)\n"
        )
        _fake_llm(monkeypatch, [answer])
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "prepare_docs.py", "--full",
                "--src", str(src_dir), "--dest", str(dest),
            ],
        )
        assert prepare_docs.main() == 0
        out = capsys.readouterr().out
        assert "[V2]" not in out  # production stays quiet per atom
        assert "1 error(s), 0 warning(s) in atoms created this run" in out
        assert "mode [3] for details" in out

    def test_clean_run_prints_no_warning(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Clean atoms: no summary line, console stays production-only."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        (src_dir / "chat.md").write_text(GOOD_SOURCE, encoding="utf-8")
        dest = tmp_path / "dest"
        dest.mkdir()
        _fake_llm(monkeypatch, [GOOD_RU_ATOMS])
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "prepare_docs.py", "--full",
                "--src", str(src_dir), "--dest", str(dest),
            ],
        )
        assert prepare_docs.main() == 0
        out = capsys.readouterr().out
        assert "in atoms created this run" not in out


# --- Component B: archivist e2e gate (plan step 2) ---

SYNTH_CHAT = (
    "#### Вы сказали:\n"
    "Привет! Выбираю домашний роутер, бюджет до десяти тысяч."
    " Что посоветуешь?\n"
    "\n"
    "#### ChatGPT сказал:\n"
    "Я бы выбрал Keenetic Extra, у него стабильная прошивка"  # noqa: RUF001
    " и запас на годы. Но сначала глянь Archer C6: он дешевле,"  # noqa: RUF001
    " для обычной квартиры хватит.\n"
    "\n"
    "#### Вы сказали:\n"
    "Ок, взвесил оба. Беру Keenetic Extra, оформляй заказ.\n"  # noqa: RUF001
    "\n"
    "#### ChatGPT сказал:\n"
    "Принято, оформляю. Когда приедет -- обнови прошивку до"
    " последней версии.\n"
    "\n"
    "#### Вы сказали:\n"
    "Хорошо, обновлю. И записывай такое: 15 июня 2025 я"
    " подключил себе интернет 500 мегабит, вношу плату каждый месяц.\n"  # noqa: RUF001
    "\n"
    "#### ChatGPT сказал:\n"
    "Записал: интернет 500 мегабит с 15 июня 2025.\n"  # noqa: RUF001
    "\n"
    "#### Вы сказали:\n"
    "И ещё про меня: слушаю подкасты по дороге на работу,"
    " обычно по два часа в день.\n"
    "\n"
    "#### ChatGPT сказал:\n"
    "Понял: подкасты в дороге, около двух часов в день.\n"
)


def _archivist_reachable() -> bool:
    """Cheap liveness probe for the configured archivist server."""
    cfg = prepare_docs._load_archivist_cfg()
    try:
        httpx.get(str(cfg["llm_api_base"]), timeout=3.0)
    except httpx.HTTPError:
        return False
    return True


class TestArchivistE2E:
    """Component B: the archivist on a fixed synthetic chat (plan step 2).

    The safety-net gate for ARCHIVIST_PROMPT edits (plan step 3). The
    chat has exactly one correct atomization: a genuine user decision
    (the Keenetic acceptance) that must survive the demotion, an
    assistant recommendation of the same model that must not become a
    decision (drift #77 subject inversion), a completed dated fact
    (the internet plan -- V2 grounds it), and an undated fact
    (podcasts) that must never grow an invented date (drift #80).
    The decision is deliberately left PENDING: a completion in the
    chat would let the archivist legitimately collapse it into a
    fact and make this gate flaky (2026-09-08).
    Runs the REAL make_atoms against the REAL server from config.yaml
    in tmp folders (never documents/ -- drift #82). Skipped when the
    server is down. Encodes the TARGET contract: a red baseline is a
    work order for step 3, not a flake -- re-run once per the
    architecture section 14 jitter rule before classifying.
    """

    @pytest.mark.online
    def test_synthetic_chat_full_contract(self, tmp_path: Path) -> None:
        """Fresh atoms pass the full V1-V5 contract and carry the
        genuine decision."""
        if not _archivist_reachable():
            pytest.skip("archivist LLM server not reachable")
        src = tmp_path / "chat.md"
        src.write_text(SYNTH_CHAT, encoding="utf-8")
        dest = tmp_path / "dest"
        dest.mkdir()
        prepare_docs.make_atoms(src, dest)

        atoms = dest / "atoms-chat.md"
        assert atoms.is_file(), "make_atoms produced no atoms file"

        violations = prepare_docs.validate_file(atoms, src.parent)
        errors = [v for v in violations if v.severity == "error"]
        assert not errors, f"archivist contract violations: {errors}"

        text = atoms.read_text(encoding="utf-8")
        # The acceptance survives in either observed form: labeled
        # ("Status: decision") or quote-only in ## Decisions -- the
        # model omits the Status label on some runs (2026-09-08).
        # The verbatim quoted acceptance is the decision test's
        # essence; the surrounding syntax varies run to run.
        assert (
            'User said: "Беру Keenetic Extra' in text
        ), "the genuine Keenetic acceptance quote did not survive"


def test_dedup_atoms_removes_cross_part_duplicates() -> None:
    atoms = (
        "## Facts\n"
        "- **[Fact one]** -- detail.\n"
        "  (Context: project; Status: fact)\n"
        "\n"
        "## Facts\n"
        "- **[Fact one]** -- detail.\n"
        "  (Context: project; Status: fact)\n"
    )
    deduped, removed = prepare_docs._dedup_atoms(atoms)
    assert removed == 1
    assert deduped.count("Fact one") == 1


def test_split_for_atoms_never_cuts_multibyte_char() -> None:
    data = ("x" + "ё" * 400 + "y" * 49).encode("utf-8")
    parts = prepare_docs._split_for_atoms(data, part_bytes=100)
    for part in parts:
        part.decode("utf-8")  # strict: a mid-character cut would raise


def test_ground_dates_strips_ungrounded_context_date(tmp_path) -> None:
    src = tmp_path / "chat.md"
    src.write_text("Setup finished on 7 Aug.", encoding="utf-8")
    atoms = (
        "- **[Setup done]** -- performed.\n"
        "  (Context: Jul 10 2024, setup; Status: fact)\n"
    )
    grounded, removed = prepare_docs._ground_dates(atoms, src)
    assert removed == 1
    assert "Jul 10 2024" not in grounded
    assert "setup" in grounded
    assert "Status: fact" in grounded


def test_ground_dates_keeps_grounded_tokens(tmp_path) -> None:
    src = tmp_path / "chat.md"
    src.write_text("We talked about the server on 2024-08-07.", encoding="utf-8")
    atoms = (
        "- **[Server]** -- discussed.\n"
        "  (Context: 2024-08-07, server; Status: fact)\n"
    )
    grounded, removed = prepare_docs._ground_dates(atoms, src)
    assert removed == 0
    assert "2024-08-07" in grounded


def test_ground_dates_drops_ungrounded_as_of_marker(tmp_path) -> None:
    src = tmp_path / "chat.md"
    src.write_text("Price unknown.", encoding="utf-8")
    atoms = "The price is high (as of May 29 2024).\n"
    grounded, removed = prepare_docs._ground_dates(atoms, src)
    assert removed == 1
    assert "as of" not in grounded
    assert "The price is high." in grounded


def test_ground_dates_strips_chronology_date(tmp_path) -> None:
    src = tmp_path / "chat.md"
    src.write_text("Topic: server, 2024.", encoding="utf-8")
    atoms = "## Chronology\nJul 10 2024 - server - tuned\n"
    grounded, removed = prepare_docs._ground_dates(atoms, src)
    assert removed == 1
    assert "server - tuned" in grounded
    assert "Jul 10" not in grounded


def test_validate_decisions_fallback_keeps_verbatim_quote(tmp_path) -> None:
    src = tmp_path / "chat.md"
    src.write_text("User: I will take the Sprinter\nAssistant: good choice")
    atoms = (
        "- **[Sprinter taken]** -- decided.\n"
        '  (User said: "I will take the Sprinter"; Status: decision)\n'
    )
    validated, demoted = prepare_docs._validate_decisions(atoms, src)
    assert demoted == 0
    assert "Status: decision" in validated


def test_validate_decisions_fallback_demotes_fabricated_quote(tmp_path) -> None:
    src = tmp_path / "chat.md"
    src.write_text("Assistant: consider the Sprinter")
    atoms = (
        "- **[Sprinter taken]** -- decided.\n"
        '  (User said: "taking the Sprinter for sure"; Status: decision)\n'
    )
    validated, demoted = prepare_docs._validate_decisions(atoms, src)
    assert demoted == 1
    assert "Status: recommendation" in validated


def test_dedup_atoms_keeps_same_statement_different_context() -> None:
    atoms = (
        "## Facts\n"
        "- **[Server configured]** -- tuned.\n"
        "  (Context: dev, 2024-03; Status: fact)\n"
        "\n"
        "## Facts\n"
        "- **[Server configured]** -- tuned.\n"
        "  (Context: prod, 2024-08; Status: fact)\n"
    )
    deduped, removed = prepare_docs._dedup_atoms(atoms)
    assert removed == 0
    assert deduped.count("Server configured") == 2
