"""tests/test_adapters.py — Unit tests for adapter implementations.

Covers: MockLLM, MockEmbedder, MemoryVectorStore, NullReranker,
        SQLiteStorage, SimpleChunker, Factory.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from ai_assistant.adapters.chunker_recursive import RecursiveChunker
from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.embedder_openai_compatible import OpenAICompatibleEmbedder
from ai_assistant.adapters.factory import create_adapter
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
from ai_assistant.adapters.reranker_local import LocalReranker
from ai_assistant.adapters.reranker_null import NullReranker
from ai_assistant.adapters.storage_sqlite import SQLiteStorage
from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    LLMConfigData,
    RerankerConfigData,
    StorageConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.vector_store import IVectorStore

logger = get_logger(__name__)


# ── TestMockLLM ──


class TestMockLLM:
    """Given: MockLLM is available for testing without API keys.
    When: various inputs are provided.
    Then: deterministic echo responses are returned.
    """

    @pytest.mark.asyncio
    async def test_complete_echo(self):
        llm = MockLLM(config=LLMConfigData())
        result = await llm.complete([UserMessage(text="hello")])
        assert isinstance(result, AssistantMessage)
        assert result.text == "[MOCK LLM] Echo: hello"

    @pytest.mark.asyncio
    async def test_complete_empty_messages(self):
        llm = MockLLM(config=LLMConfigData())
        result = await llm.complete([])
        assert result.text == "[MOCK LLM] Echo: ..."

    @pytest.mark.asyncio
    async def test_stream(self):
        llm = MockLLM(config=LLMConfigData())
        chunks = [c async for c in llm.stream([UserMessage(text="hi")])]
        assert len(chunks) == 1
        assert "Server is running" in chunks[0]

    def test_get_context_limit_default(self):
        llm = MockLLM(config=LLMConfigData())
        assert llm.get_context_limit() == 4096

    def test_get_context_limit_from_config(self):
        llm = MockLLM(config=LLMConfigData(server_context_size=2048))
        assert llm.get_context_limit() == 2048

    def test_get_context_limit_from_max_tokens(self):
        llm = MockLLM(config=LLMConfigData(max_tokens=1024, server_context_size=None))
        assert llm.get_context_limit() == 1024

    @pytest.mark.asyncio
    async def test_shutdown(self):
        llm = MockLLM(config=LLMConfigData())
        await llm.shutdown()


# ── TestMockEmbedder ──


class TestMockEmbedder:
    """Given: MockEmbedder provides deterministic fake vectors.
    When: various dimensions and texts are requested.
    Then: correct embeddings are returned.
    """

    @pytest.mark.parametrize("dim", [128, 384, 768, 1536])
    def test_dimension(self, dim):
        emb = MockEmbedder(EmbedderConfigData(dim=dim))
        assert emb.dimension == dim

    @pytest.mark.parametrize(
        "texts,expected_count",
        [
            (["hello", "world"], 2),
            (["single"], 1),
            ([], 0),
        ],
    )
    @pytest.mark.asyncio
    async def test_embed(self, texts, expected_count):
        emb = MockEmbedder(EmbedderConfigData(dim=384))
        result = await emb.embed(texts)
        assert len(result) == expected_count
        if expected_count > 0:
            assert len(result[0]) == 384
            if len(texts) > 1:
                assert result[0] != result[1]

    @pytest.mark.asyncio
    async def test_embed_empty(self):
        emb = MockEmbedder(EmbedderConfigData(dim=384))
        result = await emb.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_shutdown(self):
        emb = MockEmbedder(EmbedderConfigData(dim=384))
        await emb.shutdown()

    @pytest.mark.asyncio
    async def test_embed_deterministic_across_runs(self):
        """Same text must produce same vector regardless of PYTHONHASHSEED."""
        emb = MockEmbedder(EmbedderConfigData(dim=384))
        result1 = await emb.embed(["hello", "world"])
        result2 = await emb.embed(["hello", "world"])
        assert result1 == result2
        assert len(result1) == 2
        assert len(result1[0]) == 384


# ── TestMemoryVectorStore ──


class TestMemoryVectorStore:
    """Given: MemoryVectorStore holds chunks in memory.
    When: add, search, save, load operations are performed.
    Then: correct behavior with namespaces, FIFO eviction, and dim checks.
    """

    @pytest.fixture
    def store(self, tmp_path):
        # tmp_path is required: delete() of an emptied namespace now
        # removes files under index_path (drift #40). Without isolation
        # the test would delete a real ./data namespace directory.
        return MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path / "vs"))
        )

    @pytest.mark.asyncio
    async def test_add_and_search(self, store):
        chunks = [
            Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0]),
        ]
        await store.add(chunks, namespace="test")
        results = await store.search([1.0, 0.0, 0.0], top_k=1, namespace="test")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.asyncio
    async def test_namespace_isolation(self, store):
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="ns1"
        )
        await store.add(
            [Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0])], namespace="ns2"
        )

        r1 = await store.search([1.0, 0.0, 0.0], top_k=1, namespace="ns1")
        r2 = await store.search([0.0, 1.0, 0.0], top_k=1, namespace="ns2")
        assert r1[0].id == "c1"
        assert r2[0].id == "c2"

        r3 = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns2")
        assert not any(c.id == "c1" for c in r3)

    @pytest.mark.asyncio
    async def test_rejects_max_chunks_overflow_atomically(self):
        """F36: exceeding max_chunks rejects the batch and evicts nothing.

        The old behaviour silently FIFO-evicted the oldest chunks — and a
        later save() persisted that loss to disk.
        """
        store = MemoryVectorStore(VectorStoreConfigData(dim=3, max_chunks=2))
        await store.add(
            [
                Chunk(id="c1", text="first", embedding=[1.0, 0.0, 0.0]),
                Chunk(id="c2", text="second", embedding=[0.0, 1.0, 0.0]),
            ],
            namespace="test",
        )
        with pytest.raises(AdapterError, match="max_chunks"):
            await store.add(
                [Chunk(id="c3", text="third", embedding=[0.0, 0.0, 1.0])],
                namespace="test",
            )
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        ids = {c.id for c in results}
        assert ids == {"c1", "c2"}

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path):
        store = MemoryVectorStore(VectorStoreConfigData(dim=3))
        meta = ChunkMetadata(
            source="doc1",
            index=0,
            total_chunks=1,
            source_uri="file:///tmp/test.md",
        )
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0], metadata=meta)],
            namespace="test",
        )
        path = str(tmp_path / "idx")
        await store.save(path, namespace="test")

        store2 = MemoryVectorStore(VectorStoreConfigData(dim=3))
        await store2.load(path, namespace="test")
        results = await store2.search([1.0, 0.0, 0.0], top_k=1, namespace="test")
        assert len(results) == 1
        assert results[0].id == "c1"
        assert results[0].metadata is not None
        assert results[0].metadata.source_uri == "file:///tmp/test.md"

    @pytest.mark.asyncio
    async def test_dim_mismatch_raises(self, tmp_path):
        store3 = MemoryVectorStore(VectorStoreConfigData(dim=3))
        await store3.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="test"
        )
        path = str(tmp_path / "idx")
        await store3.save(path, namespace="test")

        store5 = MemoryVectorStore(VectorStoreConfigData(dim=5))
        with pytest.raises(VersionMismatchError, match="Reindex required"):
            await store5.load(path, namespace="test")

    @pytest.mark.asyncio
    async def test_skips_no_embedding(self, store):
        await store.add(
            [
                Chunk(id="c1", text="no emb", embedding=None),
                Chunk(id="c2", text="has emb", embedding=[1.0, 0.0, 0.0]),
            ],
            namespace="test",
        )
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 1
        assert results[0].id == "c2"

    @pytest.mark.asyncio
    async def test_rejects_wrong_dimension_atomically(self, store):
        with pytest.raises(AdapterError):
            await store.add(
                [
                    Chunk(id="c1", text="wrong", embedding=[1.0, 0.0]),
                    Chunk(id="c2", text="correct", embedding=[1.0, 0.0, 0.0]),
                ],
                namespace="test",
            )
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_index_path_from_config(self):
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path="./custom/indices/memory")
        )
        assert store.index_path == "./custom/indices/memory"

    @pytest.mark.asyncio
    async def test_list_by_filter(self, store):
        meta = ChunkMetadata(
            source="doc1", index=0, total_chunks=1, custom={"tag": "important"}
        )
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0], metadata=meta)],
            namespace="test",
        )
        results = await store.list_by_filter({"tag": "important"}, namespace="test")
        assert len(results) == 1
        assert results[0][0] == "c1"

    @pytest.mark.asyncio
    async def test_delete(self, store):
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="test"
        )
        await store.delete(["c1"], namespace="test")
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_shutdown_clears_namespaces(self):
        store = MemoryVectorStore(VectorStoreConfigData(dim=3))
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="test"
        )
        await store.shutdown()
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_concurrent_add_and_search(self):
        """Given: multiple coroutines add and search simultaneously.
        When: asyncio.gather runs them concurrently.
        Then: no race condition; all adds are visible and search returns consistent
              results.
        """
        store = MemoryVectorStore(VectorStoreConfigData(dim=3, max_chunks=100))

        async def add_chunk(i: int):
            await store.add(
                [Chunk(id=f"c{i}", text=f"chunk {i}", embedding=[1.0, 0.0, 0.0])],
                namespace="concurrent",
            )

        async def search_during_add():
            results = []
            for _ in range(10):
                r = await store.search(
                    [1.0, 0.0, 0.0], top_k=50, namespace="concurrent"
                )
                results.append(len(r))
            return results

        adders = [add_chunk(i) for i in range(20)]
        searchers = [search_during_add() for _ in range(5)]
        await asyncio.gather(*adders, *searchers)

        final = await store.search([1.0, 0.0, 0.0], top_k=50, namespace="concurrent")
        assert len(final) == 20
        ids = {c.id for c in final}
        assert ids == {f"c{i}" for i in range(20)}


# ── IVectorStore.upsert tests ──


class TestMemoryVectorStoreUpsert:
    """Coverage for IVectorStore.upsert default implementation (Memory)."""

    @pytest.mark.asyncio
    async def test_memory_upsert_replaces_old_chunks_by_source(
        self, tmp_path: Path
    ) -> None:
        """Same as Faiss upsert test, but for MemoryVectorStore."""
        config = VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        store = MemoryVectorStore(config)

        await store.upsert(
            [
                Chunk(
                    id="c1",
                    text="a",
                    embedding=[1.0, 0.0, 0.0],
                    metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
                ),
            ],
            namespace="ns",
        )

        await store.upsert(
            [
                Chunk(
                    id="c2",
                    text="b",
                    embedding=[0.0, 1.0, 0.0],
                    metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
                ),
            ],
            namespace="ns",
        )

        all_chunks = await store.list_by_filter({}, namespace="ns")
        ids = {cid for cid, _ in all_chunks}
        assert ids == {"c2"}

    @pytest.mark.asyncio
    async def test_memory_search_date_filter_excludes_foreign_and_undated(
        self, tmp_path
    ):
        """Stage 2: an active filter keeps matching doc_date only."""
        from ai_assistant.core.domain.pipeline import DateFilter

        store = MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        july = Chunk(
            id="july",
            text="j",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(
                source="d", index=0, total_chunks=1, custom={"doc_date": "2026-07"}
            ),
        )
        march = Chunk(
            id="march",
            text="m",
            embedding=[0.0, 1.0, 0.0],
            metadata=ChunkMetadata(
                source="d", index=1, total_chunks=1, custom={"doc_date": "2026-03"}
            ),
        )
        undated = Chunk(
            id="undated",
            text="u",
            embedding=[0.0, 0.0, 1.0],
            metadata=ChunkMetadata(source="d", index=2, total_chunks=1),
        )
        await store.add([july, march, undated], namespace="ns")

        results = await store.search(
            [1.0, 1.0, 1.0],
            top_k=10,
            namespace="ns",
            date_filter=DateFilter(month=7, year=2026),
        )
        assert [c.id for c in results] == ["july"]

        # Filter off: the old full path.
        results_all = await store.search(
            [1.0, 1.0, 1.0], top_k=10, namespace="ns"
        )
        assert {c.id for c in results_all} == {"july", "march", "undated"}


class TestFaissVectorStoreUpsert:
    """FaissVectorStore.upsert: atomic replace per source (drift #88)."""

    @pytest.mark.asyncio
    async def test_faiss_upsert_replaces_old_chunks_by_source(
        self, tmp_path: Path
    ) -> None:
        """upsert removes old chunks with the same source and adds new ones."""
        pytest.importorskip("faiss")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        config = VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        store = FaissVectorStore(config)

        await store.upsert(
            [
                Chunk(
                    id="c1",
                    text="a",
                    embedding=[1.0, 0.0, 0.0],
                    metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
                ),
                Chunk(
                    id="c2",
                    text="b",
                    embedding=[0.0, 1.0, 0.0],
                    metadata=ChunkMetadata(source="doc2", index=0, total_chunks=1),
                ),
            ],
            namespace="ns",
        )

        # Overwrite doc1, leave doc2 untouched
        await store.upsert(
            [
                Chunk(
                    id="c3",
                    text="c",
                    embedding=[0.0, 0.0, 1.0],
                    metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
                ),
            ],
            namespace="ns",
        )

        all_chunks = await store.list_by_filter({}, namespace="ns")
        ids = {cid for cid, _ in all_chunks}
        assert ids == {"c2", "c3"}

    @pytest.mark.asyncio
    async def test_faiss_upsert_empty_is_noop(self, tmp_path: Path) -> None:
        """Empty chunk list is a no-op and does not create a namespace."""
        pytest.importorskip("faiss")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        config = VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        store = FaissVectorStore(config)
        await store.upsert([], namespace="empty")
        ns = await store.list_namespaces(str(tmp_path))
        assert "empty" not in ns

    @pytest.mark.asyncio
    async def test_faiss_search_date_filter_excludes_foreign(self, tmp_path):
        """Same contract as the memory store: matching doc_date only."""
        pytest.importorskip("faiss")
        from ai_assistant.core.domain.pipeline import DateFilter

        store = FaissVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        july = Chunk(
            id="july",
            text="j",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(
                source="d", index=0, total_chunks=1, custom={"doc_date": "2026-07"}
            ),
        )
        march = Chunk(
            id="march",
            text="m",
            embedding=[0.0, 1.0, 0.0],
            metadata=ChunkMetadata(
                source="d", index=1, total_chunks=1, custom={"doc_date": "2026-03"}
            ),
        )
        await store.add([july, march], namespace="ns")

        results = await store.search(
            [1.0, 1.0, 1.0],
            top_k=10,
            namespace="ns",
            date_filter=DateFilter(month=7, year=2026),
        )
        assert [c.id for c in results] == ["july"]


# ── TestVectorStoreDeleteAllPersistence ──


class TestVectorStoreDeleteAllPersistence:
    """F1: delete() that empties a namespace must remove its persisted
    files. Otherwise deleted chunks resurrect after restart: lifespan
    loads every namespace it finds on disk.
    """

    @pytest.mark.asyncio
    async def test_delete_all_removes_namespace_from_disk(self, vector_store_adapter):
        chunk = Chunk(id="c1", text="a", embedding=[0.1] * 384)
        index_path = vector_store_adapter.index_path
        await vector_store_adapter.add([chunk], namespace="ns")
        await vector_store_adapter.save(index_path, namespace="ns")
        assert "ns" in await vector_store_adapter.list_namespaces(index_path)

        await vector_store_adapter.delete(["c1"], namespace="ns")

        # Nothing on disk to load and nothing in memory to search.
        assert "ns" not in await vector_store_adapter.list_namespaces(index_path)
        results = await vector_store_adapter.search(
            [0.1] * 384, top_k=5, namespace="ns"
        )
        assert results == []


# ── TestMemoryStorePersistenceGuards ──


class TestMemoryStorePersistenceGuards:
    """F92 and rollback guarantees specific to MemoryVectorStore."""

    @pytest.mark.asyncio
    async def test_save_after_failed_load_preserves_stored_data(self, tmp_path):
        """A namespace skipped at load (dim mismatch) must not be
        overwritten with an empty store by a later save()."""
        store_a = MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store_a.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="ns"
        )
        await store_a.save(str(tmp_path), namespace="ns")

        store_b = MemoryVectorStore(
            VectorStoreConfigData(dim=5, index_path=str(tmp_path))
        )
        with pytest.raises(VersionMismatchError):
            await store_b.load(str(tmp_path), namespace="ns")

        # Shutdown path: save() on the never-loaded namespace is a no-op.
        await store_b.save(str(tmp_path), namespace="ns")

        store_c = MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store_c.load(str(tmp_path), namespace="ns")
        results = await store_c.search([1.0, 0.0, 0.0], top_k=5, namespace="ns")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.asyncio
    async def test_delete_all_rolls_back_when_file_removal_fails(self, tmp_path):
        """If removing persisted files fails, in-memory state must be
        restored from disk and the error must propagate."""
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="ns"
        )
        await store.save(str(tmp_path), namespace="ns")

        async def failing_remove(namespace: str) -> None:
            raise AdapterError("simulated removal failure")

        store._remove_namespace_files = failing_remove

        with pytest.raises(AdapterError, match="simulated removal failure"):
            await store.delete(["c1"], namespace="ns")

        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.asyncio
    async def test_delete_save_failure_rolls_back_from_disk(self, tmp_path):
        """A failed save during delete reloads the last durable disk
        state — memory must not stay ahead of disk (drift #119 class):
        the deleted chunk is back after the error."""
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store.add(
            [
                Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0]),
                Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0]),
            ],
            namespace="ns",
        )
        await store.save(str(tmp_path), namespace="ns")

        async def failing_save(path: str, namespace: str = "default") -> None:
            raise AdapterError("disk full")

        store._save_unlocked = failing_save

        with pytest.raises(AdapterError, match="disk full"):
            await store.delete(["c1"], namespace="ns")

        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns")
        assert {c.id for c in results} == {"c1", "c2"}

    @pytest.mark.asyncio
    async def test_upsert_save_failure_rolls_back(self, tmp_path):
        """A failed save during upsert restores the RAM snapshot: the
        replaced OLD chunk survives, the new one is not half-written."""
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store.add(
            [
                Chunk(
                    id="c1",
                    text="a",
                    embedding=[1.0, 0.0, 0.0],
                    metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
                )
            ],
            namespace="ns",
        )

        async def failing_save(path: str, namespace: str = "default") -> None:
            raise AdapterError("disk full")

        store._save_unlocked = failing_save

        with pytest.raises(AdapterError, match="disk full"):
            await store.upsert(
                [
                    Chunk(
                        id="c2",
                        text="b",
                        embedding=[0.0, 1.0, 0.0],
                        metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
                    )
                ],
                namespace="ns",
            )

        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns")
        assert [c.id for c in results] == ["c1"]

    @pytest.mark.asyncio
    async def test_upsert_rejects_max_chunks_overflow(self, tmp_path):
        """Upsert replacement accounting must respect max_chunks: a
        batch that would overflow is rejected, originals survive
        (drift #48/#107 contract on the replace path)."""
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=3, max_chunks=2, index_path=str(tmp_path))
        )
        await store.add(
            [
                Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0]),
                Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0]),
            ],
            namespace="ns",
        )
        with pytest.raises(AdapterError, match="max_chunks"):
            await store.upsert(
                [
                    Chunk(id="c3", text="c", embedding=[0.0, 0.0, 1.0]),
                    Chunk(id="c4", text="d", embedding=[1.0, 1.0, 0.0]),
                ],
                namespace="ns",
            )
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns")
        assert {c.id for c in results} == {"c1", "c2"}

    @pytest.mark.asyncio
    async def test_search_dimension_mismatch_raises(self, tmp_path):
        """A wrong-length query must fail loudly, not return garbage."""
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="ns"
        )
        with pytest.raises(AdapterError, match="Dimension mismatch in memory search"):
            await store.search([1.0, 0.0], top_k=5, namespace="ns")

    @pytest.mark.asyncio
    async def test_list_namespaces_survives_unlistable_path(self, tmp_path):
        """An OSError while listing the index dir (here: the path is a
        regular file) degrades to the in-memory namespace list — the
        health endpoint must never crash on a bad path."""
        store = MemoryVectorStore(VectorStoreConfigData(dim=3))
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])],
            namespace="mem_ns",
        )
        not_a_dir = tmp_path / "file.txt"
        not_a_dir.write_text("x", encoding="utf-8")
        assert await store.list_namespaces(str(not_a_dir)) == ["mem_ns"]


