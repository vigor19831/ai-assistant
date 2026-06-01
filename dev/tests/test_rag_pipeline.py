"""Tests for RAG pipeline steps."""

from __future__ import annotations

import pytest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from ai_assistant.core.domain.documents import Chunk, Document
from ai_assistant.core.domain.errors import (
    EMBEDDER_NOT_PROVIDED,
    INTERNAL_SERVER_ERROR,
    LLM_NOT_PROVIDED,
    QUERY_EMBEDDING_MISSING,
    QUERY_MISSING,
    QUERY_TEXT_MISSING,
    VECTOR_STORE_NOT_PROVIDED,
)
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.ports.reranker import RerankResult
from ai_assistant.pipeline.steps import (
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

    async def complete(
        self,
        messages: list[Any],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantMessage:
        return AssistantMessage(text=self._response)


class TestEmbedQuery:
    @pytest.mark.asyncio
    async def test_embed_query_success(self):
        embedder = FakeEmbedder()
        data = PipelineData(query=UserMessage(text="hello"))
        data = replace(data, metadata={**data.metadata, "embedder": embedder})
        result = await embed_query(data)
        assert "query_embedding" in result.metadata
        assert len(result.metadata["query_embedding"]) == embedder.dimension

    @pytest.mark.asyncio
    async def test_embed_query_no_embedder(self):
        data = PipelineData(query=UserMessage(text="hello"))
        result = await embed_query(data)
        assert any(EMBEDDER_NOT_PROVIDED in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_embed_query_no_query(self):
        embedder = FakeEmbedder()
        data = PipelineData()
        data = replace(data, metadata={**data.metadata, "embedder": embedder})
        result = await embed_query(data)
        assert any(QUERY_TEXT_MISSING in e for e in result.errors)


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
        data = replace(data, metadata={**data.metadata, "vector_store": store})
        result = await retrieve(data)
        assert len(result.chunks) == 1
        assert result.chunks[0].id == "c1"

    @pytest.mark.asyncio
    async def test_retrieve_no_store(self):
        data = PipelineData(
            query=UserMessage(text="hello"),
            metadata={"query_embedding": [0.0, 1.0, 0.0]},
        )
        result = await retrieve(data)
        assert any(VECTOR_STORE_NOT_PROVIDED in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_retrieve_no_embedding(self):
        store = FakeVectorStore()
        data = PipelineData(query=UserMessage(text="hello"))
        data = replace(data, metadata={**data.metadata, "vector_store": store})
        result = await retrieve(data)
        assert any(QUERY_EMBEDDING_MISSING in e for e in result.errors)


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
        result = await build_context(data)
        assert "chunk one" in result.context
        assert "chunk two" in result.context

    @pytest.mark.asyncio
    async def test_build_context_empty(self):
        data = PipelineData(query=UserMessage(text="hello"))
        result = await build_context(data)
        assert result.context == ""

    @pytest.mark.asyncio
    async def test_build_context_skips_none_text(self):
        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[Chunk(id="c1", text="valid"), Chunk(id="c2", text="")],
        )
        result = await build_context(data)
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
        data = replace(data, metadata={**data.metadata, "reranker": FakeReranker()})
        result = await rerank(data)
        assert len(result.chunks) == 1
        assert result.metadata.get("rerank_scores") == [0.9]

    @pytest.mark.asyncio
    async def test_rerank_without_reranker_passes_through(self):
        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[Chunk(id="c1", text="test")],
        )
        result = await rerank(data)
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
        data = replace(data, metadata={**data.metadata, "reranker": FakeReranker()})
        result = await rerank(data)
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
        data = replace(data, metadata={**data.metadata, "reranker": FakeReranker()})
        result = await rerank(data)
        assert result.chunks == ()
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
        data = replace(data, metadata={**data.metadata, "reranker": BrokenReranker()})
        result = await rerank(data)
        assert any(INTERNAL_SERVER_ERROR in e for e in result.errors)


class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_success(self):
        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            metadata={"prompt_version": "v1", "prompt_name": "rag_default"},
        )
        llm = FakeLLM("answer")
        data = replace(data, metadata={**data.metadata, "llm": llm})
        result = await generate(data)
        assert result.response is not None
        assert result.response.text == "answer"

    @pytest.mark.asyncio
    async def test_generate_no_llm(self):
        data = PipelineData(
            query=UserMessage(text="q"),
            metadata={"prompt_version": "v1", "prompt_name": "rag_default"},
        )
        result = await generate(data)
        assert any(LLM_NOT_PROVIDED in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_generate_no_query(self):
        data = PipelineData(
            metadata={"prompt_version": "v1", "prompt_name": "rag_default"},
        )
        llm = FakeLLM()
        data = replace(data, metadata={**data.metadata, "llm": llm})
        result = await generate(data)
        assert any(QUERY_MISSING in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_generate_llm_error(self):
        class BrokenLLM:
            async def complete(
                self,
                messages: list[Any],
                max_tokens: int | None = None,
                temperature: float | None = None,
            ) -> AssistantMessage:
                raise RuntimeError("fail")

        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            metadata={"prompt_version": "v1", "prompt_name": "rag_default"},
        )
        data = replace(data, metadata={**data.metadata, "llm": BrokenLLM()})
        with patch("ai_assistant.pipeline.steps.asyncio.sleep", new_callable=AsyncMock):
            result = await generate(data)
        assert any(INTERNAL_SERVER_ERROR in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_generate_retries_on_transient_error(self):
        """Transient errors in LLM.complete should be retried with backoff."""
        class FlakyLLM:
            def __init__(self, fails: int = 2):
                self._fails = fails
                self._calls = 0

            async def complete(
                self,
                messages: list[Any],
                max_tokens: int | None = None,
                temperature: float | None = None,
            ) -> AssistantMessage:
                self._calls += 1
                if self._calls <= self._fails:
                    raise RuntimeError("network down")
                return AssistantMessage(text="recovered")

        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            metadata={"prompt_version": "v1", "prompt_name": "rag_default"},
        )
        llm = FlakyLLM(fails=2)
        data = replace(data, metadata={**data.metadata, "llm": llm})

        with patch("ai_assistant.pipeline.steps.asyncio.sleep", new_callable=AsyncMock):
            result = await generate(data)

        assert llm._calls == 3
        assert result.response is not None
        assert result.response.text == "recovered"
        assert not result.errors


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

        data = replace(data, metadata={**data.metadata, "embedder": embedder})
        data = await embed_query(data)
        data = replace(data, metadata={**data.metadata, "vector_store": store})
        data = await retrieve(data)
        data = await build_context(data)
        llm = FakeLLM("Paris")
        data = replace(data, metadata={**data.metadata, "llm": llm})
        data = await generate(data)

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
        data = replace(data, metadata={**data.metadata, "embedder": embedder})
        data = await embed_query(data)
        data = replace(data, metadata={**data.metadata, "vector_store": store})
        data = await retrieve(data)
        data = await build_context(data)
        llm = FakeLLM("no info")
        data = replace(data, metadata={**data.metadata, "llm": llm})
        data = await generate(data)

        assert data.response is not None


class TestEmbedQueryRetry:
    @pytest.mark.asyncio
    async def test_embed_query_retries_on_transient_error(self):
        """Transient errors (RuntimeError) in embedder should be retried."""
        class FlakyEmbedder:
            def __init__(self, fails: int = 2):
                self.dimension = 384
                self._fails = fails
                self._calls = 0

            async def embed(self, texts: list[str]) -> list[list[float]]:
                self._calls += 1
                if self._calls <= self._fails:
                    raise RuntimeError("network down")
                return [[0.1] * self.dimension for _ in texts]

        embedder = FlakyEmbedder(fails=2)
        data = PipelineData(query=UserMessage(text="hello"))
        data = replace(data, metadata={**data.metadata, "embedder": embedder})

        with patch("ai_assistant.core.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await embed_query(data)

        assert embedder._calls == 3
        assert "query_embedding" in result.metadata
        assert len(result.metadata["query_embedding"]) == embedder.dimension
        assert not result.errors

    @pytest.mark.asyncio
    async def test_embed_query_no_retry_on_permanent_error(self):
        """Permanent errors (ValueError) in embedder should NOT be retried."""
        class PermanentFailEmbedder:
            def __init__(self):
                self.dimension = 384
                self._calls = 0

            async def embed(self, texts: list[str]) -> list[list[float]]:
                self._calls += 1
                raise ValueError("bad config")

        embedder = PermanentFailEmbedder()
        data = PipelineData(query=UserMessage(text="hello"))
        data = replace(data, metadata={**data.metadata, "embedder": embedder})

        result = await embed_query(data)

        assert embedder._calls == 1
        assert any(INTERNAL_SERVER_ERROR in e for e in result.errors)


class TestRetrieveRetry:
    @pytest.mark.asyncio
    async def test_retrieve_retries_on_transient_error(self):
        """Transient errors (RuntimeError) in vector_store.search should be retried."""
        class FlakyVectorStore:
            def __init__(self, fails: int = 2):
                self._fails = fails
                self._calls = 0

            async def search(self, query_embedding, top_k=5, namespace="default"):
                self._calls += 1
                if self._calls <= self._fails:
                    raise RuntimeError("connection lost")
                return [Chunk(id="c1", text="recovered", embedding=query_embedding)]

        store = FlakyVectorStore(fails=2)
        data = PipelineData(
            query=UserMessage(text="hello"),
            metadata={
                "query_embedding": [0.0, 1.0, 0.0],
                "top_k": 5,
                "namespace": "test",
            },
        )
        data = replace(data, metadata={**data.metadata, "vector_store": store})

        with patch("ai_assistant.core.retry.asyncio.sleep", new_callable=AsyncMock):
            result = await retrieve(data)

        assert store._calls == 3
        assert len(result.chunks) == 1
        assert result.chunks[0].id == "c1"
        assert not result.errors

    @pytest.mark.asyncio
    async def test_retrieve_no_retry_on_permanent_error(self):
        """Permanent errors (ValueError) in vector_store.search should NOT be retried."""
        class PermanentFailStore:
            def __init__(self):
                self._calls = 0

            async def search(self, query_embedding, top_k=5, namespace="default"):
                self._calls += 1
                raise ValueError("bad index")

        store = PermanentFailStore()
        data = PipelineData(
            query=UserMessage(text="hello"),
            metadata={
                "query_embedding": [0.0, 1.0, 0.0],
                "top_k": 5,
                "namespace": "test",
            },
        )
        data = replace(data, metadata={**data.metadata, "vector_store": store})

        result = await retrieve(data)

        assert store._calls == 1
        assert any(INTERNAL_SERVER_ERROR in e for e in result.errors)

class TestPromptCache:
    def test_get_prompt_cache_hit(self):
        """Same kwargs should return cached result."""
        from ai_assistant.core.prompts import _render, get_prompt

        _render.cache_clear()

        result1 = get_prompt("summarize", version="v1", text="hello", max_sentences="3")
        result2 = get_prompt("summarize", version="v1", text="hello", max_sentences="3")

        assert result1 == result2
        assert _render.cache_info().hits >= 1

    def test_get_prompt_cache_miss_different_kwargs(self):
        """Different kwargs should be separate cache entries."""
        from ai_assistant.core.prompts import _render, get_prompt

        _render.cache_clear()

        result1 = get_prompt("summarize", version="v1", text="hello", max_sentences="3")
        result2 = get_prompt("summarize", version="v1", text="hello", max_sentences="5")

        assert result1 != result2
        assert _render.cache_info().misses >= 2

    def test_get_prompt_cache_with_chunks(self):
        """Cache should handle hashable Chunk objects."""
        from ai_assistant.core.prompts import _render, get_prompt

        _render.cache_clear()

        chunks = [Chunk(id="c1", text="chunk one"), Chunk(id="c2", text="chunk two")]
        result1 = get_prompt(
            "rag_default", version="v1", query="q", context="ctx", chunks=chunks
        )
        result2 = get_prompt(
            "rag_default", version="v1", query="q", context="ctx", chunks=chunks
        )

        assert result1 == result2
        assert _render.cache_info().hits >= 1
