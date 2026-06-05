"""Entry point — Uvicorn + FastAPI + Static UI."""

from __future__ import annotations

import inspect
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from ai_assistant.api.deps import InitializedAppState, get_state
from ai_assistant.api.lifespan import lifespan as _default_lifespan
from ai_assistant.api.router import assemble_routers
from ai_assistant.api.security import require_api_key

__all__ = ["create_app", "app"]


def create_app(
    state: InitializedAppState | None = None,
    lifespan: Any = None,
) -> FastAPI:
    """Application factory — creates a fresh FastAPI instance.

    Args:
        state: Optional pre-built InitializedAppState. Injected into app.state.app_state.
        lifespan: Optional lifespan context manager. Defaults to core lifespan.
    """
    _lifespan = lifespan if lifespan is not None else _default_lifespan

    app = FastAPI(
        title="AI Assistant",
        description="Modular AI Framework with Sacred Core",
        version="1.0.0",
        lifespan=_lifespan,
    )

    # --- Middleware ---
    # Use CORS config from AppState if available, otherwise defaults
    _cors_origins = ["http://localhost", "http://127.0.0.1"]
    _cors_credentials = True
    _cors_methods = ["*"]
    _cors_headers = ["*"]
    if state is not None:
        _cors_origins = state.config.cors.allow_origins or _cors_origins
        _cors_credentials = state.config.cors.allow_credentials
        _cors_methods = state.config.cors.allow_methods or _cors_methods
        _cors_headers = state.config.cors.allow_headers or _cors_headers

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=_cors_credentials,
        allow_methods=_cors_methods,
        allow_headers=_cors_headers,
    )

    # --- Routes ---
    for router in assemble_routers():
        app.include_router(router)

    if state is not None:
        app.state.app_state = state

    # --- Endpoints ---
    @app.get("/")
    async def root() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    async def _safe_get_state(request: Request) -> InitializedAppState | None:
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
        state: InitializedAppState | None = _safe_get_state_dep,
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

    return app


# Global instance for uvicorn and backward compatibility
app = create_app()