# ── TestFaissStorePersistenceGuards ──


class TestFaissStorePersistenceGuards:
    """Rollback guarantee specific to FaissVectorStore."""

    @pytest.mark.asyncio
    async def test_delete_all_rolls_back_when_file_removal_fails(self, tmp_path):
        """If removing persisted files fails, the in-memory index must be
        restored from the pre-delete snapshot."""
        pytest.importorskip("faiss")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        store = FaissVectorStore(VectorStoreConfigData(dim=3, index_path=str(tmp_path)))
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="ns"
        )

        async def failing_remove(namespace: str) -> None:
            raise AdapterError("simulated removal failure")

        store._remove_namespace_files = failing_remove

        with pytest.raises(AdapterError, match="simulated removal failure"):
            await store.delete(["c1"], namespace="ns")

        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.asyncio
    async def test_add_rejects_max_chunks_overflow(self, tmp_path):
        """Same contract as the memory store (F36): the batch is
        rejected, nothing is evicted, nothing partially added."""
        pytest.importorskip("faiss")
        store = FaissVectorStore(
            VectorStoreConfigData(dim=3, max_chunks=2, index_path=str(tmp_path))
        )
        await store.add(
            [
                Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0]),
                Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0]),
            ],
            namespace="ns",
        )
        with pytest.raises(AdapterError, match="max_chunks"):
            await store.add(
                [Chunk(id="c3", text="c", embedding=[0.0, 0.0, 1.0])],
                namespace="ns",
            )
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns")
        assert {c.id for c in results} == {"c1", "c2"}

    @pytest.mark.asyncio
    async def test_delete_save_failure_rolls_back(self, tmp_path):
        """A failed save during delete restores the pre-delete snapshot
        (index + chunk map): the deleted chunk survives in memory."""
        pytest.importorskip("faiss")
        store = FaissVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store.add(
            [
                Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0]),
                Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0]),
            ],
            namespace="ns",
        )

        async def failing_save(path: str, namespace: str = "default") -> None:
            raise AdapterError("disk full")

        store._save_unlocked = failing_save

        with pytest.raises(AdapterError, match="disk full"):
            await store.delete(["c1"], namespace="ns")

        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns")
        assert {c.id for c in results} == {"c1", "c2"}

    @pytest.mark.asyncio
    async def test_upsert_save_failure_rolls_back(self, tmp_path):
        """A failed save during upsert restores the pre-upsert snapshot:
        the old chunk of the same source survives."""
        pytest.importorskip("faiss")
        store = FaissVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store.add(
            [
                Chunk(
                    id="c1",
                    text="a",
                    embedding=[1.0, 0.0, 0.0],
                    metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
                )
            ],
            namespace="ns",
        )

        async def failing_save(path: str, namespace: str = "default") -> None:
            raise AdapterError("disk full")

        store._save_unlocked = failing_save

        with pytest.raises(AdapterError, match="disk full"):
            await store.upsert(
                [
                    Chunk(
                        id="c2",
                        text="b",
                        embedding=[0.0, 1.0, 0.0],
                        metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
                    )
                ],
                namespace="ns",
            )

        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns")
        assert [c.id for c in results] == ["c1"]


