"""Consolidated adapter tests — all implementations, parametrized.

Covers: chunker, embedder (2 types), LLM (2 types), vector store (2 types),
        reranker (2 types), storage, memory, tools, transport.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import Response

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.embedder_openai_compatible import OpenAICompatibleEmbedder
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
from ai_assistant.adapters.memory_sqlite import SQLiteMemory
from ai_assistant.adapters.reranker_api import APIReranker
from ai_assistant.adapters.reranker_dummy import DummyReranker
from ai_assistant.adapters.storage_sqlite import SQLiteStorage
from ai_assistant.adapters.tools_calculator import CalculatorTool
from ai_assistant.adapters.transport_fastapi import FastAPITransport
from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.config import EmbedderConfig, LLMConfig
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.domain.errors import VersionMismatchError
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.ports.memory import MemoryEntry

# ── Chunker ──


class TestChunker:
    @pytest.mark.parametrize(
        "size,overlap,text,expected_count",
        [
            (10, 2, "hello world this is a test", 4),
            (100, 10, "short", 1),
            (50, 5, "", 0),
            (5, 1, "1234567890", 3),  # 10 chars, step=4, chunks at 0,4,8
        ],
    )
    @pytest.mark.asyncio
    async def test_chunk_variations(self, size, overlap, text, expected_count):
        config = type("C", (), {"chunk_size": size, "chunk_overlap": overlap})()
        chunker = SimpleChunker(config)
        doc = Document(id="d1", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) == expected_count
        if chunks:
            assert all(len(c.text) <= size for c in chunks)
            # Verify total_chunks is accurate
            assert all(c.metadata.total_chunks == len(chunks) for c in chunks)

    @pytest.mark.asyncio
    async def test_chunk_preserves_metadata(self):
        config = type("C", (), {"chunk_size": 10, "chunk_overlap": 2})()
        chunker = SimpleChunker(config)
        doc = Document(id="d1", content="hello world", metadata={"tag": "test"})
        chunks = await chunker.chunk(doc)
        assert chunks[0].metadata.custom == {"tag": "test"}


# ── Embedders (parametrized) ──


class TestEmbedders:
    @pytest.mark.parametrize("dim", [128, 384, 768, 1536])
    def test_mock_dimension(self, dim):
        config = type("C", (), {"dim": dim})()
        emb = MockEmbedder(config)
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
    async def test_mock_embed(self, texts, expected_count):
        config = type("C", (), {"dim": 384})()
        emb = MockEmbedder(config)
        result = await emb.embed(texts)
        assert len(result) == expected_count
        if expected_count > 0:
            assert len(result[0]) == 384
            # Deterministic: same text = same embedding
            if len(texts) > 1:
                assert result[0] != result[1]

    @pytest.mark.asyncio
    async def test_openai_compatible_embed(self):
        config = EmbedderConfig(
            provider="openai_compatible",
            api_base="https://api.test.com/v1",
            api_key="test-key",
            dim=1536,
            timeout=5.0,
        )
        embedder = OpenAICompatibleEmbedder(config)

        with respx.mock:
            route = respx.post("https://api.test.com/v1/embeddings")
            route.return_value = Response(
                200,
                json={
                    "data": [{"embedding": [0.1] * 1536}, {"embedding": [0.2] * 1536}]
                },
            )
            result = await embedder.embed(["a", "b"])
            assert len(result) == 2
            assert len(result[0]) == 1536
            assert result[0] != result[1]

    @pytest.mark.asyncio
    async def test_openai_compatible_empty(self):
        config = EmbedderConfig(
            provider="openai_compatible",
            api_base="https://api.test.com/v1",
            api_key="key",
            dim=1536,
            timeout=5.0,
        )
        assert await OpenAICompatibleEmbedder(config).embed([]) == []


# ── LLMs (parametrized) ──


class TestLLMs:
    @pytest.mark.asyncio
    async def test_mock_complete(self):
        llm = MockLLM(config={})
        result = await llm.complete([UserMessage(text="hello")])
        assert isinstance(result, AssistantMessage)
        assert "[MOCK LLM] Echo: hello" == result.text

    @pytest.mark.asyncio
    async def test_mock_complete_empty(self):
        llm = MockLLM(config={})
        result = await llm.complete([])
        assert "[MOCK LLM] Echo: ..." == result.text

    @pytest.mark.asyncio
    async def test_mock_stream(self):
        llm = MockLLM(config={})
        chunks = [c async for c in llm.stream([UserMessage(text="hi")])]
        assert len(chunks) == 1
        assert "Server is running" in chunks[0]

    @pytest.mark.asyncio
    async def test_openai_compatible_complete(self):
        config = LLMConfig(
            provider="openai_compatible",
            api_base="https://api.test.com/v1",
            api_key="key",
            max_tokens=10,
            temperature=0.7,
            timeout=5.0,
            stop_sequences=[],
        )
        llm = OpenAICompatibleLLM(config)

        with respx.mock:
            route = respx.post("https://api.test.com/v1/chat/completions")
            route.return_value = Response(
                200, json={"choices": [{"message": {"content": "Hello there"}}]}
            )
            result = await llm.complete([UserMessage(text="hi")])
            assert result.text == "Hello there"

    @pytest.mark.asyncio
    async def test_openai_compatible_stream(self):
        config = LLMConfig(
            provider="openai_compatible",
            api_base="https://api.test.com/v1",
            api_key="key",
            max_tokens=10,
            temperature=0.7,
            timeout=5.0,
            stop_sequences=[],
        )
        llm = OpenAICompatibleLLM(config)

        with respx.mock:
            sse = (
                'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":" world"}}]}\n\n'
                "data: [DONE]\n\n"
            )
            respx.post(
                "https://api.test.com/v1/chat/completions"
            ).return_value = Response(
                200, text=sse, headers={"content-type": "text/event-stream"}
            )
            chunks = [c async for c in llm.stream([UserMessage(text="hi")])]
            assert chunks == ["Hello", " world"]


# ── Vector Stores (parametrized) ──


class TestVectorStores:
    @pytest.mark.parametrize(
        "store_cls,config",
        [
            (FaissVectorStore, type("C", (), {"dim": 3, "metric": "l2"})()),
            (MemoryVectorStore, type("C", (), {"dim": 3})()),
        ],
    )
    @pytest.mark.asyncio
    async def test_add_and_search(self, store_cls, config):
        store = store_cls(config)
        chunks = [
            Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0]),
        ]
        await store.add(chunks, namespace="test")
        results = await store.search([1.0, 0.0, 0.0], top_k=1, namespace="test")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.parametrize(
        "store_cls,config",
        [
            (FaissVectorStore, type("C", (), {"dim": 3, "metric": "l2"})()),
            (MemoryVectorStore, type("C", (), {"dim": 3})()),
        ],
    )
    @pytest.mark.asyncio
    async def test_namespace_isolation(self, store_cls, config):
        store = store_cls(config)
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

        # Cross-namespace: c1 not in ns2
        r3 = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="ns2")
        assert not any(c.id == "c1" for c in r3)

    @pytest.mark.asyncio
    async def test_faiss_list_by_filter(self):
        store = FaissVectorStore(type("C", (), {"dim": 3, "metric": "l2"})())
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
    async def test_faiss_save_and_load(self, tmp_path):
        store = FaissVectorStore(type("C", (), {"dim": 3, "metric": "l2"})())
        await store.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="test"
        )
        path = str(tmp_path / "idx")
        await store.save(path, namespace="test")

        store2 = FaissVectorStore(type("C", (), {"dim": 3, "metric": "l2"})())
        await store2.load(path, namespace="test")
        results = await store2.search([1.0, 0.0, 0.0], top_k=1, namespace="test")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_faiss_version_mismatch(self, tmp_path):
        store3 = FaissVectorStore(
            type("C", (), {"dim": 3, "metric": "l2", "embedder_model": "test"})()
        )
        await store3.add(
            [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])], namespace="test"
        )
        path = str(tmp_path / "idx")
        await store3.save(path, namespace="test")

        store5 = FaissVectorStore(
            type("C", (), {"dim": 5, "metric": "l2", "embedder_model": "test"})()
        )
        with pytest.raises(VersionMismatchError, match="Reindex required"):
            await store5.load(path, namespace="test")

    @pytest.mark.asyncio
    async def test_memory_threshold_filtering(self):
        """Memory store: low similarity → empty results."""
        store = MemoryVectorStore(type("C", (), {"dim": 3})())
        await store.add(
            [Chunk(id="c1", text="a", embedding=[0.0, 1.0, 0.0])], namespace="test"
        )
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert results == []  # Orthogonal vectors, similarity ~0

    @pytest.mark.asyncio
    async def test_memory_high_similarity(self):
        """Memory store: high similarity → results."""
        store = MemoryVectorStore(type("C", (), {"dim": 3})())
        await store.add(
            [Chunk(id="c1", text="a", embedding=[0.99, 0.01, 0.0])], namespace="test"
        )
        results = await store.search([1.0, 0.0, 0.0], top_k=5, namespace="test")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.asyncio
    async def test_memory_skips_no_embedding(self):
        store = MemoryVectorStore(type("C", (), {"dim": 3})())
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
    async def test_memory_skips_wrong_dimension(self):
        store = MemoryVectorStore(type("C", (), {"dim": 3})())
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


# ── Rerankers ──


class TestRerankers:
    @pytest.mark.asyncio
    async def test_dummy_pass_through(self):
        reranker = DummyReranker(config={})
        chunks = [Chunk(id="c1", text="hello"), Chunk(id="c2", text="world")]
        results = await reranker.rerank("query", chunks)
        assert len(results) == 2
        assert all(r.score == 1.0 for r in results)
        assert results[0].chunk.id == "c1"

    @pytest.mark.asyncio
    async def test_dummy_top_k(self):
        reranker = DummyReranker(config={})
        chunks = [Chunk(id=f"c{i}", text=f"t{i}") for i in range(10)]
        results = await reranker.rerank("q", chunks, top_k=3)
        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_dummy_empty(self):
        assert await DummyReranker(config={}).rerank("q", []) == []

    @pytest.mark.asyncio
    async def test_api_rerank_success(self):
        config = MagicMock()
        config.api_base = "https://api.cohere.com"
        config.api_key = "test-key"
        config.model = "rerank-multilingual-v3.0"
        config.timeout = 5.0
        config.threshold = 0.3

        reranker = APIReranker(config)
        chunks = [Chunk(id="c1", text="hello"), Chunk(id="c2", text="world")]

        with respx.mock:
            respx.post("https://api.cohere.com/v1/rerank").return_value = Response(
                200,
                json={
                    "results": [
                        {"index": 0, "relevance_score": 0.9},
                        {"index": 1, "relevance_score": 0.1},
                    ]
                },
            )
            results = await reranker.rerank("q", chunks, top_k=5)
            assert len(results) == 1
            assert results[0].chunk.id == "c1"
            assert results[0].score == 0.9

    @pytest.mark.asyncio
    async def test_api_rerank_respects_top_k(self):
        config = MagicMock()
        config.api_base = "https://api.cohere.com"
        config.api_key = "key"
        config.model = "model"
        config.timeout = 5.0
        config.threshold = 0.3

        reranker = APIReranker(config)
        chunks = [Chunk(id=f"c{i}", text=f"t{i}") for i in range(5)]

        with respx.mock:
            respx.post("https://api.cohere.com/v1/rerank").return_value = Response(
                200,
                json={
                    "results": [
                        {"index": i, "relevance_score": 0.9 - i * 0.1} for i in range(5)
                    ]
                },
            )
            results = await reranker.rerank("q", chunks, top_k=2)
            assert len(results) == 2
            assert results[0].score == 0.9
            assert results[1].score == 0.8

    @pytest.mark.asyncio
    async def test_api_rerank_empty_chunks(self):
        config = MagicMock()
        config.api_base = "https://api.cohere.com"
        config.api_key = "key"
        config.model = "model"
        config.timeout = 5.0
        config.threshold = 0.3
        assert await APIReranker(config).rerank("q", []) == []

    @pytest.mark.asyncio
    async def test_api_rerank_error_propagates(self):
        config = MagicMock()
        config.api_base = "https://api.cohere.com"
        config.api_key = "key"
        config.model = "model"
        config.timeout = 5.0
        config.threshold = 0.3

        with respx.mock:
            respx.post("https://api.cohere.com/v1/rerank").return_value = Response(500)
            with pytest.raises(Exception):
                await APIReranker(config).rerank("q", [Chunk(id="c1", text="hello")])


# ── Storage ──


class TestStorage:
    @pytest.fixture
    def storage(self, tmp_path):
        config = type("C", (), {"db_path": str(tmp_path / "test.db")})()
        return SQLiteStorage(config)

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
    async def test_history_limit_and_order(self, storage):
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
        await storage.init_db()
        await storage.set("key1", {"nested": True})
        assert await storage.get("key1") == {"nested": True}

    @pytest.mark.asyncio
    async def test_settings_default(self, storage):
        await storage.init_db()
        assert await storage.get("missing", "default") == "default"

    @pytest.mark.asyncio
    async def test_db_tables_created(self, storage, tmp_path):
        await storage.init_db()
        import sqlite3

        with sqlite3.connect(str(tmp_path / "test.db")) as conn:
            tables = {
                t[0]
                for t in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "chat_messages" in tables
            assert "settings" in tables


# ── Memory (Long-term) ──


class TestMemory:
    @pytest.fixture
    def memory(self, tmp_path):
        config = type("C", (), {"db_path": str(tmp_path / "memory.db")})()
        return SQLiteMemory(config)

    @pytest.mark.asyncio
    async def test_add_and_get(self, memory):
        await memory.init_db()
        entry = MemoryEntry(
            content="User likes Python",
            source="conversation",
            importance=0.8,
            tags=["pref"],
        )
        await memory.add("user-1", entry)
        results = await memory.get("user-1")
        assert len(results) == 1
        assert results[0].content == "User likes Python"
        assert results[0].tags == ["pref"]

    @pytest.mark.asyncio
    async def test_search_by_query(self, memory):
        await memory.init_db()
        await memory.add(
            "user-1", MemoryEntry(content="Loves hiking", source="explicit")
        )
        await memory.add("user-1", MemoryEntry(content="Hates rain", source="explicit"))
        results = await memory.get("user-1", query="hiking")
        assert len(results) == 1
        assert "hiking" in results[0].content

    @pytest.mark.asyncio
    async def test_forget(self, memory):
        await memory.init_db()
        entry = MemoryEntry(content="To be deleted", source="test")
        await memory.add("user-1", entry)
        results = await memory.get("user-1")
        success = await memory.forget("user-1", results[0].id)
        assert success is True
        assert len(await memory.get("user-1")) == 0

    @pytest.mark.asyncio
    async def test_consolidate_removes_old_low_importance(self, memory):
        await memory.init_db()
        import sqlite3

        # Add old low-importance memory
        with sqlite3.connect(memory.db_path) as conn:
            conn.execute(
                """
                INSERT INTO memories (user_id, content, source, importance, created_at)
                VALUES (?, ?, ?, ?, datetime('now', '-31 days'))
            """,
                ("user-1", "old", "test", 0.1),
            )
            conn.commit()
        await memory.consolidate("user-1")
        results = await memory.get("user-1")
        assert len(results) == 0


# ── Tools ──


class TestCalculator:
    @pytest.fixture
    def calc(self):
        return CalculatorTool()

    @pytest.mark.parametrize(
        "op,a,b,expected",
        [
            ("add", 2, 3, 5.0),
            ("subtract", 5, 3, 2.0),
            ("multiply", 4, 3, 12.0),
            ("divide", 10, 2, 5.0),
        ],
    )
    @pytest.mark.asyncio
    async def test_operations(self, calc, op, a, b, expected):
        result = await calc.execute("call-1", {"operation": op, "a": a, "b": b})
        assert result.is_error is False
        assert str(expected) in result.output

    @pytest.mark.asyncio
    async def test_divide_by_zero(self, calc):
        result = await calc.execute("call-2", {"operation": "divide", "a": 10, "b": 0})
        assert result.is_error is True
        assert "zero" in result.error.lower()

    @pytest.mark.asyncio
    async def test_unknown_operation(self, calc):
        result = await calc.execute("call-3", {"operation": "power", "a": 2, "b": 3})
        assert result.is_error is True
        assert "Unknown" in result.error

    def test_spec(self, calc):
        spec = calc.spec
        assert spec.name == "calculator"
        assert "add" in spec.parameters["properties"]["operation"]["enum"]


# ── Transport ──


class TestTransport:
    @pytest.mark.asyncio
    async def test_fastapi_start(self):
        transport = FastAPITransport(config=MagicMock(host="127.0.0.1", port=9000))
        with patch("uvicorn.Config") as mock_cfg:
            with patch("uvicorn.Server") as mock_srv:
                mock_srv.return_value.serve = AsyncMock()
                await transport.start()
                mock_cfg.assert_called_once()
                assert mock_cfg.call_args.kwargs["host"] == "127.0.0.1"
                assert mock_cfg.call_args.kwargs["port"] == 9000

    @pytest.mark.asyncio
    async def test_fastapi_stop_is_noop(self):
        transport = FastAPITransport(config=MagicMock())
        await transport.stop()  # should not raise
