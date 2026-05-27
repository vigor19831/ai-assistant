"""Tests for RAG pipeline steps."""

from __future__ import annotations

import pytest
from dataclasses import replace

from ai_assistant.core.domain.documents import Chunk, Document
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.ports.reranker import RerankResult
from ai_assistant.pipeline.steps import (
    StepContext,
    build_context,
    embed_query,
    generate,
    rerank,
    retrieve,
)


class FakeEmbedder:
    def __init__(self, dim: int = 384):
        self.dimension = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dimension for _ in texts]


class FakeVectorStore:
    def __init__(self):
        self._data: dict[str, list[Chunk]] = {}

    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        self._data.setdefault(namespace, []).extend(chunks)

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        namespace: str = "default",
    ) -> list[Chunk]:
        return self._data.get(namespace, [])[:top_k]

    async def list_namespaces(self, path: str) -> list[str]:
        return list(self._data.keys())


class FakeLLM:
    def __init__(self, response: str = ""):
        self._response = response

    async def complete(self, messages, **kwargs):
        return AssistantMessage(text=self._response)


class TestEmbedQuery:
    @pytest.mark.asyncio
    async def test_embed_query_success(self):
        embedder = FakeEmbedder()
        data = PipelineData(query=UserMessage(text="hello"))
        result = await embed_query(data, StepContext(embedder=embedder))
        assert "query_embedding" in result.metadata
        assert len(result.metadata["query_embedding"]) == embedder.dimension

    @pytest.mark.asyncio
    async def test_embed_query_no_embedder(self):
        data = PipelineData(query=UserMessage(text="hello"))
        result = await embed_query(data, StepContext())
        assert any("embedder not provided" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_embed_query_no_query(self):
        embedder = FakeEmbedder()
        data = PipelineData()
        result = await embed_query(data, StepContext(embedder=embedder))
        assert any("no query text" in e for e in result.errors)


class TestRetrieve:
    @pytest.mark.asyncio
    async def test_retrieve_success(self):
        store = FakeVectorStore()
        chunk = Chunk(id="c1", text="test", embedding=[0.0, 1.0, 0.0])
        await store.add([chunk], namespace="test")

        data = PipelineData(
            query=UserMessage(text="hello"),
            metadata={
                "query_embedding": [0.0, 1.0, 0.0],
                "top_k": 5,
                "namespace": "test",
            },
        )
        result = await retrieve(data, StepContext(vector_store=store))
        assert len(result.chunks) == 1
        assert result.chunks[0].id == "c1"

    @pytest.mark.asyncio
    async def test_retrieve_no_store(self):
        data = PipelineData(
            query=UserMessage(text="hello"),
            metadata={"query_embedding": [0.0, 1.0, 0.0]},
        )
        result = await retrieve(data, StepContext())
        assert any("vector_store not provided" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_retrieve_no_embedding(self):
        store = FakeVectorStore()
        data = PipelineData(query=UserMessage(text="hello"))
        result = await retrieve(data, StepContext(vector_store=store))
        assert any("no query embedding" in e for e in result.errors)


class TestBuildContext:
    @pytest.mark.asyncio
    async def test_build_context_from_chunks(self):
        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[
                Chunk(id="c1", text="chunk one"),
                Chunk(id="c2", text="chunk two"),
            ],
        )
        result = await build_context(data, StepContext())
        assert "chunk one" in result.context
        assert "chunk two" in result.context

    @pytest.mark.asyncio
    async def test_build_context_empty(self):
        data = PipelineData(query=UserMessage(text="hello"))
        result = await build_context(data, StepContext())
        assert result.context == ""

    @pytest.mark.asyncio
    async def test_build_context_skips_none_text(self):
        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[Chunk(id="c1", text="valid"), Chunk(id="c2", text="")],
        )
        result = await build_context(data, StepContext())
        assert result.context == "valid"


