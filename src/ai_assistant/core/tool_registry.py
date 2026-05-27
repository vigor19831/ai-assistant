"""Tool registry — manages available tools for LLM."""

from __future__ import annotations

import warnings

from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.tools import (
    ITool,
    IToolRegistry,
    ToolCall,
    ToolResult,
    ToolSpec,
)

__all__ = ["ToolRegistry"]

_logger = get_logger("tool_registry")


class ToolRegistry(IToolRegistry):
    """Concrete tool registry using in-memory dict storage."""

    def __init__(self) -> None:
        self._tools: dict[str, ITool] = {}

    def register(self, tool: ITool) -> None:
        """Add a tool to registry."""
        name = tool.spec.name
        if name in self._tools:
            warnings.warn(
                f"Tool '{name}' already registered; overwriting",
                stacklevel=2,
            )
        self._tools[name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool from registry."""
        if name not in self._tools:
            _logger.warning("Unregister unknown tool: %s", name)
        self._tools.pop(name, None)

    def list_tools(self) -> list[ToolSpec]:
        """Return schemas of all registered tools."""
        return [t.spec for t in self._tools.values()]

    def get_tool(self, name: str) -> ITool | None:
        """Get tool by name."""
        return self._tools.get(name)

    async def dispatch(self, call: ToolCall) -> ToolResult:
        """Execute a tool call."""
        tool = self._tools.get(call.tool_name)
        if tool is None:
            return ToolResult(
                call_id=call.call_id,
                output="",
                error=f"Tool '{call.tool_name}' not found",
                is_error=True,
            )
        try:
            return await tool.execute(call.call_id, call.arguments)
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception:
            _logger.exception("Tool %s failed", call.tool_name)
            return ToolResult(
                call_id=call.call_id,
                output="",
                error="Tool execution failed",
                is_error=True,
            )
