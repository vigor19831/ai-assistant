"""Event bus port — placeholder for future extension."""

from __future__ import annotations

from typing import Any

__all__ = ["IEventBus"]


class IEventBus:
    """Placeholder for pub/sub event bus.

    Future: integrate with RabbitMQ, Redis, or Kafka.
    """

    async def publish(self, event: str, payload: Any) -> None:
        """Publish an event to the bus."""
        ...

    async def subscribe(self, event: str, handler: Any) -> None:
        """Subscribe a handler to an event."""
        ...
