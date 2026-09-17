"""Hybrid write-path tests — stage 4a.

Contracts: IndexingManager feeds both stores (vector first — the
capacity gate; lexical mirrored, failure recorded not raised);
index_folder's skip guard requires BOTH stores to vouch (drift #93
class); orphan cleanup and checkpoints cover both stores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.lexical_bm25 import LexicalBm25Index
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.config import SourceConfig
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    LexicalIndexConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.features.rag.indexing import backfill_lexical_index, index_folder
from ai_assistant.features.rag.manager import IndexingManager


def _lexical(tmp_path: Path) -> LexicalBm25Index:
    return LexicalBm25Index(
        LexicalIndexConfigData(index_path=str(tmp_path / "lex"))
    )


def _chunker() -> SimpleChunker:
    return SimpleChunker(ChunkerConfigData(chunk_size=64, chunk_overlap=0))


def _embedder() -> MockEmbedder:
    return MockEmbedder(EmbedderConfigData())


def _vector_store(tmp_path: Path, max_chunks: int = 100_000) -> MemoryVectorStore:
    return MemoryVectorStore(
        VectorStoreConfigData(
            index_path=str(tmp_path / "vec"), max_chunks=max_chunks
        )
    )


def _doc(doc_id: str, text: str) -> dict[str, Any]:
    return {
        "id": doc_id,
        "content": text,
        "metadata": {
            "source": doc_id,
            "source_uri": f"{doc_id}.md",
            "last_modified": "2026-09-16 10:00:00",
        },
    }


class TestIndexingManagerDualWrite:
    """Given: an IndexingManager with a lexical mirror.
    When: documents are indexed.
    Then: both stores are fed; ordering and failure contracts hold."""

    async def test_dual_write_feeds_both_stores(self, tmp_path: Path) -> None:
        lexical = _lexical(tmp_path)
        manager = IndexingManager(
            chunker=_chunker(),
            embedder=_embedder(),
            vector_store=_vector_store(tmp_path),
            lexical_index=lexical,
        )
        result = await manager.index_documents(
            [_doc("d1", "Keenetic router")], namespace="ns"
        )
        assert result["errors"] == []
        vec = await manager.vector_store.list_by_filter({}, namespace="ns")
        lex = await lexical.list_by_filter({}, namespace="ns")
        assert vec and lex
        assert {cid for cid, _ in vec} == {cid for cid, _ in lex}

    async def test_lexical_failure_recorded_not_raised(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        lexical = _lexical(tmp_path)

        async def _fail(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(lexical, "upsert", _fail)
        manager = IndexingManager(
            chunker=_chunker(),
            embedder=_embedder(),
            vector_store=_vector_store(tmp_path),
            lexical_index=lexical,
        )
        result = await manager.index_documents(
            [_doc("d1", "Keenetic router")], namespace="ns"
        )
        assert result["errors"]  # loud, non-empty
        # The primary store keeps the document; the run reports failure.
        assert await manager.vector_store.list_by_filter({}, namespace="ns")

    async def test_vector_refusal_stops_before_lexical(
        self, tmp_path: Path
    ) -> None:
        lexical = _lexical(tmp_path)
        # max_chunks=1 with a multi-chunk document: the vector store
        # (the capacity gatekeeper) refuses the batch.
        manager = IndexingManager(
            chunker=_chunker(),
            embedder=_embedder(),
            vector_store=_vector_store(tmp_path, max_chunks=1),
            lexical_index=lexical,
        )
        with pytest.raises(AdapterError):
            await manager.index_documents(
                [_doc("d1", "alpha beta gamma delta " * 6)], namespace="ns"
            )
        # The lexical leg never ran: no mirror without the primary.
        assert await lexical.list_by_filter({}, namespace="ns") == []


class TestIndexFolderHybridGuard:
    """Given: index_folder with a lexical mirror.
    When: sources are indexed repeatedly.
    Then: the skip guard, orphan cleanup and checkpoints are dual-store."""

    @staticmethod
    def _write_source(tmp_path: Path, name: str, text: str) -> SourceConfig:
        root = tmp_path / "src"
        root.mkdir(exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
        return SourceConfig(
            namespace="ns", path=str(root), include=["*.md"], recursive=False
        )

    async def test_guard_requires_both_stores_and_backfills(
        self, tmp_path: Path
    ) -> None:
        source = self._write_source(tmp_path, "a.md", "Keenetic router notes")
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        chunker = _chunker()
        embedder = _embedder()
        # Run 1: both stores fed.
        r1 = await index_folder(
            target_namespace=None, clear=False, chunker=chunker,
            embedder=embedder, vector_store=store, sources=[source],
            lexical_index=lexical,
        )
        assert r1["success"] is True
        assert r1["results"]["ns"]["indexed"] == 1
        # Run 2: both stores vouch -> the document is skipped entirely.
        r2 = await index_folder(
            target_namespace=None, clear=False, chunker=chunker,
            embedder=embedder, vector_store=store, sources=[source],
            lexical_index=lexical,
        )
        assert r2["results"]["ns"]["indexed"] == 0
        # Run 3: a fresh lexical index (a crash between the two writes,
        # or a freshly enabled mirror): vector vouches, lexical does
        # not -> the document is re-read and backfilled.
        fresh = _lexical(tmp_path)
        r3 = await index_folder(
            target_namespace=None, clear=False, chunker=chunker,
            embedder=embedder, vector_store=store, sources=[source],
            lexical_index=fresh,
        )
        assert r3["results"]["ns"]["indexed"] == 1
        assert await fresh.list_by_filter({}, namespace="ns")

    async def test_orphan_cleanup_covers_both_stores(
        self, tmp_path: Path
    ) -> None:
        source = self._write_source(tmp_path, "a.md", "alpha notes")
        (Path(source.path) / "b.md").write_text("beta notes", encoding="utf-8")
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        chunker = _chunker()
        embedder = _embedder()
        r1 = await index_folder(
            target_namespace=None, clear=False, chunker=chunker,
            embedder=embedder, vector_store=store, sources=[source],
            lexical_index=lexical,
        )
        assert r1["success"] is True
        (Path(source.path) / "b.md").unlink()
        r2 = await index_folder(
            target_namespace=None, clear=False, chunker=chunker,
            embedder=embedder, vector_store=store, sources=[source],
            lexical_index=lexical,
        )
        assert r2["success"] is True
        vec = await store.list_by_filter({}, namespace="ns")
        lex = await lexical.list_by_filter({}, namespace="ns")
        assert {m.get("source_uri") for _, m in vec} == {"a.md"}
        assert {m.get("source_uri") for _, m in lex} == {"a.md"}

    async def test_checkpoint_persists_lexical(self, tmp_path: Path) -> None:
        source = self._write_source(tmp_path, "a.md", "gamma notes")
        lexical = _lexical(tmp_path)
        r = await index_folder(
            target_namespace=None, clear=False, chunker=_chunker(),
            embedder=_embedder(), vector_store=_vector_store(tmp_path),
            sources=[source], index_path=str(tmp_path / "vec"),
            lexical_index=lexical,
        )
        assert r["success"] is True
        assert (tmp_path / "lex" / "ns.json").is_file()


class TestLexicalMirrorBackfill:
    """Given: a vector store holding chunks and a lexical mirror with
    holes. When: backfill_lexical_index runs. Then: holes are filled
    from the stored texts — the function takes no chunker and no
    embedder, so re-embedding is structurally impossible (drift #146).
    """

    async def test_fresh_mirror_copied_verbatim(self, tmp_path: Path) -> None:
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        manager = IndexingManager(
            chunker=_chunker(),
            embedder=_embedder(),
            vector_store=store,
        )
        await manager.index_documents(
            [_doc("d1", "Keenetic router notes")], namespace="ns"
        )
        await manager.index_documents(
            [_doc("d2", "Zennström voip notes")], namespace="chat_ns"
        )

        copied = await backfill_lexical_index(store, lexical)

        vec = await store.list_by_filter({}, namespace="ns")
        chat_vec = await store.list_by_filter({}, namespace="chat_ns")
        lex = await lexical.list_by_filter({}, namespace="ns")
        assert copied == {"ns": len(vec), "chat_ns": len(chat_vec)}
        assert {cid for cid, _ in vec} == {cid for cid, _ in lex}
        found = await lexical.search("keenetic", top_k=5, namespace="ns")
        assert found and "Keenetic" in found[0].text
        assert (tmp_path / "lex" / "ns.json").is_file()
        assert (tmp_path / "lex" / "chat_ns.json").is_file()

    async def test_backfill_is_idempotent(self, tmp_path: Path) -> None:
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        manager = IndexingManager(
            chunker=_chunker(),
            embedder=_embedder(),
            vector_store=store,
            lexical_index=lexical,
        )
        await manager.index_documents(
            [_doc("d1", "Keenetic router notes")], namespace="ns"
        )
        expected = len(await store.list_by_filter({}, namespace="ns"))

        # A synced mirror: nothing to copy.
        assert await backfill_lexical_index(store, lexical) == {}
        # A fresh mirror: filled once, the second run copies nothing.
        fresh = _lexical(tmp_path)
        assert await backfill_lexical_index(store, fresh) == {"ns": expected}
        assert await backfill_lexical_index(store, fresh) == {}

    async def test_backfill_converges_stale_sibling(self, tmp_path: Path) -> None:
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        dual = IndexingManager(
            chunker=_chunker(),
            embedder=_embedder(),
            vector_store=store,
            lexical_index=lexical,
        )
        await dual.index_documents(
            [_doc("d1", "alpha rembrandt notes")], namespace="ns"
        )
        # Re-index new content through the vector store ONLY — the
        # lexical write was lost (a crash inside the drift #139
        # window between the two writes).
        vec_only = IndexingManager(
            chunker=_chunker(),
            embedder=_embedder(),
            vector_store=store,
        )
        updated = _doc("d1", "alpha vermeer notes")
        updated["metadata"]["last_modified"] = "2026-09-17 12:00:00"
        await vec_only.index_documents([updated], namespace="ns")

        copied = await backfill_lexical_index(store, lexical)

        vec = await store.list_by_filter({}, namespace="ns")
        lex = await lexical.list_by_filter({}, namespace="ns")
        assert copied == {"ns": len(vec)}
        assert {cid for cid, _ in vec} == {cid for cid, _ in lex}
        assert await lexical.search("rembrandt", namespace="ns") == []
        found = await lexical.search("vermeer", namespace="ns")
        assert found and "vermeer" in found[0].text

    async def test_backfill_stops_watcher_reembed(self, tmp_path: Path) -> None:
        """The main effect (drift #146): after a backfill the skip
        guard vouches for BOTH stores, so an index_folder pass reads
        nothing from disk and the embedder is not re-run. Without the
        backfill the same pass re-indexes the document (the guard
        test above, run 3 — indexed == 1).
        """
        root = tmp_path / "src"
        root.mkdir()
        (root / "a.md").write_text("Keenetic router notes", encoding="utf-8")
        source = SourceConfig(
            namespace="ns", path=str(root), include=["*.md"], recursive=False
        )
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        chunker = _chunker()
        embedder = _embedder()
        r1 = await index_folder(
            target_namespace=None, clear=False, chunker=chunker,
            embedder=embedder, vector_store=store, sources=[source],
            lexical_index=lexical,
        )
        assert r1["success"] is True
        expected = len(await store.list_by_filter({}, namespace="ns"))

        fresh = _lexical(tmp_path)
        assert await backfill_lexical_index(store, fresh) == {"ns": expected}

        r2 = await index_folder(
            target_namespace=None, clear=False, chunker=chunker,
            embedder=embedder, vector_store=store, sources=[source],
            lexical_index=fresh,
        )
        assert r2["results"]["ns"]["indexed"] == 0


def test_extract_doc_date_marker_forms() -> None:
    """The digits-only extractor: ISO markers, last-marker-wins,
    no date -> None. No language knowledge involved."""
    from ai_assistant.features.rag.indexing import _extract_doc_date

    extract = _extract_doc_date
    # Russian strings are fixture DATA (real marker forms), not code
    # language — RUF001 silenced per the project's test-data rule.
    assert extract("[Пользователь, 2024-07-10]\nтекст", 0, "") == "2024-07"  # noqa: RUF001
    assert extract("[ChatGPT, 2026-03-01]\nтекст", 0, "") == "2026-03"  # noqa: RUF001
    # Last marker wins (a chunk spanning two sessions).
    assert (
        extract("[Пользователь, 2024-07-10]\nx\n[ChatGPT, 2025-01-02]\ny", 0, "")
        == "2025-01"
    )
    # Marker without a date, no first-line date: honest None.
    assert extract("[Пользователь]\nтекст", 0, "") is None  # noqa: RUF001
    assert extract("текст без маркеров", 0, "") is None


def test_extract_doc_date_first_line_forms() -> None:
    """First-line digital dates on chunk 0 only; free-text and
    number-like noise never parse; non-zero chunks never see the
    first-line rule."""
    from ai_assistant.features.rag.indexing import _extract_doc_date

    extract = _extract_doc_date
    assert extract("текст", 0, "2026-03-12") == "2026-03"
    assert extract("текст", 0, "12.03.2026") == "2026-03"
    # Noise: not a date.
    assert extract("текст", 0, "2.5 миллиона — план") is None
    assert extract("текст", 0, "300 рублей") is None
    # The rule applies to chunk 0 only.
    assert extract("текст", 1, "2026-03-12") is None

    async def test_backfill_save_failure_degrades_to_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed post-copy save is a WARNING, not an error: the
        chunks are already mirrored in memory and serve queries; the
        next startup re-syncs (drift #146). The copy result is still
        reported."""
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        manager = IndexingManager(
            chunker=_chunker(),
            embedder=_embedder(),
            vector_store=store,
        )
        await manager.index_documents(
            [_doc("d1", "Keenetic router notes")], namespace="ns"
        )
        expected = len(await store.list_by_filter({}, namespace="ns"))

        async def _fail(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(lexical, "save", _fail)
        copied = await backfill_lexical_index(store, lexical)

        assert copied == {"ns": expected}
        # The in-memory mirror serves queries despite the save failure.
        assert await lexical.search("keenetic", namespace="ns")
        assert not (tmp_path / "lex" / "ns.json").exists()

    async def test_backfill_save_timeout_degrades_to_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A timed-out save has the same WARNING contract (drift #146):
        the sync result is reported and the startup never dies here."""
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        manager = IndexingManager(
            chunker=_chunker(),
            embedder=_embedder(),
            vector_store=store,
        )
        await manager.index_documents(
            [_doc("d1", "Keenetic router notes")], namespace="ns"
        )
        expected = len(await store.list_by_filter({}, namespace="ns"))

        async def _hang(*args: object, **kwargs: object) -> None:
            raise TimeoutError()

        monkeypatch.setattr(lexical, "save", _hang)
        copied = await backfill_lexical_index(store, lexical)

        assert copied == {"ns": expected}
