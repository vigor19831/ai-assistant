"""tests/test_domain.py — Foundation + domain layer tests.

Coverage: PipelineData, Messages, Chunks, ToolResult, Constants.
Design: Given/When/Then docstrings, one function per test case.
"""

from __future__ import annotations

import logging
from dataclasses import FrozenInstanceError, replace
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
from ai_assistant.core.domain.pipeline import PipelineData

logger = logging.getLogger(__name__)


# ───────────────────────────────────────────────
# PipelineData — functional behaviour
# ───────────────────────────────────────────────


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
        assert data2.errors == ("err",)
        assert data is not data2

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
        )
        data2 = data.add_error("new")

        assert data2.query is msg
        assert data2.chunks == (chunk,)
        assert data2.context == "ctx"
        assert data2.response is resp
        assert data2.errors == ("old", "new")
        assert data.errors == ("old",)  # original unchanged

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

    def test_slots_prevents_arbitrary_fields(self) -> None:
        """Given: PipelineData uses __slots__.
        When: arbitrary attribute is added.
        Then: AttributeError (no __dict__ to accept it)."""
        assert hasattr(PipelineData, "__slots__")
        data = PipelineData()
        assert not hasattr(data, "__dict__")


# ───────────────────────────────────────────────
# PipelineData — backward compatibility
# ───────────────────────────────────────────────


