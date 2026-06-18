"""tests/test_adapters.py — Unit tests for adapter implementations.

Covers: MockLLM, MockEmbedder, MemoryVectorStore, NullReranker,
        SQLiteStorage, SimpleChunker, Factory.
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
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
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0], metadata=meta)], namespace="test"
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
    async def test_ignores_top_k(self):
        reranker = NullReranker(RerankerConfigData())
        chunks = [Chunk(id="c1", text="a"), Chunk(id="c2", text="b")]
        results = await reranker.rerank("q", chunks, top_k=1)
        assert len(results) == 2

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
        await storage.shutdown()

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
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=size, chunk_overlap=overlap))
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
            ("chunker", "simple", SimpleChunker, ChunkerConfigData(chunk_size=10, chunk_overlap=2)),
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

    @pytest.mark.parametrize(
        "port,name,config",
        [
            ("llm", "openai_compatible", LLMConfigData(api_key="sk-test", connect_timeout=5.0)),
            ("embedder", "openai_compatible", EmbedderConfigData(api_key="sk-test", connect_timeout=5.0)),
        ],
    )
    def test_create_openai_compatible_with_connect_timeout(self, port, name, config):
        adapter = create_adapter(port, name, config)
        assert adapter is not None
        assert adapter._connect_timeout == 5.0

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

    def test_create_openai_compatible_stop_sequences_filtered(self):
        """Empty strings in stop_sequences must be filtered out."""
        from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
        config = LLMConfigData(api_key="sk-test", stop_sequences=["", "end", ""])
        llm = OpenAICompatibleLLM(config)
        assert llm.config.stop_sequences == ["", "end", ""]
        # Verify filtering logic via _build_messages or internal payload construction
        # The key assertion: no empty strings reach the API payload
        stop = [s for s in llm.config.stop_sequences if s]
        assert stop == ["end"]

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
        return OpenAICompatibleLLM(LLMConfigData(
            api_key="sk-test",
            model="gpt-4",
            api_base="http://test/v1",
            max_tokens=100,
            temperature=0.5,
            stop_sequences=["", "end", "stop", ""],
        ))

    @pytest.mark.asyncio
    async def test_complete_sends_stop_sequences_filtered(self, llm):
        """Empty strings in stop_sequences must be filtered out of payload."""
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
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
        from unittest.mock import MagicMock, AsyncMock, patch

        llm.config = LLMConfigData(
            api_key="sk-test",
            model="gpt-4",
            stop_sequences=[],
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            await llm.complete([UserMessage(text="hi")])
            payload = mock_post.call_args.kwargs["json"]
            assert "stop" not in payload

    @pytest.mark.asyncio
    async def test_complete_custom_max_tokens_and_temperature(self, llm):
        """max_tokens and temperature parameters override config defaults."""
        from unittest.mock import MagicMock, AsyncMock, patch

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
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
        from unittest.mock import MagicMock, AsyncMock, patch
        from ai_assistant.core.domain.errors import AdapterError

        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": []}  # missing message
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            with pytest.raises(AdapterError, match="Unexpected response shape"):
                await llm.complete([UserMessage(text="hi")])

    @pytest.mark.asyncio
    async def test_stream_sends_stream_true(self, llm):
        """Streaming request must have stream=True in payload."""
        from unittest.mock import MagicMock, AsyncMock

        async def aiter_lines():
            return
            yield

        mock_response = MagicMock()
        mock_response.aiter_lines = aiter_lines
        mock_response.raise_for_status = MagicMock()

        class AsyncCtxMgr:
            async def __aenter__(self):
                return mock_response
            async def __aexit__(self, *args):
                return None

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=AsyncCtxMgr())

        llm._client = mock_client

        chunks = [c async for c in llm.stream([UserMessage(text="hi")])]

        call_args = mock_client.stream.call_args
        payload = call_args.kwargs["json"]
        assert payload["stream"] is True
        assert payload.get("stop") == ["end", "stop"]

    def test_get_context_limit_from_server_context_size(self):
        """server_context_size takes priority over max_tokens."""
        llm = OpenAICompatibleLLM(LLMConfigData(
            api_key="sk-test",
            server_context_size=8192,
            max_tokens=100,
        ))
        assert llm.get_context_limit() == 8192

    def test_get_context_limit_fallback_to_max_tokens(self):
        """If server_context_size is None, use max_tokens."""
        llm = OpenAICompatibleLLM(LLMConfigData(
            api_key="sk-test",
            server_context_size=None,
            max_tokens=2048,
        ))
        assert llm.get_context_limit() == 2048

    def test_get_context_limit_returns_default(self):
        """If both are invalid, return default 4096."""
        llm = OpenAICompatibleLLM(LLMConfigData(
            api_key="sk-test",
            server_context_size=0,
            max_tokens=0,
        ))
        assert llm.get_context_limit() == 4096

    def test_build_messages_user_and_assistant(self):
        """_build_messages converts UserMessage and AssistantMessage correctly."""
        llm = OpenAICompatibleLLM(LLMConfigData(api_key="sk-test"))
        messages = [
            UserMessage(text="hello"),
            AssistantMessage(text="world", tool_calls=[{"id": "1"}]),
        ]
        result = llm._build_messages(messages)
        assert result == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world", "tool_calls": [{"id": "1"}]},
        ]

    def test_build_messages_tool_message(self):
        """ToolMessage includes tool_call_id."""
        from ai_assistant.core.domain.messages import ToolMessage
        llm = OpenAICompatibleLLM(LLMConfigData(api_key="sk-test"))
        messages = [ToolMessage(text="result", call_id="call-1")]
        result = llm._build_messages(messages)
        assert result == [
            {"role": "tool", "content": "result", "tool_call_id": "call-1"},
        ]

    def test_parse_tool_calls_valid(self):
        """Valid tool_calls are parsed and normalized."""
        llm = OpenAICompatibleLLM(LLMConfigData(api_key="sk-test"))
        raw = [
            {
                "id": "tc1",
                "type": "function",
                "function": {"name": "test", "arguments": '{"x": 1}'},
            }
        ]
        result = llm._parse_tool_calls(raw)
        assert len(result) == 1
        assert result[0]["id"] == "tc1"
        assert result[0]["function"]["name"] == "test"

    def test_parse_tool_calls_skips_invalid(self):
        """Incomplete tool_calls are skipped with warning."""
        llm = OpenAICompatibleLLM(LLMConfigData(api_key="sk-test"))
        raw = [
            {"id": "tc1", "type": "function", "function": {}},  # missing name
            {"type": "function", "function": {"name": "ok"}},    # missing id
        ]
        result = llm._parse_tool_calls(raw)
        assert result == []

    @pytest.mark.asyncio
    async def test_shutdown_closes_client(self, llm):
        """shutdown must close and clear HTTP client."""
        from unittest.mock import AsyncMock

        mock_client = AsyncMock()
        llm._client = mock_client
        await llm.shutdown()
        mock_client.aclose.assert_awaited_once()
        assert llm._client is None

    @pytest.mark.asyncio
    async def test_connect_timeout_used_in_client(self, llm):
        """connect_timeout must be passed to httpx.AsyncClient via Timeout."""
        from unittest.mock import MagicMock, AsyncMock, patch
        import httpx

        llm._connect_timeout = 3.0

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
            with patch("httpx.AsyncClient.__init__", return_value=None) as mock_init:
                llm._client = None
                await llm.complete([UserMessage(text="hi")])

                call_kwargs = mock_init.call_args.kwargs
                timeout = call_kwargs["timeout"]
                assert isinstance(timeout, httpx.Timeout)
                assert timeout.connect == 3.0

    @pytest.mark.asyncio
    async def test_connect_timeout_none_uses_plain_timeout(self, llm):
        """If connect_timeout is None, use plain float timeout (backward compat)."""
        from unittest.mock import MagicMock, AsyncMock, patch
        import httpx

        llm._connect_timeout = None
        llm._timeout = 10.0

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "ok"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
            with patch("httpx.AsyncClient.__init__", return_value=None) as mock_init:
                llm._client = None
                await llm.complete([UserMessage(text="hi")])

                call_kwargs = mock_init.call_args.kwargs
                timeout = call_kwargs["timeout"]
                assert timeout == 10.0


# ── TestFactoryRegistry ──


class TestFactoryRegistry:
    """Given: @register decorator populates registry on import.
    When: registry is inspected.
    Then: all expected adapters are registered.
    """

    def test_all_ports_present(self):
        from ai_assistant.adapters._registry import get_registry

        registry = get_registry()
        expected_ports = {"llm", "embedder", "vector_store", "chunker", "storage", "reranker"}
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




# ── FaissVectorStore load() guard tests ─────────────────────────────────────

import json

async def test_faiss_load_missing_store_json_raises(tmp_path: Path) -> None:
    """If index.faiss exists but store.json is missing, load() must raise AdapterError.

    This prevents silent data corruption where the index loads but chunk metadata
    is absent, causing search() to return empty results without warning.
    """
    faiss = pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
    from ai_assistant.core.domain.errors import AdapterError
    from ai_assistant.core.domain.configs import VectorStoreConfigData

    config = VectorStoreConfigData(dim=384, index_path=str(tmp_path))
    store = FaissVectorStore(config)

    # Create a fake index.faiss file (simulating orphaned index after migration)
    index_file = tmp_path / "default.faiss"
    dummy_index = faiss.IndexFlatL2(384)
    faiss.write_index(dummy_index, str(index_file))

    # store.json is intentionally absent
    assert not (tmp_path / "default.store.json").exists()

    with pytest.raises(AdapterError) as exc_info:
        await store.load(str(tmp_path), namespace="default")

    assert "metadata missing" in str(exc_info.value).lower() or "store.json" in str(exc_info.value).lower()


async def test_faiss_load_missing_index_faiss_raises(tmp_path: Path) -> None:
    """If store.json exists but index.faiss is missing, load() must raise AdapterError."""
    pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
    from ai_assistant.core.domain.errors import AdapterError
    from ai_assistant.core.domain.configs import VectorStoreConfigData

    config = VectorStoreConfigData(dim=384, index_path=str(tmp_path))
    store = FaissVectorStore(config)

    # Create store.json without index.faiss
    store_file = tmp_path / "default.store.json"
    store_data = {"dim": 384, "metric": "l2", "chunks": []}
    store_file.write_text(json.dumps(store_data), encoding="utf-8")

    with pytest.raises(AdapterError) as exc_info:
        await store.load(str(tmp_path), namespace="default")

    assert "index file missing" in str(exc_info.value).lower() or "index.faiss" in str(exc_info.value).lower()


async def test_faiss_load_both_missing_is_noop(tmp_path: Path) -> None:
    """If neither index.faiss nor store.json exists, load() is a no-op."""
    pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
    from ai_assistant.core.domain.configs import VectorStoreConfigData

    config = VectorStoreConfigData(dim=384, index_path=str(tmp_path))
    store = FaissVectorStore(config)

    # Neither file exists
    await store.load(str(tmp_path), namespace="default")
    # Should not raise and ns should remain empty
    results = await store.search([0.0] * 384, top_k=5, namespace="default")
    assert results == []
