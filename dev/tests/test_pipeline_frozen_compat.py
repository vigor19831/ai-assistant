"""Tests ensuring frozen PipelineData compatibility with downstream code."""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineData


class TestPipelineDataCompatibility:
    """Backward-compat tests: frozen must not break existing patterns."""

    def test_helper_methods_return_new_instances(self) -> None:
        """All helper methods must return new instances without mutating original."""
        chunk = Chunk(
            id="c1",
            text="hello",
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        msg = UserMessage(text="query")
        resp = AssistantMessage(text="answer")

        data = PipelineData(query=msg)

        # Test each method preserves original
        data2 = data.with_chunks([chunk])
        assert data.chunks == ()
        assert data2.chunks == (chunk,)
        assert data is not data2

        data3 = data2.with_context("ctx")
        assert data2.context == ""
        assert data3.context == "ctx"
        assert data2 is not data3

        data4 = data3.with_response(resp)
        assert data3.response is None
        assert data4.response is resp
        assert data3 is not data4

        data5 = data4.add_error("e1")
        assert data4.errors == ()
        assert data5.errors == ("e1",)
        assert data4 is not data5

    def test_chaining_compatibility(self) -> None:
        """Methods must be chainable in pipeline style."""
        chunk = Chunk(
            id="c1",
            text="hello",
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        resp = AssistantMessage(text="answer")

        data = (
            PipelineData()
            .with_chunks([chunk])
            .with_context("ctx")
            .with_response(resp)
            .add_error("e1")
        )

        assert data.chunks == (chunk,)
        assert data.context == "ctx"
        assert data.response is resp
        assert data.errors == ("e1",)

    def test_metadata_merge_compatibility(self) -> None:
        """replace() must work for metadata merging (pipeline pattern)."""
        from dataclasses import replace

        data = PipelineData(metadata={"a": 1})
        data2 = replace(data, metadata={**data.metadata, "b": 2})
        assert data2.metadata == {"a": 1, "b": 2}
        assert data.metadata == {"a": 1}

    def test_default_values_compatible(self) -> None:
        """Default values must work as before."""
        data = PipelineData()
        assert data.query is None
        assert data.chunks == ()
        assert data.context == ""
        assert data.response is None
        assert data.metadata == {}
        assert data.errors == ()
