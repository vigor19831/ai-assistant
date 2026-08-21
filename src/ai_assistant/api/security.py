"""API security — API key enforcement via FastAPI dependency.

Security config is loaded ONCE at startup into AppState.config.security.
This module reads from AppState via request state or env var fallback.
No YAML reloading on hot path.
"""

from __future__ import annotations

import hmac
import os
import threading

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ai_assistant.core.logger import get_logger

__all__ = [
    "SECURITY_MAX_BODY",
    "check_request_size",
    "get_expected_api_key",
    "require_api_key",
    "set_api_key",
]

_logger = get_logger("security")

SECURITY_MAX_BODY = 10_485_760
bearer_scheme = HTTPBearer(auto_error=False)

# Mutable state for rare runtime key rotation (admin endpoint).
# WARNING: this is process-local. Runtime rotation does NOT propagate
# across uvicorn/gunicorn workers. Use env var AI_SECURITY_API_KEY
# for consistent key distribution in multiprocess deployments.
_override_api_key: str | None = None
_lock = threading.Lock()


def get_expected_api_key() -> str | None:
    """Return API key from runtime override, env var, or None.
    Runtime override takes precedence to allow active key rotation via admin API.
    """
    with _lock:
        if _override_api_key is not None:
            return _override_api_key
    return os.getenv("AI_SECURITY_API_KEY")


def set_api_key(key: str | None) -> None:
    """Runtime API key rotation — called from admin endpoint."""
    global _override_api_key
    with _lock:
        _override_api_key = key


async def check_request_size(
    request: Request,
    max_sz: int = SECURITY_MAX_BODY,
) -> None:
    """Check Content-Length header against size limit.

    Args:
        request: Incoming HTTP request.
        max_sz: Maximum allowed body size in bytes. Defaults to
            SECURITY_MAX_BODY when called without an explicit limit.

    NOTE: Chunked encoding (Transfer-Encoding: chunked) bypasses this
    check because Content-Length is absent. Full protection requires
    upstream body size limiting (e.g., nginx client_max_body_size).
    """
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > max_sz:
                raise HTTPException(status_code=413, detail="Payload too large")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid Content-Length"
            ) from None


_bearer_dependency = Depends(bearer_scheme)


async def require_api_key(
    credentials: HTTPAuthorizationCredentials = _bearer_dependency,
) -> None:
    expected = get_expected_api_key()
    if not expected or credentials is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not hmac.compare_digest(credentials.credentials, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")