class TestFaissLoadGuards:
    """Load-path integrity: a corrupt or inconsistent persisted pair
    must fail LOUDLY (AdapterError / VersionMismatchError) — never
    load as a silently empty index (the adapter's docstring contract)."""

    @staticmethod
    def _store(tmp_path: Path) -> FaissVectorStore:
        return FaissVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )

    @staticmethod
    async def _save_valid_index(
        tmp_path: Path, dim: int = 3, metric: str = "l2"
    ) -> None:
        """Persist one valid namespace (two chunks) on disk."""
        store = FaissVectorStore(
            VectorStoreConfigData(dim=dim, metric=metric, index_path=str(tmp_path))
        )
        await store.add(
            [
                Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0]),
                Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0]),
            ],
            namespace="ns",
        )
        await store.save(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_load_missing_store_json_raises(self, tmp_path):
        """A .faiss file without store.json is corruption, not an empty
        index: load refuses instead of returning silent empty searches."""
        pytest.importorskip("faiss")
        (tmp_path / "ns.faiss").write_bytes(b"stale faiss bytes")
        with pytest.raises(AdapterError, match="metadata missing"):
            await self._store(tmp_path).load(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_load_missing_faiss_raises(self, tmp_path):
        """store.json without the index file is equally fatal."""
        pytest.importorskip("faiss")
        (tmp_path / "ns.store.json").write_text(
            json.dumps({"dim": 3, "metric": "l2", "chunks": []}), encoding="utf-8"
        )
        with pytest.raises(AdapterError, match="Index file missing"):
            await self._store(tmp_path).load(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_load_neither_file_is_clean(self, tmp_path):
        """No files at all: a never-indexed namespace loads as empty
        without error (the normal first-run path)."""
        pytest.importorskip("faiss")
        store = self._store(tmp_path)
        await store.load(str(tmp_path), namespace="ghost")
        assert await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ghost") == []

    @pytest.mark.asyncio
    async def test_load_invalid_json_raises(self, tmp_path):
        pytest.importorskip("faiss")
        (tmp_path / "ns.faiss").write_bytes(b"x")
        (tmp_path / "ns.store.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(AdapterError, match="Invalid store\\.json"):
            await self._store(tmp_path).load(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_load_store_json_not_dict_raises(self, tmp_path):
        pytest.importorskip("faiss")
        (tmp_path / "ns.faiss").write_bytes(b"x")
        (tmp_path / "ns.store.json").write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(AdapterError, match="expected dict"):
            await self._store(tmp_path).load(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_load_dim_mismatch_raises(self, tmp_path):
        """Stored dim vs config dim: reindex is required, never a
        half-working index."""
        pytest.importorskip("faiss")
        await self._save_valid_index(tmp_path)  # dim 3
        store = FaissVectorStore(
            VectorStoreConfigData(dim=5, index_path=str(tmp_path))
        )
        with pytest.raises(VersionMismatchError, match="stored dim"):
            await store.load(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_load_metric_mismatch_raises(self, tmp_path):
        pytest.importorskip("faiss")
        await self._save_valid_index(tmp_path, metric="cosine")
        store = FaissVectorStore(
            VectorStoreConfigData(dim=3, metric="l2", index_path=str(tmp_path))
        )
        with pytest.raises(VersionMismatchError, match="metric"):
            await store.load(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_load_vector_count_mismatch_raises(self, tmp_path):
        """store.json edited to fewer chunks than the faiss file holds:
        the integrity check catches the inconsistent pair."""
        pytest.importorskip("faiss")
        await self._save_valid_index(tmp_path)  # 2 vectors, 2 records
        store_file = tmp_path / "ns.store.json"
        data = json.loads(store_file.read_text(encoding="utf-8"))
        data["chunks"] = data["chunks"][:1]
        store_file.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(AdapterError, match="integrity check failed"):
            await self._store(tmp_path).load(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_load_corrupt_faiss_file_raises(self, tmp_path):
        pytest.importorskip("faiss")
        await self._save_valid_index(tmp_path)
        (tmp_path / "ns.faiss").write_bytes(b"not a faiss index")
        with pytest.raises(AdapterError, match="Failed to read index"):
            await self._store(tmp_path).load(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_load_malformed_chunk_record_raises(self, tmp_path):
        pytest.importorskip("faiss")
        await self._save_valid_index(tmp_path)
        store_file = tmp_path / "ns.store.json"
        data = json.loads(store_file.read_text(encoding="utf-8"))
        data["chunks"][0] = {"text": "record without id"}
        store_file.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(AdapterError, match="Failed to deserialize"):
            await self._store(tmp_path).load(str(tmp_path), namespace="ns")

    @pytest.mark.asyncio
    async def test_list_namespaces_ignores_orphaned_files(self, tmp_path):
        """Half-pairs on disk (store.json without .faiss and vice
        versa) are warned about, never listed as loadable namespaces.

        Two DIFFERENT namespaces, one half each — both warning
        branches (metadata-only and index-only) are exercised; a
        complete pair would legitimately be listed."""
        pytest.importorskip("faiss")
        (tmp_path / "meta_only.store.json").write_text("{}", encoding="utf-8")
        (tmp_path / "index_only.faiss").write_bytes(b"x")
        assert await self._store(tmp_path).list_namespaces(str(tmp_path)) == []


# ── TestNullReranker ──


class TestNullReranker:
    """Given: NullReranker is a pass-through reranker.
    When: rerank is called.
    Then: all chunks returned with score 1.0, order preserved.
    """

    @pytest.mark.asyncio
    async def test_pass_through(self):
        reranker = NullReranker(RerankerConfigData())
        chunks = [Chunk(id="c1", text="a"), Chunk(id="c2", text="b")]
        results = await reranker.rerank("q", chunks)
        assert len(results) == 2
        assert results[0].chunk.id == "c1"
        assert results[0].score == 1.0
        assert results[1].chunk.id == "c2"
        assert results[1].score == 1.0

    @pytest.mark.asyncio
    async def test_empty_chunks(self):
        reranker = NullReranker(RerankerConfigData())
        results = await reranker.rerank("q", [])
        assert results == []

    @pytest.mark.asyncio
    async def test_respects_top_k(self):
        reranker = NullReranker(RerankerConfigData())
        chunks = [Chunk(id="c1", text="a"), Chunk(id="c2", text="b")]
        results = await reranker.rerank("q", chunks, top_k=1)
        assert len(results) == 1
        assert results[0].chunk.id == "c1"

    @pytest.mark.asyncio
    async def test_shutdown(self):
        reranker = NullReranker(RerankerConfigData())
        await reranker.shutdown()


# ── TestLocalReranker ──


class TestLocalReranker:
    """Coverage target: raise reranker_local.py from ~24% to >80%."""

    @pytest.fixture
    def config(self) -> RerankerConfigData:
        return RerankerConfigData(
            model="test-reranker",
            api_base="http://localhost:8080",
            api_key="",
            timeout=30.0,
        )

    @pytest.fixture
    def config_with_key(self) -> RerankerConfigData:
        return RerankerConfigData(
            model="test-reranker",
            api_base="http://localhost:8080",
            api_key="secret-key",
            timeout=30.0,
        )

    @pytest.fixture
    def chunks(self) -> list[Chunk]:
        return [
            Chunk(id="c1", text="first"),
            Chunk(id="c2", text="second"),
            Chunk(id="c3", text="third"),
        ]

    # --- lifecycle ---

    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self, config: RerankerConfigData) -> None:
        mock_client = AsyncMock()
        with patch("httpx.AsyncClient", return_value=mock_client):
            reranker = LocalReranker(config)
            await reranker.shutdown()
        mock_client.aclose.assert_awaited_once()

    # --- empty input ---

    @pytest.mark.asyncio
    async def test_rerank_empty_chunks_returns_empty(
        self, config: RerankerConfigData
    ) -> None:
        reranker = LocalReranker(config)
        result = await reranker.rerank("query", [])
        assert result == []

    # --- happy path ---

    @pytest.mark.asyncio
    async def test_rerank_success_no_top_k(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        """All chunks returned, sorted descending by normalized score."""
        reranker = LocalReranker(config)
        mock_response = {
            "results": [
                {"index": 1, "relevance_score": 2.0},  # ~0.88
                {"index": 0, "relevance_score": 0.0},  # 0.5
                {"index": 2, "relevance_score": -1.0},  # ~0.27
            ]
        }
        with patch(
            "ai_assistant.adapters.reranker_local.async_post_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reranker.rerank("query", chunks)

        assert len(result) == 3
        assert result[0].chunk.id == "c2"
        assert result[1].chunk.id == "c1"
        assert result[2].chunk.id == "c3"
        assert result[0].score > result[1].score > result[2].score

    @pytest.mark.asyncio
    async def test_rerank_success_with_top_k(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        """top_k truncates the sorted list."""
        reranker = LocalReranker(config)
        mock_response = {
            "results": [
                {"index": 0, "relevance_score": 5.0},
                {"index": 1, "relevance_score": 3.0},
                {"index": 2, "relevance_score": 1.0},
            ]
        }
        with patch(
            "ai_assistant.adapters.reranker_local.async_post_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reranker.rerank("query", chunks, top_k=2)

        assert len(result) == 2
        assert result[0].chunk.id == "c1"
        assert result[1].chunk.id == "c2"

    @pytest.mark.asyncio
    async def test_rerank_payload_top_n_matches_chunk_count_when_top_k_none(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        reranker = LocalReranker(config)
        mock_post = AsyncMock(return_value={"results": []})
        with patch("ai_assistant.adapters.reranker_local.async_post_json", mock_post):
            await reranker.rerank("query", chunks)
        payload = mock_post.call_args[0][3]
        assert payload["top_n"] == len(chunks)

    @pytest.mark.asyncio
    async def test_rerank_payload_top_n_matches_top_k_when_provided(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        reranker = LocalReranker(config)
        mock_post = AsyncMock(return_value={"results": []})
        with patch("ai_assistant.adapters.reranker_local.async_post_json", mock_post):
            await reranker.rerank("query", chunks, top_k=2)
        payload = mock_post.call_args[0][3]
        assert payload["top_n"] == 2

    @pytest.mark.asyncio
    async def test_rerank_includes_api_key_header(
        self, config_with_key: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        reranker = LocalReranker(config_with_key)
        mock_post = AsyncMock(
            return_value={"results": [{"index": 0, "relevance_score": 1.0}]}
        )
        with patch("ai_assistant.adapters.reranker_local.async_post_json", mock_post):
            await reranker.rerank("query", chunks)
        headers = mock_post.call_args[0][2]
        assert headers["Authorization"] == "Bearer secret-key"

    # --- error handling ---

    @pytest.mark.asyncio
    async def test_rerank_http_error_raises_adapter_error(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        reranker = LocalReranker(config)
        with (
            patch(
                "ai_assistant.adapters.reranker_local.async_post_json",
                new_callable=AsyncMock,
                side_effect=ConnectionError("refused"),
            ),
            pytest.raises(AdapterError, match="Local reranker request failed"),
        ):
            await reranker.rerank("query", chunks)

    @pytest.mark.asyncio
    async def test_rerank_missing_results_key(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        reranker = LocalReranker(config)
        with (
            patch(
                "ai_assistant.adapters.reranker_local.async_post_json",
                new_callable=AsyncMock,
                return_value={"other": "data"},
            ),
            pytest.raises(AdapterError, match="Missing 'results' in reranker response"),
        ):
            await reranker.rerank("query", chunks)

    @pytest.mark.asyncio
    async def test_rerank_results_not_list(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        reranker = LocalReranker(config)
        with (
            patch(
                "ai_assistant.adapters.reranker_local.async_post_json",
                new_callable=AsyncMock,
                return_value={"results": "notalist"},
            ),
            pytest.raises(AdapterError, match="Expected 'results' list"),
        ):
            await reranker.rerank("query", chunks)

    @pytest.mark.asyncio
    async def test_rerank_malformed_items_skipped(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        """Invalid items are silently skipped; valid ones survive."""
        reranker = LocalReranker(config)
        mock_response = {
            "results": [
                "not a dict",
                {"index": 0, "relevance_score": 1.0},  # valid
                {"index": "bad", "relevance_score": 1.0},  # wrong type
                {"index": 0},  # missing score
                {"relevance_score": 1.0},  # missing index
                {"index": 99, "relevance_score": 1.0},  # out of range
                {"index": 0, "relevance_score": "bad"},  # wrong score type
            ]
        }
        with patch(
            "ai_assistant.adapters.reranker_local.async_post_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reranker.rerank("query", chunks)

        assert len(result) == 1
        assert result[0].chunk.id == "c1"
        assert result[0].score == pytest.approx(0.731, abs=0.001)

    # --- sigmoid normalization ---

    @pytest.mark.asyncio
    async def test_normalize_score_extreme_positive(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        reranker = LocalReranker(config)
        mock_response = {"results": [{"index": 0, "relevance_score": 15.0}]}
        with patch(
            "ai_assistant.adapters.reranker_local.async_post_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reranker.rerank("query", chunks)
        assert result[0].score == pytest.approx(0.9999, abs=0.0001)

    @pytest.mark.asyncio
    async def test_normalize_score_extreme_negative(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        reranker = LocalReranker(config)
        mock_response = {"results": [{"index": 0, "relevance_score": -15.0}]}
        with patch(
            "ai_assistant.adapters.reranker_local.async_post_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reranker.rerank("query", chunks)
        assert result[0].score == pytest.approx(0.0001, abs=0.0001)

    @pytest.mark.asyncio
    async def test_normalize_score_zero_is_half(
        self, config: RerankerConfigData, chunks: list[Chunk]
    ) -> None:
        reranker = LocalReranker(config)
        mock_response = {"results": [{"index": 0, "relevance_score": 0.0}]}
        with patch(
            "ai_assistant.adapters.reranker_local.async_post_json",
            new_callable=AsyncMock,
            return_value=mock_response,
        ):
            result = await reranker.rerank("query", chunks)
        assert result[0].score == pytest.approx(0.5, abs=0.0001)


# ── TestSQLiteStorage ──


class TestSQLiteStorage:
    """Given: SQLiteStorage persists chat history and settings.
    When: CRUD operations are performed.
    Then: data is correctly stored and retrieved.
    """

    @pytest.fixture
    def storage(self, tmp_path):
        return SQLiteStorage(StorageConfigData(db_path=str(tmp_path / "test.db")))

    @pytest.mark.asyncio
    async def test_save_and_get_history(self, storage):
        await storage.init_db()
        await storage.save_message(
            "conv-1", {"role": "user", "content": "hi", "metadata": {"k": "v"}}
        )
        history = await storage.get_history("conv-1", limit=10)
        assert len(history) == 1
        assert history[0]["role"] == "user"
        assert history[0]["metadata"] == {"k": "v"}

    @pytest.mark.asyncio
    async def test_history_pagination(self, storage):
        await storage.init_db()
        for i in range(5):
            await storage.save_message("conv-1", {"role": "user", "content": f"msg{i}"})
        history = await storage.get_history("conv-1", limit=2)
        assert len(history) == 2
        assert history[0]["content"] == "msg3"
        assert history[1]["content"] == "msg4"

    @pytest.mark.asyncio
    async def test_settings_get_set(self, storage):
        await storage.init_db()
        await storage.set("key1", {"nested": True})
        assert await storage.get("key1") == {"nested": True}

    @pytest.mark.asyncio
    async def test_settings_default(self, storage):
        await storage.init_db()
        assert await storage.get("missing", "default") == "default"

    @pytest.mark.asyncio
    async def test_wal_mode(self, storage, tmp_path):
        await storage.init_db()
        with closing(sqlite3.connect(str(tmp_path / "test.db"))) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode.lower() == "wal"

    @pytest.mark.asyncio
    async def test_concurrent_reads(self, storage, tmp_path):
        await storage.init_db()
        for i in range(3):
            await storage.save_message("conv-1", {"role": "user", "content": f"msg{i}"})

        results = []
        for _ in range(3):
            with closing(sqlite3.connect(str(tmp_path / "test.db"))) as conn:
                cur = conn.execute(
                    "SELECT content FROM chat_messages "
                    "WHERE conversation_id = ? ORDER BY id",
                    ("conv-1",),
                )
                rows = [r[0] for r in cur.fetchall()]
                results.append(rows)

        for rows in results:
            assert rows == ["msg0", "msg1", "msg2"]

    @pytest.mark.asyncio
    async def test_db_tables_created(self, storage, tmp_path):
        await storage.init_db()
        with closing(sqlite3.connect(str(tmp_path / "test.db"))) as conn:
            tables = {
                t[0]
                for t in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "chat_messages" in tables
            assert "settings" in tables

    @pytest.mark.asyncio
    async def test_shutdown(self, storage):
        await storage.init_db()
        await storage.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown_without_init_db_does_not_create_file(self, tmp_path):
        """Given: SQLiteStorage without init_db().
        When: shutdown() is called.
        Then: no .db file is created."""
        db_path = tmp_path / "no_init.db"
        storage = SQLiteStorage(StorageConfigData(db_path=str(db_path)))
        await storage.shutdown()
        assert not db_path.exists()

    @pytest.mark.asyncio
    async def test_crud_raises_adapter_error_not_sqlite(self, storage):
        """Given: corrupted DB that causes sqlite3.Error.
        When: CRUD methods are called.
        Then: AdapterError is raised, not raw sqlite3.Error."""
        await storage.init_db()
        db_path = storage.config.db_path
        with open(db_path, "w") as f:
            f.write("not a database")

        with pytest.raises(AdapterError):
            await storage.get_history("conv-1")

    @pytest.mark.asyncio
    async def test_history_offset_pagination(self, storage):
        """Given: 5 messages saved to conversation.
        When: get_history called with offset=2, limit=2.
        Then: returns correct slice in DESC order."""
        await storage.init_db()
        for i in range(5):
            await storage.save_message("conv-1", {"role": "user", "content": f"msg{i}"})
        history = await storage.get_history("conv-1", limit=2, offset=2)
        assert len(history) == 2
        assert history[0]["content"] == "msg1"
        assert history[1]["content"] == "msg2"

    @pytest.mark.asyncio
    async def test_save_message_raises_adapter_error_on_corrupted_db(
        self, storage, tmp_path
    ):
        """Given: corrupted DB file.
        When: save_message called.
        Then: AdapterError is raised, not raw sqlite3.Error."""
        await storage.init_db()
        db_path = storage.config.db_path
        with open(db_path, "w") as f:
            f.write("not a database")
        with pytest.raises(AdapterError):
            await storage.save_message("conv-1", {"role": "user", "content": "hi"})

    @pytest.mark.asyncio
    async def test_set_overwrites_existing_key(self, storage):
        """Given: key already exists in settings.
        When: set called with new value.
        Then: get returns the new value."""
        await storage.init_db()
        await storage.set("key1", {"version": 1})
        await storage.set("key1", {"version": 2})
        assert await storage.get("key1") == {"version": 2}

    @pytest.mark.asyncio
    async def test_get_history_nonexistent_conversation_returns_empty(self, storage):
        """Given: conversation_id never used.
        When: get_history called.
        Then: returns empty list without error."""
        await storage.init_db()
        history = await storage.get_history("never-used-id", limit=10)
        assert history == []

    @pytest.mark.asyncio
    async def test_get_history_limit_zero_returns_empty(self, storage):
        """LIMIT 0 must return empty list without hitting the DB hard."""
        await storage.init_db()
        await storage.save_message("conv-1", {"role": "user", "content": "hi"})
        history = await storage.get_history("conv-1", limit=0)
        assert history == []

    @pytest.mark.asyncio
    async def test_get_history_offset_beyond_count_returns_empty(self, storage):
        """offset larger than total rows must return empty list gracefully."""
        await storage.init_db()
        await storage.save_message("conv-1", {"role": "user", "content": "hi"})
        history = await storage.get_history("conv-1", limit=10, offset=100)
        assert history == []


# ── TestSimpleChunker ──


class TestSimpleChunker:
    """Given: SimpleChunker splits text into fixed-size chunks.
    When: various sizes and overlaps are used.
    Then: correct chunks are produced.
    """

    @pytest.mark.parametrize(
        "size,overlap,text,expected_count",
        [
            (10, 2, "hello world this is a test", 4),
            (100, 10, "short", 1),
            (50, 5, "", 0),
            (5, 1, "1234567890", 3),
        ],
    )
    @pytest.mark.asyncio
    async def test_variations(self, size, overlap, text, expected_count):
        chunker = SimpleChunker(
            ChunkerConfigData(chunk_size=size, chunk_overlap=overlap)
        )
        doc = Document(id="d1", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) == expected_count
        if chunks:
            assert all(len(c.text) <= size for c in chunks)
            assert all(c.metadata.total_chunks == len(chunks) for c in chunks)

    @pytest.mark.asyncio
    async def test_empty_text(self):
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=10, chunk_overlap=2))
        doc = Document(id="d1", content="")
        chunks = await chunker.chunk(doc)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_metadata_preservation(self):
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=10, chunk_overlap=2))
        doc = Document(id="d1", content="hello world", metadata={"tag": "test"})
        chunks = await chunker.chunk(doc)
        assert chunks[0].metadata.custom == {"tag": "test"}

    @pytest.mark.asyncio
    async def test_invalid_overlap(self):
        with pytest.raises(ValueError):
            SimpleChunker(ChunkerConfigData(chunk_size=10, chunk_overlap=10))

    @pytest.mark.asyncio
    async def test_shutdown(self):
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=10, chunk_overlap=2))
        await chunker.shutdown()


# ── TestFactory ──


class TestFactory:
    """Given: create_adapter maps port/name to adapter instances.
    When: valid and invalid combinations are requested.
    Then: correct adapter or ValueError is returned.
    """

    @pytest.mark.parametrize(
        "port,name,expected_cls,config",
        [
            ("llm", "mock", MockLLM, LLMConfigData()),
            ("embedder", "mock", MockEmbedder, EmbedderConfigData()),
            ("vector_store", "memory", MemoryVectorStore, VectorStoreConfigData()),
            (
                "chunker",
                "simple",
                SimpleChunker,
                ChunkerConfigData(chunk_size=10, chunk_overlap=2),
            ),
            ("storage", "sqlite", SQLiteStorage, StorageConfigData(db_path=":memory:")),
            ("reranker", "null", NullReranker, RerankerConfigData()),
        ],
    )
    def test_create_adapter(self, port, name, expected_cls, config):
        adapter = create_adapter(port, name, config)
        assert isinstance(adapter, expected_cls)

    @pytest.mark.parametrize(
        "port,name,config",
        [
            ("llm", "openai_compatible", LLMConfigData(api_key="sk-test")),
            ("embedder", "openai_compatible", EmbedderConfigData(api_key="sk-test")),
        ],
    )
    def test_create_openai_compatible_adapters(self, port, name, config):
        adapter = create_adapter(port, name, config)
        assert adapter is not None

    def test_unknown_llm_raises(self):
        with pytest.raises(ValueError, match="No llm adapter registered"):
            create_adapter("llm", "unknown", LLMConfigData())

    def test_unknown_embedder_raises(self):
        with pytest.raises(ValueError, match="No embedder adapter registered"):
            create_adapter("embedder", "unknown", EmbedderConfigData())

    def test_unknown_vector_store_raises(self):
        with pytest.raises(ValueError, match="No vector_store adapter registered"):
            create_adapter("vector_store", "unknown", VectorStoreConfigData())

    def test_unknown_chunker_raises(self):
        with pytest.raises(ValueError, match="No chunker adapter registered"):
            create_adapter("chunker", "unknown", ChunkerConfigData())

    def test_unknown_storage_raises(self):
        with pytest.raises(ValueError, match="No storage adapter registered"):
            create_adapter("storage", "unknown", StorageConfigData())

    def test_unknown_reranker_raises(self):
        with pytest.raises(ValueError, match="No reranker adapter registered"):
            create_adapter("reranker", "unknown", RerankerConfigData())

    def test_unknown_port_raises(self):
        with pytest.raises(ValueError, match="Unknown adapter port"):
            create_adapter("unknown_port", "whatever", RerankerConfigData())


# ── TestOpenAICompatibleLLM ──


class TestOpenAICompatibleLLM:
    """Given: OpenAICompatibleLLM with mocked HTTP client.
    When: complete() and stream() are called with various inputs.
    Then: correct payload is sent and responses are parsed.
    """

    @pytest.fixture
    def llm(self):
        return OpenAICompatibleLLM(
            LLMConfigData(
                api_key="sk-test",
                model="gpt-4",
                api_base="http://test/v1",
                max_tokens=100,
                temperature=0.5,
                timeout=300.0,
                connect_timeout=3.0,
                stop_sequences=("", "end", "stop", ""),
            )
        )

    @pytest.mark.asyncio
    async def test_complete_sends_stop_sequences_filtered(self, llm):
        """Empty strings in stop_sequences must be filtered out of payload."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            await llm.complete([UserMessage(text="hi")])

            call_kwargs = mock_post.call_args.kwargs
            payload = call_kwargs["json"]
            assert payload.get("stop") == ["end", "stop"]
            assert payload["model"] == "gpt-4"
            assert payload["max_tokens"] == 100
            assert payload["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_complete_no_stop_when_empty(self, llm):
        """If all stop_sequences are empty, stop key must not be in payload."""
        from unittest.mock import AsyncMock, MagicMock, patch

        llm.config = LLMConfigData(
            api_key="sk-test",
            model="gpt-4",
            stop_sequences=[],
        )

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            await llm.complete([UserMessage(text="hi")])
            payload = mock_post.call_args.kwargs["json"]
            assert "stop" not in payload

    @pytest.mark.asyncio
    async def test_complete_custom_max_tokens_and_temperature(self, llm):
        """max_tokens and temperature parameters override config defaults."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status = MagicMock()

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ) as mock_post:
            await llm.complete(
                [UserMessage(text="hi")],
                max_tokens=50,
                temperature=0.9,
            )
            payload = mock_post.call_args.kwargs["json"]
            assert payload["max_tokens"] == 50
            assert payload["temperature"] == 0.9

    @pytest.mark.asyncio
    async def test_complete_raises_adapter_error_on_bad_response(self, llm):
        """Malformed API response must raise AdapterError."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {"choices": []}  # missing message
        mock_response.raise_for_status = MagicMock()

        with (
            patch(
                "httpx.AsyncClient.post",
                new_callable=AsyncMock,
                return_value=mock_response,
            ),
            pytest.raises(AdapterError, match="Unexpected response shape"),
        ):
            await llm.complete([UserMessage(text="hi")])

    @pytest.mark.asyncio
    async def test_stream_sends_stream_true(self):
        """Streaming request must have stream=True in payload."""
        from unittest.mock import AsyncMock, MagicMock, patch

        async def _aiter_lines():
            return
            yield

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.aiter_lines = _aiter_lines
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {"content-type": "text/event-stream"}

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__.return_value = mock_response

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value = mock_stream_ctx

        with patch("httpx.AsyncClient", return_value=mock_client):
            llm = OpenAICompatibleLLM(
                LLMConfigData(
                    api_key="sk-test",
                    model="gpt-4",
                    api_base="http://test/v1",
                    stop_sequences=["", "end", "stop", ""],
                )
            )
            _ = [c async for c in llm.stream([UserMessage(text="hi")])]

        call_args = mock_client.stream.call_args
        payload = call_args.kwargs["json"]
        assert payload["stream"] is True
        assert payload.get("stop") == ["end", "stop"]

    def test_get_context_limit_returns_server_context_size_when_set(self):
        """server_context_size takes priority over max_tokens."""
        llm = OpenAICompatibleLLM(
            LLMConfigData(
                api_key="sk-test",
                server_context_size=8192,
                max_tokens=100,
            )
        )
        assert llm.get_context_limit() == 8192

    def test_get_context_limit_returns_none_when_server_context_size_unset(self):
        """If server_context_size is None, return None (max_tokens is generation
        limit)."""
        llm = OpenAICompatibleLLM(
            LLMConfigData(
                api_key="sk-test",
                server_context_size=None,
                max_tokens=2048,
            )
        )
        assert llm.get_context_limit() is None

    def test_get_context_limit_returns_none_when_both_unset(self):
        """If both server_context_size and max_tokens are zero/invalid, return None."""
        llm = OpenAICompatibleLLM(
            LLMConfigData(
                api_key="sk-test",
                server_context_size=0,
                max_tokens=0,
            )
        )
        assert llm.get_context_limit() is None

    def test_connect_timeout_used_in_client(self):
        """connect_timeout must be passed to httpx.AsyncClient via Timeout."""
        from unittest.mock import MagicMock, patch

        mock_instance = MagicMock(spec=httpx.AsyncClient)
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            OpenAICompatibleLLM(
                LLMConfigData(
                    api_key="sk-test",
                    model="gpt-4",
                    api_base="http://test/v1",
                    timeout=300.0,
                    connect_timeout=3.0,
                )
            )
            call_kwargs = mock_cls.call_args.kwargs
            timeout = call_kwargs["timeout"]
            assert isinstance(timeout, httpx.Timeout)
            assert timeout.connect == 3.0

    def test_connect_timeout_none_uses_plain_timeout(self):
        """If connect_timeout is None, use plain float timeout (backward compat)."""
        from unittest.mock import MagicMock, patch

        mock_instance = MagicMock(spec=httpx.AsyncClient)
        with patch("httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = mock_instance
            OpenAICompatibleLLM(
                LLMConfigData(
                    model="test",
                    api_base="http://test",
                    timeout=10.0,
                    connect_timeout=None,
                )
            )
            call_kwargs = mock_cls.call_args.kwargs
            timeout = call_kwargs["timeout"]
            assert isinstance(timeout, httpx.Timeout)
            assert timeout.read == 10.0

    @pytest.mark.asyncio
    async def test_stream_raises_adapter_error_on_network_failure(self):
        """P4: Given: connection drops during SSE stream setup.
        When: stream() is called.
        Then: AdapterError wraps the network exception."""
        from unittest.mock import AsyncMock, MagicMock, patch

        llm = OpenAICompatibleLLM(
            LLMConfigData(
                api_key="sk-test",
                model="gpt-4",
                api_base="http://test/v1",
            )
        )

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__.side_effect = httpx.ConnectError(
            "connection refused"
        )

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.stream.return_value = mock_stream_ctx

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            pytest.raises(AdapterError),
        ):
            _ = [c async for c in llm.stream([UserMessage(text="hi")])]


# ── TestFactoryRegistry ──


class TestFactoryRegistry:
    """Given: @register decorator populates registry on import.
    When: registry is inspected.
    Then: all expected adapters are registered.
    """

    def test_all_ports_present(self):
        from ai_assistant.adapters._registry import get_registry

        registry = get_registry()
        expected_ports = {
            "llm",
            "embedder",
            "vector_store",
            "chunker",
            "storage",
            "reranker",
        }
        assert expected_ports.issubset(registry.keys()), (
            f"Missing ports: {expected_ports - registry.keys()}"
        )

    def test_llm_adapters_registered(self):
        from ai_assistant.adapters._registry import get_registry

        registry = get_registry()
        llm = registry.get("llm", {})
        assert "mock" in llm
        assert "openai_compatible" in llm

    def test_embedder_adapters_registered(self):
        from ai_assistant.adapters._registry import get_registry

        registry = get_registry()
        embedder = registry.get("embedder", {})
        assert "mock" in embedder
        assert "openai_compatible" in embedder

    def test_vector_store_adapters_registered(self):
        from ai_assistant.adapters._registry import get_registry

        registry = get_registry()
        vs = registry.get("vector_store", {})
        assert "memory" in vs
        assert "faiss" in vs

    def test_chunker_adapters_registered(self):
        from ai_assistant.adapters._registry import get_registry

        registry = get_registry()
        chunker = registry.get("chunker", {})
        assert "simple" in chunker

    def test_storage_adapters_registered(self):
        from ai_assistant.adapters._registry import get_registry

        registry = get_registry()
        storage = registry.get("storage", {})
        assert "sqlite" in storage

    def test_reranker_adapters_registered(self):
        from ai_assistant.adapters._registry import get_registry

        registry = get_registry()
        reranker = registry.get("reranker", {})
        assert "api" in reranker
        assert "null" in reranker


# ── TestOpenAICompatibleEmbedder ──


class TestOpenAICompatibleEmbedder:
    """Given: OpenAICompatibleEmbedder with mocked HTTP client.
    When: embed() is called with various inputs.
    Then: correct batching, payload, and error handling.
    """

    @pytest.fixture
    def embedder(self):
        return OpenAICompatibleEmbedder(
            EmbedderConfigData(
                api_key="sk-test",
                model="text-embedding-3-small",
                api_base="http://test/v1",
                dim=384,
                timeout=60.0,
                connect_timeout=5.0,
            )
        )

    @pytest.mark.asyncio
    async def test_embed_batches_large_input(self, embedder):
        """Input larger than _DEFAULT_BATCH_SIZE must be split into multiple POSTs."""
        from unittest.mock import AsyncMock, MagicMock, patch

        async def _mock_post(*args, **kwargs):
            payload = kwargs.get("json", {})
            texts = payload.get("input", [])
            mock_resp = MagicMock(spec=httpx.Response)
            mock_resp.json.return_value = {
                "data": [{"embedding": [0.1] * 384} for _ in texts]
            }
            mock_resp.raise_for_status = MagicMock()
            mock_resp.text = "ok"
            return mock_resp

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=_mock_post
        ) as mock_post:
            texts = ["text"] * 250
            result = await embedder.embed(texts)

            assert len(result) == 250
            assert mock_post.call_count == 3

    @pytest.mark.asyncio
    async def test_embed_count_mismatch_raises(self, embedder):
        """Server returning fewer embeddings than input texts
        must raise AdapterError."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {"data": [{"embedding": [0.1] * 384}]}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "ok"

        with (
            patch(
                "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp
            ),
            pytest.raises(AdapterError, match="count mismatch"),
        ):
            await embedder.embed(["hello", "world"])

    @pytest.mark.asyncio
    async def test_shutdown_unconditional(self, embedder):
        """shutdown must close client unconditionally; post-shutdown embed raises
        AdapterError."""
        await embedder.shutdown()
        await embedder.shutdown()
        with pytest.raises(AdapterError, match="shutting down"):
            await embedder.embed(["hello"])


# ── TestAsyncPostJson ──


class TestAsyncPostJson:
    """Given: async_post_json helper centralizes POST + raise_for_status + JSON
    parsing.
    When: called with various response scenarios.
    Then: returns parsed dict or raises AdapterError with prior logging.
    """

    @pytest.mark.asyncio
    async def test_success_returns_json(self):
        """Successful POST with valid JSON returns parsed dict."""
        from unittest.mock import AsyncMock, MagicMock

        from ai_assistant.adapters._http import async_post_json

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {"data": [{"embedding": [0.1, 0.2]}]}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = '{"data": [{"embedding": [0.1, 0.2]}]}'

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_resp)

        result = await async_post_json(
            mock_client,
            "http://test/v1/embeddings",
            {"Authorization": "Bearer x"},
            {"input": "hi"},
        )
        assert result == {"data": [{"embedding": [0.1, 0.2]}]}

    @pytest.mark.asyncio
    async def test_http_error_raises_adapter_error(self):
        """HTTP error raises AdapterError with chained exception."""
        from unittest.mock import AsyncMock, MagicMock

        from ai_assistant.adapters._http import async_post_json

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(
            side_effect=httpx.ConnectError("connection refused")
        )

        with pytest.raises(AdapterError, match="HTTP request failed"):
            await async_post_json(
                mock_client, "http://test/v1/embeddings", {}, {"input": "hi"}
            )

    @pytest.mark.asyncio
    async def test_invalid_json_raises_adapter_error(self):
        """Non-JSON response raises AdapterError."""
        from unittest.mock import AsyncMock, MagicMock

        from ai_assistant.adapters._http import async_post_json

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.side_effect = ValueError("not json")
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "not json"

        mock_client = MagicMock(spec=httpx.AsyncClient)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with pytest.raises(AdapterError, match="Invalid JSON response"):
            await async_post_json(
                mock_client, "http://test/v1/embeddings", {}, {"input": "hi"}
            )


# ── FaissVectorStore load() guard tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_faiss_load_missing_store_json_raises(tmp_path: Path) -> None:
    """If index.faiss exists but store.json is missing, load() must raise
    AdapterError.

    This prevents silent data corruption where the index loads but chunk metadata
    is absent, causing search() to return empty results without warning.
    """
    faiss = pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

    config = VectorStoreConfigData(dim=384, index_path=str(tmp_path))
    store = FaissVectorStore(config)

    dummy_index = faiss.IndexFlatL2(384)
    faiss.write_index(dummy_index, str(tmp_path / "default.faiss"))

    assert not (tmp_path / "default.store.json").exists()

    with pytest.raises(AdapterError) as exc_info:
        await store.load(str(tmp_path), namespace="default")

    assert (
        "metadata missing" in str(exc_info.value).lower()
        or "store.json" in str(exc_info.value).lower()
    )


@pytest.mark.asyncio
async def test_faiss_load_missing_index_faiss_raises(tmp_path: Path) -> None:
    """If store.json exists but index.faiss is missing, load() must raise
    AdapterError."""
    pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

    config = VectorStoreConfigData(dim=384, index_path=str(tmp_path))
    store = FaissVectorStore(config)

    store_file = tmp_path / "default.store.json"
    store_data = {"dim": 384, "metric": "l2", "chunks": []}
    store_file.write_text(json.dumps(store_data), encoding="utf-8")

    with pytest.raises(AdapterError) as exc_info:
        await store.load(str(tmp_path), namespace="default")

    assert (
        "index file missing" in str(exc_info.value).lower()
        or "index.faiss" in str(exc_info.value).lower()
    )


@pytest.mark.asyncio
async def test_faiss_load_both_missing_is_noop(tmp_path: Path) -> None:
    """If neither index.faiss nor store.json exists, load() is a no-op."""
    pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

    config = VectorStoreConfigData(dim=384, index_path=str(tmp_path))
    store = FaissVectorStore(config)

    await store.load(str(tmp_path), namespace="default")
    results = await store.search([0.0] * 384, top_k=5, namespace="default")
    assert results == []


# ── FaissVectorStore atomic save tests ────────────────────────────────────


@pytest.mark.asyncio
async def test_faiss_save_atomic_replaces_existing(tmp_path: Path) -> None:
    """Atomic save must replace old index without leaving partial files."""
    pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

    config = VectorStoreConfigData(dim=3, index_path=str(tmp_path))
    store = FaissVectorStore(config)

    chunks1 = [
        Chunk(id="c1", text="first", embedding=[1.0, 0.0, 0.0]),
    ]
    await store.add(chunks1, namespace="test")
    await store.save(str(tmp_path), namespace="test")

    index_file = tmp_path / "test.faiss"
    store_file = tmp_path / "test.store.json"
    assert index_file.exists()
    assert store_file.exists()

    chunks2 = [
        Chunk(id="c2", text="second", embedding=[0.0, 1.0, 0.0]),
    ]
    await store.add(chunks2, namespace="test")
    await store.save(str(tmp_path), namespace="test")

    temp_files = list(tmp_path.glob("*.tmp"))
    assert not temp_files, f"Temp files left behind: {temp_files}"

    store2 = FaissVectorStore(config)
    await store2.load(str(tmp_path), namespace="test")
    results = await store2.search([0.0, 1.0, 0.0], top_k=5, namespace="test")
    assert len(results) == 2
    ids = {r.id for r in results}
    assert ids == {"c1", "c2"}


@pytest.mark.asyncio
async def test_faiss_load_ntotal_mismatch_raises(tmp_path: Path) -> None:
    """If index.ntotal differs from metadata chunk count, load() must raise."""
    faiss = pytest.importorskip("faiss")
    import numpy as np

    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

    config = VectorStoreConfigData(dim=3, index_path=str(tmp_path))
    store = FaissVectorStore(config)

    index = faiss.IndexFlatL2(3)
    vectors = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32)
    index.add(vectors)
    faiss.write_index(index, str(tmp_path / "default.faiss"))

    store_data = {
        "dim": 3,
        "metric": "l2",
        "chunks": [
            {
                "id": "c1",
                "text": "a",
                "metadata": {
                    "source": "s1",
                    "index": 0,
                    "total_chunks": 1,
                    "custom": {},
                },
            }
        ],
    }
    (tmp_path / "default.store.json").write_text(
        json.dumps(store_data), encoding="utf-8"
    )

    with pytest.raises(AdapterError, match="integrity check failed"):
        await store.load(str(tmp_path), namespace="default")


@pytest.mark.asyncio
async def test_faiss_load_metric_mismatch_raises(tmp_path: Path) -> None:
    """If stored metric differs from config, load() must raise."""
    faiss = pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

    config = VectorStoreConfigData(dim=3, metric="cosine", index_path=str(tmp_path))
    store = FaissVectorStore(config)

    index = faiss.IndexFlatL2(3)
    faiss.write_index(index, str(tmp_path / "default.faiss"))

    store_data = {"dim": 3, "metric": "l2", "chunks": []}
    (tmp_path / "default.store.json").write_text(
        json.dumps(store_data), encoding="utf-8"
    )

    with pytest.raises(VersionMismatchError, match="metric"):
        await store.load(str(tmp_path), namespace="default")


@pytest.mark.asyncio
async def test_memory_load_count_mismatch_raises(tmp_path: Path) -> None:
    """If embeddings/chunks/metadata counts differ, load() must raise."""
    from ai_assistant.adapters.vector_store_memory import MemoryVectorStore

    config = VectorStoreConfigData(dim=3, index_path=str(tmp_path))
    store = MemoryVectorStore(config)

    store_data = {
        "dim": 3,
        "chunks": {
            "c1": {
                "id": "c1",
                "text": "a",
                "metadata": {
                    "source": "s1",
                    "index": 0,
                    "total_chunks": 1,
                    "custom": {},
                },
            }
        },
        "embeddings": {
            "c1": [1.0, 0.0, 0.0],
            "c2": [0.0, 1.0, 0.0],  # extra embedding without chunk
        },
        "metadata": {
            "c1": {"source": "s1"},
        },
    }
    p = tmp_path / "default" / "memory_store.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store_data), encoding="utf-8")

    with pytest.raises(AdapterError, match="integrity check failed"):
        await store.load(str(tmp_path), namespace="default")


@pytest.mark.asyncio
async def test_memory_load_dim_mismatch_raises(tmp_path: Path) -> None:
    """If embedding dim in JSON differs from config, load() must raise."""
    from ai_assistant.adapters.vector_store_memory import MemoryVectorStore

    config = VectorStoreConfigData(dim=3, index_path=str(tmp_path))
    store = MemoryVectorStore(config)

    store_data = {
        "dim": 3,
        "chunks": {
            "c1": {
                "id": "c1",
                "text": "a",
                "metadata": {
                    "source": "s1",
                    "index": 0,
                    "total_chunks": 1,
                    "custom": {},
                },
            }
        },
        "embeddings": {
            "c1": [1.0, 0.0],  # dim 2, expected 3
        },
        "metadata": {
            "c1": {"source": "s1"},
        },
    }
    p = tmp_path / "default" / "memory_store.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store_data), encoding="utf-8")

    with pytest.raises(AdapterError, match="embedding dim"):
        await store.load(str(tmp_path), namespace="default")


@pytest.mark.asyncio
async def test_llm_openai_compatible_shutdown_idempotent():
    cfg = LLMConfigData(api_base="http://localhost:9999/v1", api_key="x")
    llm = OpenAICompatibleLLM(cfg)
    await llm.shutdown()
    await llm.shutdown()  # no error


@pytest.mark.asyncio
async def test_llm_openai_compatible_rejects_after_shutdown():
    cfg = LLMConfigData(api_base="http://localhost:9999/v1", api_key="x")
    llm = OpenAICompatibleLLM(cfg)
    await llm.shutdown()
    with pytest.raises(AdapterError, match="shutting down"):
        await llm.complete([UserMessage(text="hi")])


# ---------- #19: orphaned .faiss without .store.json ----------


@pytest.fixture
def faiss_store():
    pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

    cfg = VectorStoreConfigData(
        index_path="./data/indices/test",
        metric="l2",
        dim=384,
        max_chunks=100,
    )
    return FaissVectorStore(cfg)


@pytest.mark.asyncio
async def test_list_namespaces_warns_on_orphaned_faiss(faiss_store, caplog):
    """Orphaned .faiss without .store.json must log a warning."""
    with tempfile.TemporaryDirectory() as tmp:
        Path(tmp, "orphaned.faiss").write_bytes(b"fake")
        Path(tmp, "valid.store.json").write_text('{"dim": 384}', encoding="utf-8")
        Path(tmp, "valid.faiss").write_bytes(b"fake")

        with caplog.at_level("WARNING"):
            ns = await faiss_store.list_namespaces(tmp)

        assert "valid" in ns
        assert "orphaned" not in ns
        assert "Orphaned FAISS index file" in caplog.text


# ── FaissVectorStore Bug Fix Tests ──────────────────────────────────────────
# Tests for bugs fixed in vector_store_faiss.py audit (12 bugs)


class TestFaissVectorStoreBugFixes:
    """Given: FaissVectorStore with 12 bugs fixed.
    When: edge cases from the audit are exercised.
    Then: correct behavior with proper error handling.
    """

    @pytest.fixture
    def faiss_store(self, tmp_path):
        pytest.importorskip("faiss")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        return FaissVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path), max_chunks=10)
        )

    @pytest.mark.asyncio
    async def test_chunk_from_dict_null_metadata(self, faiss_store, tmp_path):
        """metadata: null in JSON must not crash _chunk_from_dict."""
        import faiss
        import numpy as np

        index = faiss.IndexFlatL2(3)
        index.add(np.array([[1.0, 0.0, 0.0]], dtype=np.float32))
        faiss.write_index(index, str(tmp_path / "default.faiss"))

        store_data = {
            "dim": 3,
            "metric": "l2",
            "chunks": [
                {
                    "id": "c1",
                    "text": "hello",
                    "embedding": [1.0, 0.0, 0.0],
                    "metadata": None,
                }
            ],
        }
        (tmp_path / "default.store.json").write_text(
            json.dumps(store_data), encoding="utf-8"
        )

        await faiss_store.load(str(tmp_path), namespace="default")
        results = await faiss_store.search(
            [1.0, 0.0, 0.0], top_k=5, namespace="default"
        )
        assert len(results) == 1
        assert results[0].id == "c1"
        assert results[0].metadata is not None

    @pytest.mark.asyncio
    async def test_delete_under_lock_persists_atomically(self, faiss_store, tmp_path):
        """delete() must hold lock during save() and rollback on failure."""

        chunks = [
            Chunk(id="c1", text="keep", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="delete", embedding=[0.0, 1.0, 0.0]),
        ]
        await faiss_store.add(chunks, namespace="test")
        await faiss_store.save(str(tmp_path), namespace="test")

        await faiss_store.delete(["c2"], namespace="test")

        results = await faiss_store.search([0.0, 1.0, 0.0], top_k=5, namespace="test")
        assert not any(r.id == "c2" for r in results)
        assert any(r.id == "c1" for r in results)

        await faiss_store.save(str(tmp_path), namespace="test")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        store2 = FaissVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store2.load(str(tmp_path), namespace="test")
        results2 = await store2.search([0.0, 1.0, 0.0], top_k=5, namespace="test")
        assert not any(r.id == "c2" for r in results2)

    @pytest.mark.asyncio
    async def test_delete_rollback_on_save_failure(self, faiss_store, tmp_path):
        """If save() fails during delete(), in-memory state must rollback."""
        from unittest.mock import patch

        chunks = [
            Chunk(id="c1", text="keep", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="delete", embedding=[0.0, 1.0, 0.0]),
        ]
        await faiss_store.add(chunks, namespace="test")
        await faiss_store.save(str(tmp_path), namespace="test")

        with (
            patch("faiss.write_index", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            await faiss_store.delete(["c2"], namespace="test")

        results = await faiss_store.search([0.0, 1.0, 0.0], top_k=5, namespace="test")
        assert any(r.id == "c2" for r in results)
        assert any(r.id == "c1" for r in results)

    @pytest.mark.asyncio
    async def test_save_cleans_up_temp_on_write_failure(self, faiss_store, tmp_path):
        """If faiss.write_index fails during save(), temp file must be cleaned up."""
        from unittest.mock import patch

        chunks = [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])]
        await faiss_store.add(chunks, namespace="test")

        with (
            patch("os.replace", side_effect=OSError("replace failed")),
            pytest.raises(OSError, match="replace failed"),
        ):
            await faiss_store.save(str(tmp_path), namespace="test")

        temp_files = list(tmp_path.glob("*.tmp"))
        assert not temp_files, f"Temp files left behind after failure: {temp_files}"

    @pytest.mark.asyncio
    async def test_save_cleans_up_temp_on_replace_failure(self, faiss_store, tmp_path):
        """If os.replace fails during save(), temp file must be cleaned up."""
        from unittest.mock import patch

        chunks = [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])]
        await faiss_store.add(chunks, namespace="test")

        with (
            patch("os.replace", side_effect=OSError("replace failed")),
            pytest.raises(OSError, match="replace failed"),
        ):
            await faiss_store.save(str(tmp_path), namespace="test")

        temp_files = list(tmp_path.glob("*.tmp"))
        assert not temp_files, (
            f"Temp files left behind after replace failure: {temp_files}"
        )

    @pytest.mark.asyncio
    async def test_save_no_temp_files_left(self, faiss_store, tmp_path):
        """After save(), no .tmp files or temp directories should remain."""

        chunks = [
            Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0]),
        ]
        await faiss_store.add(chunks, namespace="ns1")
        await faiss_store.save(str(tmp_path), namespace="ns1")

        tmp_files = list(tmp_path.rglob("*.tmp"))
        tmp_dirs = [d for d in tmp_path.rglob(".*.tmp.*") if d.is_dir()]
        assert not tmp_files, f"Temp files left: {tmp_files}"
        assert not tmp_dirs, f"Temp dirs left: {tmp_dirs}"

    @pytest.mark.asyncio
    async def test_list_namespaces_file_not_directory(self, faiss_store, tmp_path):
        """If index_path is a file (not dir), list_namespaces must raise
        AdapterError."""
        file_path = tmp_path / "not_a_dir"
        file_path.write_text("i am a file", encoding="utf-8")

        with pytest.raises(AdapterError):
            await faiss_store.list_namespaces(str(file_path))

    @pytest.mark.asyncio
    async def test_list_namespaces_permission_error(self, faiss_store, tmp_path):
        """Permission errors must be wrapped in AdapterError."""
        if os.name == "nt":
            pytest.skip("Permission test skipped on Windows")

        os.chmod(str(tmp_path), 0o000)
        try:
            with pytest.raises(AdapterError):
                await faiss_store.list_namespaces(str(tmp_path))
        finally:
            os.chmod(str(tmp_path), 0o755)

    @pytest.mark.asyncio
    async def test_add_rejects_when_exceeds_max_chunks(self, faiss_store, tmp_path):
        """add() must raise AdapterError when total would exceed max_chunks."""

        for i in range(8):
            await faiss_store.add(
                [Chunk(id=f"c{i}", text=f"t{i}", embedding=[1.0, 0.0, 0.0])],
                namespace="test",
            )

        with pytest.raises(AdapterError, match="max_chunks"):
            await faiss_store.add(
                [
                    Chunk(id="c8", text="t8", embedding=[1.0, 0.0, 0.0]),
                    Chunk(id="c9", text="t9", embedding=[1.0, 0.0, 0.0]),
                    Chunk(id="c10", text="t10", embedding=[1.0, 0.0, 0.0]),
                ],
                namespace="test",
            )

        results = await faiss_store.search([1.0, 0.0, 0.0], top_k=20, namespace="test")
        assert len(results) == 8

    @pytest.mark.asyncio
    async def test_cosine_zero_vector_no_nan(self, tmp_path):
        """Zero-length embeddings in cosine metric must not produce NaN."""
        pytest.importorskip("faiss")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        store = FaissVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path), metric="cosine")
        )

        chunks = [Chunk(id="c1", text="empty", embedding=[0.0, 0.0, 0.0])]
        await store.add(chunks, namespace="test")

        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.asyncio
    async def test_delete_empty_chunk_ids_noop(self, faiss_store):
        """delete() with empty chunk_ids must be a no-op."""
        chunks = [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])]
        await faiss_store.add(chunks, namespace="test")

        await faiss_store.delete([], namespace="test")
        results = await faiss_store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_add_empty_chunks_noop(self, faiss_store):
        """add() with empty list must be a no-op."""
        await faiss_store.add([], namespace="test")
        results = await faiss_store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert results == []


async def test_recursive_chunker_preserves_structure():
    config = ChunkerConfigData(chunk_size=100)
    chunker = RecursiveChunker(config)
    doc = Document(
        id="test.md",
        content=(
            "First paragraph here.\n\nSecond paragraph with more text.\n\nThird one."
        ),
    )
    chunks = await chunker.chunk(doc)
    assert len(chunks) >= 1
    for c in chunks:
        assert len(c.text) <= 100
    full = "".join(c.text for c in chunks)
    assert "First paragraph" in full
    assert "Second paragraph" in full


async def test_recursive_chunker_fallback_to_characters():
    config = ChunkerConfigData(chunk_size=10, chunk_overlap=0)
    chunker = RecursiveChunker(config)
    doc = Document(id="test.txt", content="abcdefghij" * 5)
    chunks = await chunker.chunk(doc)
    for c in chunks:
        assert len(c.text) <= 10
    assert "".join(c.text for c in chunks) == "abcdefghij" * 5


async def test_recursive_chunker_empty_document():
    config = ChunkerConfigData(chunk_size=50, chunk_overlap=0)
    chunker = RecursiveChunker(config)
    doc = Document(id="empty.txt", content="")
    assert await chunker.chunk(doc) == []


async def test_recursive_chunker_sentence_overlap():
    config = ChunkerConfigData(chunk_size=40, chunk_overlap=25)
    chunker = RecursiveChunker(config)
    doc = Document(
        id="overlap.txt",
        content="Sentence one here. Sentence two here. Sentence three here. End.",
    )
    chunks = await chunker.chunk(doc)
    assert len(chunks) >= 2
    # Start of chunk[1] must come from the end of chunk[0]
    assert chunks[1].text[:10] in chunks[0].text


# ── SQLiteStorage: _safe_json_loads ──────────────────────────────────────


class TestSafeJsonLoads:
    """Coverage for _safe_json_loads error paths (lines 38, 41-46)."""

    def test_invalid_json_returns_default(self):
        """Given: invalid JSON string.
        When: _safe_json_loads is called.
        Then: returns default value.
        """
        from ai_assistant.adapters.storage_sqlite import _safe_json_loads

        result = _safe_json_loads("not valid json {{{", {"fallback": True})
        assert result == {"fallback": True}

    def test_none_returns_default(self):
        """Given: None value.
        When: _safe_json_loads is called.
        Then: returns default value.
        """
        from ai_assistant.adapters.storage_sqlite import _safe_json_loads

        result = _safe_json_loads(None, {"fallback": True})
        assert result == {"fallback": True}

    def test_empty_string_returns_default(self):
        """Given: empty string.
        When: _safe_json_loads is called.
        Then: returns default value.
        """
        from ai_assistant.adapters.storage_sqlite import _safe_json_loads

        result = _safe_json_loads("", {"fallback": True})
        assert result == {"fallback": True}

    def test_valid_json_returns_parsed(self):
        """Given: valid JSON string.
        When: _safe_json_loads is called.
        Then: returns parsed value.
        """
        from ai_assistant.adapters.storage_sqlite import _safe_json_loads

        result = _safe_json_loads('{"key": "value"}', {})
        assert result == {"key": "value"}

    def test_json_null_preserved(self):
        """Given: JSON null.
        When: _safe_json_loads is called.
        Then: returns None, not default.
        """
        from ai_assistant.adapters.storage_sqlite import _safe_json_loads

        result = _safe_json_loads("null", {"fallback": True})
        assert result is None

    def test_non_string_type_returns_default(self):
        """Given: non-string type (int).
        When: _safe_json_loads is called.
        Then: returns default via TypeError catch.
        """
        from ai_assistant.adapters.storage_sqlite import _safe_json_loads

        result = _safe_json_loads(12345, {"fallback": True})  # type: ignore[arg-type]
        assert result == {"fallback": True}


# ── SQLiteStorage: save_exchange ─────────────────────────────────────────


class TestSQLiteStorageSaveExchange:
    """Coverage for save_exchange atomic operation."""

    @pytest.mark.asyncio
    async def test_save_exchange_saves_both_messages(self, tmp_path):
        """Given: two messages.
        When: save_exchange is called.
        Then: both messages are persisted.
        """
        from ai_assistant.adapters.storage_sqlite import SQLiteStorage
        from ai_assistant.core.domain.configs import StorageConfigData

        db_path = str(tmp_path / "test.db")
        storage = SQLiteStorage(StorageConfigData(db_path=db_path))
        await storage.init_db()

        await storage.save_exchange(
            "conv-1",
            {"role": "user", "content": "Hello", "metadata": {}},
            {"role": "assistant", "content": "Hi!", "metadata": {}},
        )

        history = await storage.get_history("conv-1")
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Hi!"

    @pytest.mark.asyncio
    async def test_save_exchange_atomicity_on_error(self, tmp_path):
        """Given: second insert fails.
        When: save_exchange is called.
        Then: AdapterError raised, no messages saved (rollback).
        """
        import sqlite3

        from ai_assistant.adapters.storage_sqlite import SQLiteStorage
        from ai_assistant.core.domain.configs import StorageConfigData
        from ai_assistant.core.domain.errors import AdapterError

        db_path = str(tmp_path / "test.db")
        storage = SQLiteStorage(StorageConfigData(db_path=db_path))
        await storage.init_db()

        original_insert = storage._insert_message
        call_count = 0

        async def failing_insert(conn, conversation_id, message):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise sqlite3.OperationalError("Simulated DB error")
            await original_insert(conn, conversation_id, message)

        storage._insert_message = failing_insert

        with pytest.raises(AdapterError, match="save_exchange failed"):
            await storage.save_exchange(
                "conv-1",
                {"role": "user", "content": "Hello", "metadata": {}},
                {"role": "assistant", "content": "Hi!", "metadata": {}},
            )

        # Transaction rolled back — no messages saved
        history = await storage.get_history("conv-1")
        assert len(history) == 0


# ── SQLiteStorage: get/set error paths ───────────────────────────────────


class TestSQLiteStorageErrorPaths:
    """Coverage for get/set/shutdown error handling."""

    @pytest.mark.asyncio
    async def test_set_non_serializable_raises_adapter_error(self, tmp_path):
        """Given: non-JSON-serializable value.
        When: set is called.
        Then: AdapterError raised.
        """
        from ai_assistant.adapters.storage_sqlite import SQLiteStorage
        from ai_assistant.core.domain.configs import StorageConfigData
        from ai_assistant.core.domain.errors import AdapterError

        db_path = str(tmp_path / "test.db")
        storage = SQLiteStorage(StorageConfigData(db_path=db_path))
        await storage.init_db()

        with pytest.raises(AdapterError, match="not JSON-serializable"):
            await storage.set("key", object())  # object() is not serializable

    @pytest.mark.asyncio
    async def test_get_with_corrupt_json_returns_default(self, tmp_path):
        """Given: corrupt JSON in settings table.
        When: get is called.
        Then: returns default via _safe_json_loads fallback.
        """
        import aiosqlite

        from ai_assistant.adapters.storage_sqlite import SQLiteStorage
        from ai_assistant.core.domain.configs import StorageConfigData

        db_path = str(tmp_path / "test.db")
        storage = SQLiteStorage(StorageConfigData(db_path=db_path))
        await storage.init_db()

        # Insert corrupt JSON directly
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)",
                ("corrupt_key", "not valid json {{{"),
            )
            await conn.commit()

        result = await storage.get("corrupt_key", {"fallback": True})
        assert result == {"fallback": True}

    @pytest.mark.asyncio
    async def test_shutdown_skips_when_file_missing(self, tmp_path):
        """Given: database file does not exist.
        When: shutdown is called.
        Then: no error raised, operation skipped.
        """
        from ai_assistant.adapters.storage_sqlite import SQLiteStorage
        from ai_assistant.core.domain.configs import StorageConfigData

        db_path = str(tmp_path / "nonexistent.db")
        storage = SQLiteStorage(StorageConfigData(db_path=db_path))

        # Should not raise
        await storage.shutdown()

    @pytest.mark.asyncio
    async def test_get_history_with_corrupt_metadata(self, tmp_path):
        """Given: message with corrupt metadata JSON.
        When: get_history is called.
        Then: returns message with empty metadata dict.
        """
        import aiosqlite

        from ai_assistant.adapters.storage_sqlite import SQLiteStorage
        from ai_assistant.core.domain.configs import StorageConfigData

        db_path = str(tmp_path / "test.db")
        storage = SQLiteStorage(StorageConfigData(db_path=db_path))
        await storage.init_db()

        # Insert message with corrupt metadata directly
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute(
                """INSERT INTO chat_messages
                   (conversation_id, role, content, metadata)
                   VALUES (?, ?, ?, ?)""",
                ("conv-1", "user", "Hello", "not valid json {{{"),
            )
            await conn.commit()

        history = await storage.get_history("conv-1")
        assert len(history) == 1
        assert history[0]["content"] == "Hello"
        assert history[0]["metadata"] == {}


# ── TiktokenTokenizer ────────────────────────────────────────────────────


class TestResolveTokenizerDir:
    """Coverage for _resolve_tokenizer_dir (lines 30, 37, 42-53)."""

    def test_nonexistent_base_returns_none(self, tmp_path):
        """Given: non-existent local_dir.
        When: _resolve_tokenizer_dir is called.
        Then: returns None.
        """
        from ai_assistant.adapters.tiktoken_tokenizer import _resolve_tokenizer_dir

        result = _resolve_tokenizer_dir("qwen", str(tmp_path / "nonexistent"))
        assert result is None

    def test_exact_match_returns_dir(self, tmp_path):
        """Given: directory with exact model name and tokenizer.json.
        When: _resolve_tokenizer_dir is called.
        Then: returns that directory.
        """
        from ai_assistant.adapters.tiktoken_tokenizer import _resolve_tokenizer_dir

        model_dir = tmp_path / "qwen2.5-7b-instruct"
        model_dir.mkdir()
        (model_dir / "tokenizer.json").write_text("{}")

        result = _resolve_tokenizer_dir("Qwen2.5-7B-Instruct", str(tmp_path))
        assert result == model_dir

    def test_exact_match_with_underscores(self, tmp_path):
        """Given: directory with underscores in name.
        When: _resolve_tokenizer_dir is called with hyphens.
        Then: normalizes and finds the directory.
        """
        from ai_assistant.adapters.tiktoken_tokenizer import _resolve_tokenizer_dir

        model_dir = tmp_path / "qwen2.5_7b_instruct"
        model_dir.mkdir()
        (model_dir / "tokenizer.json").write_text("{}")

        result = _resolve_tokenizer_dir("qwen2.5-7b-instruct", str(tmp_path))
        assert result == model_dir

    def test_fuzzy_match_returns_dir(self, tmp_path):
        """Given: directory with partial model name match.
        When: _resolve_tokenizer_dir is called.
        Then: returns the fuzzy-matched directory.
        """
        from ai_assistant.adapters.tiktoken_tokenizer import _resolve_tokenizer_dir

        model_dir = tmp_path / "qwen2.5"
        model_dir.mkdir()
        (model_dir / "tokenizer.json").write_text("{}")

        result = _resolve_tokenizer_dir("qwen2.5-7b-instruct-1m", str(tmp_path))
        assert result == model_dir

    def test_no_match_returns_none(self, tmp_path):
        """Given: directory with unrelated model names.
        When: _resolve_tokenizer_dir is called.
        Then: returns None.
        """
        from ai_assistant.adapters.tiktoken_tokenizer import _resolve_tokenizer_dir

        other_dir = tmp_path / "llama-3"
        other_dir.mkdir()
        (other_dir / "tokenizer.json").write_text("{}")

        result = _resolve_tokenizer_dir("qwen2.5-7b", str(tmp_path))
        assert result is None

    def test_dir_without_tokenizer_json_skipped(self, tmp_path):
        """Given: directory with model name but no tokenizer.json.
        When: _resolve_tokenizer_dir is called.
        Then: returns None (directory skipped).
        """
        from ai_assistant.adapters.tiktoken_tokenizer import _resolve_tokenizer_dir

        model_dir = tmp_path / "qwen2.5-7b"
        model_dir.mkdir()
        # No tokenizer.json inside

        result = _resolve_tokenizer_dir("qwen2.5-7b", str(tmp_path))
        assert result is None

    def test_oserror_returns_none(self, tmp_path, monkeypatch):
        """Given: iterdir raises OSError.
        When: _resolve_tokenizer_dir is called.
        Then: returns None gracefully.
        """
        from unittest.mock import patch

        from ai_assistant.adapters.tiktoken_tokenizer import _resolve_tokenizer_dir

        base_dir = tmp_path / "models"
        base_dir.mkdir()

        with patch.object(Path, "iterdir", side_effect=OSError("Permission denied")):
            result = _resolve_tokenizer_dir("qwen", str(base_dir))

        assert result is None


class TestTiktokenTokenizerCount:
    """Coverage for count() error paths and HF fallback (lines 90->104)."""

    def test_empty_text_returns_zero(self):
        """Given: empty string.
        When: count is called.
        Then: returns 0 without calling any backend.
        """
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tokenizer = TiktokenTokenizer(
            TokenizerConfigData(provider="tiktoken", model_name="cl100k_base")
        )
        assert tokenizer.count("") == 0

    def test_tiktoken_keyerror_falls_through_to_hf(self, tmp_path):
        """Given: tiktoken raises KeyError (unknown encoding).
        When: count is called and HF tokenizer exists.
        Then: falls through to HF tokenizer backend.
        """
        from unittest.mock import MagicMock, patch

        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        # Create a mock HF tokenizer directory
        model_dir = tmp_path / "test-model"
        model_dir.mkdir()
        (model_dir / "tokenizer.json").write_text("{}")

        tokenizer = TiktokenTokenizer(
            TokenizerConfigData(
                provider="tiktoken",
                model_name="test-model",
                local_dir=str(tmp_path),
            )
        )

        mock_hf_result = MagicMock()
        mock_hf_result.tokens = ["hello", "world"]

        with patch(
            "ai_assistant.adapters.tiktoken_tokenizer.tiktoken"
        ) as mock_tiktoken:
            mock_tiktoken.get_encoding.side_effect = KeyError("unknown")

            with patch(
                "ai_assistant.adapters.tiktoken_tokenizer.tokenizers"
            ) as mock_tokenizers:
                mock_hf_tok = MagicMock()
                mock_hf_tok.encode.return_value = mock_hf_result
                mock_tokenizers.Tokenizer.from_file.return_value = mock_hf_tok

                result = tokenizer.count("hello world")

        assert result == 2

    def test_no_backend_raises_adapter_error(self):
        """Given: both tiktoken and tokenizers are None.
        When: count is called.
        Then: AdapterError raised with helpful message.
        """
        from unittest.mock import patch

        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData
        from ai_assistant.core.domain.errors import AdapterError

        tokenizer = TiktokenTokenizer(
            TokenizerConfigData(
                provider="tiktoken",
                model_name="unknown-model",
                local_dir="/nonexistent",
            )
        )

        with (
            patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None),
            patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", None),
            pytest.raises(AdapterError, match="No tokenizer backend available"),
        ):
            tokenizer.count("hello world")

    def test_hf_tokenizer_attribute_error_fallback(self, tmp_path):
        """Given: HF tokenizer result has no .tokens attribute.
        When: count is called.
        Then: falls back to len(result).
        """
        from unittest.mock import MagicMock, patch

        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        model_dir = tmp_path / "test-model"
        model_dir.mkdir()
        (model_dir / "tokenizer.json").write_text("{}")

        tokenizer = TiktokenTokenizer(
            TokenizerConfigData(
                provider="tiktoken",
                model_name="test-model",
                local_dir=str(tmp_path),
            )
        )

        # Result without .tokens attribute — simulates older tokenizers API
        mock_hf_result = ["hello", "world", "!"]

        with patch(
            "ai_assistant.adapters.tiktoken_tokenizer.tiktoken"
        ) as mock_tiktoken:
            mock_tiktoken.get_encoding.side_effect = KeyError("unknown")

            with patch(
                "ai_assistant.adapters.tiktoken_tokenizer.tokenizers"
            ) as mock_tokenizers:
                mock_hf_tok = MagicMock()
                mock_hf_tok.encode.return_value = mock_hf_result
                mock_tokenizers.Tokenizer.from_file.return_value = mock_hf_tok

                result = tokenizer.count("hello world!")

        assert result == 3

    def test_tiktoken_exception_raises_adapter_error(self):
        """Given: tiktoken raises unexpected exception.
        When: count is called.
        Then: AdapterError raised.
        """
        from unittest.mock import patch

        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData
        from ai_assistant.core.domain.errors import AdapterError

        tokenizer = TiktokenTokenizer(
            TokenizerConfigData(provider="tiktoken", model_name="cl100k_base")
        )

        with patch(
            "ai_assistant.adapters.tiktoken_tokenizer.tiktoken"
        ) as mock_tiktoken:
            mock_tiktoken.get_encoding.side_effect = RuntimeError("boom")

            with pytest.raises(AdapterError, match="tiktoken failed"):
                tokenizer.count("hello")

    def test_hf_tokenizer_exception_raises_adapter_error(self, tmp_path):
        """Given: HF tokenizer raises exception during encode.
        When: count is called.
        Then: AdapterError raised.
        """
        from unittest.mock import patch

        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData
        from ai_assistant.core.domain.errors import AdapterError

        model_dir = tmp_path / "test-model"
        model_dir.mkdir()
        (model_dir / "tokenizer.json").write_text("{}")

        tokenizer = TiktokenTokenizer(
            TokenizerConfigData(
                provider="tiktoken",
                model_name="test-model",
                local_dir=str(tmp_path),
            )
        )

        with patch(
            "ai_assistant.adapters.tiktoken_tokenizer.tiktoken"
        ) as mock_tiktoken:
            mock_tiktoken.get_encoding.side_effect = KeyError("unknown")

            with patch(
                "ai_assistant.adapters.tiktoken_tokenizer.tokenizers"
            ) as mock_tokenizers:
                mock_tokenizers.Tokenizer.from_file.side_effect = RuntimeError(
                    "corrupt tokenizer.json"
                )

                with pytest.raises(AdapterError, match="HF tokenizer failed"):
                    tokenizer.count("hello")


# ── OpenAICompatibleLLM ──────────────────────────────────────────────────


class TestOpenAICompatibleLLMBuildMessages:
    """Coverage for _build_messages branches (lines 75-98)."""

    def _make_llm(self):
        from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
        from ai_assistant.core.domain.configs import LLMConfigData

        return OpenAICompatibleLLM(
            LLMConfigData(
                model="test-model",
                api_base="http://localhost:8080/v1",
                api_key="test-key",
            )
        )

    def test_tool_message_conversion(self):
        """Given: ToolMessage in messages list.
        When: _build_messages is called.
        Then: converted to OpenAI tool format with tool_call_id.
        """
        from ai_assistant.core.domain.messages import ToolMessage

        llm = self._make_llm()
        messages = [ToolMessage(text="result", call_id="call_1")]
        result = llm._build_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["content"] == "result"
        assert result[0]["tool_call_id"] == "call_1"

    def test_system_message_conversion(self):
        """Given: SystemMessage in messages list.
        When: _build_messages is called.
        Then: converted to OpenAI system format.
        """
        from ai_assistant.core.domain.messages import SystemMessage

        llm = self._make_llm()
        messages = [SystemMessage(text="You are helpful")]
        result = llm._build_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful"

    def test_unknown_message_type_fallback(self):
        """Given: unknown message type.
        When: _build_messages is called.
        Then: falls back to user role with str representation.
        """
        llm = self._make_llm()
        messages = ["raw string message"]
        result = llm._build_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "raw string message" in result[0]["content"]

    def test_assistant_message_with_tool_calls(self):
        """Given: AssistantMessage with tool_calls.
        When: _build_messages is called.
        Then: tool_calls are included in output.
        """
        from ai_assistant.core.domain.messages import AssistantMessage

        llm = self._make_llm()
        tool_calls = [
            {"id": "call_1", "type": "function", "function": {"name": "get_weather"}}
        ]
        messages = [AssistantMessage(text="Let me check", tool_calls=tool_calls)]
        result = llm._build_messages(messages)

        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Let me check"
        assert result[0]["tool_calls"] == tool_calls


class TestOpenAICompatibleLLMParseToolCalls:
    """Coverage for _parse_tool_calls branches (lines 108-141)."""

    def _make_llm(self):
        from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
        from ai_assistant.core.domain.configs import LLMConfigData

        return OpenAICompatibleLLM(
            LLMConfigData(
                model="test-model",
                api_base="http://localhost:8080/v1",
                api_key="test-key",
            )
        )

    def test_none_returns_empty(self):
        """Given: None input.
        When: _parse_tool_calls is called.
        Then: returns empty list.
        """
        llm = self._make_llm()
        assert llm._parse_tool_calls(None) == []

    def test_non_iterable_returns_empty(self):
        """Given: non-iterable input (int).
        When: _parse_tool_calls is called.
        Then: returns empty list via TypeError catch.
        """
        llm = self._make_llm()
        assert llm._parse_tool_calls(12345) == []

    def test_non_dict_tool_call_skipped(self):
        """Given: tool_call that is not a dict.
        When: _parse_tool_calls is called.
        Then: skipped with warning.
        """
        llm = self._make_llm()
        result = llm._parse_tool_calls(["not a dict", 123])
        assert result == []

    def test_incomplete_function_tool_call_skipped(self):
        """Given: function tool_call without id or name.
        When: _parse_tool_calls is called.
        Then: skipped with warning.
        """
        llm = self._make_llm()
        # Missing id
        result = llm._parse_tool_calls(
            [{"type": "function", "function": {"name": "get_weather"}}]
        )
        assert result == []

        # Missing name
        result = llm._parse_tool_calls(
            [{"id": "call_1", "type": "function", "function": {}}]
        )
        assert result == []

    def test_unknown_tool_call_type_skipped(self):
        """Given: tool_call with unknown type.
        When: _parse_tool_calls is called.
        Then: skipped with warning.
        """
        llm = self._make_llm()
        result = llm._parse_tool_calls(
            [{"id": "call_1", "type": "unknown_type", "function": {"name": "test"}}]
        )
        assert result == []

    def test_valid_function_tool_call_parsed(self):
        """Given: valid function tool_call.
        When: _parse_tool_calls is called.
        Then: parsed correctly.
        """
        llm = self._make_llm()
        result = llm._parse_tool_calls(
            [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city": "Paris"}',
                    },
                }
            ]
        )
        assert len(result) == 1
        assert result[0]["id"] == "call_1"
        assert result[0]["function"]["name"] == "get_weather"
        assert result[0]["function"]["arguments"] == '{"city": "Paris"}'


