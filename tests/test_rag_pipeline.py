"""Full RAG pipeline tests — from document to answer.

Tests the complete flow: chunk → embed → store → query → retrieve → rerank \
→ build_context → generate.
Validates integration between all pipeline steps.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.chunker_simple import SimpleChunker
from adapters.embedder_mock import MockEmbedder
from adapters.vector_store_memory import MemoryVectorStore
from core.domain.documents import Chunk, ChunkMetadata, Document
from core.domain.messages import AssistantMessage, UserMessage
from core.domain.pipeline import PipelineData
from features.rag.manager import IndexingManager, RAGManager
from pipeline.steps import build_context, embed_query, generate, rerank, retrieve

# ── Pipeline Steps Integration ──


class TestPipelineSteps:
    @pytest.mark.asyncio
    async def test_embed_query_success(self):
        class FakeEmbedder:
            async def embed(self, texts: list[str]) -> list[list[float]]:
                return [[1.0, 2.0, 3.0]]

        data = PipelineData(query=UserMessage(text="hello"))
        result = await embed_query(data, embedder=FakeEmbedder())
        assert result.metadata["query_embedding"] == [1.0, 2.0, 3.0]
        assert not result.errors

    @pytest.mark.asyncio
    async def test_embed_query_no_embedder(self):
        data = PipelineData(query=UserMessage(text="hello"))
        result = await embed_query(data, embedder=None)
        assert "embedder not provided" in result.errors[0]

    @pytest.mark.asyncio
    async def test_embed_query_no_text(self):
        class FakeEmbedder:
            async def embed(self, texts: list[str]) -> list[list[float]]:
                return []

        data = PipelineData(query=UserMessage(text=""))
        result = await embed_query(data, embedder=FakeEmbedder())
        assert "no query text" in result.errors[0]

    @pytest.mark.asyncio
    async def test_retrieve_success(self):
        class FakeStore:
            async def search(self, emb, top_k=5, namespace="default"):
                return [Chunk(id="c1", text="result")]

        data = PipelineData(query=UserMessage(text="hello"))
        data.metadata["query_embedding"] = [1.0, 2.0]
        data.metadata["top_k"] = 5
        data.metadata["namespace"] = "default"
        result = await retrieve(data, vector_store=FakeStore())
        assert len(result.chunks) == 1
        assert result.chunks[0].id == "c1"

    @pytest.mark.asyncio
    async def test_retrieve_no_store(self):
        data = PipelineData(query=UserMessage(text="hello"))
        result = await retrieve(data, vector_store=None)
        assert "vector_store not provided" in result.errors[0]

    @pytest.mark.asyncio
    async def test_retrieve_no_embedding(self):
        data = PipelineData(query=UserMessage(text="hello"))
        result = await retrieve(data, vector_store=MagicMock())
        assert "no query embedding" in result.errors[0]

    @pytest.mark.asyncio
    async def test_build_context_from_chunks(self):
        data = PipelineData(query=UserMessage(text="hello"))
        data.chunks = [
            Chunk(id="c1", text="chunk one"),
            Chunk(id="c2", text="chunk two"),
        ]
        result = await build_context(data)
        assert "chunk one" in result.context
        assert "chunk two" in result.context
        assert "\n\n" in result.context

    @pytest.mark.asyncio
    async def test_build_context_empty_chunks(self):
        data = PipelineData(query=UserMessage(text="hello"))
        result = await build_context(data)
        assert result.context == ""

    @pytest.mark.asyncio
    async def test_build_context_skips_none_text(self):
        data = PipelineData(query=UserMessage(text="hello"))
        data.chunks = [Chunk(id="c1", text="valid"), Chunk(id="c2", text="")]
        result = await build_context(data)
        assert result.context == "valid"

    @pytest.mark.asyncio
    async def test_rerank_with_reranker(self):
        from core.ports.reranker import RerankResult

        class FakeReranker:
            async def rerank(self, query, chunks, top_k=None):
                return [RerankResult(chunk=c, score=0.9) for c in chunks]

        data = PipelineData(query=UserMessage(text="hello"))
        data.chunks = [Chunk(id="c1", text="test")]
        data.metadata["top_k"] = 5
        data.metadata["relevance_threshold"] = 0.3
        result = await rerank(data, reranker=FakeReranker())
        assert len(result.chunks) == 1
        assert result.metadata["rerank_scores"] == [0.9]

    @pytest.mark.asyncio
    async def test_rerank_without_reranker_passes_through(self):
        data = PipelineData(query=UserMessage(text="hello"))
        data.chunks = [Chunk(id="c1", text="test")]
        result = await rerank(data, reranker=None)
        assert len(result.chunks) == 1  # pass-through

    @pytest.mark.asyncio
    async def test_rerank_empty_chunks(self):
        data = PipelineData(query=UserMessage(text="hello"))
        result = await rerank(data, reranker=None)
        assert result.chunks == []

    @pytest.mark.asyncio
    async def test_rerank_filters_by_threshold(self):
        from core.ports.reranker import RerankResult

        class FakeReranker:
            async def rerank(self, query, chunks, top_k=None):
                return [
                    RerankResult(chunk=chunks[0], score=0.9),
                    RerankResult(chunk=chunks[1], score=0.1),
                ]

        data = PipelineData(query=UserMessage(text="hello"))
        data.chunks = [Chunk(id="c1", text="high"), Chunk(id="c2", text="low")]
        data.metadata["top_k"] = 5
        data.metadata["relevance_threshold"] = 0.3
        result = await rerank(data, reranker=FakeReranker())
        assert len(result.chunks) == 1
        assert result.chunks[0].id == "c1"

    @pytest.mark.asyncio
    async def test_rerank_all_filtered_out(self):
        from core.ports.reranker import RerankResult

        class FakeReranker:
            async def rerank(self, query, chunks, top_k=None):
                return [RerankResult(chunk=c, score=0.1) for c in chunks]

        data = PipelineData(query=UserMessage(text="hello"))
        data.chunks = [Chunk(id="c1", text="low")]
        data.metadata["top_k"] = 5
        data.metadata["relevance_threshold"] = 0.3
        result = await rerank(data, reranker=FakeReranker())
        assert result.chunks == []
        assert result.metadata.get("rerank_filtered_out") is True

    @pytest.mark.asyncio
    async def test_rerank_error_fallback(self):
        class BrokenReranker:
            async def rerank(self, query, chunks, top_k=None):
                raise RuntimeError("down")

        data = PipelineData(query=UserMessage(text="hello"))
        data.chunks = [Chunk(id="c1", text="test")]
        result = await rerank(data, reranker=BrokenReranker())
        assert len(result.chunks) == 1  # fallback
        assert "rerank failed" in result.errors[0]

    @pytest.mark.asyncio
    async def test_generate_success(self):
        class FakeLLM:
            async def complete(self, messages):
                return AssistantMessage(text="answer")

        data = PipelineData(query=UserMessage(text="question"))
        data.chunks = [Chunk(id="c1", text="context")]
        data.metadata["prompt_version"] = "v1"
        data.metadata["prompt_name"] = "rag_default"
        result = await generate(data, llm=FakeLLM())
        assert result.response.text == "answer"

    @pytest.mark.asyncio
    async def test_generate_no_llm(self):
        data = PipelineData(query=UserMessage(text="q"))
        result = await generate(data, llm=None)
        assert "llm not provided" in result.errors[0]

    @pytest.mark.asyncio
    async def test_generate_no_query(self):
        class FakeLLM:
            async def complete(self, messages):
                return None

        data = PipelineData(query=None)
        result = await generate(data, llm=FakeLLM())
        assert "no query" in result.errors[0]

    @pytest.mark.asyncio
    async def test_generate_llm_error(self):
        class BrokenLLM:
            async def complete(self, messages):
                raise RuntimeError("fail")

        data = PipelineData(query=UserMessage(text="question"))
        data.chunks = [Chunk(id="c1", text="context")]
        data.metadata["prompt_version"] = "v1"
        data.metadata["prompt_name"] = "rag_default"
        result = await generate(data, llm=BrokenLLM())
        assert "generate failed" in result.errors[0]
        assert "Sorry, I encountered an error" in result.response.text

    @pytest.mark.asyncio
    async def test_generate_context_truncation(self):
        """Long context triggers chunk removal to fit token budget."""

        class FakeLLM:
            config = MagicMock()
            config.server_context_size = 100

            async def complete(self, messages):
                return AssistantMessage(text="truncated answer")

        data = PipelineData(query=UserMessage(text="q"))
        # Create many chunks to exceed context limit
        data.chunks = [Chunk(id=f"c{i}", text="word " * 50) for i in range(20)]
        data.metadata["prompt_version"] = "v1"
        data.metadata["prompt_name"] = "rag_default"
        result = await generate(data, llm=FakeLLM())
        # Should still produce a response, possibly with fewer chunks
        assert result.response is not None


# ── Full Pipeline Integration ──


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_end_to_end_rag(self):
        """Complete RAG: chunk → embed → store → query → retrieve → generate."""
        # 1. Chunk document
        chunker = SimpleChunker(
            type("C", (), {"chunk_size": 100, "chunk_overlap": 5})()
        )
        doc = Document(
            id="doc1",
            content="The capital of France is Paris. It is known for the Eiffel Tower.",
        )
        chunks = await chunker.chunk(doc)
        assert len(chunks) > 0

        # 2. Embed chunks
        embedder = MockEmbedder(type("C", (), {"dim": 3})())
        texts = [c.text for c in chunks]
        embeddings = await embedder.embed(texts)
        assert len(embeddings) == len(chunks)

        # 3. Store in vector store
        from dataclasses import replace

        embedded_chunks = []
        for i, chunk in enumerate(chunks):
            embedded_chunks.append(replace(chunk, embedding=embeddings[i]))
        chunks = embedded_chunks
        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": -1.0})()
        )
        await store.add(chunks, namespace="test")

        # 4. Query pipeline
        query = "What is the capital of France?"
        data = PipelineData(query=UserMessage(text=query))
        data.metadata = {
            "top_k": 3,
            "prompt_version": "v1",
            "prompt_name": "rag_default",
            "namespace": "test",
            "relevance_threshold": -1.0,
        }

        # Run embed_query
        data = await embed_query(data, embedder=embedder)
        assert "query_embedding" in data.metadata

        # Run retrieve
        data = await retrieve(data, vector_store=store)
        assert len(data.chunks) > 0

        # Run build_context
        data = await build_context(data)
        assert "Paris" in data.context or "France" in data.context

        # Run generate with fake LLM
        class FakeLLM:
            async def complete(self, messages):
                return AssistantMessage(text="Paris is the capital of France.")

        data = await generate(data, llm=FakeLLM())
        assert "Paris" in data.response.text

    @pytest.mark.asyncio
    async def test_rag_no_relevant_chunks(self):
        """Query with no matching chunks returns empty context."""
        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": 0.99})()
        )
        await store.add(
            [Chunk(id="c1", text="irrelevant", embedding=[0.0, 1.0, 0.0])],
            namespace="test",
        )

        data = PipelineData(query=UserMessage(text="completely different topic"))
        data.metadata = {
            "top_k": 3,
            "prompt_version": "v1",
            "prompt_name": "rag_default",
            "namespace": "test",
            "relevance_threshold": 0.99,
        }

        embedder = MockEmbedder(type("C", (), {"dim": 3})())
        data = await embed_query(data, embedder=embedder)
        data = await retrieve(data, vector_store=store)
        assert len(data.chunks) == 0

        data = await build_context(data)
        assert data.context == ""


# ── RAG Manager Integration ──


class TestRAGManager:
    @pytest.fixture
    def indexing_manager(self):
        chunker = SimpleChunker(
            type("C", (), {"chunk_size": 50, "chunk_overlap": 10})()
        )
        embedder = MockEmbedder(type("C", (), {"dim": 3})())
        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": -1.0})()
        )
        return IndexingManager(chunker, embedder, store)

    @pytest.fixture
    def rag_manager(self, mock_llm, mock_embedder, mock_vector_store):
        pipeline = MagicMock()
        pipeline.run = AsyncMock(
            return_value=MagicMock(
                chunks=[
                    Chunk(
                        id="c1",
                        text="context",
                        metadata=ChunkMetadata(source="d1", index=0, total_chunks=1),
                    )
                ],
                response=MagicMock(text="Answer"),
                errors=[],
            )
        )
        return RAGManager(pipeline, mock_llm, mock_vector_store, embedder=mock_embedder)

    @pytest.mark.asyncio
    async def test_index_documents(self, indexing_manager):
        docs = [{"id": "d1", "content": "hello world", "metadata": {}}]
        result = await indexing_manager.index_documents(docs, namespace="test")
        assert result["indexed_count"] == 1
        assert result["chunk_count"] > 0

    @pytest.mark.asyncio
    async def test_index_empty_content(self, indexing_manager):
        docs = [{"id": "d1", "content": "   ", "metadata": {}}]
        result = await indexing_manager.index_documents(docs, namespace="test")
        assert result["indexed_count"] == 0
        assert len(result["errors"]) == 1

    @pytest.mark.asyncio
    async def test_query_returns_answer_and_sources(self, rag_manager):
        result = await rag_manager.query(
            "What is AI?",
            top_k=5,
            prompt_name="rag_default",
            prompt_version="v1",
            namespace="default",
        )
        assert result["answer"] == "Answer"
        assert result["chunks_used"] == 1
        assert len(result["sources"]) == 1
        assert result["sources"][0]["chunk_id"] == "c1"

    @pytest.mark.asyncio
    async def test_query_no_info_detected(self, rag_manager):
        """When answer indicates no info, sources should be empty."""
        rag_manager.pipeline.run = AsyncMock(
            return_value=MagicMock(
                chunks=[Chunk(id="c1", text="context")],
                response=MagicMock(text="I don't have enough information."),
                errors=[],
            )
        )
        result = await rag_manager.query(
            "unknown?",
            top_k=5,
            prompt_name="rag_default",
            prompt_version="v1",
            namespace="default",
        )
        assert len(result["sources"]) == 0  # No sources when no info

    @pytest.mark.asyncio
    async def test_health(self, rag_manager, mock_vector_store):
        mock_vector_store.list_namespaces = AsyncMock(return_value=["default"])
        mock_vector_store.list_by_filter = AsyncMock(return_value=[("c1", {})])
        health = await rag_manager.health()
        assert health["status"] == "ok"
        assert health["index_loaded"] is True
        assert health["chunk_count"] == 1


# ── Chat Manager RAG Integration ──


class TestChatManagerRAG:
    @pytest.fixture
    def chat_manager(self, mock_llm, mock_storage, mock_embedder, mock_vector_store):
        from features.chat.manager import ChatManager

        return ChatManager(
            llm=mock_llm,
            voice_recognizer=None,
            vision=None,
            storage=mock_storage,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
            reranker=None,
        )

    @pytest.mark.asyncio
    async def test_chat_with_namespace_prefix(
        self, chat_manager, mock_vector_store, mock_embedder
    ):
        """[p] prefix triggers RAG in personal namespace."""
        mock_vector_store.search = AsyncMock(
            return_value=[Chunk(id="c1", text="Paris is the capital of France.")]
        )
        mock_embedder.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

        _ = await chat_manager.chat("[p] What is the capital of France?", "conv-1")
        assert mock_vector_store.search.called
        # The query should have been processed through RAG

    @pytest.mark.asyncio
    async def test_chat_without_prefix_no_rag(self, chat_manager, mock_vector_store):
        """No prefix = no RAG, direct LLM call."""
        _ = await chat_manager.chat("Hello, how are you?", "conv-1")
        assert not mock_vector_store.search.called
        assert chat_manager.llm.complete.called

    @pytest.mark.asyncio
    async def test_chat_history_loaded(self, chat_manager, mock_storage):
        mock_storage.get_history = AsyncMock(
            return_value=[
                {"role": "user", "content": "Previous question"},
                {"role": "assistant", "content": "Previous answer"},
            ]
        )
        _ = await chat_manager.chat("Follow up", "conv-1")
        assert mock_storage.get_history.called
        assert mock_storage.save_message.call_count == 2  # user + assistant

    @pytest.mark.asyncio
    async def test_stream_chat(self, chat_manager):
        chunks = []
        async for chunk in chat_manager.stream_chat("Hello", "conv-1"):
            chunks.append(chunk)
        assert "".join(chunks) == "Mocked streaming response"
