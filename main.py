"""Entry point — Uvicorn + FastAPI + Static UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.deps import AppState, MetricsMiddleware, get_state
from api.lifespan import lifespan
from api.router import assemble_routers
from api.security import LimitMiddleware, _load_security_cfg
from core.config import load_config

_config = load_config()

app = FastAPI(
    title="AI Assistant",
    description="Modular AI Framework with Sacred Core",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(MetricsMiddleware)

sec_cfg = _load_security_cfg()


# === CORS: always allow any origin, any method, any header ===
@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        response = await call_next(request)
    else:
        response = await call_next(request)
    # Always set CORS headers — works for browser extensions (null origin)
    response.headers["Access-Control-Allow-Origin"] = request.headers.get("origin", "*")
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = request.headers.get("access-control-request-headers", "*")
    return response


app.add_middleware(LimitMiddleware)
if sec_cfg.get("allowed_hosts") and not _config.debug:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=sec_cfg["allowed_hosts"])

@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "ai-assistant"}

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "ai-assistant"}

async def _safe_get_state(request: Request) -> AppState | None:
    app = request.app
    override: Any = app.dependency_overrides.get(get_state)
    try:
        if override is not None:
            return override()
        return get_state(request)
    except RuntimeError:
        return None

@app.get("/info")
async def get_info(state: AppState | None = Depends(_safe_get_state)) -> dict[str, str]:
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
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="static")