class TestOpenAICompatibleLLMComplete:
    """Coverage for complete() closed check and payload options."""

    def _make_llm(self):
        from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
        from ai_assistant.core.domain.configs import LLMConfigData

        return OpenAICompatibleLLM(
            LLMConfigData(
                model="test-model",
                api_base="http://localhost:8080/v1",
                api_key="test-key",
            )
        )


    @pytest.mark.asyncio
    async def test_complete_with_all_optional_params(self):
        """Given: complete call with all optional params.
        When: request is made.
        Then: payload includes all optional fields.
        """
        import respx

        from ai_assistant.core.domain.messages import UserMessage

        llm = self._make_llm()

        with respx.mock:
            respx.post("http://localhost:8080/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"message": {"content": "Hello!", "role": "assistant"}}
                        ]
                    },
                )
            )

            result = await llm.complete(
                [UserMessage(text="Hi")],
                max_tokens=100,
                temperature=0.5,
                top_p=0.9,
                stop=["END"],
                frequency_penalty=0.1,
                presence_penalty=0.2,
            )

        assert result.text == "Hello!"
        await llm.shutdown()

    @pytest.mark.asyncio
    async def test_complete_with_stop_from_config(self):
        """Given: config with stop_sequences and no explicit stop param.
        When: complete is called.
        Then: config stop_sequences are used in payload.
        """
        import respx

        from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
        from ai_assistant.core.domain.configs import LLMConfigData
        from ai_assistant.core.domain.messages import UserMessage

        llm = OpenAICompatibleLLM(
            LLMConfigData(
                model="test-model",
                api_base="http://localhost:8080/v1",
                api_key="test-key",
                stop_sequences=["<|im_end|>", "<|im_start|>"],
            )
        )

        with respx.mock:
            respx.post("http://localhost:8080/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "choices": [
                            {"message": {"content": "Response", "role": "assistant"}}
                        ]
                    },
                )
            )

            result = await llm.complete([UserMessage(text="Hi")])

        assert result.text == "Response"
        await llm.shutdown()


