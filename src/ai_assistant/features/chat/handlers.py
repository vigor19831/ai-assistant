"""Chat feature HTTP handlers."""

from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ai_assistant.api.deps import AppState, get_state
from ai_assistant.core.logger import get_logger
from ai_assistant.features.chat.manager import ChatManager
from ai_assistant.features.chat.schemas import (
    ChatRequest,
    ChatResponse,
    OAIChatCompletion,
    OAIChatCompletionRequest,
    OAIChatMessage,
    OAIChoice,
    OAIDeltaChunk,
    OAIModel,
    OAIModelList,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = ["router", "router_oai"]

_logger = get_logger("chat.handlers")

router = APIRouter(tags=["chat"])
router_oai = APIRouter(tags=["chat-oai"])


def _get_chat_manager(state: Annotated[AppState, Depends(get_state)]) -> ChatManager:
    return ChatManager(
        llm=state.llm,
        voice_recognizer=state.voice_recognizer,
        vision=state.vision,
        storage=state.storage,
        history_limit=state.config.chat.history_limit,
        max_context_tokens=state.config.chat.max_context_tokens,
        tokenizer_model=state.config.chat.tokenizer_model,
        tool_registry=state.tool_registry,
        embedder=state.embedder,
        vector_store=state.vector_store,
        reranker=state.reranker,
    )


# --- Legacy endpoints (under /api/v1 via wrapper) ---


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    manager: Annotated[ChatManager, Depends(_get_chat_manager)],
) -> ChatResponse:
    conv_id = req.conversation_id or str(uuid.uuid4())
    try:
        response = await manager.chat(
            message=req.message,
            conversation_id=conv_id,
            image_url=req.image_url,
            image_base64=req.image_base64,
            voice_base64=req.voice_base64,
            metadata=req.metadata,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _logger.exception("Chat failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(
        message=response.text or "",
        conversation_id=conv_id,
        metadata=response.metadata,
    )


@router.post("/chat/stream", response_model=None)
async def chat_stream(
    req: ChatRequest,
    manager: Annotated[ChatManager, Depends(_get_chat_manager)],
) -> StreamingResponse:
    conv_id = req.conversation_id or str(uuid.uuid4())

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for chunk in manager.stream_chat(
                message=req.message,
                conversation_id=conv_id,
                image_url=req.image_url,
                image_base64=req.image_base64,
                voice_base64=req.voice_base64,
                metadata=req.metadata,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as exc:
            _logger.exception("Stream failed")
            payload = json.dumps({"error": str(exc)})
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- OpenAI-compatible endpoints (stay at root /v1/*) ---


@router_oai.get("/v1/models", response_model=OAIModelList)
async def list_models(state: Annotated[AppState, Depends(get_state)]) -> OAIModelList:
    models = getattr(state.config.llm, "available_models", [])
    if not models:
        models = [state.config.llm.model]
    return OAIModelList(data=[OAIModel(id=m) for m in models])


@router_oai.post("/v1/chat/completions", response_model=None)
async def openai_chat_completions(
    req: OAIChatCompletionRequest,
    manager: Annotated[ChatManager, Depends(_get_chat_manager)],
    state: Annotated[AppState, Depends(get_state)],
) -> OAIChatCompletion | StreamingResponse:
    last_user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user" and m.content is not None:
            last_user_msg = m.content
            break

    conv_id = str(uuid.uuid4())
    model_id = getattr(req, "model", state.config.llm.model)

    if req.stream:

        async def event_generator() -> AsyncIterator[str]:
            try:
                async for chunk in manager.stream_chat(
                    message=last_user_msg,
                    conversation_id=conv_id,
                ):
                    delta = OAIDeltaChunk(
                        model=model_id,
                        choices=[
                            OAIChoice(
                                index=0,
                                delta=OAIChatMessage(role="assistant", content=chunk),
                                finish_reason=None,
                            )
                        ],
                    )
                    yield f"data: {delta.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as exc:
               _logger.exception("OpenAI stream failed")
               payload = json.dumps({"error": str(exc)})
               yield f"data: {payload}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    try:
        response = await manager.chat(
            message=last_user_msg,
            conversation_id=conv_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        _logger.exception("OpenAI chat failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return OAIChatCompletion(
        model=model_id,
        created=int(time.time()),
        choices=[
            OAIChoice(
                index=0,
                message=OAIChatMessage(role="assistant", content=response.text or ""),
                finish_reason="stop",
            )
        ],
    )
