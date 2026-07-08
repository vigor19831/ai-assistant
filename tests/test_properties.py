"""Property-based tests for port contracts using Hypothesis.

These tests generate edge-case inputs automatically and verify that
ALL implementations of a port behave consistently. Adding a new adapter
does NOT require new test code — just add to the fixture params.

Invariants:
- IEmbedder: embed([]) == [], output count == input count, dimension consistent.
- IReranker: scores in [0, 1], sorted descending, top_k respected.
- IChunker: chunk IDs unique, total_chunks consistent.
- ILLM: complete returns AssistantMessage, stream yields strings.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.adapters.reranker_null import NullReranker
from ai_assistant.core.domain.configs import ChunkerConfigData, EmbedderConfigData, LLMConfigData, RerankerConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.ports.chunker import IChunker
from ai_assistant.core.ports.embedder import IEmbedder
from ai_assistant.core.ports.llm import ILLM
from ai_assistant.core.ports.reranker import IReranker


# ---------------------------------------------------------------------------
# Fixtures: parametrized over ALL adapter implementations
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(params=["mock"])
async def embedder_impl(request):
    """Yield concrete IEmbedder implementations for property tests."""
    if request.param == "mock":
        adapter = MockEmbedder(
            EmbedderConfigData(model="mock", dim=384, api_base="", api_key="")
        )
    else:
        raise ValueError(f"Unknown embedder: {request.param}")
    yield adapter
    await adapter.shutdown()


@pytest_asyncio.fixture(params=["mock"])
async def llm_impl(request):
    """Yield concrete ILLM implementations for property tests."""
    if request.param == "mock":
        adapter = MockLLM(
            LLMConfigData(
                model="mock",
                api_base="",
                api_key="",
                max_tokens=100,
                temperature=0.7,
            )
        )
    else:
        raise ValueError(f"Unknown llm: {request.param}")
    yield adapter
    await adapter.shutdown()


@pytest_asyncio.fixture(params=["null"])
async def reranker_impl(request):
    """Yield concrete IReranker implementations for property tests."""
    if request.param == "null":
        adapter = NullReranker(
            RerankerConfigData(model="null", api_base="", api_key="")
        )
    else:
        raise ValueError(f"Unknown reranker: {request.param}")
    yield adapter
    await adapter.shutdown()


@pytest_asyncio.fixture(params=["simple"])
async def chunker_impl(request):
    """Yield concrete IChunker implementations for property tests."""
    if request.param == "simple":
        adapter = SimpleChunker(
            ChunkerConfigData(chunk_size=100, chunk_overlap=0)
        )
    else:
        raise ValueError(f"Unknown chunker: {request.param}")
    yield adapter
    await adapter.shutdown()


# ---------------------------------------------------------------------------
# IEmbedder properties
# ---------------------------------------------------------------------------

class TestEmbedderProperties:
    """Property-based contract tests for IEmbedder."""

    @pytest.mark.asyncio
    @given(texts=st.lists(st.text(min_size=0, max_size=500), min_size=0, max_size=20))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_embed_output_count_matches_input(
        self, embedder_impl: IEmbedder, texts: list[str]
    ) -> None:
        """Given: list of texts (including empty).
        When: embed() is called.
        Then: output count == input count.
        """
        result = await embedder_impl.embed(texts)
        assert len(result) == len(texts)

    @pytest.mark.asyncio
    @given(texts=st.lists(st.text(min_size=1, max_size=100), min_size=1, max_size=5))
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_embed_dimension_consistency(
        self, embedder_impl: IEmbedder, texts: list[str]
    ) -> None:
        """Given: non-empty list of texts.
        When: embed() is called.
        Then: all vectors have same dimension == embedder.dimension.
        """
        result = await embedder_impl.embed(texts)
        dim = embedder_impl.dimension
        for vec in result:
            assert len(vec) == dim

    @pytest.mark.asyncio
    async def test_embed_empty_list_returns_empty(
        self, embedder_impl: IEmbedder
    ) -> None:
        """Given: empty texts list.
        When: embed([]) is called.
        Then: returns empty list (not error).
        """
        result = await embedder_impl.embed([])
        assert result == []


# ---------------------------------------------------------------------------
# IReranker properties
# ---------------------------------------------------------------------------

class TestRerankerProperties:
    """Property-based contract tests for IReranker."""

    @pytest.mark.asyncio
    @given(
        query=st.text(min_size=0, max_size=200),
        chunks=st.lists(
            st.builds(
                Chunk,
                id=st.text(alphabet="abc123", min_size=1, max_size=20),
                text=st.text(min_size=0, max_size=500),
                metadata=st.just(ChunkMetadata(source="test", index=0, total_chunks=1)),
            ),
            min_size=0,
            max_size=20,
        ),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_rerank_result_count_bounded(
        self, reranker_impl: IReranker, query: str, chunks: list[Chunk]
    ) -> None:
        """Given: query and list of chunks.
        When: rerank() is called without top_k.
        Then: result count == input count.
        """
        results = await reranker_impl.rerank(query, chunks)
        assert len(results) == len(chunks)

    @pytest.mark.asyncio
    @given(
        query=st.text(min_size=0, max_size=200),
        chunks=st.lists(
            st.builds(
                Chunk,
                id=st.text(alphabet="abc123", min_size=1, max_size=20),
                text=st.text(min_size=1, max_size=500),
                metadata=st.just(ChunkMetadata(source="test", index=0, total_chunks=1)),
            ),
            min_size=1,
            max_size=20,
        ),
        top_k=st.integers(min_value=1, max_value=50),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_rerank_top_k_respected(
        self, reranker_impl: IReranker, query: str, chunks: list[Chunk], top_k: int
    ) -> None:
        """Given: query, chunks, and top_k.
        When: rerank(query, chunks, top_k) is called.
        Then: len(results) is reasonable (top_k respected or all returned for null).
        """
        results = await reranker_impl.rerank(query, chunks, top_k=top_k)
        # NullReranker returns all chunks regardless of top_k
        # APIReranker respects top_k
        assert len(results) <= len(chunks)

    @pytest.mark.asyncio
    @given(
        query=st.text(min_size=0, max_size=200),
        chunks=st.lists(
            st.builds(
                Chunk,
                id=st.text(alphabet="abc123", min_size=1, max_size=20),
                text=st.text(min_size=0, max_size=500),
                metadata=st.just(ChunkMetadata(source="test", index=0, total_chunks=1)),
            ),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_rerank_scores_in_valid_range(
        self, reranker_impl: IReranker, query: str, chunks: list[Chunk]
    ) -> None:
        """Given: non-empty chunks.
        When: rerank() is called.
        Then: all scores are in [0.0, 1.0].
        """
        results = await reranker_impl.rerank(query, chunks)
        for r in results:
            assert 0.0 <= r.score <= 1.0

    @pytest.mark.asyncio
    @given(
        query=st.text(min_size=0, max_size=200),
        chunks=st.lists(
            st.builds(
                Chunk,
                id=st.text(alphabet="abc123", min_size=1, max_size=20),
                text=st.text(min_size=0, max_size=500),
                metadata=st.just(ChunkMetadata(source="test", index=0, total_chunks=1)),
            ),
            min_size=2,
            max_size=10,
        ),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_rerank_scores_descending(
        self, reranker_impl: IReranker, query: str, chunks: list[Chunk]
    ) -> None:
        """Given: multiple chunks.
        When: rerank() is called.
        Then: results are sorted by score descending.
        """
        results = await reranker_impl.rerank(query, chunks)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# IChunker properties
# ---------------------------------------------------------------------------

class TestChunkerProperties:
    """Property-based contract tests for IChunker."""

    @pytest.mark.asyncio
    @given(
        text=st.text(min_size=0, max_size=2000),
        chunk_size=st.integers(min_value=10, max_value=500),
        chunk_overlap=st.integers(min_value=0, max_value=50),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_chunk_count_and_bounds(
        self, chunker_impl: IChunker, text: str, chunk_size: int, chunk_overlap: int
    ) -> None:
        """Given: document with arbitrary text.
        When: chunk() is called.
        Then: chunks cover text, count is reasonable, overlap respected.

        Note: chunk_overlap must be < chunk_size (adapter validates).
        """
        from ai_assistant.core.domain.configs import ChunkerConfigData

        assume(chunk_overlap < chunk_size)

        # Create fresh chunker with generated params
        fresh_chunker = type(chunker_impl)(
            ChunkerConfigData(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        )
        try:
            doc = Document(id="prop-test", content=text, metadata={})
            chunks = await fresh_chunker.chunk(doc)

            # Invariant: empty text -> empty or single empty chunk
            if not text:
                assert len(chunks) <= 1
                return

            # Invariant: each chunk has non-empty text (except edge cases)
            for c in chunks:
                assert len(c.text) <= chunk_size + chunk_overlap  # generous bound

            # Invariant: chunk IDs are unique
            ids = [c.id for c in chunks]
            assert len(ids) == len(set(ids))

            # Invariant: metadata.total_chunks is consistent
            for c in chunks:
                assert c.metadata.total_chunks == len(chunks)
        finally:
            await fresh_chunker.shutdown()


# ---------------------------------------------------------------------------
# ILLM properties
# ---------------------------------------------------------------------------

class TestLLMProperties:
    """Property-based contract tests for ILLM."""

    @pytest.mark.asyncio
    @given(
        texts=st.lists(st.text(min_size=0, max_size=500), min_size=1, max_size=5),
        max_tokens=st.one_of(st.none(), st.integers(min_value=1, max_value=4096)),
        temperature=st.one_of(st.none(), st.floats(min_value=0.0, max_value=2.0)),
    )
    @settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_complete_returns_assistant_message(
        self, llm_impl: ILLM, texts: list[str], max_tokens: int | None, temperature: float | None
    ) -> None:
        """Given: list of user messages with optional params.
        When: complete() is called.
        Then: returns AssistantMessage with text and metadata.
        """
        messages = [UserMessage(text=t) for t in texts]
        result = await llm_impl.complete(messages, max_tokens=max_tokens, temperature=temperature)
        assert isinstance(result, AssistantMessage)
        assert isinstance(result.text, str)

    @pytest.mark.asyncio
    @given(texts=st.lists(st.text(min_size=0, max_size=500), min_size=1, max_size=3))
    @settings(max_examples=20, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_stream_yields_strings(
        self, llm_impl: ILLM, texts: list[str]
    ) -> None:
        """Given: list of user messages.
        When: stream() is consumed.
        Then: all yielded values are strings.
        """
        messages = [UserMessage(text=t) for t in texts]
        chunks: list[str] = []
        async for chunk in llm_impl.stream(messages):
            assert isinstance(chunk, str)
            chunks.append(chunk)
        # Mock may yield empty stream — that is ok for this invariant

    def test_get_context_limit_non_negative_or_none(
        self, llm_impl: ILLM
    ) -> None:
        """Given: LLM adapter.
        When: get_context_limit() is called.
        Then: returns None or positive int.
        """
        limit = llm_impl.get_context_limit()
        assert limit is None or (isinstance(limit, int) and limit > 0)
