"""Core immutability and PipelineData mutation guards."""

from __future__ import annotations

import pytest
from dataclasses import FrozenInstanceError
from unittest import mock

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineData


class TestPipelineDataFrozen:
    """Tests for frozen PipelineData — must use replace(), never mutate."""

    def test_frozen_instance_error_on_context_mutation(self) -> None:
        """Attempting to set data.context = 'x' must raise FrozenInstanceError."""
        data = PipelineData()
        with pytest.raises(FrozenInstanceError):
            data.context = "x"  # type: ignore[misc]

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

    def test_add_error_returns_new_instance(self) -> None:
        """add_error() must return a new PipelineData; original must be unchanged."""
        data = PipelineData()
        data2 = data.add_error("err")

        assert data.errors == []
        assert data2.errors == ["err"]
        assert data is not data2

    def test_add_error_preserves_other_fields(self) -> None:
        """add_error() must preserve all other fields."""
        chunk = Chunk(
            id="c1",
            text="hello",
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        msg = UserMessage(text="query")
        resp = AssistantMessage(text="answer")
        data = PipelineData(
            query=msg,
            chunks=[chunk],
            context="ctx",
            response=resp,
            metadata={"k": "v"},
            errors=["old"],
        )
        data2 = data.add_error("new")

        assert data2.query is msg
        assert data2.chunks == [chunk]
        assert data2.context == "ctx"
        assert data2.response is resp
        assert data2.metadata == {"k": "v"}
        assert data2.errors == ["old", "new"]
        # Original unchanged
        assert data.errors == ["old"]

    def test_with_chunks_returns_new_instance(self) -> None:
        """with_chunks() must return a new PipelineData with updated chunks."""
        chunk = Chunk(
            id="c1",
            text="hello",
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        data = PipelineData()
        data2 = data.with_chunks([chunk])

        assert data.chunks == []
        assert data2.chunks == [chunk]
        assert data is not data2

    def test_with_context_returns_new_instance(self) -> None:
        """with_context() must return a new PipelineData with updated context."""
        data = PipelineData()
        data2 = data.with_context("new context")

        assert data.context == ""
        assert data2.context == "new context"
        assert data is not data2

    def test_with_response_returns_new_instance(self) -> None:
        """with_response() must return a new PipelineData with updated response."""
        resp = AssistantMessage(text="hi")
        data = PipelineData()
        data2 = data.with_response(resp)

        assert data.response is None
        assert data2.response is resp
        assert data is not data2

    def test_chaining_methods(self) -> None:
        """Methods must be chainable via intermediate variables."""
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

        assert data.chunks == [chunk]
        assert data.context == "ctx"
        assert data.response is resp
        assert data.errors == ["e1", "e2"]


def test_get_prompt_env_cached_once(tmp_path, monkeypatch):
    """Environment constructor called exactly once per version on hot path."""
    from ai_assistant.core import prompts as prompts_module

    # Prepare fake template directories
    v1 = tmp_path / "v1"
    v1.mkdir()
    (v1 / "dummy.j2").write_text("{{ x }}")

    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "dummy.j2").write_text("{{ x }}")

    # Reset cache and repoint module's __file__ so Path(__file__).parent == tmp_path
    monkeypatch.setattr(prompts_module, "_env_cache", {})
    monkeypatch.setattr(prompts_module, "__file__", str(tmp_path / "prompts.py"))

    with mock.patch.object(prompts_module, "Environment") as MockEnv:
        fake_template = mock.Mock()
        fake_template.render.side_effect = lambda **kw: "ok"
        fake_env = mock.Mock()
        fake_env.get_template.return_value = fake_template
        MockEnv.return_value = fake_env

        # Two calls with the same version → Environment constructed once
        prompts_module.get_prompt("dummy", version="v1", x="a")
        prompts_module.get_prompt("dummy", version="v1", x="b")
        assert MockEnv.call_count == 1

        # Different version → new Environment
        prompts_module.get_prompt("dummy", version="v2", x="c")
        assert MockEnv.call_count == 2


class TestConstants:
    """Tests for core constants."""

    def test_no_info_phrases_is_frozenset(self) -> None:
        """FROZEN_NO_INFO_PHRASES must be a frozenset of strings."""
        from ai_assistant.core.constants import FROZEN_NO_INFO_PHRASES

        assert isinstance(FROZEN_NO_INFO_PHRASES, frozenset)
        assert all(isinstance(ph, str) for ph in FROZEN_NO_INFO_PHRASES)
        assert "not enough" in FROZEN_NO_INFO_PHRASES
        assert "у меня недостаточно" in FROZEN_NO_INFO_PHRASES


class TestToolRegistryErrorHandling:
    """Tests for ToolRegistry.dispatch error handling."""

    async def test_dispatch_logs_exception_on_tool_failure(self) -> None:
        """Tool raising ValueError must trigger logger.exception with tool name."""
        from unittest.mock import MagicMock, patch

        from ai_assistant.core.ports.tools import ToolCall
        from ai_assistant.core.tool_registry import ToolRegistry

        registry = ToolRegistry()
        mock_tool = MagicMock()
        mock_tool.spec.name = "failing_tool"
        mock_tool.execute.side_effect = ValueError("boom")

        registry.register(mock_tool)

        call = ToolCall(tool_name="failing_tool", arguments={}, call_id="call-1")

        with patch("ai_assistant.core.tool_registry._logger.exception") as mock_exc:
            result = await registry.dispatch(call)

        assert result.is_error is True
        assert result.error == "Tool execution failed"
        assert result.output == ""
        mock_exc.assert_called_once_with("Tool %s failed", "failing_tool")
