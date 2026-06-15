"""Adapters package — eager imports trigger @register side-effects.

All adapters self-register via @register(port, name) on class definition.
Factory does lazy lookup in the registry — no if/elif branching.
"""

from __future__ import annotations

from ai_assistant.adapters._registry import register
from ai_assistant.adapters.factory import create_adapter

__all__ = ["create_adapter", "register"]
