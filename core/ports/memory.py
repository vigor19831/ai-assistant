"""Long-term memory port — persistent conversation and agent memory.

Extends beyond IChatStorage (which is request-scoped history) to:
- Cross-session facts (user preferences, learned information)
- Episodic memory (summarized past conversations)
- Semantic memory (knowledge graph, embeddings of facts)

This is the foundation for agents that remember you across months.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

__all__ = ["MemoryEntry", "ILongTermMemory"]


@dataclass
class MemoryEntry:
    """Single fact or episode in long-term memory."""

    id: str = ""  # Database-assigned ID
    content: str = ""
    source: str = "conversation"  # "conversation", "explicit", "inferred"
    importance: float = 1.0  # 0.0-1.0, for retention priority
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)


class ILongTermMemory(ABC):
    """Persistent memory that survives individual sessions."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def add(self, user_id: str, entry: MemoryEntry) -> None:
        """Store a new memory entry for a user."""
        ...

    @abstractmethod
    async def get(
        self, user_id: str, query: str | None = None, limit: int = 20
    ) -> list[MemoryEntry]:
        """Retrieve relevant memories. If query provided, use semantic search."""
        ...

    @abstractmethod
    async def forget(self, user_id: str, entry_id: str) -> bool:
        """Remove a specific memory entry."""
        ...

    @abstractmethod
    async def consolidate(self, user_id: str) -> None:
        """Compress and summarize old memories (run periodically)."""
        ...
