"""Application entry point."""

from __future__ import annotations

import os
from typing import Annotated, Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_assistant.api.deps import InitializedAppState, get_state
from ai_assistant.api.lifespan import lifespan as _default_lifespan
from ai_assistant.api.middleware import MetricsMiddleware
from ai_assistant.api.router import assemble_routers
from ai_assistant.core.config import CORSConfig, SecurityConfig, load_config

__all__ = ["create_app"]


class _InfoResponse(BaseModel):
    app_name: str
    config_version: str
    debug: bool
    llm_model: str
    llm_provider: str


def _load_cors_config(state: InitializedAppState | None) -> CORSConfig:
    """Return CORS config from state or fallback to safe defaults."""
    if state is not None:
        return state.config.cors
    config_path = os.getenv("AI_CONFIG_PATH", "config.yaml")
    try:
        return load_config(config_path).cors
    except (FileNotFoundError, ValueError):
        return CORSConfig(
            allow_origins=[],
            allow_credentials=False,
            allow_methods=["GET"],
            allow_headers=[],
        )


def create_app(
    state: InitializedAppState | None = None,
    lifespan: Any = None,
) -> FastAPI:
    """Application factory — creates a fresh FastAPI instance."""
    app = FastAPI(
        title="AI Assistant",
        version="1.0.0",
        lifespan=lifespan or _default_lifespan,
    )

    if state is not None:
        app.state.app_state = state

    cors_cfg = _load_cors_config(state)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_cfg.allow_origins),
        allow_credentials=cors_cfg.allow_credentials,
        allow_methods=list(cors_cfg.allow_methods),
        allow_headers=list(cors_cfg.allow_headers),
    )

    security: SecurityConfig | None = None
    if state is not None:
        security = state.config.security

    app.add_middleware(
        MetricsMiddleware,
        allowed_hosts=security.allowed_hosts if security is not None else [],
    )

    for router in assemble_routers(security=security):
        app.include_router(router)

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/info", response_model=_InfoResponse)
    async def get_info(
        state: Annotated[InitializedAppState, Depends(get_state)],
    ) -> _InfoResponse:
        """Application info. Uses DI — fails loudly if state is missing."""
        cfg = state.config
        return _InfoResponse(
            app_name=cfg.app_name,
            config_version=cfg.config_version,
            debug=cfg.debug,
            llm_model=cfg.llm.model,
            llm_provider=cfg.llm.provider,
        )

    return app


app = create_app()
