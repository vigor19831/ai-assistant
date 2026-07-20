
"""Chat feature HTTP handlers."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import suppress
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ai_assistant.api.deps import InitializedAppState, get_state
from ai_assistant.core.domain.errors import LLM_UNAVAILABLE_MSG, AdapterError
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


def _raise_llm_unavailable(exc: AdapterError) -> None:
    """Map adapter-level failure to 503 Service Unavailable."""
    raise HTTPException(
        status_code=503,
        detail=LLM_UNAVAILABLE_MSG,
    ) from exc


def get_chat_manager(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> ChatManager:
    """Create ChatManager from state adapters — pipeline is built internally."""
    return ChatManager(
        llm=state.llm,
        reranker=state.reranker,
        storage=state.storage,
        history_limit=state.config.chat.history_limit,
        max_context_tokens=state.config.chat.max_context_tokens,
        embedder=state.embedder,
        vector_store=state.vector_store,
        namespaces=state.config.namespaces,
        prompt_version=state.config.rag.prompt_version,
        top_k=state.config.rag.top_k,
        token_margin_min=state.config.rag.token_margin_min,
        token_margin_pct=state.config.rag.token_margin_pct,
        tokenizer=state.tokenizer,
        system_message=state.config.llm.system_message,
    )


_logger = get_logger("chat.handlers")

router = APIRouter(tags=["chat"])
router_oai = APIRouter(tags=["chat-oai"])

# --- Heartbeat helper -------------------------------------------------------

SSE_HEARTBEAT_INTERVAL: float = 15.0  # seconds


async def _stream_with_heartbeat(
    stream: AsyncIterator[str],
    interval: float = SSE_HEARTBEAT_INTERVAL,
) -> AsyncIterator[str]:
    """Wrap async iterator with SSE heartbeat comments to prevent proxy timeout."""
    queue: asyncio.Queue[str | None | Exception | asyncio.CancelledError] = asyncio.Queue()

    async def _producer() -> None:
        try:
            async for chunk in stream:
                await queue.put(chunk)
            await queue.put(None)  # EOF sentinel
        except (Exception, asyncio.CancelledError) as exc:
            await queue.put(exc)

    task = asyncio.create_task(_producer())
    loop = asyncio.get_running_loop()
    last_activity = loop.time()

    try:
        while True:
            elapsed = loop.time() - last_activity
            timeout = max(0.1, interval - elapsed)

            try:
                item = await asyncio.wait_for(queue.get(), timeout=timeout)
            except TimeoutError:
                yield ": ping\n\n"
                last_activity = loop.time()
                continue

            if item is None:
                yield "data: [DONE]\n\n"
                return

            if isinstance(item, (Exception, asyncio.CancelledError)):
                raise item

            yield f"data: {item}\n\n"
            last_activity = loop.time()

    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


# --- Legacy endpoints (under /api/v1 via wrapper) ---------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    manager: Annotated[ChatManager, Depends(get_chat_manager)],
) -> ChatResponse:
    conv_id = req.conversation_id or str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    _logger.info(
        "Chat handler start",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )
    try:
        response = await manager.chat(
            message=req.message,
            conversation_id=conv_id,
            metadata={**req.metadata, "trace_id": trace_id},
        )
    except AdapterError as exc:
        _logger.warning(
            "LLM unavailable",
            extra={"trace_id": trace_id, "error": str(exc)},
        )
        _raise_llm_unavailable(exc)
    except HTTPException:
        raise
    except Exception:
        _logger.exception("Chat failed", extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail="Internal server error") from None
    _logger.info(
        "Chat handler done",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )
    return ChatResponse(
        message=response.text or "",
        conversation_id=conv_id,
        metadata=response.metadata,
    )


@router.post("/chat/stream", response_model=None)
async def chat_stream(
    req: ChatRequest,
    manager: Annotated[ChatManager, Depends(get_chat_manager)],
) -> StreamingResponse:
    conv_id = req.conversation_id or str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    _logger.info(
        "Chat stream handler start",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )

    async def _llm_stream() -> AsyncIterator[str]:
        try:
            async for chunk in manager.stream_chat(
                message=req.message,
                conversation_id=conv_id,
                metadata={**req.metadata, "trace_id": trace_id},
            ):
                yield chunk
        except AdapterError as exc:
            _logger.warning(
                "LLM unavailable in stream",
                extra={"trace_id": trace_id, "error": str(exc)},
            )
            raise
        except Exception:
            _logger.exception("Stream failed", extra={"trace_id": trace_id})
            raise

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for item in _stream_with_heartbeat(_llm_stream()):
                yield item
        except AdapterError:
            payload = json.dumps(
                {
                    "error": LLM_UNAVAILABLE_MSG
                }
            )
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"
        except Exception:
            payload = json.dumps({"error": "Internal server error"})
            yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- OpenAI-compatible endpoints (stay at root /v1/*) ---------------------


@router_oai.get("/v1/models", response_model=OAIModelList)
async def list_models(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> OAIModelList:
    cfg = state.config.llm
    models = cfg.available_models if cfg.available_models else []
    if not models:
        models = [cfg.model]
    return OAIModelList(data=[OAIModel(id=m) for m in models])


@router_oai.post("/v1/chat/completions", response_model=None)
async def openai_chat_completions(
    req: OAIChatCompletionRequest,
    manager: Annotated[ChatManager, Depends(get_chat_manager)],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> OAIChatCompletion | StreamingResponse:
    last_user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user" and m.content is not None:
            last_user_msg = m.content
            break

    if not last_user_msg.strip():
        raise HTTPException(
            status_code=400,
            detail="At least one user message with non-empty content is required.",
        )

    conv_id = str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    _logger.info(
        "OpenAI handler start",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )
    model_id = req.model if req.model is not None else state.config.llm.model

    if req.stream:

        async def _llm_stream() -> AsyncIterator[str]:
            try:
                async for chunk in manager.stream_chat(
                    message=last_user_msg,
                    conversation_id=conv_id,
                    metadata={"trace_id": trace_id},
                    max_tokens=req.max_tokens,
                    temperature=req.temperature,
                    top_p=req.top_p,
                    stop=req.stop,
                    frequency_penalty=req.frequency_penalty,
                    presence_penalty=req.presence_penalty,
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
                    yield delta.model_dump_json()
            except AdapterError as exc:
                _logger.warning(
                    "LLM unavailable in stream",
                    extra={"trace_id": trace_id, "error": str(exc)},
                )
                raise
            except Exception:
                _logger.exception("OpenAI stream failed", extra={"trace_id": trace_id})
                raise

        async def event_generator() -> AsyncIterator[str]:
            try:
                async for item in _stream_with_heartbeat(_llm_stream()):
                    yield item
            except AdapterError:
                payload = json.dumps(
                    {
                        "error": LLM_UNAVAILABLE_MSG
                    }
                )
                yield f"data: {payload}\n\n"
                yield "data: [DONE]\n\n"
            except Exception:
                payload = json.dumps({"error": "Internal server error"})
                yield f"data: {payload}\n\n"
                yield "data: [DONE]\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    try:
        response = await manager.chat(
            message=last_user_msg,
            conversation_id=conv_id,
            metadata={"trace_id": trace_id},
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            top_p=req.top_p,
            stop=req.stop,
            frequency_penalty=req.frequency_penalty,
            presence_penalty=req.presence_penalty,
        )
    except AdapterError as exc:
        _logger.warning(
            "LLM unavailable",
            extra={"trace_id": trace_id, "error": str(exc)},
        )
        _raise_llm_unavailable(exc)
    except HTTPException:
        raise
    except Exception:
        _logger.exception("OpenAI chat failed", extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail="Internal server error") from None

    _logger.info(
        "OpenAI handler done",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )
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