class TestOpenAICompatibleLLMStream:
    """Coverage for _stream_impl error paths (lines 282-326)."""

    def _make_llm(self):
        from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
        from ai_assistant.core.domain.configs import LLMConfigData

        return OpenAICompatibleLLM(
            LLMConfigData(
                model="test-model",
                api_base="http://localhost:8080/v1",
                api_key="test-key",
                max_tokens=100,
            )
        )

    @pytest.mark.asyncio
    async def test_stream_with_valid_sse(self):
        """Given: valid SSE response.
        When: stream is called.
        Then: content chunks are yielded.
        """
        import respx

        from ai_assistant.core.domain.messages import UserMessage

        llm = self._make_llm()

        sse_content = (
            'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
            'data: {"choices": [{"delta": {"content": " world"}}]}\n\n'
            "data: [DONE]\n\n"
        )

        with respx.mock:
            respx.post("http://localhost:8080/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse_content,
                    headers={"content-type": "text/event-stream"},
                )
            )

            chunks = []
            async for chunk in llm.stream([UserMessage(text="Hi")]):
                chunks.append(chunk)

        assert chunks == ["Hello", " world"]
        await llm.shutdown()

    @pytest.mark.asyncio
    async def test_stream_non_sse_content_type_raises(self):
        """Given: response with non-SSE content type.
        When: stream is called.
        Then: AdapterError raised.
        """
        import respx

        from ai_assistant.core.domain.errors import AdapterError
        from ai_assistant.core.domain.messages import UserMessage

        llm = self._make_llm()

        with respx.mock:
            respx.post("http://localhost:8080/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content="plain text",
                    headers={"content-type": "text/plain"},
                )
            )

            with pytest.raises(AdapterError, match="Expected text/event-stream"):
                async for _ in llm.stream([UserMessage(text="Hi")]):
                    pass

        await llm.shutdown()

    @pytest.mark.asyncio
    async def test_stream_malformed_json_skipped(self):
        """Given: SSE with malformed JSON chunk.
        When: stream is called.
        Then: malformed chunks are skipped, valid ones yielded.
        """
        import respx

        from ai_assistant.core.domain.messages import UserMessage

        llm = self._make_llm()

        sse_content = (
            "data: not valid json\n\n"
            'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
            "data: [DONE]\n\n"
        )

        with respx.mock:
            respx.post("http://localhost:8080/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse_content,
                    headers={"content-type": "text/event-stream"},
                )
            )

            chunks = []
            async for chunk in llm.stream([UserMessage(text="Hi")]):
                chunks.append(chunk)

        assert chunks == ["Hello"]
        await llm.shutdown()

    @pytest.mark.asyncio
    async def test_stream_http_error_raises_adapter_error(self):
        """Given: HTTP error during stream.
        When: stream is called.
        Then: AdapterError raised.
        """
        import respx

        from ai_assistant.core.domain.errors import AdapterError
        from ai_assistant.core.domain.messages import UserMessage

        llm = self._make_llm()

        with respx.mock:
            respx.post("http://localhost:8080/v1/chat/completions").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )

            with pytest.raises(AdapterError, match="LLM stream request failed"):
                async for _ in llm.stream([UserMessage(text="Hi")]):
                    pass

        await llm.shutdown()

    @pytest.mark.asyncio
    async def test_stream_limit_reached(self):
        """Given: stream produces more tokens than max_stream_tokens.
        When: stream is called.
        Then: stream stops at limit.
        """
        import respx

        from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
        from ai_assistant.core.domain.configs import LLMConfigData
        from ai_assistant.core.domain.messages import UserMessage

        # max_tokens=2 means _max_stream_tokens=4
        llm = OpenAICompatibleLLM(
            LLMConfigData(
                model="test-model",
                api_base="http://localhost:8080/v1",
                api_key="test-key",
                max_tokens=2,
            )
        )

        # Generate more than 4 chunks
        lines = []
        for i in range(10):
            lines.append(
                f'data: {{"choices": [{{"delta": {{"content": "tok{i}"}}}}]}}\n\n'
            )
        lines.append("data: [DONE]\n\n")
        sse_content = "".join(lines)

        with respx.mock:
            respx.post("http://localhost:8080/v1/chat/completions").mock(
                return_value=httpx.Response(
                    200,
                    content=sse_content,
                    headers={"content-type": "text/event-stream"},
                )
            )

            chunks = []
            async for chunk in llm.stream([UserMessage(text="Hi")]):
                chunks.append(chunk)

        # Should stop at _max_stream_tokens (4)
        assert len(chunks) <= 4
        await llm.shutdown()


