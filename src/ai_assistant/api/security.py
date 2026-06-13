"""API security — API key enforcement via FastAPI dependency.

Security config is loaded ONCE at startup into AppState.config.security.
This module reads from AppState via request state or env var fallback.
No YAML reloading on hot path.
"""

from __future__ import annotations

import os
import threading

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ai_assistant.core.logger import get_logger

__all__ = [
    "check_request_size",
    "get_expected_api_key",
    "require_api_key",
    "SECURITY_MAX_BODY",
    "set_api_key",
]

_logger = get_logger("security")

SECURITY_MAX_BODY = 10_485_760
bearer_scheme = HTTPBearer(auto_error=False)

# Mutable state for rare runtime key rotation (admin endpoint)
_override_api_key: str | None = None
_lock = threading.Lock()


def get_expected_api_key() -> str | None:
    """Return API key from env var, runtime override, or None.

    Callers that have AppState should prefer state.config.security.api_key.
    This function exists for code paths without AppState access.
    """
    env_key = os.getenv("AI_SECURITY_API_KEY")
    if env_key is not None:
        return env_key or None
    with _lock:
        return _override_api_key


def set_api_key(key: str | None) -> None:
    """Runtime API key rotation — called from admin endpoint."""
    global _override_api_key
    with _lock:
        _override_api_key = key


async def check_request_size(request: Request) -> None:
    cl = request.headers.get("content-length")
    # Default max body size — can be overridden by caller with AppState
    max_sz = SECURITY_MAX_BODY
    if cl:
        try:
            if int(cl) > int(max_sz):
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
    if not expected:
        raise HTTPException(status_code=401, detail="API key not configured")
    if not credentials or not hasattr(credentials, "credentials"):
        raise HTTPException(status_code=401, detail="Missing API key")
    if credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")
