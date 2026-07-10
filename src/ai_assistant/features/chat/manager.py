"""Chat manager — routes Text/Voice/Image to LLM."""

from __future__ import annotations

import asyncio
import os
import re
import time
from typing import TYPE_CHECKING, Any

from ai_assistant.core.config import RAGStep
from ai_assistant.core.constants import (
    FROZEN_NO_INFO_PHRASES,
)
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from ai_assistant.core.domain.pipeline import PipelineConfig, PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import STEP_REGISTRY
from ai_assistant.core.ports.llm import Message
from ai_assistant.core.ports.tokenizer import ITokenizer
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.query_parser import build_prefix_map, parse_rag_query

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from ai_assistant.core.domain.documents import Chunk
    from ai_assistant.core.ports import (
        ILLM,
        IChatStorage,
        IEmbedder,
        IReranker,
        IVectorStore,
    )

__all__ = ["ChatManager"]

logger = get_logger("chat")


# ---------------------------------------------------------------------------
# Pipeline step functions — moved from deps.py to where they are used
# ---------------------------------------------------------------------------

_STEP_MAP: dict[RAGStep, Any] = {
    RAGStep(k): v for k, v in STEP_REGISTRY.items() if k in {m.value for m in RAGStep}
}


class ChatManager:
    """Universal chat router."""

    @staticmethod
    def _append_rag_sources(answer: str, chunks: tuple[Chunk, ...]) -> str:
        if not chunks or any(ph in answer.lower() for ph in FROZEN_NO_INFO_PHRASES):
            return answer

        def _path_to_file_uri(path: str) -> str:
            """Convert a filesystem path to a proper file URI (RFC 8089)."""
            # Windows absolute path: C:\dir\file or C:/dir/file
            if re.match(r"^[A-Za-z]:[/\\]", path):
                path = path.replace("\\", "/")
                return f"file:///{path}"
            # Unix absolute path
            if path.startswith("/"):
                return f"file://{path}"
            # Relative path — not ideal, but handle gracefully
            return f"file:///{path}"

        def _source_key(chunk: Chunk) -> str:
            """Return unique key for deduplication: source_uri > original_path > source."""
            if chunk.metadata is None:
                return "unknown"
            return chunk.metadata.source_uri or chunk.metadata.original_path or chunk.metadata.source or "unknown"

        def _source_link(chunk: Chunk) -> str:
            if chunk.metadata is None:
                return "unknown"

            md = chunk.metadata
            display = md.source or "unknown"
            url = None

            if md.source_uri:
                # source_uri is a relative path; extract filename for display
                display = md.source_uri.rsplit("/", 1)[-1] or md.source
                url = md.source_uri
            elif md.original_path:
                display = os.path.basename(md.original_path) or md.source
                url = _path_to_file_uri(md.original_path)

            if url:
                return f"{display} — {url}"
            return display

        # Deduplicate by source key while preserving order
        seen: set[str] = set()
        unique_lines: list[str] = []
        for chunk in chunks:
            key = _source_key(chunk)
            if key not in seen:
                seen.add(key)
                unique_lines.append(_source_link(chunk))

        src_lines = [f"[{i + 1}] {line}" for i, line in enumerate(unique_lines)]
        return answer + "\n\nSources:\n" + "\n".join(src_lines)

    tokenizer: ITokenizer | None = None

    def __init__(
        self,
        llm: ILLM,
        reranker: IReranker,
        storage: IChatStorage | None = None,
        history_limit: int = 10,
        max_context_tokens: int | None = None,
        embedder: IEmbedder | None = None,
        vector_store: IVectorStore | None = None,
        namespaces: dict[str, Any] | None = None,
        prompt_version: str = "v1",
        top_k: int = 5,
        token_margin_min: int = 256,
        token_margin_pct: float = 0.1,
        tokenizer: ITokenizer | None = None,
        rag_steps: list[RAGStep] | None = None,
        system_message: str | None = None,
    ) -> None:
        self.llm = llm
        self.reranker = reranker
        self.storage = storage
        self.history_limit = history_limit
        self.system_message = system_message
        self.max_context_tokens = max_context_tokens
        self.embedder = embedder
        self.vector_store = vector_store
        self.namespaces = namespaces or {}
        self.prompt_version = prompt_version
        self.top_k = top_k
        self.token_margin_min = token_margin_min
        self.token_margin_pct = token_margin_pct
        self.tokenizer = tokenizer
        self._prefix_map = build_prefix_map(self.namespaces)

        # Build pipeline internally — ChatManager owns its pipeline.
        # rag_steps parameter exists for tests and future overrides.
        # Factory in handlers.py does NOT pass it; hardcoded retrieval
        # steps are used instead. Generation is handled separately via
        # llm.complete(), so cfg.rag.steps (which includes GENERATE)
        # is not appropriate here.
        self._pipeline = self._build_pipeline(rag_steps)

    def _build_pipeline(self, rag_steps: list[RAGStep] | None = None) -> RAGPipeline | None:
        """Build the RAG pipeline for retrieval. Returns None if no steps configured."""
        if self.embedder is None or self.vector_store is None:
            return None

        if rag_steps is None:
            # Default retrieval pipeline: condense_question -> embed_query -> retrieve -> rerank -> build_context
            default_steps = [
                RAGStep.CONDENSE_QUESTION,
                RAGStep.EMBED_QUERY,
                RAGStep.RETRIEVE,
                RAGStep.RERANK,
                RAGStep.BUILD_CONTEXT,
            ]
            step_funcs = []
            for step in default_steps:
                func = _STEP_MAP.get(step)
                if func is None:
                    raise ValueError(
                        f"Default step {step.value!r} not found in STEP_REGISTRY. "
                        f"Available: {list(STEP_REGISTRY.keys())}"
                    )
                step_funcs.append(func)
            return RAGPipeline(step_funcs) if step_funcs else None

        step_funcs = []
        for step in rag_steps:
            if step == RAGStep.GENERATE:
                break  # ChatManager does its own generation via LLM
            func = _STEP_MAP.get(step)
            if func is None:
                raise ValueError(
                    f"Unknown pipeline step: {step.value!r}. "
                    f"Available: {list(STEP_REGISTRY.keys())}"
                )
            step_funcs.append(func)
        return RAGPipeline(step_funcs) if step_funcs else None

    async def _count_tokens(self, text: str) -> int:
        if self.tokenizer is None:
            raise RuntimeError("Tokenizer not configured")
        return await asyncio.to_thread(self.tokenizer.count, text)

    async def _trim_history(
        self,
        history: list[dict[str, Any]],
        user_msg: UserMessage,
    ) -> list[dict[str, Any]]:
        """Trim oldest messages so system + history + user_msg fit token budget.

        Keeps the most recent messages that fit within the token budget.
        """
        budget = self.max_context_tokens or self.llm.get_context_limit()
        if not budget:
            limit = max(1, self.history_limit - 1)
            return (
                history[-limit:]
                if len(history) > limit
                else history
            )

        user_tokens = await self._count_tokens(user_msg.text or "")
        system_message = self.system_message
        system_tokens = await self._count_tokens(
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
            tokens = await self._count_tokens(text)
            if total + tokens > available:
                break
            total += tokens
            keep.append(h)

        keep.reverse()
        return keep

    async def _retrieve_context(
        self,
        message: str,
        history: list[dict[str, Any]] | None = None,
        trace_id: str | None = None,
    ) -> tuple[str, str, str | None, tuple[Chunk, ...]]:
        """Run RAG pipeline to build context for the given message.

        Args:
            message: Raw user message (may contain RAG prefix).
            history: Chat history as list of {role, content} dicts.
            trace_id: Structured logging trace identifier.

        Returns:
            (prompt_for_llm, original_query, namespace, rag_chunks)
        """
        if not self._pipeline:
            query_text, namespace = parse_rag_query(message, self._prefix_map)
            if namespace is not None:
                return query_text, query_text, namespace, ()
            return message, message, None, ()

        query_text, namespace = parse_rag_query(message, self._prefix_map)
        if namespace is None:
            # No RAG prefix detected — return original message unchanged
            return message, message, None, ()

        # Convert history dicts to (role, text) tuples for PipelineData
        chat_history: tuple[tuple[str, str], ...] = ()
        if history:
            chat_history = tuple(
                (h.get("role", "user"), h.get("content", ""))
                for h in history[-8:]
            )

        original_query_text = query_text  # preserve before pipeline mutation

        ns_cfg = self.namespaces.get(namespace)
        pipeline_config = PipelineConfig(
            top_k=self.top_k,
            namespace=namespace,
            relevance_threshold=ns_cfg.relevance_threshold if ns_cfg else 0.1,
            prompt_name=ns_cfg.prompt if ns_cfg else "rag_strict",
            prompt_version=self.prompt_version,
            token_margin_min=self.token_margin_min,
            token_margin_pct=self.token_margin_pct,
        )

        data = PipelineData(
            query=UserMessage(text=query_text),
            original_query=UserMessage(text=original_query_text),
            chat_history=chat_history,
            trace_id=trace_id or "",
            embedder=self.embedder,
            vector_store=self.vector_store,
            reranker=self.reranker,
            llm=self.llm,
            pipeline_config=pipeline_config,
            tokenizer=self.tokenizer,
        )

        data = await self._pipeline.run(data)

        # Recover original query if condense_question rewrote it
        if data.original_query is not None:
            original_query_text = data.original_query.text

        if data.errors:
            logger.warning(
                "Pipeline errors during retrieval",
                extra={"trace_id": trace_id, "errors": list(data.errors)},
            )

        if not data.chunks:
            # For general knowledge fallback, use the original (non-condensed) question
            prompt_text = (
                data.original_query.text
                if data.original_query is not None
                else (data.query.text if data.query else original_query_text)
            )
            return prompt_text, original_query_text, namespace, ()

        prompt = get_prompt(
            pipeline_config.prompt_name,
            version=self.prompt_version,
            query=data.query.text if data.query else original_query_text,
            context=data.context,
        )
        return prompt, original_query_text, namespace, data.chunks

    async def _build_messages(
        self,
        prompt_for_llm: str,
        conversation_id: str,
        history: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> list[Message]:
        """Build message list with history, system prompt, and token trimming.

        Prepend historical messages before the current user message.
        History is loaded once by the caller and passed through to avoid
        duplicate storage queries.
        """
        user_msg = UserMessage(text=prompt_for_llm, metadata=metadata or {})
        messages: list[Message] = [user_msg]

        if history is None and self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id,
                    limit=self.history_limit,
                    offset=0,
                )
            except Exception as exc:
                logger.warning("History load failed", extra={"error": str(exc)})
                history = []

        if history:
            try:
                trimmed = await self._trim_history(history, user_msg)
            except Exception as exc:
                logger.warning(
                    "Token-based trim failed, falling back to count-based",
                    extra={"error": str(exc)},
                )
                trimmed = (
                    history[-self.history_limit :]
                    if len(history) > self.history_limit
                    else list(history)
                )
            for h in trimmed:
                role = h.get("role", "")
                content = h.get("content", "")
                if role == "user":
                    messages.insert(-1, UserMessage(text=content))
                elif role == "assistant":
                    messages.insert(-1, AssistantMessage(text=content))

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
        start = time.perf_counter()
        logger.info(
            "Chat request",
            extra={
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "msg_len": len(message),
            },
        )

        # Load history once for both condensation and message building
        history: list[dict[str, Any]] = []
        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id,
                    limit=self.history_limit,
                    offset=0,
                )
            except Exception as exc:
                logger.warning("History load failed", extra={"error": str(exc)})

        (
            prompt_for_llm,
            original_query,
            namespace,
            rag_chunks,
        ) = await self._retrieve_context(
            message, history=history, trace_id=trace_id
        )

        messages = await self._build_messages(
            prompt_for_llm,
            conversation_id,
            history=history,
            metadata=meta,
        )

        try:
            response = await self.llm.complete(messages)
        except AdapterError:
            raise
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.error(
                "Chat failed",
                extra={
                    "trace_id": trace_id,
                    "conversation_id": conversation_id,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                },
            )
            raise AdapterError(f"LLM call failed: {exc}") from exc

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "Chat response",
            extra={
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "resp_len": len(response.text or ""),
                "duration_ms": duration_ms,
                "namespace": namespace,
                "chunks_used": len(rag_chunks),
            },
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
                logger.warning("History save failed", extra={"error": str(exc)})

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
        start = time.perf_counter()
        logger.info(
            "Stream request",
            extra={
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "msg_len": len(message),
            },
        )

        # Load history once for both condensation and message building
        history: list[dict[str, Any]] = []
        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id,
                    limit=self.history_limit,
                    offset=0,
                )
            except Exception as exc:
                logger.warning("History load failed", extra={"error": str(exc)})

        (
            prompt_for_llm,
            original_query,
            namespace,
            rag_chunks,
        ) = await self._retrieve_context(
            message, history=history, trace_id=trace_id
        )

        messages = await self._build_messages(
            prompt_for_llm,
            conversation_id,
            history=history,
            metadata=meta,
        )

        full_response = ""
        try:
            async for chunk in self.llm.stream(messages):
                full_response += chunk
                yield chunk
        except AdapterError:
            raise
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.error(
                "Stream failed",
                extra={
                    "trace_id": trace_id,
                    "conversation_id": conversation_id,
                    "duration_ms": duration_ms,
                    "error": str(exc),
                },
            )
            raise AdapterError(f"LLM stream failed: {exc}") from exc

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "Stream response",
            extra={
                "trace_id": trace_id,
                "conversation_id": conversation_id,
                "resp_len": len(full_response),
                "duration_ms": duration_ms,
                "namespace": namespace,
                "chunks_used": len(rag_chunks),
            },
        )

        # Yield sources block so the client sees them in the stream
        sources_text = self._append_rag_sources(full_response, rag_chunks)
        if sources_text != full_response:
            yield sources_text[len(full_response):]

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
                logger.warning("History save failed", extra={"error": str(exc)})
