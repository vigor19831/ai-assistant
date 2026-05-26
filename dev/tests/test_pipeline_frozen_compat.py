"""Compatibility tests for frozen PipelineData with RAG pipeline."""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineData


class TestPipelineDataCompatibility:
    """Ensure frozen PipelineData works with existing pipeline patterns."""

    def test_pipeline_data_is_frozen(self) -> None:
        """PipelineData must be immutable."""
        data = PipelineData()
        with pytest.raises(FrozenInstanceError):
            data.context = "test"

    def test_frozen_instance_error_on_chunks_mutation(self) -> None:
        """Attempting to set data.chunks = [...] must raise FrozenInstanceError."""
        data = PipelineData()
        with pytest.raises(FrozenInstanceError):
            data.chunks = []  # type: ignore[misc]

    def test_frozen_instance_error_on_errors_mutation(self) -> None:
        """Attempting to set data.errors = [...] must raise FrozenInstanceError."""
        data = PipelineData()
        with pytest.raises(FrozenInstanceError):
            data.errors = []  # type: ignore[misc]

    def test_frozen_instance_error_on_metadata_mutation(self) -> None:
        """Attempting to set data.metadata = {} must raise FrozenInstanceError."""
        data = PipelineData()
        with pytest.raises(FrozenInstanceError):
            data.metadata = {}  # type: ignore[misc]

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
        assert data.chunks == []
        assert data2.chunks == [chunk]

        data3 = data.with_context("ctx")
        assert data.context == ""
        assert data3.context == "ctx"

        data4 = data.with_response(resp)
        assert data.response is None
        assert data4.response is resp

        data5 = data.add_error("err")
        assert data.errors == []
        assert data5.errors == ["err"]

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

        assert data.chunks == [chunk]
        assert data.context == "ctx"
        assert data.response is resp
        assert data.errors == ["e1"]

    def test_metadata_merge_compatibility(self) -> None:
        """Metadata must be mergeable via replace pattern."""
        from dataclasses import replace

        data = PipelineData(metadata={"a": 1})
        new_metadata = {**data.metadata, "b": 2}
        data2 = replace(data, metadata=new_metadata)

        assert data.metadata == {"a": 1}
        assert data2.metadata == {"a": 1, "b": 2}

    def test_default_values_compatible(self) -> None:
        """Default values must work as before."""
        data = PipelineData()
        assert data.query is None
        assert data.chunks == []
        assert data.context == ""
        assert data.response is None
        assert data.metadata == {}
        assert data.errors == []
