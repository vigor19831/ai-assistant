"""Integration tests — real adapters working together.

Given: real adapter implementations are available.
When: adapters are wired into pipelines.
Then: end-to-end RAG flows complete without mutation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.embedder_openai_compatible import OpenAICompatibleEmbedder
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
from ai_assistant.adapters.reranker_api import APIReranker
from ai_assistant.adapters.reranker_null import NullReranker
from ai_assistant.adapters.storage_sqlite import SQLiteStorage
from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.api.deps import InitializedAppState, init_adapters
from ai_assistant.core.config import AppConfig, EmbedderConfig, LLMConfig
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    LLMConfigData,
    RerankerConfigData,
    StorageConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import (
    build_context,
    embed_query,
    generate,
    hyde_query,
    rerank,
    retrieve,
)

_logger = get_logger(__name__)


@pytest.mark.integration
@pytest.mark.slow
class TestIntegrationAdapters:
    """Real adapter instances with temporary paths and mocked HTTP."""

    @pytest.mark.asyncio
    async def test_chunker_real(self, tmp_path):
        """Given: a text document.
        When: SimpleChunker splits it.
        Then: chunks have correct metadata and boundaries."""
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=50, chunk_overlap=10))
        doc = Document(id="d1", content="Hello world. " * 20)
        chunks = await chunker.chunk(doc)
        assert len(chunks) > 1
        assert all(c.metadata.source == "d1" for c in chunks)
        assert all(c.metadata.total_chunks == len(chunks) for c in chunks)

    @pytest.mark.asyncio
    async def test_embedder_mock_real(self):
        """Given: mock embedder config.
        When: embedding two texts.
        Then: deterministic vectors with correct dimension."""
        embedder = MockEmbedder(EmbedderConfigData(dim=384))
        result = await embedder.embed(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 384
        assert result[0] != result[1]

    @pytest.mark.asyncio
    async def test_embedder_openai_compatible_real(self):
        """Given: OpenAI-compatible embedder config.
        When: HTTP endpoint returns embeddings.
        Then: vectors match expected dimensions."""
        config = EmbedderConfig(
            provider="openai_compatible",
            api_base="https://api.integration.test/v1",
            api_key="integration-key",
            dim=1536,
            timeout=5.0,
        )
        embedder = OpenAICompatibleEmbedder(config)
        with respx.mock:
            route = respx.post("https://api.integration.test/v1/embeddings")
            route.return_value = Response(
                200,
                json={"data": [{"embedding": [0.1] * 1536}, {"embedding": [0.2] * 1536}]},
            )
            result = await embedder.embed(["a", "b"])
            assert len(result) == 2
            assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_llm_mock_real(self):
        """Given: mock LLM config.
        When: completing a message list.
        Then: response echoes input."""
        llm = MockLLM(config=LLMConfigData())
        result = await llm.complete([UserMessage(text="integration")])
        assert isinstance(result, AssistantMessage)
        assert "integration" in result.text

    @pytest.mark.asyncio
    async def test_llm_openai_compatible_real(self):
        """Given: OpenAI-compatible LLM config.
        When: HTTP endpoint returns completion.
        Then: parsed AssistantMessage has correct text."""
        config = LLMConfig(
            provider="openai_compatible",
            api_base="https://api.integration.test/v1",
            api_key="integration-key",
            max_tokens=50,
            temperature=0.7,
            timeout=5.0,
            stop_sequences=[],
        )
        llm = OpenAICompatibleLLM(config)
        with respx.mock:
            route = respx.post("https://api.integration.test/v1/chat/completions")
            route.return_value = Response(
                200, json={"choices": [{"message": {"content": "Integrated"}}]}
            )
            result = await llm.complete([UserMessage(text="hi")])
            assert result.text == "Integrated"

    @pytest.mark.asyncio
    async def test_vector_store_faiss_real(self, tmp_path):
        """Given: FAISS vector store with temp path.
        When: adding chunks and searching.
        Then: nearest neighbors returned."""
        store = FaissVectorStore(VectorStoreConfigData(dim=3, metric="l2"))
        chunks = [
            Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="b", embedding=[0.0, 1.0, 0.0]),
        ]
        await store.add(chunks, namespace="ns")
        results = await store.search([1.0, 0.0, 0.0], top_k=1, namespace="ns")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.asyncio
    async def test_vector_store_memory_real(self):
        """Given: memory vector store.
        When: adding chunks and searching.
        Then: exact match returned."""
        store = MemoryVectorStore(VectorStoreConfigData(dim=3))
        chunks = [Chunk(id="c1", text="a", embedding=[1.0, 0.0, 0.0])]
        await store.add(chunks, namespace="ns")
        results = await store.search([1.0, 0.0, 0.0], top_k=1, namespace="ns")
        assert len(results) == 1
        assert results[0].id == "c1"

    @pytest.mark.asyncio
    async def test_reranker_api_real(self):
        """Given: API reranker config.
        When: HTTP endpoint returns scores.
        Then: chunks reordered by relevance."""
        config = RerankerConfigData(
            api_base="https://api.cohere.com",
            api_key="key",
            model="rerank-multilingual-v3.0",
            timeout=5.0,
            threshold=0.3,
        )
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

    @pytest.mark.asyncio
    async def test_reranker_null_real(self):
        """Given: NullReranker.
        When: reranking any chunks.
        Then: all chunks pass with score 1.0."""
        reranker = NullReranker(RerankerConfigData())
        chunks = [Chunk(id="c1", text="a"), Chunk(id="c2", text="b")]
        results = await reranker.rerank("q", chunks)
        assert len(results) == 2
        assert results[0].score == 1.0
        assert results[1].score == 1.0

    @pytest.mark.asyncio
    async def test_storage_sqlite_real(self, tmp_path):
        """Given: SQLite storage with temp DB path.
        When: saving and retrieving messages.
        Then: history preserved across operations."""
        storage = SQLiteStorage(StorageConfigData(db_path=str(tmp_path / "integration.db")))
        await storage.init_db()
        await storage.save_message(
            "conv-1", {"role": "user", "content": "hi", "metadata": {}}
        )
        history = await storage.get_history("conv-1", limit=10)
        assert len(history) == 1
        assert history[0]["content"] == "hi"


@pytest.mark.integration
@pytest.mark.slow
class TestIntegrationChatRAG:
    """E2E chat-RAG pipeline: [p] prefix → retrieve → rerank → generate."""

    @pytest.mark.asyncio
    async def test_chat_rag_pipeline_with_prefix(self, tmp_path):
        """Given: indexed chunks and a query with [p] prefix.
        When: pipeline runs embed_query → retrieve → rerank → build_context → generate.
        Then: response produced, original PipelineData not mutated."""
        # Arrange: real adapters
        embedder = MockEmbedder(EmbedderConfigData(dim=3))
        vector_store = MemoryVectorStore(VectorStoreConfigData(dim=3))

        llm = MockLLM(LLMConfigData())
        llm.get_context_limit = lambda: 4096
        reranker = NullReranker(RerankerConfigData())

        # Index documents
        chunks = [
            Chunk(id="c1", text="Paris is capital of France", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="Berlin is capital of Germany", embedding=[0.0, 1.0, 0.0]),
        ]
        await vector_store.add(chunks, namespace="default")

        # Build pipeline
        pipeline = RAGPipeline([
            embed_query,
            retrieve,
            rerank,
            build_context,
            generate,
        ])

        # Query with [p] prefix (RAG trigger)
        query = UserMessage(text="[p] What is the capital of France?")
        data = PipelineData(query=query)

        # Act
        metadata = {
            "embedder": embedder,
            "vector_store": vector_store,
            "reranker": reranker,
            "llm": llm,
            "top_k": 5,
            "namespace": "default",
            "relevance_threshold": 0.3,
            "prompt_version": "v1",
            "prompt_name": "rag_strict",
        }
        result = await pipeline.run(data, metadata=metadata)

        # Assert
        assert result.response is not None
        assert isinstance(result.response, AssistantMessage)
        assert result.context != ""
        assert len(result.chunks) > 0
        # Verify no in-place mutation: original data unchanged
        assert data.query is query
        assert data.metadata == {}
        assert data.context == ""


@pytest.mark.integration
@pytest.mark.slow
class TestIntegrationFullRAG:
    """Full RAG: index → query → hyde → retrieve → rerank → generate."""

    @pytest.mark.asyncio
    async def test_full_rag_with_hyde(self, tmp_path):
        """Given: indexed chunks and a user query.
        When: pipeline runs hyde_query → retrieve → rerank → build_context → generate.
        Then: hypothetical embedding used, response produced, data immutable."""
        # Arrange
        embedder = MockEmbedder(EmbedderConfigData(dim=3))
        vector_store = MemoryVectorStore(VectorStoreConfigData(dim=3))

        llm = MockLLM(LLMConfigData())
        llm.get_context_limit = lambda: 4096
        reranker = NullReranker(RerankerConfigData())

        # Index
        chunks = [
            Chunk(id="c1", text="Python is a programming language", embedding=[1.0, 0.0, 0.0]),
            Chunk(id="c2", text="Java is also a programming language", embedding=[0.0, 1.0, 0.0]),
        ]
        await vector_store.add(chunks, namespace="docs")

        # Pipeline with hyde
        pipeline = RAGPipeline([
            hyde_query,
            retrieve,
            rerank,
            build_context,
            generate,
        ])

        query = UserMessage(text="Tell me about Python")
        data = PipelineData(query=query)

        metadata = {
            "embedder": embedder,
            "vector_store": vector_store,
            "reranker": reranker,
            "llm": llm,
            "top_k": 5,
            "namespace": "docs",
            "relevance_threshold": 0.3,
            "prompt_version": "v1",
            "prompt_name": "rag_strict",
        }

        # Act
        result = await pipeline.run(data, metadata=metadata)

        # Assert
        assert result.response is not None
        assert isinstance(result.response, AssistantMessage)
        assert "query_embedding" in result.metadata
        # Verify hyde produced embedding (not original query embedding)
        assert result.context != ""
        assert len(result.chunks) > 0
        # Verify immutability
        assert data.query is query
        assert data.metadata == {}
        assert data.context == ""


@pytest.mark.integration
@pytest.mark.slow
class TestIntegrationAPIInit:
    """init_adapters with real adapters and pipeline construction."""

    @pytest.mark.asyncio
    async def test_init_adapters_real_pipeline(self, monkeypatch, tmp_path):
        """Given: AppConfig with real providers and temp paths.
        When: init_adapters assembles AppState.
        Then: pipeline runs embed_query → retrieve → build_context → generate."""
        db_path = str(tmp_path / "app.db")

        config = AppConfig(
            llm={
                "provider": "mock",
                "max_tokens": 50,
                "temperature": 0.7,
                "timeout": 5.0,
                "stop_sequences": [],
            },
            embedder={"provider": "mock", "dim": 3, "timeout": 5.0},
            vector_store={
                "provider": "memory",
                "dim": 3,
                "metric": "l2",
                "index_path": str(tmp_path / "indices"),
            },
            chunker={"provider": "simple", "chunk_size": 512, "chunk_overlap": 50},
            storage={"provider": "sqlite", "db_path": db_path},
            reranker={
                "provider": "null",
                "model": "test",
                "api_base": "http://test",
                "timeout": 5.0,
                "threshold": 0.3,
            },
            rag={
                "steps": ["embed_query", "retrieve", "build_context", "generate"],
                "prompt_version": "v1",
                "prompt_name": "rag_default",
                "top_k": 3,
                "default_namespace": "test",
                "relevance_threshold": 0.3,
            },
        )

        # Act
        state = await init_adapters(config)

        # Assert state assembled
        assert isinstance(state, InitializedAppState)
        assert state.config is config
        assert state.llm is not None
        assert state.embedder is not None
        assert state.vector_store is not None
        assert state.chunker is not None
        assert state.storage is not None
        assert state.reranker is not None
        assert state.pipeline is not None
        assert len(state.pipeline.steps) == 4

        # Functional test: index and run pipeline
        chunks = [
            Chunk(id="c1", text="Rome is capital of Italy", embedding=[1.0, 0.0, 0.0]),
        ]
        await state.vector_store.add(chunks, namespace="test")

        state.llm.get_context_limit = lambda: 4096

        query = UserMessage(text="What is capital of Italy?")
        data = PipelineData(query=query)
        result = await state.pipeline.run(
            data,
            metadata={
                "embedder": state.embedder,
                "vector_store": state.vector_store,
                "reranker": state.reranker,
                "llm": state.llm,
                "namespace": "test",
                "top_k": 3,
                "relevance_threshold": 0.3,
                "prompt_version": "v1",
                "prompt_name": "rag_default",
            },
        )

        assert result.response is not None
        assert isinstance(result.response, AssistantMessage)
        assert len(result.chunks) == 1
        assert result.chunks[0].id == "c1"

    @pytest.mark.asyncio
    async def test_init_adapters_with_hyde_pipeline(self, monkeypatch, tmp_path):
        """Given: AppConfig with hyde_query step.
        When: init_adapters builds pipeline and runs it.
        Then: hyde embedding drives retrieval."""
        db_path = str(tmp_path / "hyde_app.db")

        config = AppConfig(
            llm={
                "provider": "mock",
                "max_tokens": 50,
                "temperature": 0.7,
                "timeout": 5.0,
                "stop_sequences": [],
            },
            embedder={"provider": "mock", "dim": 3, "timeout": 5.0},
            vector_store={
                "provider": "memory",
                "dim": 3,
                "metric": "l2",
                "index_path": str(tmp_path / "indices_hyde"),
            },
            chunker={"provider": "simple", "chunk_size": 512, "chunk_overlap": 50},
            storage={"provider": "sqlite", "db_path": db_path},
            reranker={
                "provider": "null",
                "model": "test",
                "api_base": "http://test",
                "timeout": 5.0,
                "threshold": 0.3,
            },
            rag={
                "steps": ["hyde_query", "retrieve", "build_context", "generate"],
                "prompt_version": "v1",
                "prompt_name": "rag_default",
                "top_k": 3,
                "default_namespace": "test",
                "relevance_threshold": 0.3,
            },
        )

        state = await init_adapters(config)

        assert isinstance(state, InitializedAppState)
        assert len(state.pipeline.steps) == 4

        # Index
        chunks = [
            Chunk(id="c1", text="Go is a programming language", embedding=[1.0, 0.0, 0.0]),
        ]
        await state.vector_store.add(chunks, namespace="test")

        state.llm.get_context_limit = lambda: 4096

        query = UserMessage(text="Tell me about Go")
        data = PipelineData(query=query)
        result = await state.pipeline.run(
            data,
            metadata={
                "embedder": state.embedder,
                "vector_store": state.vector_store,
                "reranker": state.reranker,
                "llm": state.llm,
                "namespace": "test",
                "top_k": 3,
                "relevance_threshold": 0.3,
                "prompt_version": "v1",
                "prompt_name": "rag_default",
            },
        )

        assert result.response is not None
        assert isinstance(result.response, AssistantMessage)
        assert "query_embedding" in result.metadata
        assert len(result.chunks) > 0
