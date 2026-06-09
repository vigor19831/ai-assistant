"""Application entry point."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_assistant.api.deps import InitializedAppState, get_state  # noqa: TC001
from ai_assistant.api.lifespan import lifespan as _default_lifespan
from ai_assistant.api.middleware import MetricsMiddleware
from ai_assistant.api.router import assemble_routers
from ai_assistant.core.metrics import get_metrics, get_metrics_json

__all__ = ["create_app"]


class _InfoResponse(BaseModel):
    app_name: str
    config_version: str
    debug: bool
    llm_model: str
    llm_provider: str


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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(MetricsMiddleware)

    for router in assemble_routers():
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

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(content=get_metrics(), media_type="text/plain")

    @app.get("/metrics/json")
    async def metrics_json() -> dict[str, Any]:
        return get_metrics_json()

    return app
