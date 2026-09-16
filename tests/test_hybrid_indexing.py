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
from ai_assistant.features.rag.indexing import index_folder
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
