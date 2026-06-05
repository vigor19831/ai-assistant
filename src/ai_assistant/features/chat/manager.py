"""Chat manager — routes Text/Voice/Image to LLM."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ai_assistant.core.constants import (
    FROZEN_NO_INFO_PHRASES,
)
from ai_assistant.core.constants import (
    RAG_NS_MAP as _NS_MAP,
)
from ai_assistant.core.constants import (
    RAG_PREFIX_RE as _PREFIX_RE,
)
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.utils import count_tokens, get_context_limit

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ai_assistant.core.domain.documents import Chunk
    from ai_assistant.core.pipeline import RAGPipeline
    from ai_assistant.core.ports import (
        ILLM,
        IChatStorage,
        IEmbedder,
        IReranker,
        IVectorStore,
    )

__all__ = ["ChatManager"]

logger = get_logger("chat")

# RAG prefix constants imported from core.constants as _NS_MAP / _PREFIX_RE


class ChatManager:
    """Universal chat router."""

    @staticmethod
    def _append_rag_sources(answer: str, chunks: tuple[Chunk, ...]) -> str:
        if not chunks or any(ph in answer.lower() for ph in FROZEN_NO_INFO_PHRASES):
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
        return f"{answer}\n\nSources:\n" + "\n".join(src_lines) if src_lines else answer

    def __init__(
        self,
        llm: ILLM,
        storage: IChatStorage | None = None,
        history_limit: int = 10,
        max_history_messages: int = 10_000,
        max_context_tokens: int | None = None,
        tokenizer_model: str = "gpt-4o",
        embedder: IEmbedder | None = None,
        vector_store: IVectorStore | None = None,
        reranker: IReranker | None = None,
        pipeline: RAGPipeline | None = None,
        namespaces: dict[str, Any] | None = None,
        prompt_version: str = "v1",
    ) -> None:
        self.llm = llm
        self.storage = storage
        self.history_limit = history_limit
        self.max_history_messages = max_history_messages
        self.max_context_tokens = max_context_tokens
        self.tokenizer_model = tokenizer_model
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker
        self.pipeline = pipeline
        self.namespaces = namespaces or {}
        self.prompt_version = prompt_version

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

    async def _maybe_rag(
        self, message: str, trace_id: str | None = None
    ) -> tuple[str, str, tuple[Chunk, ...]]:
        """Return (prompt_for_llm, original_query, rag_chunks).

        If RAG not triggered, prompt_for_llm == original_query == message.
        """
        if not self.pipeline:
            return message, message, ()

        m = _PREFIX_RE.match(message)
        if not m:
            return message, message, ()

        ns_short = m.group(1).lower()
        query_text = m.group(2) or ""
        namespace = _NS_MAP.get(ns_short, "default")

        ns_cfg = self.namespaces.get(namespace)
        relevance_threshold = ns_cfg.relevance_threshold if ns_cfg else 0.3
        prompt_name = ns_cfg.prompt if ns_cfg else "rag_strict"

        data = PipelineData(
            query=UserMessage(text=query_text),
            trace_id=trace_id or "",
        )

        metadata = {
            "top_k": 5,
            "prompt_name": prompt_name,
            "prompt_version": self.prompt_version,
            "namespace": namespace,
            "relevance_threshold": relevance_threshold,
            "embedder": self.embedder,
            "vector_store": self.vector_store,
        }

        data = await self.pipeline.run(data, metadata=metadata)

        if not data.chunks:
            # Return query_text (without prefix), not message (with prefix)
            return query_text, query_text, ()

        prompt = get_prompt(
            prompt_name,
            version=self.prompt_version,
            query=query_text,
            context=data.context,
        )
        return prompt, query_text, data.chunks

    async def chat(
        self,
        message: str,
        conversation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> AssistantMessage:
        """Process a chat message."""
        meta = metadata or {}
        trace_id = meta.get("trace_id")
        logger.info(
            "Chat request: conv=%s, msg_len=%d, trace_id=%s",
            conversation_id,
            len(message),
            trace_id or "none",
        )

        # Graceful degradation: RAG requested but infrastructure unavailable
        if _PREFIX_RE.match(message) and not self.pipeline:
            return AssistantMessage(
                text="Document search (RAG) temporarily unavailable."
            )

        prompt_for_llm, original_query, rag_chunks = await self._maybe_rag(
            message, trace_id=trace_id
        )

        user_msg = UserMessage(
            text=prompt_for_llm,
            metadata=meta,
        )

        messages: list[UserMessage | AssistantMessage | dict[str, Any]] = [user_msg]
        input_tokens = self._count_tokens(prompt_for_llm or "")

        history: list[dict[str, Any]] = []
        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id,
                    limit=min(self.history_limit, self.max_history_messages),
                    offset=0,
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

        try:
            response = await self.llm.complete(messages)
        except AdapterError:
            raise
        except Exception as exc:
            logger.error(
                "Chat failed: conv=%s, trace_id=%s, error=%s",
                conversation_id,
                trace_id or "none",
                exc,
            )
            raise AdapterError(f"LLM call failed: {exc}") from exc

        logger.info(
            "Chat response: conv=%s, trace_id=%s, resp_len=%d",
            conversation_id,
            trace_id or "none",
            len(response.text or ""),
        )

        response = AssistantMessage(
            text=self._append_rag_sources(response.text or "", rag_chunks),
            metadata=response.metadata,
            tool_calls=response.tool_calls,
        )

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
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat response.

        TODO: tool calls are not handled in streaming mode.
        """
        meta = metadata or {}
        trace_id = meta.get("trace_id")

        # Graceful degradation: RAG requested but infrastructure unavailable
        if _PREFIX_RE.match(message) and not self.pipeline:
            yield "Document search (RAG) temporarily unavailable."
            return

        prompt_for_llm, original_query, rag_chunks = await self._maybe_rag(
            message, trace_id=trace_id
        )

        user_msg = UserMessage(
            text=prompt_for_llm,
            metadata=meta,
        )

        messages: list[UserMessage | AssistantMessage | dict[str, Any]] = [user_msg]
        input_tokens = self._count_tokens(prompt_for_llm or "")

        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id,
                    limit=min(self.history_limit, self.max_history_messages),
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
        try:
            async for chunk in self.llm.stream(messages):
                output_text += chunk
                yield chunk
        except Exception as exc:
            raise AdapterError(f"LLM stream failed: {exc}") from exc

        output_text = self._append_rag_sources(output_text, rag_chunks)

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
