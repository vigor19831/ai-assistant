"""FastAPI middleware for request metrics."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Response  # noqa: TC002  # BaseHTTPMiddleware dispatch uses runtime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import (
    Request,  # noqa: TC002  # BaseHTTPMiddleware dispatch uses runtime
)

from ai_assistant.core.metrics import increment_counter, observe_histogram

__all__ = ["MetricsMiddleware"]


class MetricsMiddleware(BaseHTTPMiddleware):
    """Count requests and record latency per path."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method
        path = request.url.path
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.perf_counter() - start
            status = str(response.status_code) if response is not None else "500"
            increment_counter(
                "ai_assistant_requests_total",
                labels={"method": method, "path": path, "status": status},
            )
            observe_histogram(
                "ai_assistant_request_duration_seconds",
                value=duration,
                labels={"path": path},
            )
