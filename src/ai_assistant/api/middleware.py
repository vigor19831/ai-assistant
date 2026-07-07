"""FastAPI middleware for request metrics."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Response  # noqa: TC002  # BaseHTTPMiddleware dispatch uses runtime
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import (
    Request,  # noqa: TC002  # BaseHTTPMiddleware dispatch uses runtime
)

from ai_assistant.core import metrics

__all__ = ["MetricsMiddleware"]


class MetricsMiddleware(BaseHTTPMiddleware):
    """Count requests and record latency per path."""

    def __init__(
        self,
        app: Callable[..., Any],
        allowed_hosts: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.allowed_hosts = allowed_hosts or []

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if self.allowed_hosts:
            host = request.headers.get("host", "").split(":")[0]
            if host not in self.allowed_hosts:
                return Response(
                    content="Invalid host header",
                    status_code=400,
                )

        method = request.method
        path = request.url.path
        start = time.perf_counter()
        response: Response | None = None
        status = "500"
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        except StarletteHTTPException as exc:
            status = str(exc.status_code)
            raise
        finally:
            duration = time.perf_counter() - start
            # Collapse dynamic path segments to the route pattern to prevent
            # Prometheus cardinality explosion (e.g. /reindex/status/abc-123
            # becomes /reindex/status/{task_id}).
            # Unmatched routes get a fixed label to prevent arbitrary-URL
            # cardinality explosion on 404s.
            route = request.scope.get("route")
            path = getattr(route, "path", path) if route is not None else "/__unmatched"
            metrics.increment_counter(
                "ai_assistant_requests_total",
                labels={"method": method, "path": path, "status": status},
            )
            metrics.observe_histogram(
                "ai_assistant_request_duration_seconds",
                value=duration,
                labels={"path": path},
            )
