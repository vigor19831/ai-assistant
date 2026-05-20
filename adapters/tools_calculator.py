"""Calculator tool — allows LLM to perform math operations."""

from __future__ import annotations

import json
import operator
from typing import Any

from core.ports.tools import ITool, ToolResult, ToolSpec
from core.registry import register


@register("tool", "calculator")
class CalculatorTool(ITool):
    """Simple calculator for LLM function calling."""

    def __init__(self, config: Any = None) -> None:
        self._ops = {
            "add": operator.add,
            "subtract": operator.sub,
            "multiply": operator.mul,
            "divide": operator.truediv,
        }

    @property
    def spec(self) -> ToolSpec:
        """Schema describing the calculator for LLM."""
        return ToolSpec(
            name="calculator",
            description=(
                "Perform basic math operations: add, subtract, multiply, divide"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "Math operation to perform",
                    },
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["operation", "a", "b"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the calculation."""
        try:
            op_name = arguments.get("operation")
            a = float(arguments.get("a", 0))
            b = float(arguments.get("b", 0))

            if op_name not in self._ops:
                return ToolResult(
                    call_id="",
                    output="",
                    error=f"Unknown operation: {op_name}",
                    is_error=True,
                )

            if op_name == "divide" and b == 0:
                return ToolResult(
                    call_id="",
                    output="",
                    error="Division by zero",
                    is_error=True,
                )

            result = self._ops[op_name](a, b)
            return ToolResult(
                call_id="",
                output=json.dumps({"result": result}),
            )

        except Exception as e:
            return ToolResult(
                call_id="",
                output="",
                error=str(e),
                is_error=True,
            )
