"""FastAPI transport adapter."""

from __future__ import annotations

from typing import Any

from core.ports.transport import ITransport
from core.registry import register


@register("transport", "fastapi")
class FastAPITransport(ITransport):
    """FastAPI HTTP/WebSocket server."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.host: str = config.host
        self.port: int = config.port

    async def start(self) -> None:
        import uvicorn

        from main import app

        config = uvicorn.Config(app, host=self.host, port=self.port)
        server = uvicorn.Server(config)
        await server.serve()

    async def stop(self) -> None:
        pass
