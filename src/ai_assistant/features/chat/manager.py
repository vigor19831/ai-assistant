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
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import STEP_REGISTRY
from ai_assistant.core.ports.tokenizer import ITokenizer
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.query_parser import parse_rag_query

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
    from ai_assistant.core.ports.llm import Message

__all__ = ["ChatManager"]

logger = get_logger("chat")


# ---------------------------------------------------------------------------
# Pipeline step functions — moved from deps.py to where they are used
# ---------------------------------------------------------------------------

_STEP_MAP: dict[RAGStep, Any] = {
    RAGStep(k): v for k, v in STEP_REGISTRY.items() if k in {m.value for m in RAGStep}
}


def _build_step_funcs(
    cfg: Any,
    stop_at: RAGStep | None = None,
) -> list[Any]:
    """Build pipeline step functions. Stops before *stop_at* if provided.

    NOTE: Currently unused. ChatManager uses a fixed retrieval pipeline
    (embed_query -> retrieve -> rerank -> build_context) because generation
    is handled separately via llm.complete(). If a unified pipeline is
    needed in the future, wire this function into _build_pipeline and
    pass cfg.rag.steps from handlers.py. See ai_rules.md §2.1.
    """
    step_funcs: list[Any] = []
    for step in cfg.rag.steps:
        if stop_at is not None and step == stop_at:
            break
        func = _STEP_MAP.get(step)
        if func is None:
            raise ValueError(f"Unknown step: {step}")
        step_funcs.append(func)
    return step_funcs


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
        max_history_messages: int = 10_000,
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
    ) -> None:
        self.llm = llm
        self.reranker = reranker
        self.storage = storage
        self.history_limit = history_limit
        self.max_history_messages = max_history_messages
        self.max_context_tokens = max_context_tokens
        self.embedder = embedder
        self.vector_store = vector_store
        self.namespaces = namespaces or {}
        self.prompt_version = prompt_version
        self.top_k = top_k
        self.token_margin_min = token_margin_min
        self.token_margin_pct = token_margin_pct
        self.tokenizer = tokenizer

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
            # Default retrieval pipeline: embed_query -> retrieve -> rerank -> build_context
            default_steps = [
                RAGStep.EMBED_QUERY,
                RAGStep.RETRIEVE,
                RAGStep.RERANK,
                RAGStep.BUILD_CONTEXT,
            ]
            step_funcs = []
            for step in default_steps:
                func = _STEP_MAP.get(step)
                if func is not None:
                    step_funcs.append(func)
            return RAGPipeline(step_funcs) if step_funcs else None

        step_funcs = []
        for step in rag_steps:
            if step == RAGStep.GENERATE:
                break  # ChatManager does its own generation via LLM
            func = _STEP_MAP.get(step)
            if func is not None:
                step_funcs.append(func)
        return RAGPipeline(step_funcs) if step_funcs else None

    async def _count_tokens(self, text: str) -> int:
        if self.tokenizer is None:
            raise RuntimeError("Tokenizer not configured")
        return await asyncio.to_thread(self.tokenizer.count, text, self.tokenizer.model_name)

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
            return (
                history[-self.history_limit :]
                if len(history) > self.history_limit
                else history
            )

        user_tokens = await self._count_tokens(user_msg.text or "")
        system_message = self.llm.system_message
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
        self, message: str, trace_id: str | None = None
    ) -> tuple[str, str, str, tuple[Chunk, ...]]:
        """Run RAG retrieval and return (prompt_for_llm, original_query, namespace, rag_chunks).

        If RAG is not triggered or no results are found, returns the original
        message unchanged with empty chunks.
        """
        if not self._pipeline:
            return message, message, "default", ()

        query_text, namespace = parse_rag_query(message)
        if namespace == "default" and message == query_text:
            # No RAG prefix detected — return original message unchanged
            return message, message, "default", ()

        ns_cfg = self.namespaces.get(namespace)
        relevance_threshold = ns_cfg.relevance_threshold if ns_cfg else 0.3
        prompt_name = ns_cfg.prompt if ns_cfg else "rag_strict"

        from ai_assistant.core.domain.pipeline import PipelineConfig

        pipeline_config = PipelineConfig(
            top_k=self.top_k,
            namespace=namespace,
            relevance_threshold=relevance_threshold,
            prompt_name=prompt_name,
            prompt_version=self.prompt_version,
            token_margin_min=self.token_margin_min,
            token_margin_pct=self.token_margin_pct,
        )

        data = PipelineData(
            query=UserMessage(text=query_text),
            trace_id=trace_id or "",
            embedder=self.embedder,
            vector_store=self.vector_store,
            reranker=self.reranker,
            pipeline_config=pipeline_config,
            tokenizer=self.tokenizer,
        )

        data = await self._pipeline.run(data)

        if not data.chunks:
            return query_text, query_text, namespace, ()

        prompt = get_prompt(
            prompt_name,
            version=self.prompt_version,
            query=query_text,
            context=data.context,
        )
        return prompt, query_text, namespace, data.chunks

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
                    history = await self._trim_history(history, user_msg)
                except Exception as exc:
                    logger.warning(
                        "Token-based trim failed, falling back to count-based",
                        extra={"error": str(exc)},
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
                logger.warning("History load failed", extra={"error": str(exc)})

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

        # Graceful degradation: RAG requested but infrastructure unavailable
        _clean, _ns = parse_rag_query(message)
        if _ns != "default" and not self._pipeline:
            return AssistantMessage(
                text="Document search (RAG) temporarily unavailable."
            )

        (
            prompt_for_llm,
            original_query,
            namespace,
            rag_chunks,
        ) = await self._retrieve_context(message, trace_id=trace_id)

        messages = await self._build_messages(
            prompt_for_llm, conversation_id, metadata=meta
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

        # Graceful degradation: RAG requested but infrastructure unavailable
        _clean, _ns = parse_rag_query(message)
        if _ns != "default" and not self._pipeline:
            yield "Document search (RAG) temporarily unavailable."
            return

        (
            prompt_for_llm,
            original_query,
            namespace,
            rag_chunks,
        ) = await self._retrieve_context(message, trace_id=trace_id)

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
        sources_text = self._append_rag_sources("", rag_chunks)
        if sources_text:
            yield sources_text

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
