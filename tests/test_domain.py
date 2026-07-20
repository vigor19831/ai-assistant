"""tests/test_domain.py — Foundation + domain layer tests.

Coverage: PipelineData, Messages, Chunks, ToolResult, Constants.
Design: Given/When/Then docstrings, one function per test case.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import os
from unittest import mock
from unittest.mock import patch

import pytest

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import (
    AssistantMessage,
    ToolMessage,
    UserMessage,
)
from ai_assistant.core.domain.pipeline import PipelineConfig, PipelineData


# ───────────────────────────────────────────────
# PipelineData — functional behaviour
# ───────────────────────────────────────────────


class TestPipelineConfig:
    """Given: PipelineConfig validates pipeline parameters.
    When: constructed with invalid values.
    Then: ValueError is raised for invalid input."""

    def test_top_k_less_than_one_raises_value_error(self) -> None:
        """Given: top_k is 0.
        When: PipelineConfig is constructed.
        Then: ValueError with descriptive message is raised."""
        with pytest.raises(ValueError, match="top_k must be >= 1, got 0"):
            PipelineConfig(top_k=0)

    def test_top_k_negative_raises_value_error(self) -> None:
        """Given: top_k is -1.
        When: PipelineConfig is constructed.
        Then: ValueError with descriptive message is raised."""
        with pytest.raises(ValueError, match="top_k must be >= 1, got -1"):
            PipelineConfig(top_k=-1)

    def test_valid_top_k_accepted(self) -> None:
        """Given: top_k is 1.
        When: PipelineConfig is constructed.
        Then: instance is created without error."""
        cfg = PipelineConfig(top_k=1)
        assert cfg.top_k == 1


class TestPipelineDataFunctional:
    """Given: PipelineData is the immutable carrier of pipeline state.
    When: helper methods are called.
    Then: new instances are returned; originals remain untouched."""

    def test_add_error_returns_new_instance(self) -> None:
        """Given: empty PipelineData.
        When: add_error() is called.
        Then: new instance with error is returned; original is unchanged."""
        data = PipelineData()
        data2 = data.add_error("err")

        assert data.errors == ()
        assert data.error_details == ()
        assert data2.errors == ("err",)
        assert data2.error_details == (None,)
        assert data is not data2

    def test_add_error_with_detail(self) -> None:
        """Given: add_error called with detail.
        When: error and detail are recorded.
        Then: both tuples match; lengths equal."""
        data = PipelineData().add_error("err", detail="connection timeout")
        assert data.errors == ("err",)
        assert data.error_details == ("connection timeout",)

    def test_add_error_without_detail(self) -> None:
        """Given: add_error called without detail.
        When: error is recorded.
        Then: detail is None."""
        data = PipelineData().add_error("err")
        assert data.errors == ("err",)
        assert data.error_details == (None,)

    def test_error_and_detail_lengths_match(self) -> None:
        """Given: multiple errors with mixed detail presence.
        When: errors and details recorded.
        Then: tuples always same length."""
        data = (
            PipelineData()
            .add_error("a", detail="x")
            .add_error("b")
            .add_error("c", detail="y")
        )
        assert len(data.errors) == 3
        assert len(data.error_details) == 3
        assert data.error_details == ("x", None, "y")

    def test_add_error_preserves_other_fields(self) -> None:
        """Given: fully populated PipelineData.
        When: add_error() appends a new error.
        Then: all other fields are preserved; error is appended."""
        chunk = Chunk(
            id="c1",
            text="hello",
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        msg = UserMessage(text="query")
        resp = AssistantMessage(text="answer")
        data = PipelineData(
            query=msg,
            chunks=(chunk,),
            context="ctx",
            response=resp,
            errors=("old",),
            error_details=("old_detail",),
        )
        data2 = data.add_error("new", detail="new_detail")

        assert data2.query is msg
        assert data2.chunks == (chunk,)
        assert data2.context == "ctx"
        assert data2.response is resp
        assert data2.errors == ("old", "new")
        assert data2.error_details == ("old_detail", "new_detail")
        assert data.errors == ("old",)  # original unchanged
        assert data.error_details == ("old_detail",)  # original unchanged

    def test_with_chunks_returns_new_instance(self) -> None:
        """Given: empty PipelineData.
        When: with_chunks() is called with a list.
        Then: new instance holds tuple of chunks; original is empty."""
        chunk = Chunk(
            id="c1",
            text="hello",
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        data = PipelineData()
        data2 = data.with_chunks([chunk])

        assert data.chunks == ()
        assert data2.chunks == (chunk,)
        assert data is not data2

    def test_with_context_returns_new_instance(self) -> None:
        """Given: empty PipelineData.
        When: with_context() is called.
        Then: new instance holds context; original is empty."""
        data = PipelineData()
        data2 = data.with_context("new context")

        assert data.context == ""
        assert data2.context == "new context"
        assert data is not data2

    def test_with_response_returns_new_instance(self) -> None:
        """Given: empty PipelineData.
        When: with_response() is called.
        Then: new instance holds response; original is None."""
        resp = AssistantMessage(text="hi")
        data = PipelineData()
        data2 = data.with_response(resp)

        assert data.response is None
        assert data2.response is resp
        assert data is not data2

    def test_with_embedder_returns_new_instance(self) -> None:
        """Given: empty PipelineData.
        When: replace() is called with embedder.
        Then: new instance holds embedder; original is None."""
        class FakeEmbedder:
            pass
        embedder = FakeEmbedder()
        data = PipelineData()
        data2 = replace(data, embedder=embedder)

        assert data.embedder is None
        assert data2.embedder is embedder
        assert data is not data2

    def test_with_vector_store_returns_new_instance(self) -> None:
        """Given: empty PipelineData.
        When: replace() is called with vector_store.
        Then: new instance holds vector_store; original is None."""
        class FakeVS:
            pass
        vs = FakeVS()
        data = PipelineData()
        data2 = replace(data, vector_store=vs)

        assert data.vector_store is None
        assert data2.vector_store is vs
        assert data is not data2

    def test_with_llm_returns_new_instance(self) -> None:
        """Given: empty PipelineData.
        When: replace() is called with llm.
        Then: new instance holds llm; original is None."""
        class FakeLLM:
            pass
        llm = FakeLLM()
        data = PipelineData()
        data2 = replace(data, llm=llm)

        assert data.llm is None
        assert data2.llm is llm
        assert data is not data2

    def test_chaining_methods(self) -> None:
        """Given: empty PipelineData.
        When: methods are chained via intermediate variables.
        Then: final instance carries all accumulated state."""
        chunk = Chunk(
            id="c1",
            text="hello",
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        resp = AssistantMessage(text="answer")
        data = PipelineData()
        data = data.with_chunks([chunk])
        data = data.with_context("ctx")
        data = data.with_response(resp)
        data = data.add_error("e1")
        data = data.add_error("e2")

        assert data.chunks == (chunk,)
        assert data.context == "ctx"
        assert data.response is resp
        assert data.errors == ("e1", "e2")
        assert data.error_details == (None, None)

    def test_chunks_type_is_tuple(self) -> None:
        """Given: chunks passed as tuple.
        When: PipelineData is constructed.
        Then: chunks remains a tuple."""
        data = PipelineData(chunks=(Chunk(id="c", text="t"),))
        assert isinstance(data.chunks, tuple)

    def test_errors_type_is_tuple(self) -> None:
        """Given: errors passed as tuple.
        When: PipelineData is constructed.
        Then: errors remains a tuple."""
        data = PipelineData(errors=("e1",))
        assert isinstance(data.errors, tuple)


# ───────────────────────────────────────────────
# PipelineData — frozen immutability guards
# ───────────────────────────────────────────────


class TestPipelineDataFrozen:
    """Given: PipelineData is frozen (slots=True, frozen=True).
    When: direct field mutation is attempted.
    Then: FrozenInstanceError is raised."""

    def test_frozen_query_mutation(self) -> None:
        """Given: PipelineData with query.
        When: query is reassigned.
        Then: FrozenInstanceError."""
        data = PipelineData(query=UserMessage(text="q"))
        with pytest.raises(FrozenInstanceError):
            data.query = None  # type: ignore[misc]

    def test_frozen_chunks_mutation(self) -> None:
        """Given: empty PipelineData.
        When: chunks are reassigned.
        Then: FrozenInstanceError."""
        data = PipelineData()
        with pytest.raises(FrozenInstanceError):
            data.chunks = ()  # type: ignore[misc]

    def test_frozen_context_mutation(self) -> None:
        """Given: empty PipelineData.
        When: context is reassigned.
        Then: FrozenInstanceError."""
        data = PipelineData()
        with pytest.raises(FrozenInstanceError):
            data.context = "x"  # type: ignore[misc]

    def test_frozen_response_mutation(self) -> None:
        """Given: PipelineData with response.
        When: response is reassigned.
        Then: FrozenInstanceError."""
        data = PipelineData(response=AssistantMessage(text="r"))
        with pytest.raises(FrozenInstanceError):
            data.response = None  # type: ignore[misc]

    def test_frozen_embedder_mutation(self) -> None:
        """Given: PipelineData with embedder.
        When: embedder is reassigned.
        Then: FrozenInstanceError."""
        class FakeEmbedder:
            pass
        data = PipelineData(embedder=FakeEmbedder())
        with pytest.raises(FrozenInstanceError):
            data.embedder = None  # type: ignore[misc]

    def test_frozen_vector_store_mutation(self) -> None:
        """Given: PipelineData with vector_store.
        When: vector_store is reassigned.
        Then: FrozenInstanceError."""
        class FakeVS:
            pass
        data = PipelineData(vector_store=FakeVS())
        with pytest.raises(FrozenInstanceError):
            data.vector_store = None  # type: ignore[misc]

    def test_frozen_errors_mutation(self) -> None:
        """Given: empty PipelineData.
        When: errors are reassigned.
        Then: FrozenInstanceError."""
        data = PipelineData()
        with pytest.raises(FrozenInstanceError):
            data.errors = ()  # type: ignore[misc]

    def test_frozen_trace_id_mutation(self) -> None:
        """Given: empty PipelineData.
        When: trace_id is reassigned.
        Then: FrozenInstanceError."""
        data = PipelineData()
        with pytest.raises(FrozenInstanceError):
            data.trace_id = "x"  # type: ignore[misc]

    # Removed: testing __slots__ is an implementation detail.
    # FrozenInstanceError tests above are sufficient for immutability.


# Removed: TestPipelineDataCompatibility duplicated TestPipelineDataFunctional
# and TestPipelineDataFrozen. FrozenInstanceError and helper-method tests above
# are sufficient.


# ───────────────────────────────────────────────
# Messages — construction and immutability
# ───────────────────────────────────────────────


class TestUserMessage:
    """Given: UserMessage represents a user query.
    When: constructed and inspected.
    Then: fields are correct; instance is frozen."""

    def test_construction_with_text(self) -> None:
        """Given: text content.
        When: UserMessage is constructed.
        Then: text is set."""
        msg = UserMessage(text="hello")
        assert msg.text == "hello"

    def test_construction_with_metadata(self) -> None:
        """Given: text and metadata.
        When: UserMessage is constructed.
        Then: metadata is preserved."""
        msg = UserMessage(text="hello", metadata={"lang": "en"})
        assert msg.metadata == {"lang": "en"}

    def test_frozen_rejects_text_mutation(self) -> None:
        """Given: constructed UserMessage.
        When: text is reassigned.
        Then: FrozenInstanceError."""
        msg = UserMessage(text="hello")
        with pytest.raises(FrozenInstanceError):
            msg.text = "world"  # type: ignore[misc]

    # Removed: testing __slots__ is an implementation detail.


class TestAssistantMessage:
    """Given: AssistantMessage represents an AI response.
    When: constructed and inspected.
    Then: fields are correct; instance is frozen."""

    def test_construction_with_text(self) -> None:
        """Given: text content.
        When: AssistantMessage is constructed.
        Then: text is set."""
        msg = AssistantMessage(text="hi there")
        assert msg.text == "hi there"

    def test_construction_with_tool_calls(self) -> None:
        """Given: text and tool_calls.
        When: AssistantMessage is constructed.
        Then: tool_calls are preserved."""
        msg = AssistantMessage(text="ok", tool_calls=[{"id": "t1"}])
        assert msg.tool_calls == [{"id": "t1"}]

    def test_frozen_rejects_text_mutation(self) -> None:
        """Given: constructed AssistantMessage.
        When: text is reassigned.
        Then: FrozenInstanceError."""
        msg = AssistantMessage(text="hi")
        with pytest.raises(FrozenInstanceError):
            msg.text = "bye"  # type: ignore[misc]

    def test_frozen_rejects_tool_calls_mutation(self) -> None:
        """Given: constructed AssistantMessage with tool_calls.
        When: tool_calls are reassigned.
        Then: FrozenInstanceError."""
        msg = AssistantMessage(text="ok", tool_calls=[])
        with pytest.raises(FrozenInstanceError):
            msg.tool_calls = []  # type: ignore[misc]

    # Removed: testing __slots__ is an implementation detail.


class TestToolMessage:
    """Given: ToolMessage represents a tool execution result.
    When: constructed and inspected.
    Then: fields are correct; instance is frozen."""

    def test_construction_with_content_and_call_id(self) -> None:
        """Given: content and tool_call_id.
        When: ToolMessage is constructed.
        Then: both fields are set."""
        msg = ToolMessage(text="ok", call_id="c1")
        assert msg.text == "ok"
        assert msg.call_id == "c1"

    def test_construction_with_metadata(self) -> None:
        """Given: content, tool_call_id, and metadata.
        When: ToolMessage is constructed.
        Then: metadata is preserved."""
        msg = ToolMessage(text="data", call_id="c1", metadata={"k": "v"})
        assert msg.text == "data"
        assert msg.call_id == "c1"
        assert msg.metadata == {"k": "v"}

    def test_frozen_rejects_text_mutation(self) -> None:
        """Given: constructed ToolMessage.
        When: text is reassigned.
        Then: FrozenInstanceError."""
        msg = ToolMessage(text="ok", call_id="c1")
        with pytest.raises(FrozenInstanceError):
            msg.text = "new"  # type: ignore[misc]

    def test_frozen_rejects_tool_call_id_mutation(self) -> None:
        """Given: constructed ToolMessage.
        When: tool_call_id is reassigned.
        Then: FrozenInstanceError."""
        msg = ToolMessage(text="ok", call_id="c1")
        with pytest.raises(FrozenInstanceError):
            msg.call_id = "c2"  # type: ignore[misc]

    # Removed: testing __slots__ is an implementation detail.


# ───────────────────────────────────────────────
# Chunks — construction and immutability
# ───────────────────────────────────────────────


class TestChunk:
    """Given: Chunk represents a document fragment.
    When: constructed and inspected.
    Then: fields are correct; instance is frozen."""

    def test_construction_with_id_and_text(self) -> None:
        """Given: id and text.
        When: Chunk is constructed.
        Then: both fields are set."""
        chunk = Chunk(id="c1", text="hello world")
        assert chunk.id == "c1"
        assert chunk.text == "hello world"

    def test_construction_with_metadata(self) -> None:
        """Given: id, text, and metadata.
        When: Chunk is constructed.
        Then: metadata is preserved."""
        meta = ChunkMetadata(source="doc-1", index=0, total_chunks=1)
        chunk = Chunk(id="c1", text="hello", metadata=meta)
        assert chunk.metadata == meta
        assert chunk.metadata.source == "doc-1"
        assert chunk.metadata.index == 0
        assert chunk.metadata.total_chunks == 1

    def test_frozen_rejects_id_mutation(self) -> None:
        """Given: constructed Chunk.
        When: id is reassigned.
        Then: FrozenInstanceError."""
        chunk = Chunk(id="c1", text="hello")
        with pytest.raises(FrozenInstanceError):
            chunk.id = "c2"  # type: ignore[misc]

    def test_frozen_rejects_text_mutation(self) -> None:
        """Given: constructed Chunk.
        When: text is reassigned.
        Then: FrozenInstanceError."""
        chunk = Chunk(id="c1", text="hello")
        with pytest.raises(FrozenInstanceError):
            chunk.text = "world"  # type: ignore[misc]

    def test_frozen_rejects_metadata_mutation(self) -> None:
        """Given: constructed Chunk with metadata.
        When: metadata is reassigned.
        Then: FrozenInstanceError."""
        chunk = Chunk(id="c1", text="hello", metadata=ChunkMetadata(source="doc", index=0, total_chunks=1))
        with pytest.raises(FrozenInstanceError):
            chunk.metadata = ChunkMetadata(source="doc2", index=0, total_chunks=1)  # type: ignore[misc]

    # Removed: testing __slots__ is an implementation detail.


class TestChunkMetadata:
    """Given: ChunkMetadata describes chunk provenance.
    When: constructed and inspected.
    Then: fields are correct; instance is frozen."""

    def test_construction_with_all_fields(self) -> None:
        """Given: source, index, total_chunks, source_uri.
        When: ChunkMetadata is constructed.
        Then: all fields are set."""
        meta = ChunkMetadata(
            source="doc-1",
            index=3,
            total_chunks=10,
            source_uri="file:///tmp/doc.md",
        )
        assert meta.source == "doc-1"
        assert meta.index == 3
        assert meta.total_chunks == 10
        assert meta.source_uri == "file:///tmp/doc.md"

    def test_frozen_rejects_source_mutation(self) -> None:
        """Given: constructed ChunkMetadata.
        When: source is reassigned.
        Then: FrozenInstanceError."""
        meta = ChunkMetadata(source="doc", index=0, total_chunks=1)
        with pytest.raises(FrozenInstanceError):
            meta.source = "doc2"  # type: ignore[misc]

    def test_frozen_rejects_index_mutation(self) -> None:
        """Given: constructed ChunkMetadata.
        When: index is reassigned.
        Then: FrozenInstanceError."""
        meta = ChunkMetadata(source="doc", index=0, total_chunks=1)
        with pytest.raises(FrozenInstanceError):
            meta.index = 1  # type: ignore[misc]

    # Removed: testing __slots__ is an implementation detail.


# ───────────────────────────────────────────────
# ToolResult — frozen immutability
# ───────────────────────────────────────────────


class TestToolResultFrozen:
    """Given: ToolResult carries tool execution output.
    When: constructed and inspected.
    Then: all fields are present; instance is frozen."""

    def test_frozen_instance_error_on_error_mutation(self) -> None:
        """Given: ToolResult with output.
        When: error is reassigned.
        Then: FrozenInstanceError."""
        from ai_assistant.core.ports.tools import ToolResult

        result = ToolResult(call_id="c1", output="ok")
        with pytest.raises(FrozenInstanceError):
            result.error = "new error"  # type: ignore[misc]

    def test_frozen_instance_error_on_is_error_mutation(self) -> None:
        """Given: ToolResult with output.
        When: is_error is reassigned.
        Then: FrozenInstanceError."""
        from ai_assistant.core.ports.tools import ToolResult

        result = ToolResult(call_id="c1", output="ok")
        with pytest.raises(FrozenInstanceError):
            result.is_error = True  # type: ignore[misc]

    def test_frozen_instance_error_on_output_mutation(self) -> None:
        """Given: ToolResult with output.
        When: output is reassigned.
        Then: FrozenInstanceError."""
        from ai_assistant.core.ports.tools import ToolResult

        result = ToolResult(call_id="c1", output="ok")
        with pytest.raises(FrozenInstanceError):
            result.output = "new output"  # type: ignore[misc]

    def test_tool_result_constructed_with_all_fields(self) -> None:
        """Given: all fields provided.
        When: ToolResult is constructed.
        Then: every field is accessible."""
        from ai_assistant.core.ports.tools import ToolResult

        result = ToolResult(
            call_id="c1",
            output="data",
            error="fail",
            is_error=True,
        )
        assert result.call_id == "c1"
        assert result.output == "data"
        assert result.error == "fail"
        assert result.is_error is True


# ───────────────────────────────────────────────
# Prompts — caching behaviour
# ───────────────────────────────────────────────


# Removed: test_get_prompt_env_cached_once tested private _env_cache and __file__
# patching — implementation details, not public contract.


class TestAtomicWrite:
    """Given: atomic_write utility for safe file operations.
    When: called with various modes and content types.
    Then: correct behavior or appropriate TypeError/ValueError."""

    @pytest.mark.asyncio
    async def test_invalid_mode_raises_value_error(self, tmp_path: Path) -> None:
        """Given: invalid mode 'x'.
        When: atomic_write is called.
        Then: ValueError is raised."""
        from ai_assistant.core.io_utils import atomic_write

        target = tmp_path / "out.txt"
        with pytest.raises(ValueError):
            await atomic_write(str(target), "text", mode="x")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_str_content_with_wb_mode_raises_type_error(self, tmp_path: Path) -> None:
        """Given: str content with mode='wb'.
        When: atomic_write is called.
        Then: TypeError is raised."""
        from ai_assistant.core.io_utils import atomic_write

        target = tmp_path / "out.bin"
        with pytest.raises(TypeError):
            await atomic_write(str(target), "text", mode="wb")

    @pytest.mark.asyncio
    async def test_bytes_content_with_w_mode_raises_type_error(self, tmp_path: Path) -> None:
        """Given: bytes content with mode='w'.
        When: atomic_write is called.
        Then: TypeError is raised."""
        from ai_assistant.core.io_utils import atomic_write

        target = tmp_path / "out.txt"
        with pytest.raises(TypeError):
            await atomic_write(str(target), b"bytes", mode="w")

    # Removed: test_oserror_on_dir_open_is_ignored patched internal os.open
    # usage — implementation detail, not public contract.
