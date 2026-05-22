"""Calculator tool — allows LLM to perform math operations."""

from __future__ import annotations

import json
import math
import operator
from typing import Any

from core.ports.tools import ITool, ToolResult, ToolSpec
from core.registry import register

__all__ = ["CalculatorTool"]


@register("tool", "calculator")
class CalculatorTool(ITool):
    """Simple calculator for LLM function calling."""

    def __init__(self, config: Any = None) -> None:
        super().__init__(config)
        self._ops: dict[str, Any] = {
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
                        "enum": list(self._ops.keys()),
                        "description": "Math operation to perform",
                    },
                    "a": {
                        "type": "number",
                        "description": "First number",
                    },
                    "b": {
                        "type": "number",
                        "description": "Second number",
                    },
                },
                "required": ["operation", "a", "b"],
            },
        )

    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute the calculation."""
        op_name = arguments.get("operation")
        if not isinstance(op_name, str) or op_name not in self._ops:
            return ToolResult(
                call_id=call_id,
                output="",
                error=f"Unknown or missing operation: {op_name}",
                is_error=True,
            )

        try:
            a = float(arguments["a"])
            b = float(arguments["b"])
        except (KeyError, TypeError, ValueError) as exc:
            return ToolResult(
                call_id=call_id,
                output="",
                error=f"Invalid arguments: {exc}",
                is_error=True,
            )

        if op_name == "divide" and b == 0:
            return ToolResult(
                call_id=call_id,
                output="",
                error="Division by zero",
                is_error=True,
            )

        try:
            result = self._ops[op_name](a, b)
            if math.isinf(result) or math.isnan(result):
                return ToolResult(
                    call_id=call_id,
                    output="",
                    error="Result is infinite or NaN",
                    is_error=True,
                )
            return ToolResult(
                call_id=call_id,
                output=json.dumps({"result": result}),
            )
        except (TypeError, ValueError) as exc:
            return ToolResult(
                call_id=call_id,
                output="",
                error=str(exc),
                is_error=True,
            )
