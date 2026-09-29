"""All-namespaces fan-out (NAMESPACE_ALL) contract tests.

The sentinel fans retrieval out over every namespace the store lists
and fuses candidates by RRF into ONE untruncated pool for the
reranker. The regular-namespace path stays byte-identical: one search
per leg, fetch_k truncation preserved (pinned below)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import (
    NAMESPACE_ALL,
    DateFilter,
    PipelineConfig,
    PipelineData,
)
from ai_assistant.core.pipeline_steps import (
    _rrf_fuse,
    _rrf_fuse_many,
    multi_query_retrieve,
    retrieve,
)
from ai_assistant.core.ports.embedder import IEmbedder
from ai_assistant.core.ports.lexical_index import ILexicalIndex
from ai_assistant.core.ports.llm import ILLM
from ai_assistant.core.ports.vector_store import IVectorStore


def _chunk(cid: str, text: str = "chunk text") -> Chunk:
    """Canonical test chunk (conftest build_chunk shape)."""
    return Chunk(
        id=cid,
        text=text,
        embedding=[1.0, 0.0, 0.0],
        metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
    )


def _store(namespaces: list[str], by_ns: dict[str, list[Chunk]]) -> MagicMock:
    """Spec-mock IVectorStore: lists *namespaces*, searches per ns."""
    store = MagicMock(spec=IVectorStore)
    store.index_path = "/tmp/fanout_indices"
    store.list_namespaces = AsyncMock(return_value=namespaces)

    async def _search(embedding, top_k, namespace, date_filter=None):
        return by_ns.get(namespace, [])

    store.search = AsyncMock(side_effect=_search)
    return store


def _lexical(hits_by_ns: dict[str, list[Chunk]]) -> MagicMock:
    """Spec-mock ILexicalIndex returning per-namespace hits."""
    lex = MagicMock(spec=ILexicalIndex)

    async def _search(query, top_k, namespace, date_filter=None):
        return hits_by_ns.get(namespace, [])

    lex.search = AsyncMock(side_effect=_search)
    return lex


def _embedder() -> MagicMock:
    emb = MagicMock(spec=IEmbedder)
    emb.embed = AsyncMock(return_value=[[1.0, 0.0, 0.0]])
    return emb


def _data(
    vector_store: IVectorStore,
    namespace: str,
    date_filter: DateFilter | None = None,
    top_k: int = 5,
) -> PipelineData:
    return PipelineData(
        query=UserMessage(text="what do I like"),
        query_embedding=[1.0, 0.0, 0.0],
        vector_store=vector_store,
        pipeline_config=PipelineConfig(
            top_k=top_k, namespace=namespace, date_filter=date_filter
        ),
    )


def test_rrf_fuse_delegates_to_fuse_many_identically() -> None:
    """Two-leg fuse and the N-list generalization agree exactly."""
    dense = [_chunk("d1"), _chunk("d2"), _chunk("d3")]
    lexical = [_chunk("d2"), _chunk("l1")]
    assert _rrf_fuse(dense, lexical, 2) == _rrf_fuse_many([dense, lexical], 2)
    assert _rrf_fuse(dense, lexical, 10) == _rrf_fuse_many([dense, lexical], 10)


@pytest.mark.asyncio
async def test_retrieve_fanout_searches_every_namespace_sorted() -> None:
    """NAMESPACE_ALL: one search per listed namespace, sorted order."""
    store = _store(
        ["ns_b", "ns_a"],
        {"ns_a": [_chunk("a1")], "ns_b": [_chunk("b1")]},
    )
    result = await retrieve(_data(store, NAMESPACE_ALL))
    assert store.list_namespaces.await_count == 1
    assert store.search.await_count == 2
    called_ns = [c.kwargs["namespace"] for c in store.search.call_args_list]
    assert called_ns == ["ns_a", "ns_b"]
    assert {c.id for c in result.chunks} == {"a1", "b1"}


@pytest.mark.asyncio
async def test_retrieve_fanout_keeps_full_pool() -> None:
    """The fan-out pool is NOT cut by the single-namespace fetch_k."""
    store = _store(
        ["ns_a", "ns_b"],
        {
            "ns_a": [_chunk(f"a{i}") for i in range(5)],
            "ns_b": [_chunk(f"b{i}") for i in range(5)],
        },
    )
    result = await retrieve(_data(store, NAMESPACE_ALL, top_k=5))
    assert len(result.chunks) == 10


@pytest.mark.asyncio
async def test_retrieve_regular_namespace_path_unchanged() -> None:
    """Regular namespace: ONE search, fetch_k truncation preserved."""
    store = _store(["ns_x"], {"ns_x": [_chunk(f"x{i}") for i in range(8)]})
    result = await retrieve(_data(store, "ns_x", top_k=5))
    assert store.search.await_count == 1
    assert store.list_namespaces.await_count == 0
    assert len(result.chunks) == 5


@pytest.mark.asyncio
async def test_retrieve_fanout_empty_listing_returns_no_chunks() -> None:
    """Empty listing: no searches, empty chunks (honest refusal path)."""
    store = _store([], {})
    result = await retrieve(_data(store, NAMESPACE_ALL))
    assert store.search.await_count == 0
    assert result.chunks == ()


@pytest.mark.asyncio
async def test_retrieve_fanout_passes_date_filter_to_every_namespace() -> None:
    """The date frame applies in EVERY namespace (architecture 13.8)."""
    frame = DateFilter(month=7, year=2026)
    store = _store(
        ["ns_a", "ns_b"],
        {"ns_a": [_chunk("a1")], "ns_b": [_chunk("b1")]},
    )
    await retrieve(_data(store, NAMESPACE_ALL, date_filter=frame))
    assert store.search.await_count == 2
    for call in store.search.call_args_list:
        assert call.kwargs["date_filter"] is frame


@pytest.mark.asyncio
async def test_multi_query_fanout_skips_variations_on_any_lexical_hit() -> None:
    """Exact terms hit in ONE namespace: variations skipped (drift #207)."""
    llm = MagicMock(spec=ILLM)
    llm.complete = AsyncMock(
        return_value=AssistantMessage(text="should not be used", metadata={})
    )
    store = _store(
        ["ns_a", "ns_b"],
        {"ns_a": [_chunk("a1")], "ns_b": []},
    )
    data = PipelineData(
        query=UserMessage(text="exact terms"),
        vector_store=store,
        embedder=_embedder(),
        llm=llm,
        lexical_index=_lexical({"ns_a": [_chunk("l1")]}),
        pipeline_config=PipelineConfig(top_k=5, namespace=NAMESPACE_ALL),
    )
    result = await multi_query_retrieve(data)
    llm.complete.assert_not_awaited()
    assert store.search.await_count == 2
    assert {c.id for c in result.chunks} >= {"a1", "l1"}


@pytest.mark.asyncio
async def test_multi_query_fanout_variations_search_every_namespace() -> None:
    """No lexical hit anywhere: each variation searches all namespaces."""
    llm = MagicMock(spec=ILLM)
    llm.complete = AsyncMock(
        return_value=AssistantMessage(text="var one\nvar two", metadata={})
    )
    store = _store(
        ["ns_a", "ns_b"],
        {"ns_a": [_chunk("a1")], "ns_b": [_chunk("b1")]},
    )
    data = PipelineData(
        query=UserMessage(text="vague paraphrase"),
        vector_store=store,
        embedder=_embedder(),
        llm=llm,
        pipeline_config=PipelineConfig(top_k=5, namespace=NAMESPACE_ALL),
    )
    result = await multi_query_retrieve(data)
    # 1 original + 2 variations, each over 2 namespaces
    assert store.search.await_count == 6
    assert llm.complete.await_count == 1
    assert {c.id for c in result.chunks} == {"a1", "b1"}


@pytest.mark.asyncio
async def test_multi_query_regular_namespace_path_unchanged() -> None:
    """Regular namespace: one search, lexical hit skips variations."""
    llm = MagicMock(spec=ILLM)
    llm.complete = AsyncMock(
        return_value=AssistantMessage(text="unused", metadata={})
    )
    store = _store(["ns_x"], {"ns_x": [_chunk(f"l{i}") for i in range(8)]})
    data = PipelineData(
        query=UserMessage(text="exact terms"),
        vector_store=store,
        embedder=_embedder(),
        llm=llm,
        lexical_index=_lexical({"ns_x": [_chunk("lx")]}),
        pipeline_config=PipelineConfig(top_k=5, namespace="ns_x"),
    )
    result = await multi_query_retrieve(data)
    llm.complete.assert_not_awaited()
    assert store.search.await_count == 1
    assert len(result.chunks) == 5
