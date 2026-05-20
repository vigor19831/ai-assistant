"""Chat manager — routes Text/Voice/Image to LLM."""

from __future__ import annotations

import base64
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from core.domain.errors import AdapterError
from core.domain.messages import AssistantMessage, ImagePayload, UserMessage
from core.domain.pipeline import PipelineData
from core.logger import get_logger
from core.metrics import record_metric
from core.ports.tools import ToolCall
from core.prompts import get_prompt
from core.utils import count_tokens, get_context_limit
from pipeline.steps import build_context, embed_query, rerank, retrieve

logger = get_logger("chat")

_NS_MAP = {"p": "personal", "w": "work", "o": "other"}
_PREFIX_RE = re.compile(r"^\[(p|w|o)\]\s*(.*)", re.IGNORECASE)


class ChatManager:
    """Universal chat router."""

    def __init__(
        self,
        llm: Any,
        voice_recognizer: Any | None = None,
        vision: Any | None = None,
        storage: Any | None = None,
        history_limit: int = 10,
        max_context_tokens: int | None = None,
        tokenizer_model: str = "gpt-4o",
        tool_registry: Any | None = None,
        embedder: Any | None = None,
        vector_store: Any | None = None,
        reranker: Any | None = None,
    ) -> None:
        self.llm = llm
        self.voice_recognizer = voice_recognizer
        self.vision = vision
        self.storage = storage
        self.history_limit = history_limit
        self.max_context_tokens = max_context_tokens
        self.tokenizer_model = tokenizer_model
        self.tool_registry = tool_registry
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker

    def _count_tokens(self, text: str) -> int:
        return count_tokens(text, self.tokenizer_model)

    def _trim_history(
        self,
        history: list[dict[str, Any]],
        user_msg: UserMessage,
    ) -> list[dict[str, Any]]:
        """Trim oldest messages so system + history + user_msg fit token budget.

        Keeps the most recent messages that fit within the token budget.
        """
        budget = self.max_context_tokens
        if isinstance(budget, (int, float)) and budget > 0:
            pass
        else:
            budget = get_context_limit(self.llm)
        if not isinstance(budget, (int, float)) or budget <= 0:
            # No tokenizer available — simple count-based fallback
            return (
                history[-self.history_limit :]
                if len(history) > self.history_limit
                else history
            )

        user_tokens = self._count_tokens(user_msg.text or "")
        system_msg = getattr(self.llm, "system_message", None)
        system_tokens = self._count_tokens(str(system_msg) if system_msg else "")
        overhead = 50
        reserved = user_tokens + system_tokens + overhead

        available = budget - reserved
        if available <= 0:
            return []

        # Walk from newest to oldest, accumulating until budget exhausted
        total = 0
        keep: list[dict[str, Any]] = []
        for h in reversed(history):
            text = h.get("content", "")
            tokens = self._count_tokens(text)
            if total + tokens > available:
                break
            total += tokens
            keep.append(h)

        # Reverse to restore chronological order (oldest first)
        keep.reverse()
        return keep

    async def _maybe_rag(self, message: str) -> tuple[str, int]:
        if not self.embedder or not self.vector_store:
            return message, 0

        m = _PREFIX_RE.match(message)
        if not m:
            return message, 0  # Без префикса → RAG НЕ запускается

        ns_short = m.group(1).lower()
        query_text = m.group(2)
        namespace = _NS_MAP.get(ns_short, "default")

        data = PipelineData(
            query=UserMessage(text=query_text),
            metadata={
                "top_k": 5,
                "prompt_name": "rag_strict",
                "prompt_version": "v1",
                "namespace": namespace,
                "relevance_threshold": 0.3,
            },
        )

        data = await embed_query(data, embedder=self.embedder)
        if not data.errors:
            data = await retrieve(data, vector_store=self.vector_store)
        if self.reranker and not data.errors:
            data = await rerank(data, reranker=self.reranker)
        data = await build_context(data)

        if not data.context:
            logger.debug(f"RAG skipped: no relevant chunks in {namespace}")
            return query_text, 0

        chunks_for_prompt = [{"text": c.text or " "} for c in data.chunks]
        rag_prompt = get_prompt(
            "rag_strict",
            version="v1",
            query=query_text,
            chunks=json.dumps(chunks_for_prompt, ensure_ascii=False),
            context=data.context,
        )
        return rag_prompt, len(data.chunks)

    async def chat(
        self,
        message: str,
        conversation_id: str,
        image_url: str | None = None,
        image_base64: str | None = None,
        voice_base64: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssistantMessage:
        """Process a chat message (text, image, or voice)."""
        meta = metadata or {}
        logger.info(f"Chat request: conv={conversation_id}, msg_len={len(message)}")

        if voice_base64:
            if self.voice_recognizer is None:
                raise AdapterError("Voice recognizer not configured")
            audio_bytes = base64.b64decode(voice_base64)
            transcribed = await self.voice_recognizer.transcribe(audio_bytes)
            message = transcribed

        image_payload = None
        if image_url:
            image_payload = ImagePayload(url=image_url)
        elif image_base64:
            image_payload = ImagePayload(base64_data=image_base64)

        # --- RAG injection ---
        message, rag_chunks = await self._maybe_rag(message)
        record_metric("rag_chunks", rag_chunks)
        # ---------------------

        user_msg = UserMessage(
            text=message,
            image=image_payload,
            metadata=meta,
        )

        messages: list[Any] = [user_msg]
        input_tokens = self._count_tokens(message or "")

        history: list[dict[str, Any]] = []
        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id, limit=self.history_limit
                )
                try:
                    history = self._trim_history(history, user_msg)
                except Exception as e:
                    logger.warning(
                        "Token-based trim failed (%s), falling back to count-based", e
                    )
                    history = (
                        history[: -self.history_limit]
                        if len(history) > self.history_limit
                        else history
                    )
                for h in history:
                    role = h.get("role", "")
                    content = h.get("content", "")
                    if role == "user":
                        messages.insert(-1, UserMessage(text=content))
                    elif role == "assistant":
                        messages.insert(-1, AssistantMessage(text=content))
                    input_tokens += self._count_tokens(content)
            except Exception:
                pass

        response: AssistantMessage | None = None
        for _ in range(3):
            try:
                response = await self.llm.complete(messages)
            except Exception as e:
                logger.error(f"Chat failed: conv={conversation_id}, error={e}")
                raise

            if not response.tool_calls:
                break

            messages.append(response)

            if self.tool_registry:
                for call in response.tool_calls:
                    try:
                        func = call.get("function", {})
                        tool_name = func.get("name", "")
                        arguments = json.loads(func.get("arguments", "{}"))
                        tc = ToolCall(
                            tool_name=tool_name,
                            arguments=arguments,
                            call_id=call.get("id", ""),
                        )
                        result = await self.tool_registry.execute(tc)
                        content = (
                            result.output
                            if not result.is_error
                            else f"Error: {result.error}"
                        )
                    except Exception as e:
                        content = f"Error: {e}"

                    messages.append(
                        {
                            "role": "tool",
                            "content": str(content),
                            "tool_call_id": call.get("id", ""),
                        }
                    )
            else:
                break

        if response is None:
            response = AssistantMessage(text="Error: no response generated")

        output_tokens = self._count_tokens(response.text or "")
        tools_used = sum(
            len(m.tool_calls)
            for m in messages
            if isinstance(m, AssistantMessage) and m.tool_calls
        )

        record_metric("input_tokens", input_tokens)
        record_metric("output_tokens", output_tokens)
        record_metric("tools_used", tools_used)

        logger.info(
            f"Chat response: conv={conversation_id}, "
            f"resp_len={len(response.text or '')}"
        )

        if self.storage:
            try:
                await self.storage.save_message(
                    conversation_id,
                    {"role": "user", "content": message, "metadata": meta},
                )
                await self.storage.save_message(
                    conversation_id,
                    {
                        "role": "assistant",
                        "content": response.text or "",
                        "metadata": {},
                    },
                )
            except Exception:
                pass

        return response

    async def stream_chat(
        self,
        message: str,
        conversation_id: str,
        image_url: str | None = None,
        image_base64: str | None = None,
        voice_base64: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat response."""
        meta = metadata or {}

        if voice_base64:
            if self.voice_recognizer is None:
                raise AdapterError("Voice recognizer not configured")
            audio_bytes = base64.b64decode(voice_base64)
            transcribed = await self.voice_recognizer.transcribe(audio_bytes)
            message = transcribed

        image_payload = None
        if image_url:
            image_payload = ImagePayload(url=image_url)
        elif image_base64:
            image_payload = ImagePayload(base64_data=image_base64)

        # --- RAG injection ---
        message, rag_chunks = await self._maybe_rag(message)
        record_metric("rag_chunks", rag_chunks)
        # ---------------------

        user_msg = UserMessage(
            text=message,
            image=image_payload,
            metadata=meta,
        )

        messages: list[Any] = [user_msg]
        input_tokens = self._count_tokens(message or "")

        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id, limit=self.history_limit
                )
                try:
                    history = self._trim_history(history, user_msg)
                except Exception:
                    history = (
                        history[-self.history_limit :]
                        if len(history) > self.history_limit
                        else history
                    )
                for h in history:
                    role = h.get("role", "")
                    content = h.get("content", "")
                    if role == "user":
                        messages.insert(-1, UserMessage(text=content))
                    elif role == "assistant":
                        messages.insert(-1, AssistantMessage(text=content))
                    input_tokens += self._count_tokens(content)
            except Exception:
                pass

        output_text = ""
        async for chunk in self.llm.stream(messages):
            output_text += chunk
            yield chunk

        record_metric("input_tokens", input_tokens)
        record_metric("output_tokens", self._count_tokens(output_text))
        record_metric("tools_used", 0)
