"""Chat manager — routes Text/Voice/Image to LLM."""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import TYPE_CHECKING, Any

from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import (
    AssistantMessage,
    ImagePayload,
    UserMessage,
)
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.metrics import record_metric
from ai_assistant.core.ports.tools import ToolCall
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.utils import count_tokens, get_context_limit
from ai_assistant.pipeline.steps import (
    StepContext,
    build_context,
    embed_query,
    retrieve,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ai_assistant.core.domain.documents import Chunk

__all__ = ["ChatManager"]

logger = get_logger("chat")

_NS_MAP = {"p": "personal", "w": "work", "o": "other"}
_PREFIX_RE = re.compile(r"^\[(p|w|o)\]\s*(.*)", re.IGNORECASE)

NO_INFO_PHRASES = [
    "не достаточно",
    "недостаточно",
    "не имею",
    "не знаю",
    "not enough",
    "don't have",
    "no information",
    "не найдено",
    "not found",
    "i don't have",
    "i do not have",
    "don't know",
    "do not know",
    "у меня недостаточно",
    "у меня нет",
]


class ChatManager:
    """Universal chat router."""

    @staticmethod
    def _append_rag_sources(answer: str, chunks: list[Chunk]) -> str:
        if not chunks or any(ph in answer.lower() for ph in NO_INFO_PHRASES):
            return answer
        cited: set[int] = set()
        for m in re.finditer(r"\[(\d+)\]", answer):
            try:
                cited.add(int(m.group(1)) - 1)
            except (ValueError, IndexError):
                continue
        src_lines = [
            f"[{i + 1}] {chunks[i].metadata.source if chunks[i].metadata is not None else 'unknown'}"  # type: ignore[union-attr]
            for i in sorted(cited)
            if 0 <= i < len(chunks)
        ]
        return (
            f"{answer}\n\n📎 Источники:\n" + "\n".join(src_lines)
            if src_lines
            else answer
        )

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
        budget = self.max_context_tokens or get_context_limit(self.llm)
        if not budget:
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

        total = 0
        keep: list[dict[str, Any]] = []
        for h in reversed(history):
            text = h.get("content", "")
            tokens = self._count_tokens(text)
            if total + tokens > available:
                break
            total += tokens
            keep.append(h)

        keep.reverse()
        return keep

    async def _maybe_rag(self, message: str) -> tuple[str, str, list[Chunk]]:
        """Return (prompt_for_llm, original_query, rag_chunks).

        If RAG not triggered, prompt_for_llm == original_query == message.
        """
        if not self.embedder or not self.vector_store:
            return message, message, []

        m = _PREFIX_RE.match(message)
        if not m:
            return message, message, []

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

        data = await embed_query(data, StepContext(embedder=self.embedder))
        data = await retrieve(data, StepContext(vector_store=self.vector_store))
        data = await build_context(data, StepContext())

        if not data.chunks:
            # Возвращаем query_text (без префикса), а не message (с префиксом)
            return query_text, query_text, []

        prompt = get_prompt(
            "rag_strict",
            version="v1",
            query=query_text,
            context=data.context,
        )
        return prompt, query_text, data.chunks

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
        logger.info(
            "Chat request: conv=%s, msg_len=%d",
            conversation_id,
            len(message),
        )

        if voice_base64:
            if self.voice_recognizer is None:
                raise AdapterError("Voice recognizer not configured")
            try:
                audio_bytes = base64.b64decode(voice_base64)
            except (binascii.Error, ValueError) as exc:
                raise AdapterError(f"Invalid voice_base64: {exc}") from exc
            transcribed = await self.voice_recognizer.transcribe(audio_bytes)
            message = transcribed

        image_payload = None
        if image_url:
            image_payload = ImagePayload(url=image_url)
        elif image_base64:
            image_payload = ImagePayload(base64_data=image_base64)

        prompt_for_llm, original_query, rag_chunks = await self._maybe_rag(message)
        record_metric("rag_chunks", len(rag_chunks))

        user_msg = UserMessage(
            text=prompt_for_llm,
            image=image_payload,
            metadata=meta,
        )

        messages: list[UserMessage | AssistantMessage | dict[str, Any]] = [user_msg]
        input_tokens = self._count_tokens(prompt_for_llm or "")

        history: list[dict[str, Any]] = []
        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id,
                    limit=self.history_limit,
                )
                try:
                    history = self._trim_history(history, user_msg)
                except Exception as exc:
                    logger.warning(
                        "Token-based trim failed (%s), falling back to count-based",
                        exc,
                    )
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
            except Exception as exc:
                logger.warning("History load failed: %s", exc)

        response: AssistantMessage | None = None
        for attempt in range(3):
            try:
                response = await self.llm.complete(messages)
            except Exception as exc:
                logger.error(
                    "Chat failed (attempt %d): conv=%s, error=%s",
                    attempt + 1,
                    conversation_id,
                    exc,
                )
                if attempt == 2:
                    raise
                continue

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
                        result = await self.tool_registry.dispatch(tc)
                        content = (
                            result.output
                            if not result.is_error
                            else f"Error: {result.error}"
                        )
                    except Exception as exc:
                        content = f"Error: {exc}"

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
            "Chat response: conv=%s, resp_len=%d",
            conversation_id,
            len(response.text or ""),
        )

        response = AssistantMessage(text=self._append_rag_sources(response.text or "", rag_chunks), metadata=response.metadata, tool_calls=response.tool_calls)

        if self.storage:
            try:
                await self.storage.save_message(
                    conversation_id,
                    {
                        "role": "user",
                        "content": original_query,
                        "metadata": meta,
                    },
                )
                await self.storage.save_message(
                    conversation_id,
                    {
                        "role": "assistant",
                        "content": response.text or "",
                        "metadata": {},
                    },
                )
            except Exception as exc:
                logger.warning("History save failed: %s", exc)

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
        """Stream chat response.

        TODO: tool calls are not handled in streaming mode.
        """
        meta = metadata or {}

        if voice_base64:
            if self.voice_recognizer is None:
                raise AdapterError("Voice recognizer not configured")
            try:
                audio_bytes = base64.b64decode(voice_base64)
            except (binascii.Error, ValueError) as exc:
                raise AdapterError(f"Invalid voice_base64: {exc}") from exc
            transcribed = await self.voice_recognizer.transcribe(audio_bytes)
            message = transcribed

        image_payload = None
        if image_url:
            image_payload = ImagePayload(url=image_url)
        elif image_base64:
            image_payload = ImagePayload(base64_data=image_base64)

        prompt_for_llm, original_query, rag_chunks = await self._maybe_rag(message)
        record_metric("rag_chunks", len(rag_chunks))

        user_msg = UserMessage(
            text=prompt_for_llm,
            image=image_payload,
            metadata=meta,
        )

        messages: list[UserMessage | AssistantMessage | dict[str, Any]] = [user_msg]
        input_tokens = self._count_tokens(prompt_for_llm or "")

        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id,
                    limit=self.history_limit,
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
            except Exception as exc:
                logger.warning("History load failed: %s", exc)

        output_text = ""
        async for chunk in self.llm.stream(messages):
            output_text += chunk
            yield chunk

        output_text = self._append_rag_sources(output_text, rag_chunks)

        record_metric("input_tokens", input_tokens)
        record_metric("output_tokens", self._count_tokens(output_text))
        record_metric("tools_used", 0)

        if self.storage:
            try:
                await self.storage.save_message(
                    conversation_id,
                    {
                        "role": "user",
                        "content": original_query,
                        "metadata": meta,
                    },
                )
                await self.storage.save_message(
                    conversation_id,
                    {
                        "role": "assistant",
                        "content": output_text,
                        "metadata": {},
                    },
                )
            except Exception as exc:
                logger.warning("History save failed: %s", exc)
