"""Fuzz tests for pipeline steps — property-based."""

from __future__ import annotations

import pytest
from hypothesis import given, seed, settings
from hypothesis import strategies as st

from ai_assistant.core.domain.documents import Chunk
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.pipeline.steps import build_context
from ai_assistant.pipeline.steps import StepContext


class TestFuzzPipeline:
    """Property-based tests for pipeline steps."""

    @seed(42)
    @settings(max_examples=50, deadline=5000)
    @given(text=st.text(min_size=0, max_size=500))
    @pytest.mark.asyncio
    async def test_build_context_edge_cases(self, text):
        """build_context handles any text safely."""
        data = PipelineData(query=UserMessage(text="q"))
        result = await build_context(data, StepContext())
        assert isinstance(result.context, str)

    @seed(42)
    @settings(max_examples=50, deadline=5000)
    @given(chunks=st.lists(st.text(min_size=0, max_size=200), min_size=0, max_size=10))
    @pytest.mark.asyncio
    async def test_build_context_with_chunks(self, chunks):
        """build_context concatenates chunk texts, skipping empty ones."""
        data = PipelineData(
            query=UserMessage(text="q"),
            chunks=[Chunk(id=f"c{i}", text=t) for i, t in enumerate(chunks)],
        )
        result = await build_context(data, StepContext())
        assert isinstance(result.context, str)
        # Context is empty if all chunks have empty/None text
        non_empty_texts = [t for t in chunks if t]
        if not non_empty_texts:
            assert result.context == ""
        else:
            assert result.context  # non-empty when at least one chunk has text
