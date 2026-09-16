"""Tests for the BM25 lexical index adapter."""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_assistant.adapters.lexical_bm25 import LexicalBm25Index
from ai_assistant.core.domain.configs import LexicalIndexConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError


def _chunk(chunk_id: str, text: str, source: str = "doc.md") -> Chunk:
    return Chunk(
        id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            source=source, index=0, total_chunks=1, source_uri=source
        ),
    )


def _make_index(tmp_path: Path) -> LexicalBm25Index:
    return LexicalBm25Index(LexicalIndexConfigData(index_path=str(tmp_path)))


class TestLexicalBm25Index:
    """Given: a BM25 lexical index adapter.
    When: chunks are added, searched, upserted, deleted, persisted.
    Then: exact-term ranking, lifecycle and drift-#40/#41 contracts hold."""

    async def test_search_ranks_exact_term_first(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add(
            [
                _chunk("common", "the user likes blue color and the sea"),
                _chunk("rare", "the Keenetic Extra router was bought"),
            ],
            namespace="ns",
        )
        found = await index.search("Keenetic Extra", top_k=2, namespace="ns")
        assert [c.id for c in found] == ["rare"]

    async def test_search_misses_return_empty(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add([_chunk("c1", "alpha beta")], namespace="ns")
        assert await index.search("alpha", namespace="nope") == []
        assert await index.search("gamma", namespace="ns") == []
        assert await index.search("", namespace="ns") == []

    async def test_search_cyrillic_terms(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add(
            [_chunk("ru1", "Мой любимый цвет — синий", source="ru.md")],
            namespace="ns",
        )
        found = await index.search("любимый", top_k=1, namespace="ns")
        assert [c.id for c in found] == ["ru1"]
        assert found[0].metadata is not None
        assert found[0].metadata.source_uri == "ru.md"

    async def test_search_tie_breaks_by_id(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add([_chunk("b", "alpha"), _chunk("a", "alpha")], namespace="ns")
        found = await index.search("alpha", top_k=2, namespace="ns")
        assert [c.id for c in found] == ["a", "b"]

    async def test_upsert_replaces_same_source(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add(
            [
                _chunk("old1", "first version of the doc", source="doc.md"),
                _chunk("keep", "other document entirely", source="other.md"),
            ],
            namespace="ns",
        )
        await index.upsert(
            [_chunk("new1", "second version of the doc", source="doc.md")],
            namespace="ns",
        )
        found = await index.search("version", top_k=10, namespace="ns")
        ids = {c.id for c in found}
        assert "new1" in ids
        assert "old1" not in ids
        # BM25 finds only chunks containing the query terms: verify the
        # sibling source survives by searching a term from ITS text.
        kept = await index.search("entirely", top_k=10, namespace="ns")
        assert [c.id for c in kept] == ["keep"]

    async def test_upsert_empty_is_noop(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.upsert([], namespace="ns")
        assert await index.search("alpha", namespace="ns") == []

    async def test_upsert_idempotent(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        chunks = [
            _chunk("a", "alpha one", source="s.md"),
            _chunk("b", "alpha two", source="t.md"),
        ]
        await index.upsert(chunks, namespace="ns")
        await index.upsert(chunks, namespace="ns")
        found = await index.search("alpha", top_k=10, namespace="ns")
        assert {c.id for c in found} == {"a", "b"}

    async def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add([_chunk("c1", "the Keenetic router")], namespace="ns")
        await index.save(str(tmp_path), namespace="ns")
        revived = _make_index(tmp_path)
        await revived.load(str(tmp_path), namespace="ns")
        found = await revived.search("keenetic", top_k=1, namespace="ns")
        assert [c.id for c in found] == ["c1"]

    async def test_load_missing_file_is_empty(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.load(str(tmp_path), namespace="ghost")
        assert await index.search("alpha", namespace="ghost") == []

    async def test_load_version_mismatch_raises(self, tmp_path: Path) -> None:
        (tmp_path / "ns.json").write_text(
            '{"format_version": 99, "chunks": []}', encoding="utf-8"
        )
        index = _make_index(tmp_path)
        with pytest.raises(VersionMismatchError):
            await index.load(str(tmp_path), namespace="ns")

    async def test_load_corrupt_file_raises(self, tmp_path: Path) -> None:
        (tmp_path / "ns.json").write_text("{not json", encoding="utf-8")
        index = _make_index(tmp_path)
        with pytest.raises(AdapterError):
            await index.load(str(tmp_path), namespace="ns")

    async def test_delete_persists_across_restart(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add(
            [_chunk("c1", "alpha"), _chunk("c2", "beta")], namespace="ns"
        )
        await index.shutdown()
        revived = _make_index(tmp_path)
        await revived.load(str(tmp_path), namespace="ns")
        await revived.delete(["c1"], namespace="ns")
        third = _make_index(tmp_path)
        await third.load(str(tmp_path), namespace="ns")
        assert [c.id for c in await third.search("beta", namespace="ns")] == ["c2"]
        assert await third.search("alpha", namespace="ns") == []

    async def test_delete_to_empty_removes_files(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add([_chunk("c1", "alpha")], namespace="ns")
        await index.save(str(tmp_path), namespace="ns")
        assert (tmp_path / "ns.json").is_file()
        await index.delete(["c1"], namespace="ns")
        assert not (tmp_path / "ns.json").exists()
        assert await index.list_namespaces(str(tmp_path)) == []

    async def test_save_never_loaded_writes_no_file(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.save(str(tmp_path), namespace="ghost")
        assert not (tmp_path / "ghost.json").exists()

    async def test_shutdown_persists_all_namespaces(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add([_chunk("c1", "alpha")], namespace="one")
        await index.add([_chunk("c2", "beta")], namespace="two")
        await index.shutdown()
        assert (tmp_path / "one.json").is_file()
        assert (tmp_path / "two.json").is_file()
        revived = _make_index(tmp_path)
        await revived.load(str(tmp_path), namespace="one")
        assert [c.id for c in await revived.search("alpha", namespace="one")] == [
            "c1"
        ]

    async def test_delete_rollback_on_save_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        index = _make_index(tmp_path)
        await index.add(
            [_chunk("c1", "alpha"), _chunk("c2", "beta")], namespace="ns"
        )

        async def _fail(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(
            "ai_assistant.adapters.lexical_bm25.atomic_write", _fail
        )
        with pytest.raises(AdapterError):
            await index.delete(["c1"], namespace="ns")
        monkeypatch.undo()
        # In-memory state rolled back: the chunk is still searchable.
        assert [c.id for c in await index.search("alpha", namespace="ns")] == ["c1"]
        await index.delete(["c1"], namespace="ns")
        assert await index.search("alpha", namespace="ns") == []

    async def test_list_by_filter_empty_filters_returns_all(
        self, tmp_path: Path
    ) -> None:
        index = _make_index(tmp_path)
        await index.add([_chunk("c1", "alpha")], namespace="ns")
        listed = await index.list_by_filter({}, namespace="ns")
        assert [cid for cid, _ in listed] == ["c1"]
        meta = listed[0][1]
        assert meta["source"] == "doc.md"
        assert meta["source_uri"] == "doc.md"
        assert meta["total_chunks"] == 1

    async def test_list_by_filter_filters_by_key(self, tmp_path: Path) -> None:
        index = _make_index(tmp_path)
        await index.add(
            [
                _chunk("c1", "alpha", source="one.md"),
                _chunk("c2", "beta", source="two.md"),
            ],
            namespace="ns",
        )
        listed = await index.list_by_filter(
            {"source_uri": "two.md"}, namespace="ns"
        )
        assert [cid for cid, _ in listed] == ["c2"]
        missed = await index.list_by_filter(
            {"source_uri": "none.md"}, namespace="ns"
        )
        assert missed == []

    async def test_list_by_filter_unknown_namespace_creates_nothing(
        self, tmp_path: Path
    ) -> None:
        index = _make_index(tmp_path)
        assert await index.list_by_filter({}, namespace="ghost") == []
        # Read-only: no phantom namespace materialized anywhere.
        await index.save(str(tmp_path), namespace="ghost")
        assert not (tmp_path / "ghost.json").exists()
        assert await index.list_namespaces(str(tmp_path)) == []