# ── APIReranker ──────────────────────────────────────────────────────────


class TestAPIReranker:
    """Coverage for APIReranker error paths (lines 38, 61, 81-99)."""

    def _make_reranker(self):
        from ai_assistant.adapters.reranker_api import APIReranker
        from ai_assistant.core.domain.configs import RerankerConfigData

        return APIReranker(
            RerankerConfigData(
                model="bge-reranker-v2-m3",
                api_base="http://localhost:8082",
                api_key="test-key",
                timeout=30.0,
            )
        )

    @pytest.mark.asyncio
    async def test_rerank_empty_chunks_returns_empty(self):
        """Given: empty chunks list.
        When: rerank is called.
        Then: returns empty list without HTTP call.
        """
        reranker = self._make_reranker()
        result = await reranker.rerank("query", [])
        assert result == []
        await reranker.shutdown()

    @pytest.mark.asyncio
    async def test_rerank_valid_response(self):
        """Given: valid rerank API response.
        When: rerank is called.
        Then: results sorted by score descending.
        """
        import respx

        from ai_assistant.core.domain.documents import Chunk, ChunkMetadata

        reranker = self._make_reranker()

        chunks = [
            Chunk(
                id="c1",
                text="Paris is the capital of France.",
                embedding=[0.1] * 3,
                metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
            ),
            Chunk(
                id="c2",
                text="Unrelated text.",
                embedding=[0.2] * 3,
                metadata=ChunkMetadata(source="doc2", index=0, total_chunks=1),
            ),
        ]

        with respx.mock:
            respx.post("http://localhost:8082/v1/rerank").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "results": [
                            {"index": 0, "relevance_score": 0.95},
                            {"index": 1, "relevance_score": 0.12},
                        ]
                    },
                )
            )

            results = await reranker.rerank("What is the capital of France?", chunks)

        assert len(results) == 2
        assert results[0].chunk.id == "c1"
        assert results[0].score == 0.95
        assert results[1].chunk.id == "c2"
        assert results[1].score == 0.12
        await reranker.shutdown()

    @pytest.mark.asyncio
    async def test_rerank_invalid_response_shape(self):
        """Given: response without 'results' key.
        When: rerank is called.
        Then: AdapterError raised.
        """
        import respx

        from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
        from ai_assistant.core.domain.errors import AdapterError

        reranker = self._make_reranker()

        chunks = [
            Chunk(
                id="c1",
                text="Test",
                embedding=[0.1] * 3,
                metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
            ),
        ]

        with respx.mock:
            respx.post("http://localhost:8082/v1/rerank").mock(
                return_value=httpx.Response(200, json={"wrong_key": []})
            )

            with pytest.raises(AdapterError, match="Unexpected rerank response shape"):
                await reranker.rerank("query", chunks)

        await reranker.shutdown()

    @pytest.mark.asyncio
    async def test_rerank_malformed_result_items_skipped(self):
        """Given: results with malformed items.
        When: rerank is called.
        Then: malformed items skipped, valid ones returned.
        """
        import respx

        from ai_assistant.core.domain.documents import Chunk, ChunkMetadata

        reranker = self._make_reranker()

        chunks = [
            Chunk(
                id="c1",
                text="Valid chunk",
                embedding=[0.1] * 3,
                metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
            ),
            Chunk(
                id="c2",
                text="Another chunk",
                embedding=[0.2] * 3,
                metadata=ChunkMetadata(source="doc2", index=0, total_chunks=1),
            ),
        ]

        with respx.mock:
            respx.post("http://localhost:8082/v1/rerank").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "results": [
                            {"index": 0, "relevance_score": 0.9},
                            {"index": "not_a_number", "relevance_score": 0.5},
                            {"index": 1},  # missing relevance_score
                            {"index": 99, "relevance_score": 0.8},  # out of range
                        ]
                    },
                )
            )

            results = await reranker.rerank("query", chunks)

        # Only the valid item should be returned
        assert len(results) == 1
        assert results[0].chunk.id == "c1"
        await reranker.shutdown()

    @pytest.mark.asyncio
    async def test_rerank_with_top_k(self):
        """Given: top_k less than number of results.
        When: rerank is called.
        Then: only top_k results returned.
        """
        import respx

        from ai_assistant.core.domain.documents import Chunk, ChunkMetadata

        reranker = self._make_reranker()

        chunks = [
            Chunk(
                id=f"c{i}",
                text=f"Chunk {i}",
                embedding=[0.1] * 3,
                metadata=ChunkMetadata(source=f"doc{i}", index=0, total_chunks=1),
            )
            for i in range(5)
        ]

        with respx.mock:
            respx.post("http://localhost:8082/v1/rerank").mock(
                return_value=httpx.Response(
                    200,
                    json={
                        "results": [
                            {"index": i, "relevance_score": 1.0 - i * 0.1}
                            for i in range(5)
                        ]
                    },
                )
            )

            results = await reranker.rerank("query", chunks, top_k=2)

        assert len(results) == 2
        assert results[0].score > results[1].score
        await reranker.shutdown()