class TestRerank:
    @pytest.mark.asyncio
    async def test_rerank_with_reranker(self):
        class FakeReranker:
            async def rerank(self, query, chunks, top_k=None):
                return [RerankResult(chunk=c, score=0.9) for c in chunks]

        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[Chunk(id="c1", text="test")],
        )
        result = await rerank(data, StepContext(reranker=FakeReranker()))
        assert len(result.chunks) == 1
        assert result.metadata.get("rerank_scores") == [0.9]

    @pytest.mark.asyncio
    async def test_rerank_without_reranker_passes_through(self):
        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[Chunk(id="c1", text="test")],
        )
        result = await rerank(data, StepContext())
        assert len(result.chunks) == 1

    @pytest.mark.asyncio
    async def test_rerank_filters_by_threshold(self):
        class FakeReranker:
            async def rerank(self, query, chunks, top_k=None):
                return [
                    RerankResult(chunk=chunks[0], score=0.9),
                    RerankResult(chunk=chunks[1], score=0.1),
                ]

        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[Chunk(id="c1", text="high"), Chunk(id="c2", text="low")],
        )
        result = await rerank(data, StepContext(reranker=FakeReranker()))
        assert len(result.chunks) == 1
        assert result.chunks[0].text == "high"

    @pytest.mark.asyncio
    async def test_rerank_all_filtered_out(self):
        class FakeReranker:
            async def rerank(self, query, chunks, top_k=None):
                return [RerankResult(chunk=c, score=0.1) for c in chunks]

        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[Chunk(id="c1", text="low")],
        )
        result = await rerank(data, StepContext(reranker=FakeReranker()))
        assert result.chunks == []
        assert result.metadata.get("rerank_filtered_out") is True

    @pytest.mark.asyncio
    async def test_rerank_error_fallback(self):
        class BrokenReranker:
            async def rerank(self, query, chunks, top_k=None):
                raise RuntimeError("down")

        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[Chunk(id="c1", text="test")],
        )
        result = await rerank(data, StepContext(reranker=BrokenReranker()))
        assert any("Internal server error" in e for e in result.errors)


class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_success(self):
        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            metadata={"prompt_version": "v1", "prompt_name": "rag_default"},
        )
        llm = FakeLLM("answer")
        result = await generate(data, StepContext(llm=llm))
        assert result.response is not None
        assert result.response.text == "answer"

    @pytest.mark.asyncio
    async def test_generate_no_llm(self):
        data = PipelineData(
            query=UserMessage(text="q"),
            metadata={"prompt_version": "v1", "prompt_name": "rag_default"},
        )
        result = await generate(data, StepContext())
        assert any("llm not provided" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_generate_no_query(self):
        data = PipelineData(
            metadata={"prompt_version": "v1", "prompt_name": "rag_default"},
        )
        llm = FakeLLM()
        result = await generate(data, StepContext(llm=llm))
        assert any("no query" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_generate_llm_error(self):
        class BrokenLLM:
            async def complete(self, messages, **kwargs):
                raise RuntimeError("fail")

        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            metadata={"prompt_version": "v1", "prompt_name": "rag_default"},
        )
        result = await generate(data, StepContext(llm=BrokenLLM()))
        assert any("Internal server error" in e for e in result.errors)


class TestFullPipeline:
    @pytest.mark.asyncio
    async def test_end_to_end_rag(self):
        """Complete RAG: chunk → embed → store → query → retrieve → generate."""
        from ai_assistant.adapters.chunker_simple import SimpleChunker
        from ai_assistant.adapters.vector_store_memory import MemoryVectorStore

        chunker = SimpleChunker(
            type("C", (), {"chunk_size": 100, "chunk_overlap": 5})()
        )
        doc = Document(
            id="doc1",
            content="The capital of France is Paris. It is known for the Eiffel Tower.",
        )
        chunks = await chunker.chunk(doc)
        assert len(chunks) > 0

        embedder = FakeEmbedder(3)
        texts = [c.text for c in chunks]
        embeddings = await embedder.embed(texts)
        assert len(embeddings) == len(chunks)

        embedded_chunks = []
        for i, chunk in enumerate(chunks):
            embedded_chunks.append(replace(chunk, embedding=embeddings[i]))
        chunks = embedded_chunks

        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": -1.0})()
        )
        await store.add(chunks, namespace="test")

        query = "What is the capital of France?"
        data = PipelineData(
            query=UserMessage(text=query),
            metadata={
                "top_k": 3,
                "prompt_version": "v1",
                "prompt_name": "rag_default",
                "namespace": "test",
                "relevance_threshold": -1.0,
            },
        )

        data = await embed_query(data, StepContext(embedder=embedder))
        data = await retrieve(data, StepContext(vector_store=store))
        data = await build_context(data, StepContext())
        llm = FakeLLM("Paris")
        data = await generate(data, StepContext(llm=llm))

        assert data.response is not None
        assert "Paris" in (data.response.text or "")

    @pytest.mark.asyncio
    async def test_rag_no_relevant_chunks(self):
        """Query with no matching chunks returns empty context."""
        from ai_assistant.adapters.vector_store_memory import MemoryVectorStore

        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": 0.99})()
        )
        await store.add(
            [Chunk(id="c1", text="irrelevant", embedding=[0.0, 1.0, 0.0])],
            namespace="test",
        )

        data = PipelineData(
            query=UserMessage(text="completely different topic"),
            metadata={
                "top_k": 3,
                "prompt_version": "v1",
                "prompt_name": "rag_default",
                "namespace": "test",
                "relevance_threshold": 0.99,
            },
        )

        embedder = FakeEmbedder(3)
        data = await embed_query(data, StepContext(embedder=embedder))
        data = await retrieve(data, StepContext(vector_store=store))
        data = await build_context(data, StepContext())
        llm = FakeLLM("no info")
        data = await generate(data, StepContext(llm=llm))

        assert data.response is not None