class TestPipelineDataCompatibility:
    """Given: downstream code relies on historical patterns.
    When: frozen PipelineData is introduced.
    Then: existing patterns continue to work."""

    def test_helper_methods_return_new_instances(self) -> None:
        """Given: populated PipelineData.
        When: each helper is called.
        Then: original is never mutated."""
        chunk = Chunk(
            id="c1",
            text="hello",
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        msg = UserMessage(text="query")
        resp = AssistantMessage(text="answer")

        data = PipelineData(query=msg)

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
        """Given: pipeline-style chaining is used.
        When: methods are chained fluently.
        Then: final state is correct."""
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

    def test_default_values_compatible(self) -> None:
        """Given: no arguments to constructor.
        When: PipelineData() is called.
        Then: sensible defaults are provided."""
        data = PipelineData()
        assert data.query is None
        assert data.chunks == ()
        assert data.context == ""
        assert data.response is None
        assert data.errors == ()
        assert data.embedder is None
        assert data.vector_store is None
        assert data.reranker is None
        assert data.llm is None
        assert data.pipeline_config is None
        assert data.query_embedding is None
        assert data.tokenizer_model is None
        assert data.rerank_filtered_out is None
        assert data.rerank_scores is None

    def test_frozen_rejects_direct_mutation(self) -> None:
        """Given: frozen PipelineData.
        When: direct field mutation is attempted.
        Then: FrozenInstanceError is raised."""
        data = PipelineData(embedder=None)
        with pytest.raises(FrozenInstanceError):
            data.embedder = None  # type: ignore[misc]


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

    def test_slots_prevents_arbitrary_fields(self) -> None:
        """Given: UserMessage uses __slots__.
        When: arbitrary attribute is added.
        Then: AttributeError."""
        assert hasattr(UserMessage, "__slots__")
        msg = UserMessage(text="hello")
        assert not hasattr(msg, "__dict__")


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

    def test_slots_prevents_arbitrary_fields(self) -> None:
        """Given: AssistantMessage uses __slots__.
        When: arbitrary attribute is added.
        Then: AttributeError."""
        assert hasattr(AssistantMessage, "__slots__")
        msg = AssistantMessage(text="hi")
        assert not hasattr(msg, "__dict__")


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

    def test_slots_prevents_arbitrary_fields(self) -> None:
        """Given: ToolMessage uses __slots__.
        When: arbitrary attribute is added.
        Then: AttributeError."""
        assert hasattr(ToolMessage, "__slots__")
        msg = ToolMessage(text="ok", call_id="c1")
        assert not hasattr(msg, "__dict__")


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

    def test_slots_prevents_arbitrary_fields(self) -> None:
        """Given: Chunk uses __slots__.
        When: arbitrary attribute is added.
        Then: AttributeError."""
        assert hasattr(Chunk, "__slots__")
        chunk = Chunk(id="c1", text="hello")
        assert not hasattr(chunk, "__dict__")


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

    def test_slots_prevents_arbitrary_fields(self) -> None:
        """Given: ChunkMetadata uses __slots__.
        When: arbitrary attribute is added.
        Then: AttributeError."""
        assert hasattr(ChunkMetadata, "__slots__")
        meta = ChunkMetadata(source="doc", index=0, total_chunks=1, source_uri=None)
        assert not hasattr(meta, "__dict__")


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
# Constants — immutability contracts
# ───────────────────────────────────────────────


class TestConstants:
    """Given: core constants define system-wide invariants.
    When: imported and inspected.
    Then: types and values are correct."""

    def test_no_info_phrases_is_frozenset(self) -> None:
        """Given: FROZEN_NO_INFO_PHRASES constant.
        When: inspected.
        Then: it is a frozenset of strings containing expected phrases."""
        from ai_assistant.core.constants import FROZEN_NO_INFO_PHRASES

        assert isinstance(FROZEN_NO_INFO_PHRASES, frozenset)
        assert all(isinstance(ph, str) for ph in FROZEN_NO_INFO_PHRASES)
        assert "not enough" in FROZEN_NO_INFO_PHRASES
        assert "у меня недостаточно" in FROZEN_NO_INFO_PHRASES


# ───────────────────────────────────────────────
# Prompts — caching behaviour
# ───────────────────────────────────────────────


def test_get_prompt_env_cached_once(tmp_path, monkeypatch):
    """Given: Jinja2 template directories for two versions.
    When: get_prompt is called multiple times.
    Then: Environment is constructed exactly once per version."""
    from ai_assistant.core import prompts as prompts_module

    v1 = tmp_path / "v1"
    v1.mkdir()
    (v1 / "dummy.j2").write_text("{{ x }}")

    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "dummy.j2").write_text("{{ x }}")

    monkeypatch.setattr(prompts_module, "_env_cache", {})
    monkeypatch.setattr(prompts_module, "__file__", str(tmp_path / "prompts.py"))

    with mock.patch.object(prompts_module, "Environment") as MockEnv:
        fake_template = mock.Mock()
        fake_template.render.side_effect = lambda **kw: "ok"
        fake_env = mock.Mock()
        fake_env.get_template.return_value = fake_template
        MockEnv.return_value = fake_env

        prompts_module.get_prompt("dummy", version="v1", x="a")
        prompts_module.get_prompt("dummy", version="v1", x="b")
        assert MockEnv.call_count == 1

        prompts_module.get_prompt("dummy", version="v2", x="c")
        assert MockEnv.call_count == 2


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
        with pytest.raises(ValueError, match="mode must be 'w' or 'wb'"):
            await atomic_write(str(target), "text", mode="x")  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_str_content_with_wb_mode_raises_type_error(self, tmp_path: Path) -> None:
        """Given: str content with mode='wb'.
        When: atomic_write is called.
        Then: TypeError is raised."""
        from ai_assistant.core.io_utils import atomic_write

        target = tmp_path / "out.bin"
        with pytest.raises(TypeError, match=r"Expected bytes for mode='wb'"):
            await atomic_write(str(target), "text", mode="wb")

    @pytest.mark.asyncio
    async def test_bytes_content_with_w_mode_raises_type_error(self, tmp_path: Path) -> None:
        """Given: bytes content with mode='w'.
        When: atomic_write is called.
        Then: TypeError is raised."""
        from ai_assistant.core.io_utils import atomic_write

        target = tmp_path / "out.txt"
        with pytest.raises(TypeError, match=r"Expected str for mode='w'"):
            await atomic_write(str(target), b"bytes", mode="w")

    @pytest.mark.asyncio
    async def test_oserror_on_dir_open_is_ignored(self, tmp_path: Path) -> None:
        """Given: os.open for directory fsync raises OSError (Windows).
        When: atomic_write completes write.
        Then: OSError on dir open is silently ignored; file is written."""
        from ai_assistant.core.io_utils import atomic_write

        target = tmp_path / "out.txt"
        real_os_open = os.open
        with patch("ai_assistant.core.io_utils.os.open") as mock_open:
            def fake_open(path, flags, *args, **kwargs):
                o_directory = getattr(os, "O_DIRECTORY", 0)
                if o_directory and (flags & o_directory):
                    raise OSError("no dir fsync")
                return real_os_open(path, flags, *args, **kwargs)
            mock_open.side_effect = fake_open
            await atomic_write(str(target), "hello", mode="w")
        assert target.read_text() == "hello"