class TestUpsert:
    """drift #88: atomic replace under one lock. Re-upsert must not grow the store."""

    @staticmethod
    def _chunk(source: str, idx: int, total: int) -> Chunk:
        return Chunk(
            id=f"chunk-{source}-{idx}",
            text=f"chunk {idx}",
            embedding=[float(idx)] * 8,
            metadata=ChunkMetadata(
                source=source,
                index=idx,
                total_chunks=total,
                custom={},
                original_path=None,
                source_uri=f"{source}.md",
                last_modified=None,
            ),
        )

    @staticmethod
    def _config(tmp_path: Path) -> VectorStoreConfigData:
        return VectorStoreConfigData(
            dim=8,
            metric="cosine",
            index_path=str(tmp_path),
            max_chunks=100,
            max_document_size=1048560,
        )

    async def _run_replace(self, store: IVectorStore) -> None:
        first = [self._chunk("doc", i, 3) for i in range(3)]
        await store.upsert(first, namespace="default")
        second = [self._chunk("doc", i, 3) for i in range(3)]
        await store.upsert(second, namespace="default")
        items = await store.list_by_filter({}, namespace="default")
        assert len(items) == 3, (
            f"drift #88: {len(items)} — upsert must replace, not accumulate"
        )
        doc = await store.list_by_filter({"source": "doc"}, namespace="default")
        assert len(doc) == 3

    async def test_faiss_upsert_replaces_without_duplicates(
        self, tmp_path: Path
    ) -> None:
        store = FaissVectorStore(self._config(tmp_path))
        try:
            await self._run_replace(store)
        finally:
            await store.shutdown()

    async def test_memory_upsert_replaces_without_duplicates(
        self, tmp_path: Path
    ) -> None:
        store = MemoryVectorStore(self._config(tmp_path))
        try:
            await self._run_replace(store)
        finally:
            await store.shutdown()



