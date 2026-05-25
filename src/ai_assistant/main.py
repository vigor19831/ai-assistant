"""Entry point — Uvicorn + FastAPI + Static UI."""

from __future__ import annotations

import inspect
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ai_assistant.api.deps import AppState, MetricsMiddleware, get_state
from ai_assistant.api.lifespan import lifespan
from ai_assistant.api.router import assemble_routers
from ai_assistant.api.security import (
    APIKeyMiddleware,
    LimitMiddleware,
    _load_security_cfg,
    require_api_key,
)
from ai_assistant.core.config import load_config
from ai_assistant.core.logger import get_logger

_logger = get_logger("ai_assistant.main")

_config = load_config(os.getenv("AI_CONFIG_PATH", "config.yaml"))

app = FastAPI(
    title="AI Assistant",
    description="Modular AI Framework with Sacred Core",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(APIKeyMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_config.cors.allow_origins,
    allow_credentials=_config.cors.allow_credentials,
    allow_methods=_config.cors.allow_methods,
    allow_headers=_config.cors.allow_headers,
)

sec_cfg = _load_security_cfg()

app.add_middleware(LimitMiddleware)
if sec_cfg.get("allowed_hosts") and not _config.debug:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=sec_cfg["allowed_hosts"],
    )


@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


async def _safe_get_state(request: Request) -> AppState | None:
    fastapi_app = request.app
    override: Any = fastapi_app.dependency_overrides.get(get_state)
    try:
        if override is not None:
            result = override()
            if inspect.isawaitable(result):
                return await result
            return result
        result = get_state(request)
        if inspect.isawaitable(result):
            return await result
        return result
    except RuntimeError as exc:
        _logger.debug("Failed to get app state: %s", exc)
        return None


@app.get("/info", dependencies=[Depends(require_api_key)])
async def get_info(
    state: AppState | None = Depends(_safe_get_state),
) -> dict[str, str]:
    if state is None:
        return {"provider": "unknown", "model": "unknown"}
    provider = state.config.llm.provider
    if provider == "mock":
        model = "mock"
    elif provider == "openai_compatible":
        model = getattr(state.config.llm, "model", None) or "unknown"
    else:
        model = provider
    return {"provider": provider, "model": model}


for router in assemble_routers():
    app.include_router(router)

static_dir = Path(_config.ui.static_path)
if not static_dir.is_absolute():
    static_dir = Path(__file__).parent / static_dir
if static_dir.exists():
    app.mount(
        "/ui",
        StaticFiles(directory=str(static_dir), html=True),
        name="static",
    )
