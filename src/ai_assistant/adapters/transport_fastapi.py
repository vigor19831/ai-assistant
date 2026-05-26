"""FastAPI transport adapter."""

from __future__ import annotations

from typing import Any

from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.transport import ITransport
from ai_assistant.core.registry import register

__all__ = ["FastAPITransport"]

_logger = get_logger("transport.fastapi")


@register("transport", "fastapi")
class FastAPITransport(ITransport):
    """FastAPI HTTP/WebSocket server."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.host: str = getattr(config, "host", "0.0.0.0")
        self.port: int = getattr(config, "port", 8000)
        self._server: Any | None = None

    async def start(self) -> None:
        import uvicorn

        from ai_assistant.main import app

        _logger.info("Starting FastAPI on %s:%d", self.host, self.port)
        uvicorn_config = uvicorn.Config(app, host=self.host, port=self.port)
        self._server = uvicorn.Server(uvicorn_config)
        await self._server.serve()

    async def stop(self) -> None:
        if self._server is not None:
            _logger.info("Stopping FastAPI server")
            self._server.should_exit = True