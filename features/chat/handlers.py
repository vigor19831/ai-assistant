"""Chat feature HTTP handlers."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import AppState, get_state
from api.security import require_api_key
from features.chat.manager import ChatManager
from features.chat.schemas import (
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

router = APIRouter(tags=["chat"])


def _get_chat_manager(state: AppState = Depends(get_state)) -> ChatManager:
    return ChatManager(
        llm=state.llm,
        voice_recognizer=state.voice_recognizer,
        vision=state.vision,
        storage=getattr(state, "storage", None),
        history_limit=state.config.chat.history_limit,
        max_context_tokens=getattr(state.config.chat, "max_context_tokens", None),
        tokenizer_model=getattr(state.config.chat, "tokenizer_model", "gpt-4o"),
        tool_registry=getattr(state, "tool_registry", None),
        embedder=getattr(state, "embedder", None),
        vector_store=getattr(state, "vector_store", None),
        reranker=getattr(state, "reranker", None),
    )


# --- Legacy endpoints (backward compatible) ---


@router.post(
    "/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)]
)
async def chat(
    req: ChatRequest,
    manager: ChatManager = Depends(_get_chat_manager),
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(
        message=response.text or "",
        conversation_id=conv_id,
        metadata=response.metadata,
    )


@router.post(
    "/chat/stream", response_model=None, dependencies=[Depends(require_api_key)]
)
async def chat_stream(
    req: ChatRequest,
    manager: ChatManager = Depends(_get_chat_manager),
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
        except Exception as e:
            yield f"data: ERROR: {e}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- OpenAI-compatible endpoints ---


@router.get(
    "/v1/models",
    response_model=OAIModelList,
    dependencies=[Depends(require_api_key)],
)
async def list_models(state: AppState = Depends(get_state)) -> OAIModelList:
    models = getattr(state.config.llm, "available_models", [])
    if not models:
        models = [state.config.llm.model]
    return OAIModelList(data=[OAIModel(id=m) for m in models])


@router.post(
    "/v1/chat/completions", response_model=None, dependencies=[Depends(require_api_key)]
)
async def openai_chat_completions(
    req: OAIChatCompletionRequest,
    manager: ChatManager = Depends(_get_chat_manager),
) -> OAIChatCompletion | StreamingResponse:
    # Extract last user message as our "message"
    last_user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user" and m.content:
            last_user_msg = m.content
            break

    conv_id = str(uuid.uuid4())

    if req.stream:

        async def event_generator() -> AsyncIterator[str]:
            try:
                async for chunk in manager.stream_chat(
                    message=last_user_msg,
                    conversation_id=conv_id,
                ):
                    delta = OAIDeltaChunk(
                        choices=[
                            OAIChoice(
                                index=0,
                                delta=OAIChatMessage(role="assistant", content=chunk),
                                finish_reason=None,
                            )
                        ]
                    )
                    yield f"data: {delta.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f'data: {{"error": "{e}"}}\n\n'

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    try:
        response = await manager.chat(
            message=last_user_msg,
            conversation_id=conv_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return OAIChatCompletion(
        created=int(time.time()),
        choices=[
            OAIChoice(
                index=0,
                message=OAIChatMessage(role="assistant", content=response.text or ""),
                finish_reason="stop",
            )
        ],
    )
