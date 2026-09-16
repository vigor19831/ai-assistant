"""Tests for hybrid (RRF) retrieval — stage 2.

Contract: PipelineData.lexical_index=None must reproduce pre-hybrid
behavior byte-identically; a provided lexical_index fuses legs via
RRF with deterministic tie-breaking.
"""

from __future__ import annotations

from typing import Any

from ai_assistant.core.constants import RRF_K
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.domain.pipeline import PipelineConfig, PipelineData
from ai_assistant.core.pipeline_steps import retrieve


def _chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        text=text,
        metadata=ChunkMetadata(source="s.md", index=0, total_chunks=1),
    )


class _StubStore:
    """Minimal IVectorStore stand-in: returns a fixed ranking."""

    def __init__(self, ranking: list[Chunk]) -> None:
        self._ranking = ranking
        self.calls: list[dict[str, Any]] = []

    async def search(
        self, embedding: list[float], top_k: int = 5, namespace: str = "default"
    ) -> list[Chunk]:
        self.calls.append({"top_k": top_k, "namespace": namespace})
        return self._ranking[:top_k]

    async def shutdown(self) -> None:
        return None


class _StubLexical:
    """Minimal ILexicalIndex stand-in: returns a fixed ranking."""

    def __init__(self, ranking: list[Chunk]) -> None:
        self._ranking = ranking
        self.calls: list[dict[str, Any]] = []

    async def search(
        self, query_text: str, top_k: int = 5, namespace: str = "default"
    ) -> list[Chunk]:
        self.calls.append({"query": query_text, "top_k": top_k})
        return self._ranking[:top_k]

    async def shutdown(self) -> None:
        return None


def _data(
    store: _StubStore,
    lexical: _StubLexical | None,
    top_k: int = 2,
) -> PipelineData:
    return PipelineData(
        query=UserMessage(text="Keenetic Extra router"),
        query_embedding=[0.1, 0.2],
        vector_store=store,  # type: ignore[arg-type]
        lexical_index=lexical,  # type: ignore[arg-type]
        pipeline_config=PipelineConfig(top_k=top_k, namespace="ns"),
    )


class TestHybridRetrieval:
    """Given: retrieve step with and without a lexical leg.
    When: the step runs.
    Then: None leg = dense-only byte-identical; provided leg = RRF fusion."""

    async def test_none_lexical_is_dense_only(self) -> None:
        store = _StubStore([_chunk("a", "alpha"), _chunk("b", "beta")])
        data = await retrieve(_data(store, None))
        assert [c.id for c in data.chunks] == ["a", "b"]
        # Dense-only: the lexical leg is never called.
        assert data.errors == ()

    async def test_rrf_fusion_boosts_both_legs_chunk(self) -> None:
        # Dense: [a, b, c]; lexical: [c, d]. top_k=3 = the candidate
        # budget each leg may deliver: only then does c reach fusion
        # from BOTH legs (with top_k=1 the legs deliver one chunk each
        # and the both-legs situation never materializes).
        store = _StubStore(
            [_chunk("a", "alpha"), _chunk("b", "beta"), _chunk("c", "gamma")]
        )
        lexical = _StubLexical([_chunk("c", "gamma exact term"), _chunk("d", "delta")])
        data = await retrieve(_data(store, lexical, top_k=3))
        ids = [c.id for c in data.chunks]
        # c: 1/(60+3) + 1/(60+1) ~= 0.032 > a: 1/(60+1) ~= 0.016.
        assert ids[0] == "c"

    async def test_rrf_tie_breaks_by_chunk_id(self) -> None:
        # Both legs return disjoint one-element lists: equal scores,
        # tie must break by chunk id ascending.
        store = _StubStore([_chunk("z", "zeta")])
        lexical = _StubLexical([_chunk("a", "alpha")])
        data = await retrieve(_data(store, lexical, top_k=2))
        assert [c.id for c in data.chunks] == ["a", "z"]

    async def test_lexical_failure_degrades_dense_only(self) -> None:
        store = _StubStore([_chunk("a", "alpha"), _chunk("b", "beta")])

        class _Broken(_StubLexical):
            async def search(
                self, query_text: str, top_k: int = 5, namespace: str = "default"
            ) -> list[Chunk]:
                raise RuntimeError("boom")

        data = await retrieve(_data(store, _Broken([])))
        assert [c.id for c in data.chunks] == ["a", "b"]
        assert data.errors == ()  # degraded, not errored

    async def test_rrf_k_constant_is_sane(self) -> None:
        # Guard: RRF_K must stay a small positive int; a change here
        # shifts every fused ranking and needs a re-baseline.
        assert isinstance(RRF_K, int)
        assert 0 < RRF_K < 1000
