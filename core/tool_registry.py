"""Tool registry — manages available tools for LLM."""

from __future__ import annotations

from core.ports.tools import ITool, IToolRegistry, ToolCall, ToolResult, ToolSpec


class ToolRegistry(IToolRegistry):
    """Concrete tool registry using in-memory dict storage."""

    def __init__(self) -> None:
        self._tools: dict[str, ITool] = {}

    def register(self, tool: ITool) -> None:
        """Add a tool to registry."""
        self._tools[tool.spec.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool from registry."""
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
            return await tool.execute(call.arguments)
        except Exception as e:
            return ToolResult(
                call_id=call.call_id,
                output="",
                error=str(e),
                is_error=True,
            )
