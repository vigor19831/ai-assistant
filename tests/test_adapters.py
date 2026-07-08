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

import httpx
import pytest

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.embedder_openai_compatible import OpenAICompatibleEmbedder
from ai_assistant.adapters.factory import create_adapter
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
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
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.reranker import RerankResult

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
    def store(self):
        return MemoryVectorStore(VectorStoreConfigData(dim=3))

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
    async def test_fifo_eviction(self):
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
    async def test_skips_wrong_dimension(self, store):
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
            await storage.save_message(
                "conv-1", {"role": "user", "content": f"msg{i}"}
            )

        results = []
        for _ in range(3):
            with closing(sqlite3.connect(str(tmp_path / "test.db"))) as conn:
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
    async def test_implements_ichatstorage_and_initializable(self, storage):
        from ai_assistant.core.ports.initializable import IInitializable
        from ai_assistant.core.ports.storage import IChatStorage

        assert isinstance(storage, IChatStorage)
        assert isinstance(storage, IInitializable)


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
        assert type(adapter).__name__.startswith("OpenAICompatible")

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
                stop_sequences=["", "end", "stop", ""],
            )
        )

    @pytest.mark.asyncio
    async def test_complete_sends_stop_sequences_filtered(self, llm):
        """Empty strings in stop_sequences must be filtered out of payload."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
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
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
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
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
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

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response
        ):
            with pytest.raises(AdapterError, match="Unexpected response shape"):
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
            chunks = [c async for c in llm.stream([UserMessage(text="hi")])]

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
        """Server returning fewer embeddings than input texts must raise AdapterError."""
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {"data": [{"embedding": [0.1] * 384}]}
        mock_resp.raise_for_status = MagicMock()
        mock_resp.text = "ok"

        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp
        ):
            with pytest.raises(AdapterError, match="count mismatch"):
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
    faiss = pytest.importorskip("faiss")
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
    vectors = np.array(
        [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]], dtype=np.float32
    )
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

    config = VectorStoreConfigData(
        dim=3, metric="cosine", index_path=str(tmp_path)
    )
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
        import faiss

        chunks = [
            Chunk(id="c1", text="keep", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="delete", embedding=[0.0, 1.0, 0.0]),
        ]
        await faiss_store.add(chunks, namespace="test")
        await faiss_store.save(str(tmp_path), namespace="test")

        await faiss_store.delete(["c2"], namespace="test")

        results = await faiss_store.search(
            [0.0, 1.0, 0.0], top_k=5, namespace="test"
        )
        assert not any(r.id == "c2" for r in results)
        assert any(r.id == "c1" for r in results)

        await faiss_store.save(str(tmp_path), namespace="test")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
        store2 = FaissVectorStore(
            VectorStoreConfigData(dim=3, index_path=str(tmp_path))
        )
        await store2.load(str(tmp_path), namespace="test")
        results2 = await store2.search(
            [0.0, 1.0, 0.0], top_k=5, namespace="test"
        )
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

        with patch("faiss.write_index", side_effect=OSError("disk full")):
            with pytest.raises(OSError, match="disk full"):
                await faiss_store.delete(["c2"], namespace="test")

        results = await faiss_store.search(
            [0.0, 1.0, 0.0], top_k=5, namespace="test"
        )
        assert any(r.id == "c2" for r in results)
        assert any(r.id == "c1" for r in results)

    @pytest.mark.asyncio
    async def test_save_cleans_up_temp_on_write_failure(self, faiss_store, tmp_path):
        """If faiss.write_index fails during save(), temp file must be cleaned up."""
        from unittest.mock import patch

        chunks = [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])]
        await faiss_store.add(chunks, namespace="test")

        with patch("faiss.write_index", side_effect=OSError("simulated write failure")):
            with pytest.raises(OSError, match="simulated write failure"):
                await faiss_store.save(str(tmp_path), namespace="test")

        temp_files = list(tmp_path.glob("*.tmp"))
        assert not temp_files, f"Temp files left behind after failure: {temp_files}"

    @pytest.mark.asyncio
    async def test_save_cleans_up_temp_on_replace_failure(self, faiss_store, tmp_path):
        """If os.replace fails during save(), temp file must be cleaned up."""
        from unittest.mock import patch

        chunks = [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])]
        await faiss_store.add(chunks, namespace="test")

        with patch("os.replace", side_effect=OSError("replace failed")):
            with pytest.raises(OSError, match="replace failed"):
                await faiss_store.save(str(tmp_path), namespace="test")

        temp_files = list(tmp_path.glob("*.tmp"))
        assert not temp_files, f"Temp files left behind after replace failure: {temp_files}"

    @pytest.mark.asyncio
    async def test_save_no_temp_files_left(self, faiss_store, tmp_path):
        """After save(), no .tmp files or temp directories should remain."""
        import faiss

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
        import faiss

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

        results = await faiss_store.search(
            [1.0, 0.0, 0.0], top_k=20, namespace="test"
        )
        assert len(results) == 8

    @pytest.mark.asyncio
    async def test_cosine_zero_vector_no_nan(self, tmp_path):
        """Zero-length embeddings in cosine metric must not produce NaN."""
        pytest.importorskip("faiss")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        store = FaissVectorStore(
            VectorStoreConfigData(
                dim=3, index_path=str(tmp_path), metric="cosine"
            )
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
        results = await faiss_store.search(
            [1.0, 0.0, 0.0], top_k=5, namespace="test"
        )
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_add_empty_chunks_noop(self, faiss_store):
        """add() with empty list must be a no-op."""
        await faiss_store.add([], namespace="test")
        results = await faiss_store.search(
            [1.0, 0.0, 0.0], top_k=5, namespace="test"
        )
        assert results == []
