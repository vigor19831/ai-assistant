"""Chat feature Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Universal chat request."""

    message: str
    conversation_id: str | None = Field(
        default=None, description="Thread ID for continuity"
    )
    stream: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Chat response."""

    message: str
    conversation_id: str
    role: str = "assistant"
    metadata: dict[str, object] = Field(default_factory=dict)


# --- OpenAI-compatible schemas ---


class OAIChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    content: str | None = None
    name: str | None = None


class OAIChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str | None = None
    messages: list[OAIChatMessage] = Field(min_length=1)
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: list[str] | str | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    user: str | None = None


class OAIChoice(BaseModel):
    index: int = 0
    message: OAIChatMessage | None = None
    delta: OAIChatMessage | None = None
    finish_reason: str | None = None


class OAIChatCompletion(BaseModel):
    id: str = "chatcmpl-local"
    object: str = "chat.completion"
    created: int = 0
    model: str = "local"
    choices: list[OAIChoice]


class OAIDeltaChunk(BaseModel):
    id: str = "chatcmpl-local"
    object: str = "chat.completion.chunk"
    created: int = 0
    model: str = "local"
    choices: list[OAIChoice]


class OAIModel(BaseModel):
    id: str
    object: str = "model"
    created: int = 1677610602
    owned_by: str = "local"


class OAIModelList(BaseModel):
    object: str = "list"
    data: list[OAIModel]


__all__ = [
    "ChatRequest",
    "ChatResponse",
    "OAIChatMessage",
    "OAIChatCompletionRequest",
    "OAIChoice",
    "OAIChatCompletion",
    "OAIDeltaChunk",
    "OAIModel",
    "OAIModelList",
]
