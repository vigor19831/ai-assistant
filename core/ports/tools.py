"""Tool port — external capabilities (calculator, search, APIs, code execution).

This enables the LLM to call external tools, similar to OpenAI function calling
but framework-agnostic. ToolRegistry manages available tools; ITool is the
interface for individual tool implementations.

Future directions:
- MCP (Model Context Protocol) adapter
- Local code execution sandbox
- Hardware control (robotics, IoT)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolSpec:
    """Schema describing a tool for LLM consumption.

    Mirrors OpenAI function schema but framework-agnostic.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    required: list[str] = field(default_factory=list)


@dataclass
class ToolCall:
    """A request from LLM to invoke a tool."""

    tool_name: str
    arguments: dict[str, Any]
    call_id: str = ""  # For matching response to request


@dataclass
class ToolResult:
    """Result of a tool invocation."""

    call_id: str
    output: str | dict[str, Any]
    error: str | None = None
    is_error: bool = False


class ITool(ABC):
    """Single tool implementation."""

    @property
    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return the schema for this tool."""
        ...

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the tool with given arguments."""
        ...


class IToolRegistry(ABC):
    """Pure interface for tool registry — implementations provide storage strategy."""

    @abstractmethod
    def register(self, tool: ITool) -> None:
        """Add a tool to registry."""
        ...

    @abstractmethod
    def unregister(self, name: str) -> None:
        """Remove a tool from registry."""
        ...

    @abstractmethod
    def list_tools(self) -> list[ToolSpec]:
        """Return schemas of all registered tools."""
        ...

    @abstractmethod
    def get_tool(self, name: str) -> ITool | None:
        """Get tool by name."""
        ...

    @abstractmethod
    async def dispatch(self, call: ToolCall) -> ToolResult:
        """Execute a tool call by dispatching to the registered tool."""
        ...
