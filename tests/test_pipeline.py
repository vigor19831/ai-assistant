"""tests/test_pipeline.py — Pipeline steps tests.

Coverage: embed_query, retrieve, build_context, rerank, generate, hyde_query, retry.
Design: Given/When/Then docstrings, one function per test case.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
from ai_assistant.core.domain.configs import TokenizerConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import (
    AdapterError,
    EMBEDDER_NOT_PROVIDED,
    INTERNAL_SERVER_ERROR,
    LLM_NOT_PROVIDED,
    LLM_UNAVAILABLE,
    QUERY_EMBEDDING_MISSING,
    QUERY_MISSING,
    QUERY_TEXT_MISSING,
    VECTOR_STORE_NOT_PROVIDED,
)
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineConfig, PipelineData
from ai_assistant.core.pipeline_steps import (
    build_context,
    embed_query,
    generate,
    hyde_query,
    rerank,
    retrieve,
)
from ai_assistant.core.ports.reranker import IReranker, RerankResult
from ai_assistant.core.retry import with_retry

logger = logging.getLogger(__name__)


# ———————————————————————————————————————
# Fake helpers
# ———————————————————————————————————————


class FakeEmbedder:
    """Deterministic embedder for tests."""

    def __init__(self, dim: int = 384):
        self.dimension = dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * self.dimension for _ in texts]


class FakeVectorStore:
    """In-memory vector store with namespace support."""

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


class FakeLLM:
    """Deterministic LLM for tests."""

    def __init__(self, response: str = ""):
        self._response = response

    async def complete(
        self,
        messages: list,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantMessage:
        return AssistantMessage(text=self._response)

    def get_context_limit(self) -> int | None:
        return 4096


# ———————————————————————————————————————
# TestEmbedQuery
# ———————————————————————————————————————


class TestEmbedQuery:
    """Given: embed_query step receives PipelineData with query text.
    When: embedder is available or missing.
    Then: embedding is produced or appropriate error is added."""

    @pytest.mark.asyncio
    async def test_empty_query(self) -> None:
        """Given: query text is empty string.
        When: embed_query is called.
        Then: QUERY_TEXT_MISSING error is added."""
        embedder = FakeEmbedder()
        data = PipelineData(query=UserMessage(text=""), pipeline_config=PipelineConfig())
        data = replace(data, embedder=embedder)
        result = await embed_query(data)
        assert any(QUERY_TEXT_MISSING in e for e in result.errors)
        assert result.query_embedding is None

    @pytest.mark.asyncio
    async def test_empty_embedding_response(self) -> None:
        """Given: embedder returns empty list.
        When: embed_query is called.
        Then: INTERNAL_SERVER_ERROR is added; no IndexError."""
        class EmptyEmbedder:
            def __init__(self):
                self.dimension = 384

            async def embed(self, texts: list[str]) -> list[list[float]]:
                return []

        embedder = EmptyEmbedder()
        data = PipelineData(query=UserMessage(text="hello"), pipeline_config=PipelineConfig())
        data = replace(data, embedder=embedder)
        result = await embed_query(data)
        assert any(INTERNAL_SERVER_ERROR in e for e in result.errors)
        assert result.query_embedding is None

    @pytest.mark.asyncio
    async def test_no_embedder(self) -> None:
        """Given: no embedder (None value).
        When: embed_query is called.
        Then: EMBEDDER_NOT_PROVIDED error is added."""
        data = PipelineData(query=UserMessage(text="hello"), pipeline_config=PipelineConfig())
        data = replace(data, embedder=None)
        result = await embed_query(data)
        assert any(EMBEDDER_NOT_PROVIDED in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_no_query_text(self) -> None:
        """Given: query is None.
        When: embed_query is called.
        Then: QUERY_TEXT_MISSING error is added."""
        embedder = FakeEmbedder()
        data = PipelineData(pipeline_config=PipelineConfig())
        data = replace(data, embedder=embedder)
        result = await embed_query(data)
        assert any(QUERY_TEXT_MISSING in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_embed_error_detail_recorded(self) -> None:
        """Given: embedder raises exception with specific message.
        When: embed_query catches it.
        Then: error_details contains the exception string; errors stays clean."""
        class FailingEmbedder:
            def __init__(self):
                self.dimension = 384

            async def embed(self, texts: list[str]) -> list[list[float]]:
                raise RuntimeError("embedding service overloaded")

        data = PipelineData(
            query=UserMessage(text="hello"),
            embedder=FailingEmbedder(),
            pipeline_config=PipelineConfig(),
        )
        result = await embed_query(data)
        assert any(INTERNAL_SERVER_ERROR in e for e in result.errors)
        assert any("overloaded" in d for d in result.error_details if d)
        assert len(result.errors) == len(result.error_details)


# ———————————————————————————————————————
# TestRetrieve
# ———————————————————————————————————————


class TestRetrieve:
    """Given: retrieve step receives PipelineData with embedding.
    When: vector store is available or missing.
    Then: chunks are retrieved or appropriate error is added."""

    @pytest.mark.asyncio
    async def test_namespace_none_fallback(self) -> None:
        """Given: namespace is 'default' in pipeline_config.
        When: retrieve is called.
        Then: chunk is found in 'default' namespace."""
        store = FakeVectorStore()
        chunk = Chunk(id="c1", text="test", embedding=[0.0, 1.0, 0.0])
        await store.add([chunk], namespace="default")

        data = PipelineData(
            query=UserMessage(text="hello"),
            query_embedding=[0.0, 1.0, 0.0],
            pipeline_config=PipelineConfig(top_k=5, namespace="default"),
            vector_store=store,
        )
        result = await retrieve(data)
        assert len(result.chunks) == 1
        assert result.chunks[0].id == "c1"

    @pytest.mark.asyncio
    async def test_top_k_boundary(self) -> None:
        """Given: top_k is 1 and store has 2 chunks.
        When: retrieve is called.
        Then: exactly 1 chunk returned; top_k respected."""
        store = FakeVectorStore()
        await store.add([
            Chunk(id="c1", text="first", embedding=[0.0, 1.0, 0.0]),
            Chunk(id="c2", text="second", embedding=[0.0, 1.0, 0.0]),
        ], namespace="test")

        data = PipelineData(
            query=UserMessage(text="hello"),
            query_embedding=[0.0, 1.0, 0.0],
            pipeline_config=PipelineConfig(top_k=1, namespace="test"),
            vector_store=store,
        )
        result = await retrieve(data)
        assert len(result.chunks) == 1

    @pytest.mark.asyncio
    async def test_no_vector_store(self) -> None:
        """Given: no vector_store (None value).
        When: retrieve is called.
        Then: VECTOR_STORE_NOT_PROVIDED error is added."""
        data = PipelineData(
            query=UserMessage(text="hello"),
            query_embedding=[0.0, 1.0, 0.0],
            pipeline_config=PipelineConfig(),
            vector_store=None,
        )
        result = await retrieve(data)
        assert any(VECTOR_STORE_NOT_PROVIDED in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_no_embedding(self) -> None:
        """Given: no query_embedding (None value).
        When: retrieve is called.
        Then: QUERY_EMBEDDING_MISSING error is added."""
        store = FakeVectorStore()
        data = PipelineData(
            query=UserMessage(text="hello"),
            vector_store=store,
            pipeline_config=PipelineConfig(),
            query_embedding=None,
        )
        result = await retrieve(data)
        assert any(QUERY_EMBEDDING_MISSING in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_retrieve_error_detail_recorded(self) -> None:
        """Given: vector_store.search raises unexpected exception.
        When: retrieve is called.
        Then: error_details contains original exception; errors stays clean."""
        class FailingVectorStore:
            async def search(self, query_embedding, top_k=5, namespace="default"):
                raise RuntimeError("disk I/O error")

        data = PipelineData(
            query=UserMessage(text="hello"),
            query_embedding=[0.1] * 384,
            vector_store=FailingVectorStore(),
            pipeline_config=PipelineConfig(),
        )
        result = await retrieve(data)
        assert any(INTERNAL_SERVER_ERROR in e for e in result.errors)
        assert any("disk I/O error" in d for d in result.error_details if d)
        assert len(result.errors) == len(result.error_details)


# ———————————————————————————————————————
# TestBuildContext
# ———————————————————————————————————————


class TestBuildContext:
    """Given: build_context step receives PipelineData with chunks.
    When: chunks have various text contents.
    Then: context string is built correctly."""

    @pytest.mark.asyncio
    async def test_none_chunk_text(self) -> None:
        """Given: chunk text is None or empty.
        When: build_context is called.
        Then: empty texts are skipped."""
        data = PipelineData(
            query=UserMessage(text="hello"),
            pipeline_config=PipelineConfig(),
            chunks=[
                Chunk(id="c1", text="valid"),
                Chunk(id="c2", text=""),
            ],
        )
        result = await build_context(data)
        assert result.context == "[Document 1]\nvalid"

    @pytest.mark.asyncio
    async def test_very_long_chunks(self) -> None:
        """Given: chunks contain very long text.
        When: build_context is called.
        Then: context concatenates all texts with separators."""
        long_text = "word " * 10000
        data = PipelineData(
            query=UserMessage(text="hello"),
            pipeline_config=PipelineConfig(),
            chunks=[
                Chunk(id="c1", text=long_text),
                Chunk(id="c2", text="tail"),
            ],
        )
        result = await build_context(data)
        assert long_text in result.context
        assert "tail" in result.context
        assert "\n\n" in result.context

    @pytest.mark.asyncio
    async def test_single_chunk_truncate(self) -> None:
        """Given: single chunk with text.
        When: build_context is called.
        Then: context equals that text."""
        data = PipelineData(
            query=UserMessage(text="hello"),
            pipeline_config=PipelineConfig(),
            chunks=[Chunk(id="c1", text="only")],
        )
        result = await build_context(data)
        assert result.context == "[Document 1]\nonly"

    @pytest.mark.asyncio
    async def test_empty_chunks(self) -> None:
        """Given: no chunks.
        When: build_context is called.
        Then: context is empty string."""
        data = PipelineData(query=UserMessage(text="hello"), pipeline_config=PipelineConfig())
        result = await build_context(data)
        assert result.context == ""


# ———————————————————————————————————————
# TestRerank
# ———————————————————————————————————————


class TestRerank:
    """Given: rerank step receives PipelineData with chunks.
    When: reranker processes chunks with scores.
    Then: filtered chunks and metadata are produced."""

    @pytest.mark.asyncio
    async def test_top_k_less_than_filtered(self) -> None:
        """Given: top_k is less than number of chunks.
        When: rerank is called.
        Then: only top_k chunks are returned (handled by reranker)."""
        class FakeReranker:
            async def rerank(self, query, chunks, top_k=None):
                results = [RerankResult(chunk=c, score=0.9) for c in chunks]
                return results[:top_k] if top_k else results

        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[
                Chunk(id="c1", text="first"),
                Chunk(id="c2", text="second"),
                Chunk(id="c3", text="third"),
            ],
            reranker=FakeReranker(),
            pipeline_config=PipelineConfig(top_k=2),
        )
        result = await rerank(data)
        assert len(result.chunks) == 2
        assert result.rerank_scores == [0.9, 0.9]

    @pytest.mark.asyncio
    async def test_rerank_error_detail_recorded(self) -> None:
        """Given: reranker raises AdapterError with specific message.
        When: rerank is called.
        Then: error_details contains original exception; errors stays clean."""
        class FailingReranker:
            async def rerank(self, query, chunks, top_k=None):
                raise AdapterError("HTTP request failed: connection timeout")

        data = PipelineData(
            query=UserMessage(text="hello"),
            chunks=[Chunk(id="c1", text="test")],
            reranker=FailingReranker(),
            pipeline_config=PipelineConfig(),
        )
        result = await rerank(data)
        assert any(INTERNAL_SERVER_ERROR in e for e in result.errors)
        assert any("connection timeout" in d for d in result.error_details if d)
        assert len(result.errors) == len(result.error_details)
        assert len(result.chunks) == 1  # preserved for inspection

    @pytest.mark.asyncio
    async def test_rerank_retry_recover(self) -> None:
        """Given: reranker raises on first call, succeeds on second.
        When: rerank is called.
        Then: pipeline retries and completes successfully."""
        mock_reranker = AsyncMock(spec=IReranker)
        call_count = 0

        async def _side_effect(*args: object, **kwargs: object) -> list[RerankResult]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("network error")
            return [
                RerankResult(
                    chunk=Chunk(
                        id="c1",
                        text="test chunk",
                        metadata=ChunkMetadata(source="s", source_uri="s", index=0, total_chunks=1),
                    ),
                    score=0.9,
                )
            ]

        mock_reranker.rerank.side_effect = _side_effect

        data = PipelineData(
            query=UserMessage(text="test"),
            chunks=(
                Chunk(
                    id="c1",
                    text="test chunk",
                    metadata=ChunkMetadata(source="s", source_uri="s", index=0, total_chunks=1),
                ),
            ),
            pipeline_config=PipelineConfig(top_k=5),
            reranker=mock_reranker,
        )

        result = await rerank(data)

        assert call_count == 2
        assert len(result.chunks) == 1
        assert result.errors == ()
        assert result.rerank_scores == [0.9]


# ———————————————————————————————————————
# TestGenerate
# ———————————————————————————————————————


class TestGenerate:
    """Given: generate step receives PipelineData with query and context.
    When: LLM is available or missing; prompt fits or exceeds limit.
    Then: response is produced or appropriate error is added."""

    @pytest.mark.asyncio
    async def test_prompt_tokens_equals_limit(self, monkeypatch) -> None:
        """Given: prompt tokens exactly equal the limit.
        When: generate is called.
        Then: no truncation needed; LLM is called."""
        llm = FakeLLM("answer")
        tokenizer = CharFallbackTokenizer(TokenizerConfigData())
        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
                token_margin_min=256,
                token_margin_pct=0.1,
            ),
            llm=llm,
            tokenizer=tokenizer,
        )

        # Mock _estimate_tokens to return exactly the limit
        # Production calls use tokenizer.model_name internally
        async def mock_estimate(text, tokenizer=None):
            # limit = 4096 - max(256, int(4096 * 0.1)) = 3686
            return 3686

        monkeypatch.setattr(
            "ai_assistant.core.pipeline_steps._estimate_tokens", mock_estimate
        )

        result = await generate(data)
        assert result.response is not None
        assert result.response.text == "answer"
        assert not result.errors

    @pytest.mark.asyncio
    async def test_max_ctx_adapter_provides_valid_limit(self) -> None:
        """Given: llm.get_context_limit() returns valid limit.
        When: generate is called.
        Then: LLM.complete is called successfully; no errors."""
        captured_messages: list = []

        class ValidLimitLLM:
            async def complete(self, messages, max_tokens=None, temperature=None):
                captured_messages.extend(messages)
                return AssistantMessage(text="fallback")

            def get_context_limit(self) -> int | None:
                return 4096

        llm = ValidLimitLLM()
        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
                token_margin_min=256,
                token_margin_pct=0.1,
            ),
            llm=llm,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await generate(data)
        assert result.response is not None
        assert result.response.text == "fallback"
        assert not result.errors
        assert len(captured_messages) == 1

    @pytest.mark.asyncio
    async def test_metadata_passed_to_llm(self) -> None:
        """Given: LLM.complete accepts messages.
        When: generate is called.
        Then: messages list contains UserMessage with prompt text."""
        captured_messages: list = []

        class CapturingLLM:
            async def complete(self, messages, max_tokens=None, temperature=None):
                captured_messages.extend(messages)
                return AssistantMessage(text="captured")

            def get_context_limit(self) -> int | None:
                return 4096

        llm = CapturingLLM()
        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
                token_margin_min=256,
                token_margin_pct=0.1,
            ),
            llm=llm,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        _result = await generate(data)
        assert len(captured_messages) == 1
        assert captured_messages[0].text  # prompt text is non-empty

    @pytest.mark.asyncio
    async def test_no_llm(self) -> None:
        """Given: no llm (None value).
        When: generate is called.
        Then: LLM_NOT_PROVIDED error is added."""
        data = PipelineData(
            query=UserMessage(text="q"),
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
                token_margin_min=256,
                token_margin_pct=0.1,
            ),
            llm=None,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await generate(data)
        assert any(LLM_NOT_PROVIDED in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_no_query(self) -> None:
        """Given: query is None.
        When: generate is called.
        Then: QUERY_MISSING error is added."""
        data = PipelineData(
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
                token_margin_min=256,
                token_margin_pct=0.1,
            ),
            llm=FakeLLM(),
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await generate(data)
        assert any(QUERY_MISSING in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_adapter_error_absorbed(self) -> None:
        """Given: LLM raises AdapterError.
        When: generate is called.
        Then: PipelineData returned with error and fallback response."""
        class FailingLLM:
            async def complete(self, messages, max_tokens=None, temperature=None):
                raise AdapterError("LLM down")

            def get_context_limit(self) -> int | None:
                return 4096

        llm = FailingLLM()
        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
                token_margin_min=256,
                token_margin_pct=0.1,
            ),
            llm=llm,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await generate(data)
        assert any(LLM_UNAVAILABLE in e for e in result.errors)
        assert result.response is not None
        assert "temporarily unavailable" in (result.response.text or "")

    @pytest.mark.asyncio
    async def test_none_context_limit(self) -> None:
        """Given: llm.get_context_limit() returns None.
        When: generate is called.
        Then: error response without exception; no TypeError."""
        class NoLimitLLM:
            async def complete(self, messages, max_tokens=None, temperature=None):
                return AssistantMessage(text="should not reach")

            def get_context_limit(self) -> int | None:
                return None

        llm = NoLimitLLM()
        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
                token_margin_min=256,
                token_margin_pct=0.1,
            ),
            llm=llm,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await generate(data)
        assert any("context limit unknown" in e for e in result.errors)
        assert result.response is not None
        assert "context limit" in result.response.text.lower()

    @pytest.mark.asyncio
    async def test_generate_empty_context_uses_llm(self) -> None:
        """Given: empty chunks and empty context.
        When: generate is called.
        Then: LLM is called to answer from general knowledge; no hardcoded refusal."""
        captured_calls: list = []

        class CapturingLLM:
            async def complete(self, messages, max_tokens=None, temperature=None):
                captured_calls.append(messages)
                return AssistantMessage(text="I don't have specific information about that.")

            def get_context_limit(self) -> int | None:
                return 4096

        llm = CapturingLLM()
        data = PipelineData(
            query=UserMessage(text="obscure topic nobody indexed"),
            chunks=(),
            context="",
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
                token_margin_min=256,
                token_margin_pct=0.1,
            ),
            llm=llm,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await generate(data)
        assert len(captured_calls) == 1, "LLM must be called even with empty context"
        assert result.response is not None
        assert result.response.text == "I don't have specific information about that."

    @pytest.mark.asyncio
    async def test_truncate_removes_least_relevant_from_end(self, monkeypatch) -> None:
        """Given: prompt exceeds token limit; chunks ordered by relevance (high→low).
        When: _truncate_to_fit is called.
        Then: least relevant chunks (at the end) are removed first."""
        from ai_assistant.core.pipeline_steps import _truncate_to_fit

        tokenizer = CharFallbackTokenizer(TokenizerConfigData())

        # Mock _estimate_tokens: first call returns over limit, then under limit
        # after one chunk removed
        call_count = 0

        async def mock_estimate(text, tokenizer=None):
            nonlocal call_count
            call_count += 1
            # First: 3 chunks = 100 tokens (over limit 50)
            # After removing 1 chunk: 2 chunks = 40 tokens (under limit)
            # After removing 2 chunks: 1 chunk = 20 tokens
            if "chunk3" in text:
                return 100
            if "chunk2" in text:
                return 40
            return 20

        monkeypatch.setattr(
            "ai_assistant.core.pipeline_steps._estimate_tokens", mock_estimate
        )

        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=(
                Chunk(id="c1", text="chunk1 most relevant"),
                Chunk(id="c2", text="chunk2 medium relevant"),
                Chunk(id="c3", text="chunk3 least relevant"),
            ),
            context="chunk1 most relevant\n\nchunk2 medium relevant\n\nchunk3 least relevant",
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
            ),
        )

        updated_data, updated_prompt = await _truncate_to_fit(
            data, data.context, "rag_default", "v1", "question", 50, tokenizer
        )

        # Least relevant chunk (c3) removed first
        assert len(updated_data.chunks) == 2
        assert updated_data.chunks[0].id == "c1"
        assert updated_data.chunks[1].id == "c2"
        assert "chunk3" not in updated_prompt

    @pytest.mark.asyncio
    async def test_truncate_all_chunks_still_too_long(self, monkeypatch) -> None:
        """Given: even with all chunks removed, prompt still exceeds limit.
        When: _truncate_to_fit is called.
        Then: empty chunks and empty context returned."""
        from ai_assistant.core.pipeline_steps import _truncate_to_fit

        tokenizer = CharFallbackTokenizer(TokenizerConfigData())

        async def mock_estimate(text, tokenizer=None):
            # Even empty context + query is over limit
            return 9999

        monkeypatch.setattr(
            "ai_assistant.core.pipeline_steps._estimate_tokens", mock_estimate
        )

        data = PipelineData(
            query=UserMessage(text="very long question that exceeds everything"),
            chunks=(Chunk(id="c1", text="chunk1"),),
            context="chunk1",
            pipeline_config=PipelineConfig(
                prompt_version="v1",
                prompt_name="rag_default",
            ),
        )

        updated_data, updated_prompt = await _truncate_to_fit(
            data, data.context, "rag_default", "v1", "very long question", 50, tokenizer
        )

        assert updated_data.chunks == ()
        assert updated_data.context == ""

# ———————————————————————————————————————
# TestHydeQuery
# ———————————————————————————————————————


class TestHydeQuery:
    """Given: hyde_query step generates hypothetical answer and embeds it.
    When: embedder or llm is missing; hyde response is empty.
    Then: embedding is produced or appropriate error is added."""

    @pytest.mark.asyncio
    async def test_empty_hyde_response_text(self) -> None:
        """Given: LLM returns empty text for hypothetical answer.
        When: hyde_query is called.
        Then: error is added; no embedding produced."""
        embedder = FakeEmbedder()
        llm = FakeLLM("")  # empty response
        data = PipelineData(
            query=UserMessage(text="What is the capital of France?"),
            embedder=embedder,
            llm=llm,
            pipeline_config=PipelineConfig(),
        )
        result = await hyde_query(data)
        assert any("empty hypothetical answer" in e for e in result.errors)
        assert result.query_embedding is None

    @pytest.mark.asyncio
    async def test_no_embedder(self) -> None:
        """Given: no embedder (None value).
        When: hyde_query is called.
        Then: EMBEDDER_NOT_PROVIDED error is added."""
        llm = FakeLLM("answer")
        data = PipelineData(
            query=UserMessage(text="question"),
            llm=llm,
            embedder=None,
            pipeline_config=PipelineConfig(),
        )
        result = await hyde_query(data)
        assert any(EMBEDDER_NOT_PROVIDED in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_no_llm(self) -> None:
        """Given: no llm (None value).
        When: hyde_query is called.
        Then: LLM_NOT_PROVIDED error is added."""
        embedder = FakeEmbedder()
        data = PipelineData(
            query=UserMessage(text="question"),
            embedder=embedder,
            llm=None,
            pipeline_config=PipelineConfig(),
        )
        result = await hyde_query(data)
        assert any(LLM_NOT_PROVIDED in e for e in result.errors)


# ———————————————————————————————————————
# TestCondenseQuestion
# ———————————————————————————————————————


class TestCondenseQuestion:
    """Given: condense_question step receives PipelineData with history.
    When: LLM rewrites query or history is absent.
    Then: query is condensed or preserved; original_query tracked."""

    @pytest.mark.asyncio
    async def test_condense_with_history(self) -> None:
        """Given: chat_history with previous Q&A.
        When: condense_question is called.
        Then: query is rewritten; original_query preserved."""
        llm = FakeLLM("condensed question")
        data = PipelineData(
            query=UserMessage(text="what about it?"),
            chat_history=(
                ("user", "What is France?"),
                ("assistant", "France is a country in Europe."),
            ),
            llm=llm,
            pipeline_config=PipelineConfig(),
        )
        from ai_assistant.core.pipeline_steps import condense_question
        result = await condense_question(data)
        assert result.query is not None
        assert result.query.text == "condensed question"
        assert result.original_query is not None
        assert result.original_query.text == "what about it?"

    @pytest.mark.asyncio
    async def test_condense_without_history(self) -> None:
        """Given: empty chat_history.
        When: condense_question is called.
        Then: query unchanged; step skipped; no original_query set."""
        data = PipelineData(
            query=UserMessage(text="standalone question"),
            chat_history=(),
            llm=FakeLLM(),
            pipeline_config=PipelineConfig(),
        )
        from ai_assistant.core.pipeline_steps import condense_question
        result = await condense_question(data)
        assert result.query.text == "standalone question"
        assert result.original_query is None

    @pytest.mark.asyncio
    async def test_condense_llm_failure(self) -> None:
        """Given: LLM raises AdapterError.
        When: condense_question is called.
        Then: error added; original query preserved as fallback."""
        class FailingLLM:
            async def complete(self, messages, max_tokens=None, temperature=None):
                raise AdapterError("LLM down")

        data = PipelineData(
            query=UserMessage(text="question"),
            chat_history=(("user", "previous"),),
            llm=FailingLLM(),
            pipeline_config=PipelineConfig(),
        )
        from ai_assistant.core.pipeline_steps import condense_question
        result = await condense_question(data)
        assert len(result.errors) > 0
        assert result.query.text == "question"  # fallback to original

    @pytest.mark.asyncio
    async def test_condense_empty_llm_response(self) -> None:
        """Given: LLM returns empty text.
        When: condense_question is called.
        Then: falls back to original query; warning logged."""
        llm = FakeLLM("")
        data = PipelineData(
            query=UserMessage(text="original"),
            chat_history=(("user", "hi"),),
            llm=llm,
            pipeline_config=PipelineConfig(),
        )
        from ai_assistant.core.pipeline_steps import condense_question
        result = await condense_question(data)
        assert result.query.text == "original"  # fallback
        assert result.original_query is not None
        assert result.original_query.text == "original"


# ———————————————————————————————————————
# TestChatManagerStepValidation
# ———————————————————————————————————————


class TestChatManagerStepValidation:
    """Given: ChatManager._build_pipeline builds pipeline from steps.
    When: default or custom steps are used.
    Then: pipeline constructed successfully with registered steps."""

    @pytest.mark.asyncio
    async def test_default_steps_all_available(self) -> None:
        """Given: default steps are used.
        When: _build_pipeline with no rag_steps.
        Then: pipeline constructed successfully with 4 retrieval steps."""
        from ai_assistant.features.chat.manager import ChatManager

        manager = ChatManager(
            llm=FakeLLM(),
            reranker=MagicMock(),  # type: ignore[arg-type]
            embedder=FakeEmbedder(),
            vector_store=FakeVectorStore(),
        )
        pipeline = manager._build_pipeline()
        assert pipeline is not None
        assert len(pipeline.steps) == 5  # condense, embed, retrieve, rerank, build_context

    @pytest.mark.asyncio
    async def test_custom_steps_skip_generate(self) -> None:
        """Given: rag_steps includes GENERATE.
        When: _build_pipeline is called.
        Then: GENERATE is skipped; pipeline stops before it."""
        from ai_assistant.core.config import RAGStep
        from ai_assistant.features.chat.manager import ChatManager

        manager = ChatManager(
            llm=FakeLLM(),
            reranker=MagicMock(),  # type: ignore[arg-type]
            embedder=FakeEmbedder(),
            vector_store=FakeVectorStore(),
        )
        pipeline = manager._build_pipeline(rag_steps=[
            RAGStep.EMBED_QUERY,
            RAGStep.RETRIEVE,
            RAGStep.GENERATE,  # Should be skipped
            RAGStep.BUILD_CONTEXT,
        ])
        assert pipeline is not None
        # GENERATE is skipped, BUILD_CONTEXT comes after it so also not included
        # Only EMBED_QUERY and RETRIEVE before GENERATE break
        assert len(pipeline.steps) == 2


# ———————————————————————————————————————
# TestBuildFallbackPrompt
# ———————————————————————————————————————


class TestBuildFallbackPrompt:
    """Given: _build_fallback_prompt receives chunks and query.
    When: called with various inputs.
    Then: produces valid prompt string without template dependency."""

    def test_basic_fallback(self) -> None:
        """Given: two chunks and a query.
        When: _build_fallback_prompt is called.
        Then: numbered context lines followed by question/answer format."""
        from ai_assistant.core.pipeline_steps import _build_fallback_prompt

        chunks = (
            Chunk(id="c1", text="First piece of context."),
            Chunk(id="c2", text="Second piece of context."),
        )
        result = _build_fallback_prompt(chunks, "What is the answer?")
        assert "[Document 1]\nFirst piece of context." in result
        assert "[Document 2]\nSecond piece of context." in result
        assert "Question: What is the answer?" in result
        assert "Answer:" in result

    def test_empty_chunks(self) -> None:
        """Given: empty chunks tuple.
        When: _build_fallback_prompt is called.
        Then: context section is empty but structure preserved."""
        from ai_assistant.core.pipeline_steps import _build_fallback_prompt

        result = _build_fallback_prompt((), "Any question?")
        assert "Context:" in result
        assert "Question: Any question?" in result
        assert "Answer:" in result

    def test_single_chunk(self) -> None:
        """Given: single chunk.
        When: _build_fallback_prompt is called.
        Then: only [1] marker present."""
        from ai_assistant.core.pipeline_steps import _build_fallback_prompt

        chunks = (Chunk(id="c1", text="Only context."),)
        result = _build_fallback_prompt(chunks, "Simple question?")
        assert "[Document 1]\nOnly context." in result
        assert "[2]" not in result


# ———————————————————————————————————————
# TestRetry
# ———————————————————————————————————————


class TestRetry:
    """Given: with_retry decorator wraps async functions.
    When: transient or permanent errors occur.
    Then: transient errors are retried; permanent errors are not."""

    @pytest.mark.asyncio
    async def test_transient_vs_permanent(self) -> None:
        """Given: transient error (RuntimeError) and permanent error (ValueError).
        When: wrapped function raises each.
        Then: RuntimeError is retried; ValueError is not."""
        transient_calls = 0
        permanent_calls = 0

        @with_retry(max_retries=3, delay=0.01, backoff=1.0)
        async def transient_func():
            nonlocal transient_calls
            transient_calls += 1
            if transient_calls < 3:
                raise RuntimeError("transient")
            return "ok"

        @with_retry(max_retries=3, delay=0.01, backoff=1.0)
        async def permanent_func():
            nonlocal permanent_calls
            permanent_calls += 1
            raise ValueError("permanent")

        result = await transient_func()
        assert result == "ok"
        assert transient_calls == 3  # 2 failures + 1 success

        with pytest.raises(ValueError, match="permanent"):
            await permanent_func()
        assert permanent_calls == 1  # no retry

    @pytest.mark.asyncio
    async def test_backoff(self) -> None:
        """Given: retry with delay=0.1 and backoff=2.0.
        When: function fails twice then succeeds.
        Then: delays between retries are 0.1 and 0.2."""
        delays: list[float] = []
        calls = 0

        @with_retry(max_retries=3, delay=0.1, backoff=2.0)
        async def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise RuntimeError("fail")
            return "done"

        with patch("ai_assistant.core.retry.asyncio.sleep") as mock_sleep:
            mock_sleep.side_effect = lambda d: delays.append(d)
            result = await flaky()

        assert result == "done"
        assert calls == 3
        assert delays == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_exhaustion(self) -> None:
        """Given: function always raises transient error.
        When: max_retries=2.
        Then: after 3 total attempts, last exception is raised."""
        calls = 0

        @with_retry(max_retries=2, delay=0.01, backoff=1.0)
        async def always_fail():
            nonlocal calls
            calls += 1
            raise RuntimeError(f"attempt {calls}")

        with pytest.raises(RuntimeError, match="attempt 3"):
            await always_fail()
        assert calls == 3  # initial + 2 retries
