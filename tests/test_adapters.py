"""tests/test_adapters.py — Unit tests for adapter implementations.

Covers: MockLLM, MockEmbedder, MemoryVectorStore, NullReranker,
        SQLiteStorage, SimpleChunker, Factory.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.factory import create_adapter
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.adapters.reranker_null import NullReranker
from ai_assistant.adapters.storage_sqlite import SQLiteStorage
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
from ai_assistant.core.domain.errors import VersionMismatchError
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.ports.reranker import RerankResult

logger = logging.getLogger(__name__)


# ── TestMockLLM ──


class TestMockLLM:
    """Given: MockLLM is available for testing without API keys.
    When: various inputs are provided.
    Then: deterministic echo responses are returned.
    """

    @pytest.mark.asyncio
    async def test_complete_echo(self):
        """Given: a user message.
        When: complete is called.
        Then: echo response with last message text is returned.
        """
        llm = MockLLM(config=LLMConfigData())
        result = await llm.complete([UserMessage(text="hello")])
        assert isinstance(result, AssistantMessage)
        assert result.text == "[MOCK LLM] Echo: hello"

    @pytest.mark.asyncio
    async def test_complete_empty_messages(self):
        """Given: empty message list.
        When: complete is called.
        Then: fallback echo with '...' is returned.
        """
        llm = MockLLM(config=LLMConfigData())
        result = await llm.complete([])
        assert result.text == "[MOCK LLM] Echo: ..."

    @pytest.mark.asyncio
    async def test_stream(self):
        """Given: a user message.
        When: stream is called.
        Then: single chunk with server hint is yielded.
        """
        llm = MockLLM(config=LLMConfigData())
        chunks = [c async for c in llm.stream([UserMessage(text="hi")])]
        assert len(chunks) == 1
        assert "Server is running" in chunks[0]

    def test_get_context_limit_default(self):
        """Given: no context size in config.
        When: get_context_limit is called.
        Then: default 4096 is returned.
        """
        llm = MockLLM(config=LLMConfigData())
        assert llm.get_context_limit() == 4096

    def test_get_context_limit_from_config(self):
        """Given: config with server_context_size.
        When: get_context_limit is called.
        Then: configured value is returned.
        """
        llm = MockLLM(config=LLMConfigData(server_context_size=2048))
        assert llm.get_context_limit() == 2048

    def test_get_context_limit_from_max_tokens(self):
        """Given: config with max_tokens but no server_context_size.
        When: get_context_limit is called.
        Then: max_tokens value is returned.
        """
        llm = MockLLM(config=LLMConfigData(max_tokens=1024, server_context_size=None))
        assert llm.get_context_limit() == 1024

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Given: MockLLM instance.
        When: shutdown is called.
        Then: no error is raised.
        """
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
        """Given: dimension config.
        When: property is accessed.
        Then: correct dimension is returned.
        """
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
        """Given: list of texts.
        When: embed is called.
        Then: correct count of embeddings is returned with proper dimension.
        """
        emb = MockEmbedder(EmbedderConfigData(dim=384))
        result = await emb.embed(texts)
        assert len(result) == expected_count
        if expected_count > 0:
            assert len(result[0]) == 384
            if len(texts) > 1:
                assert result[0] != result[1]

    @pytest.mark.asyncio
    async def test_embed_empty(self):
        """Given: empty text list.
        When: embed is called.
        Then: empty list is returned.
        """
        emb = MockEmbedder(EmbedderConfigData(dim=384))
        result = await emb.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Given: MockEmbedder instance.
        When: shutdown is called.
        Then: no error is raised.
        """
        emb = MockEmbedder(EmbedderConfigData(dim=384))
        await emb.shutdown()


# ── TestMemoryVectorStore ──


class TestMemoryVectorStore:
    """Given: MemoryVectorStore holds chunks in memory.
    When: add, search, save, load operations are performed.
    Then: correct behavior with namespaces, FIFO eviction, and dim checks.
    """

    @pytest.fixture
    def store(self):
        """Given: default 3-dimensional memory store config.
        When: fixture is requested.
        Then: MemoryVectorStore instance is returned.
        """
        return MemoryVectorStore(VectorStoreConfigData(dim=3))

    @pytest.mark.asyncio
    async def test_add_and_search(self, store):
        """Given: chunks with embeddings.
        When: added and searched.
        Then: nearest neighbor is returned.
        """
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
        """Given: chunks in different namespaces.
        When: searched per namespace.
        Then: only namespace-local chunks are returned.
        """
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
    async def test_fifo_eviction(self):
        """Given: store with max_chunks=2.
        When: 3 chunks are added.
        Then: oldest chunk is evicted.
        """
        store = MemoryVectorStore(VectorStoreConfigData(dim=3, max_chunks=2))
        chunks = [
            Chunk(id="c1", text="first", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="second", embedding=[0.0, 1.0, 0.0]),
            Chunk(id="c3", text="third", embedding=[0.0, 0.0, 1.0]),
        ]
        await store.add(chunks, namespace="test")
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert not any(c.id == "c1" for c in results)
        assert any(c.id == "c2" for c in results)
        assert any(c.id == "c3" for c in results)

    @pytest.mark.asyncio
    async def test_save_and_load(self, tmp_path):
        """Given: store with a chunk.
        When: saved to disk and loaded into new store.
        Then: chunk is recoverable.
        """
        store = MemoryVectorStore(VectorStoreConfigData(dim=3))
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="test"
        )
        path = str(tmp_path / "idx")
        await store.save(path, namespace="test")

        store2 = MemoryVectorStore(VectorStoreConfigData(dim=3))
        await store2.load(path, namespace="test")
        results = await store2.search([1.0, 0.0, 0.0], top_k=1, namespace="test")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.asyncio
    async def test_dim_mismatch_raises(self, tmp_path):
        """Given: store saved with dim=3.
        When: loaded into store with dim=5.
        Then: VersionMismatchError is raised.
        """
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
        """Given: chunks with and without embeddings.
        When: added and searched.
        Then: only chunks with embeddings are searchable.
        """
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
    async def test_skips_wrong_dimension(self, store):
        """Given: chunks with wrong and correct dimensions.
        When: added and searched.
        Then: only correctly-dimensioned chunks are searchable.
        """
        await store.add(
            [
                Chunk(id="c1", text="wrong", embedding=[1.0, 0.0]),
                Chunk(id="c2", text="correct", embedding=[1.0, 0.0, 0.0]),
            ],
            namespace="test",
        )
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 1
        assert results[0].id == "c2"

    @pytest.mark.asyncio
    async def test_index_path_from_config(self):
        """Given: config with index_path.
        When: store is created.
        Then: index_path property returns configured value.
        """
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=3, index_path="./custom/indices/memory")
        )
        assert store.index_path == "./custom/indices/memory"

    @pytest.mark.asyncio
    async def test_list_by_filter(self, store):
        """Given: chunk with custom metadata.
        When: list_by_filter is called with matching filter.
        Then: matching chunk ids and metadata are returned.
        """
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
        """Given: chunk in store.
        When: delete is called.
        Then: chunk is no longer searchable.
        """
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="test"
        )
        await store.delete(["c1"], namespace="test")
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_shutdown_clears_namespaces(self):
        """Given: store with data.
        When: shutdown is called.
        Then: namespaces are cleared.
        """
        store = MemoryVectorStore(VectorStoreConfigData(dim=3))
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="test"
        )
        await store.shutdown()
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 0


# ── TestNullReranker ──


class TestNullReranker:
    """Given: NullReranker is a pass-through reranker.
    When: rerank is called.
    Then: all chunks returned with score 1.0, order preserved.
    """

    @pytest.mark.asyncio
    async def test_pass_through(self):
        """Given: list of chunks.
        When: rerank is called.
        Then: all chunks returned with score 1.0 in original order.
        """
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
        """Given: empty chunk list.
        When: rerank is called.
        Then: empty list is returned.
        """
        reranker = NullReranker(RerankerConfigData())
        results = await reranker.rerank("q", [])
        assert results == []

    @pytest.mark.asyncio
    async def test_ignores_top_k(self):
        """Given: chunks and top_k parameter.
        When: rerank is called.
        Then: all chunks returned regardless of top_k.
        """
        reranker = NullReranker(RerankerConfigData())
        chunks = [Chunk(id="c1", text="a"), Chunk(id="c2", text="b")]
        results = await reranker.rerank("q", chunks, top_k=1)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Given: NullReranker instance.
        When: shutdown is called.
        Then: no error is raised.
        """
        reranker = NullReranker(RerankerConfigData())
        await reranker.shutdown()


