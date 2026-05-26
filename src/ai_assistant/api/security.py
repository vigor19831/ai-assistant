"""API security — rate limiting, request size, API key enforcement.

Security config is loaded ONCE at startup into AppState.config.security.
This module reads from AppState via get_state() or env var fallback.
No YAML reloading on hot path.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from typing import Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from ai_assistant.core.logger import get_logger

__all__ = [
    "APIKeyMiddleware",
    "apply_rate_limit",
    "check_request_size",
    "get_expected_api_key",
    "LimitMiddleware",
    "require_api_key",
    "reset_security_state",
    "SECURITY_MAX_BODY",
]

_logger = get_logger("security")

SECURITY_MAX_BODY = 10_485_760
bearer_scheme = HTTPBearer(auto_error=False)

# Mutable state for rare runtime key rotation (admin endpoint)
_override_api_key: str | None = None

_PUBLIC_PATHS: frozenset[str] = frozenset({
    "/",
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
})


class SecurityLimiter:
    def __init__(self, rate_limit: str = "100/minute") -> None:
        self.requests: dict[str, list[float]] = defaultdict(list)
        self.max_req, self.window = self._parse_rate_limit(rate_limit)

    def reset(self, rate_limit: str = "100/minute") -> None:
        """Clear all tracked requests and re-apply rate limit settings."""
        self.requests.clear()
        self.max_req, self.window = self._parse_rate_limit(rate_limit)

    @staticmethod
    def _parse_rate_limit(rate_str: str) -> tuple[int, float]:
        try:
            max_req, period = rate_str.split("/")
            return int(max_req), 60.0 if period == "minute" else 1.0
        except (ValueError, IndexError):
            _logger.warning(
                "Invalid rate_limit format %r, using default 100/minute",
                rate_str,
            )
            return 100, 60.0

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        self.requests[ip] = [t for t in self.requests[ip] if t > now - self.window]
        if not self.requests[ip]:
            del self.requests[ip]
        current = self.requests.get(ip, [])
        if len(current) >= self.max_req:
            return False
        self.requests[ip].append(now)
        return True


# Global limiter instance — never replaced, only reset
limiter = SecurityLimiter()


def get_expected_api_key() -> str | None:
    """Return API key from env var, runtime override, or None.

    Callers that have AppState should prefer state.config.security.api_key.
    This function exists for code paths without AppState access.
    """
    env_key: str | None = os.getenv("AI_API_KEY")
    if env_key:
        return env_key
    if _override_api_key is not None:
        return _override_api_key
    return None


def reset_security_state() -> None:
    """Reset mutable security state — used in tests and admin endpoints.

    Calls limiter.reset() so the global instance stays the same object,
    avoiding stale references imported by tests or middleware.
    """
    global _override_api_key
    _override_api_key = None
    limiter.reset()


def set_api_key(key: str | None) -> None:
    """Runtime API key rotation — called from admin endpoint."""
    global _override_api_key
    _override_api_key = key


class LimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        ip = request.client.host if request.client else "unknown"
        if not limiter.is_allowed(ip):
            return Response(
                "Rate limit exceeded",
                status_code=429,
                media_type="text/plain",
            )
        return await call_next(request)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Enforce API key on every request except public paths."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method == "OPTIONS":
            return await call_next(request)

        path = request.url.path
        if path in _PUBLIC_PATHS or path.startswith(("/docs/", "/redoc")):
            return await call_next(request)

        expected = get_expected_api_key()
        if not expected:
            return Response(
                "API key not configured",
                status_code=401,
                media_type="text/plain",
            )

        auth = request.headers.get("Authorization", "")
        if not auth:
            return Response(
                "Missing API key",
                status_code=401,
                media_type="text/plain",
            )

        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or token != expected:
            return Response(
                "Invalid API key",
                status_code=401,
                media_type="text/plain",
            )

        return await call_next(request)


async def check_request_size(request: Request) -> None:
    cl = request.headers.get("content-length")
    # Default max body size — can be overridden by caller with AppState
    max_sz = SECURITY_MAX_BODY
    if cl and int(cl) > int(max_sz):
        raise HTTPException(status_code=413, detail="Payload too large")


_bearer_dependency = Depends(bearer_scheme)


async def require_api_key(
    credentials: HTTPAuthorizationCredentials = _bearer_dependency,
) -> None:
    expected = get_expected_api_key()
    if not expected:
        raise HTTPException(status_code=401, detail="API key not configured")
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing API key")
    if credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def apply_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
