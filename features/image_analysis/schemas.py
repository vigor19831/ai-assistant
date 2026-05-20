"""Image analysis schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    image_base64: str | None = None
    image_url: str | None = None
    prompt: str = "Describe this image."
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalyzeResponse(BaseModel):
    description: str
    source: str = "vision"
    metadata: dict[str, Any] = Field(default_factory=dict)