# ── TestSQLiteStorage ──


class TestSQLiteStorage:
    """Given: SQLiteStorage persists chat history and settings.
    When: CRUD operations are performed.
    Then: data is correctly stored and retrieved.
    """

    @pytest.fixture
    def storage(self, tmp_path):
        """Given: temporary database path.
        When: fixture is requested.
        Then: SQLiteStorage instance is returned.
        """
        return SQLiteStorage(StorageConfigData(db_path=str(tmp_path / "test.db")))

    @pytest.mark.asyncio
    async def test_save_and_get_history(self, storage):
        """Given: a message to save.
        When: saved and history retrieved.
        Then: message is returned with correct role and metadata.
        """
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
        """Given: multiple messages.
        When: history is retrieved with limit.
        Then: correct subset in chronological order is returned.
        """
        await storage.init_db()
        for i in range(5):
            await storage.save_message("conv-1", {"role": "user", "content": f"msg{i}"})
        history = await storage.get_history("conv-1", limit=2)
        assert len(history) == 2
        # DESC LIMIT 2 → msg4,msg3 → reversed → msg3,msg4
        assert history[0]["content"] == "msg3"
        assert history[1]["content"] == "msg4"

    @pytest.mark.asyncio
    async def test_settings_get_set(self, storage):
        """Given: a setting value.
        When: set and then get.
        Then: same value is returned.
        """
        await storage.init_db()
        await storage.set("key1", {"nested": True})
        assert await storage.get("key1") == {"nested": True}

    @pytest.mark.asyncio
    async def test_settings_default(self, storage):
        """Given: missing key.
        When: get with default.
        Then: default value is returned.
        """
        await storage.init_db()
        assert await storage.get("missing", "default") == "default"

    @pytest.mark.asyncio
    async def test_wal_mode(self, storage, tmp_path):
        """Given: initialized database.
        When: PRAGMA journal_mode is queried.
        Then: WAL mode is enabled.
        """
        await storage.init_db()
        with sqlite3.connect(str(tmp_path / "test.db")) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode.lower() == "wal"

    @pytest.mark.asyncio
    async def test_concurrent_reads(self, storage, tmp_path):
        """Given: messages in database.
        When: multiple read operations occur.
        Then: all reads succeed without locking errors.
        """
        await storage.init_db()
        for i in range(3):
            await storage.save_message(
                "conv-1", {"role": "user", "content": f"msg{i}"}
            )

        # Simulate concurrent reads by opening separate connections
        results = []
        for _ in range(3):
            with sqlite3.connect(str(tmp_path / "test.db")) as conn:
                cur = conn.execute(
                    "SELECT content FROM chat_messages WHERE conversation_id = ? ORDER BY id",
                    ("conv-1",),
                )
                rows = [r[0] for r in cur.fetchall()]
                results.append(rows)

        for rows in results:
            assert rows == ["msg0", "msg1", "msg2"]

    @pytest.mark.asyncio
    async def test_db_tables_created(self, storage, tmp_path):
        """Given: fresh database.
        When: init_db is called.
        Then: chat_messages and settings tables exist.
        """
        await storage.init_db()
        with sqlite3.connect(str(tmp_path / "test.db")) as conn:
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
        """Given: SQLiteStorage instance.
        When: shutdown is called.
        Then: no error is raised.
        """
        await storage.shutdown()


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
        """Given: text and chunk parameters.
        When: chunk is called.
        Then: expected number of chunks with correct constraints.
        """
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=size, chunk_overlap=overlap))
        doc = Document(id="d1", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) == expected_count
        if chunks:
            assert all(len(c.text) <= size for c in chunks)
            assert all(c.metadata.total_chunks == len(chunks) for c in chunks)

    @pytest.mark.asyncio
    async def test_empty_text(self):
        """Given: empty document content.
        When: chunk is called.
        Then: empty list is returned.
        """
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=10, chunk_overlap=2))
        doc = Document(id="d1", content="")
        chunks = await chunker.chunk(doc)
        assert chunks == []

    @pytest.mark.asyncio
    async def test_metadata_preservation(self):
        """Given: document with custom metadata.
        When: chunk is called.
        Then: metadata is preserved in chunk metadata.
        """
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=10, chunk_overlap=2))
        doc = Document(id="d1", content="hello world", metadata={"tag": "test"})
        chunks = await chunker.chunk(doc)
        assert chunks[0].metadata.custom == {"tag": "test"}

    @pytest.mark.asyncio
    async def test_invalid_overlap(self):
        """Given: overlap >= chunk_size.
        When: chunker is created.
        Then: ValueError is raised.
        """
        with pytest.raises(ValueError):
            SimpleChunker(ChunkerConfigData(chunk_size=10, chunk_overlap=10))

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Given: SimpleChunker instance.
        When: shutdown is called.
        Then: no error is raised.
        """
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
            ("chunker", "simple", SimpleChunker, ChunkerConfigData(chunk_size=10, chunk_overlap=2)),
            ("storage", "sqlite", SQLiteStorage, StorageConfigData(db_path=":memory:")),
            ("reranker", "null", NullReranker, RerankerConfigData()),
        ],
    )
    def test_create_adapter(self, port, name, expected_cls, config):
        """Given: valid port and name.
        When: create_adapter is called.
        Then: correct adapter instance is returned.
        """
        adapter = create_adapter(port, name, config)
        assert isinstance(adapter, expected_cls)

    def test_unknown_llm_raises(self):
        """Given: unknown LLM name.
        When: create_adapter is called.
        Then: ValueError is raised.
        """
        with pytest.raises(ValueError, match="No LLM adapter registered"):
            create_adapter("llm", "unknown", LLMConfigData())

    def test_unknown_embedder_raises(self):
        """Given: unknown embedder name.
        When: create_adapter is called.
        Then: ValueError is raised.
        """
        with pytest.raises(ValueError, match="No embedder adapter registered"):
            create_adapter("embedder", "unknown", EmbedderConfigData())

    def test_unknown_vector_store_raises(self):
        """Given: unknown vector_store name.
        When: create_adapter is called.
        Then: ValueError is raised.
        """
        with pytest.raises(ValueError, match="No vector_store adapter registered"):
            create_adapter("vector_store", "unknown", VectorStoreConfigData())

    def test_unknown_chunker_raises(self):
        """Given: unknown chunker name.
        When: create_adapter is called.
        Then: ValueError is raised.
        """
        with pytest.raises(ValueError, match="No chunker adapter registered"):
            create_adapter("chunker", "unknown", ChunkerConfigData())

    def test_unknown_storage_raises(self):
        """Given: unknown storage name.
        When: create_adapter is called.
        Then: ValueError is raised.
        """
        with pytest.raises(ValueError, match="No storage adapter registered"):
            create_adapter("storage", "unknown", StorageConfigData())

    def test_unknown_reranker_raises(self):
        """Given: unknown reranker name.
        When: create_adapter is called.
        Then: ValueError is raised.
        """
        with pytest.raises(ValueError, match="No reranker adapter registered"):
            create_adapter("reranker", "unknown", RerankerConfigData())

    def test_unknown_port_raises(self):
        """Given: unknown port name.
        When: create_adapter is called.
        Then: ValueError is raised."""
        with pytest.raises(ValueError, match="Unknown adapter port"):
            create_adapter("unknown_port", "whatever", RerankerConfigData())