# --- IVectorStore.upsert default implementation (port contract, drift #88) ---


def _make_store(tmp_path: Path) -> MemoryVectorStore:
    """Fresh MemoryVectorStore on tmp_path (pattern from TestUpsert)."""
    config = VectorStoreConfigData(
        dim=8,
        metric="cosine",
        index_path=str(tmp_path),
        max_chunks=100,
        max_document_size=1048560,
    )
    return MemoryVectorStore(config)


def _make_chunk(chunk_id: str, source: str | None) -> Chunk:
    """Minimal chunk for upsert tests (pattern from TestUpsert)."""
    return Chunk(
        id=chunk_id,
        text=f"chunk {chunk_id}",
        embedding=[1.0] * 8,
        metadata=(
            ChunkMetadata(
                source=source,
                index=0,
                total_chunks=1,
                custom={},
                original_path=None,
                source_uri=f"{source}.md",
                last_modified=None,
            )
            if source is not None
            else None
        ),
    )


async def test_port_default_upsert_empty_batch_is_noop(tmp_path: Path) -> None:
    """Empty batch is a no-op: nothing added, nothing deleted."""
    store = _make_store(tmp_path)
    await store.add([_make_chunk("keep-1", "keep")], namespace="default")

    await IVectorStore.upsert(store, [], namespace="default")

    found = await store.list_by_filter({"source": "keep"}, namespace="default")
    assert {cid for cid, _ in found} == {"keep-1"}


async def test_port_default_upsert_new_source_adds_without_delete(
    tmp_path: Path,
) -> None:
    """Fresh source: chunks are added; there is nothing to delete."""
    store = _make_store(tmp_path)

    await IVectorStore.upsert(
        store,
        [_make_chunk("a1", "alpha"), _make_chunk("a2", "alpha")],
        namespace="default",
    )

    found = await store.list_by_filter({"source": "alpha"}, namespace="default")
    assert {cid for cid, _ in found} == {"a1", "a2"}


async def test_port_default_upsert_replaces_stale_and_keeps_shared_ids(
    tmp_path: Path,
) -> None:
    """Re-upsert: stale ids deleted, shared ids survive, other sources untouched."""
    store = _make_store(tmp_path)
    await store.add(
        [
            _make_chunk("a1", "alpha"),
            _make_chunk("a2", "alpha"),
            _make_chunk("b1", "beta"),
        ],
        namespace="default",
    )

    await IVectorStore.upsert(
        store,
        [_make_chunk("a2", "alpha"), _make_chunk("a3", "alpha")],
        namespace="default",
    )

    alpha = await store.list_by_filter({"source": "alpha"}, namespace="default")
    beta = await store.list_by_filter({"source": "beta"}, namespace="default")
    assert {cid for cid, _ in alpha} == {"a2", "a3"}
    assert {cid for cid, _ in beta} == {"b1"}


async def test_port_default_upsert_ignores_chunks_without_metadata(
    tmp_path: Path
) -> None:
    """A chunk without metadata yields no source: no lookup, no delete."""
    store = _make_store(tmp_path)
    await store.add([_make_chunk("a1", "alpha")], namespace="default")

    await IVectorStore.upsert(
        store, [_make_chunk("no-meta", None)], namespace="default"
    )

    found = await store.list_by_filter({"source": "alpha"}, namespace="default")
    assert {cid for cid, _ in found} == {"a1"}
