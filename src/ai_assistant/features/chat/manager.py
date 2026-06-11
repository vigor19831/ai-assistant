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
from ai_assistant.core.utils import count_tokens

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
    from ai_assistant.core.ports.llm import Message

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
        reranker: IReranker,
        storage: IChatStorage | None = None,
        history_limit: int = 10,
        max_history_messages: int = 10_000,
        max_context_tokens: int | None = None,
        tokenizer_model: str = "gpt-4o",
        embedder: IEmbedder | None = None,
        vector_store: IVectorStore | None = None,
        pipeline: RAGPipeline | None = None,
        namespaces: dict[str, Any] | None = None,
        prompt_version: str = "v1",
        top_k: int = 5,
    ) -> None:
        self.llm = llm
        self.reranker = reranker
        self.storage = storage
        self.history_limit = history_limit
        self.max_history_messages = max_history_messages
        self.max_context_tokens = max_context_tokens
        self.tokenizer_model = tokenizer_model
        self.embedder = embedder
        self.vector_store = vector_store
        self.pipeline = pipeline
        self.namespaces = namespaces or {}
        self.prompt_version = prompt_version
        self.top_k = top_k

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
        budget = self.max_context_tokens or self.llm.get_context_limit()
        if not budget:
            return (
                history[-self.history_limit :]
                if len(history) > self.history_limit
                else history
            )

        user_tokens = self._count_tokens(user_msg.text or "")
        system_message = self.llm.system_message
        system_tokens = self._count_tokens(
            str(system_message) if system_message else ""
        )
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

    async def _retrieve_context(
        self, message: str, trace_id: str | None = None
    ) -> tuple[str, str, tuple[Chunk, ...]]:
        """Run RAG retrieval and return (prompt_for_llm, original_query, rag_chunks).

        If RAG is not triggered or no results are found, returns the original
        message unchanged with empty chunks.
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
            "top_k": self.top_k,
            "prompt_name": prompt_name,
            "prompt_version": self.prompt_version,
            "namespace": namespace,
            "relevance_threshold": relevance_threshold,
            "embedder": self.embedder,
            "vector_store": self.vector_store,
        }

        data = await self.pipeline.run(data, metadata=metadata)

        if not data.chunks:
            return query_text, query_text, ()

        prompt = get_prompt(
            prompt_name,
            version=self.prompt_version,
            query=query_text,
            context=data.context,
        )
        return prompt, query_text, data.chunks

    async def _build_messages(
        self,
        prompt_for_llm: str,
        conversation_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> list[Message]:
        """Build message list with history, system prompt, and token trimming.

        Loads conversation history from storage, trims it to fit the token
        budget, and prepends historical messages before the current user message.
        """
        user_msg = UserMessage(text=prompt_for_llm, metadata=metadata or {})
        messages: list[Message] = [user_msg]

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
            except Exception as exc:
                logger.warning("History load failed: %s", exc)

        return messages

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

        prompt_for_llm, original_query, rag_chunks = await self._retrieve_context(
            message, trace_id=trace_id
        )

        messages = await self._build_messages(
            prompt_for_llm, conversation_id, metadata=meta
        )

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
        """Stream chat response token by token."""
        meta = metadata or {}
        trace_id = meta.get("trace_id")
        logger.info(
            "Stream request: conv=%s, msg_len=%d, trace_id=%s",
            conversation_id,
            len(message),
            trace_id or "none",
        )

        # Graceful degradation: RAG requested but infrastructure unavailable
        if _PREFIX_RE.match(message) and not self.pipeline:
            yield "Document search (RAG) temporarily unavailable."
            return

        prompt_for_llm, original_query, rag_chunks = await self._retrieve_context(
            message, trace_id=trace_id
        )

        messages = await self._build_messages(
            prompt_for_llm, conversation_id, metadata=meta
        )

        full_response = ""
        try:
            async for chunk in self.llm.stream(messages):
                full_response += chunk
                yield chunk
        except AdapterError:
            raise
        except Exception as exc:
            logger.error(
                "Stream failed: conv=%s, trace_id=%s, error=%s",
                conversation_id,
                trace_id or "none",
                exc,
            )
            raise AdapterError(f"LLM stream failed: {exc}") from exc

        logger.info(
            "Stream response: conv=%s, trace_id=%s, resp_len=%d",
            conversation_id,
            trace_id or "none",
            len(full_response),
        )

        # Save to history after streaming completes
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
                        "content": self._append_rag_sources(full_response, rag_chunks),
                        "metadata": {},
                    },
                )
            except Exception as exc:
                logger.warning("History save failed: %s", exc)
