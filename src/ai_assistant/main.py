"""Entry point — Uvicorn + FastAPI + Static UI."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai_assistant.api.deps import AppState, MetricsMiddleware, get_state
from ai_assistant.api.lifespan import lifespan
from ai_assistant.api.router import assemble_routers
from ai_assistant.api.security import APIKeyMiddleware, LimitMiddleware, require_api_key

app = FastAPI(
    title="AI Assistant",
    description="Modular AI Framework with Sacred Core",
    version="1.0.0",
    lifespan=lifespan,
)

# --- Middleware (added ONCE at import time) ---
app.add_middleware(MetricsMiddleware)
app.add_middleware(APIKeyMiddleware)
app.add_middleware(LimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Routes ---
for router in assemble_routers():
    app.include_router(router)

# --- Static files (lazy mount) ---
_static_mounted = False


def _mount_static(config: Any) -> None:
    """Mount /ui once, only if directory exists."""
    global _static_mounted
    if _static_mounted:
        return
    ui_cfg = getattr(config, "ui", None)
    if ui_cfg is None:
        return
    static_dir = Path(ui_cfg.static_path)
    if not static_dir.is_absolute():
        static_dir = Path(__file__).parent / static_dir
    if static_dir.exists():
        app.mount(
            "/ui",
            StaticFiles(directory=str(static_dir), html=True),
            name="static",
        )
        _static_mounted = True


# --- Endpoints ---
@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


async def _safe_get_state(request: Request) -> AppState | None:
    """Get state without raising on uninitialized state."""
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
    except RuntimeError:
        return None


_safe_get_state_dep = Depends(_safe_get_state)


@app.get("/info", dependencies=[Depends(require_api_key)])
async def get_info(
    state: AppState | None = _safe_get_state_dep,
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
