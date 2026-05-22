"""API security — rate limiting, request size, API key enforcement."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

CONFIG_PATH = Path("config.yaml")
SECURITY_MAX_BODY = 10_485_760
bearer_scheme = HTTPBearer(auto_error=False)


def _load_security_cfg() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}).get("security", {})
    return {}


class SecurityLimiter:
    def __init__(self) -> None:
        self.requests: dict[str, list[float]] = defaultdict(list)
        cfg = _load_security_cfg()
        rate_str = cfg.get("rate_limit", "100/minute")
        try:
            self.max_req, period = int(rate_str.split("/")[0]), rate_str.split("/")[1]
            self.window = 60.0 if period == "minute" else 1.0
        except Exception:
            self.max_req, self.window = 100, 60.0

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        self.requests[ip] = [t for t in self.requests[ip] if t > now - self.window]
        if len(self.requests[ip]) >= self.max_req:
            return False
        self.requests[ip].append(now)
        return True


limiter = SecurityLimiter()


def get_expected_api_key() -> str | None:
    cfg = _load_security_cfg()
    env_key: str | None = os.getenv("AI_API_KEY")
    if env_key:
        return env_key
    cfg_key = cfg.get("api_key")
    return cfg_key if isinstance(cfg_key, str) else None


class LimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        ip = request.client.host if request.client else "unknown"
        if not limiter.is_allowed(ip):
            return Response(
                "Rate limit exceeded", status_code=429, media_type="text/plain"
            )
        return await call_next(request)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Enforce API key on every request except public paths."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        public_paths = {"/", "/health", "/docs", "/openapi.json", "/redoc"}
        path = request.url.path
        if path in public_paths or path.startswith(("/docs/", "/redoc")):
            return await call_next(request)

        expected = get_expected_api_key()
        if not expected:
            return Response(
                "API key not configured", status_code=401, media_type="text/plain"
            )

        auth = request.headers.get("Authorization", "")
        if not auth:
            return Response("Missing API key", status_code=401, media_type="text/plain")

        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or token != expected:
            return Response("Invalid API key", status_code=401, media_type="text/plain")

        return await call_next(request)


async def check_request_size(request: Request) -> None:
    cl = request.headers.get("content-length")
    max_sz = _load_security_cfg().get("max_body_size", SECURITY_MAX_BODY)
    if cl and int(cl) > int(max_sz):
        raise HTTPException(status_code=413, detail="Payload too large")


async def require_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
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
