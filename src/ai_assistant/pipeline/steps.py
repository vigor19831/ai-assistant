"""RAG pipeline steps with namespace and rerank support.

All steps return new PipelineData instances via dataclasses.replace().
No in-place mutation.
"""

from __future__ import annotations

import asyncio
import json
import random
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ai_assistant.core.domain.errors import (
    EMBEDDER_NOT_PROVIDED,
    INTERNAL_SERVER_ERROR,
    LLM_NOT_PROVIDED,
    QUERY_EMBEDDING_MISSING,
    QUERY_MISSING,
    QUERY_TEXT_MISSING,
    VECTOR_STORE_NOT_PROVIDED,
)
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.metrics import record_metric
from ai_assistant.core.ports.tools import ToolCall
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import count_tokens, get_context_limit
from ai_assistant.pipeline.decorators import step

if TYPE_CHECKING:
    from ai_assistant.core.domain.pipeline import PipelineData

__all__: list[str] = [
    "build_context",
    "embed_query",
    "generate",
    "rerank",
    "retrieve",
]

_logger = get_logger("pipeline.steps")


def _estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    return count_tokens(text, model)


def _get_llm_context_limit(llm: Any) -> int | None:
    return get_context_limit(llm)


# --- retry helpers for network calls ----------------------------------------


@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def _call_embed(embedder: Any, text: str) -> list[list[float]]:
    """Embed a single text with retry."""
    return await embedder.embed([text])


@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def _call_search(
    vector_store: Any, embedding: list[float], top_k: int, namespace: str
) -> list[Any]:
    """Search vector store with retry."""
    return await vector_store.search(embedding, top_k=top_k, namespace=namespace)


@step("embed_query")
async def embed_query(data: PipelineData) -> PipelineData:
    """Embed the user query text.

    Metadata contract:
        IN:  embedder (IEmbedder) — required.
        OUT: query_embedding (list[float]) — produced on success.
        DATA: query.text (str) — must be non-empty.

    Errors added on failure:
        EMBEDDER_NOT_PROVIDED, QUERY_TEXT_MISSING, INTERNAL_SERVER_ERROR.
    """
    embedder = data.metadata.get("embedder")
    if embedder is None:
        return data.add_error(EMBEDDER_NOT_PROVIDED)
    if data.query is None or not data.query.text:
        return data.add_error(QUERY_TEXT_MISSING)
    try:
        embeddings = await _call_embed(embedder, data.query.text)
        new_metadata = {**data.metadata, "query_embedding": embeddings[0]}
        return replace(data, metadata=new_metadata)
    except Exception:
        _logger.exception("embed_query failed")
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("retrieve")
async def retrieve(data: PipelineData) -> PipelineData:
    """Retrieve relevant chunks from vector store (namespace-aware).

    Metadata contract:
        IN:  vector_store (IVectorStore) — required.
             query_embedding (list[float]) — produced by embed_query.
             top_k (int) — optional, default 5.
             namespace (str) — optional, default "default".
        OUT: chunks (list[Chunk]) — written to PipelineData.chunks.
             Metric "rag_chunks" recorded.

    Errors added on failure:
        VECTOR_STORE_NOT_PROVIDED, QUERY_EMBEDDING_MISSING, INTERNAL_SERVER_ERROR.
    """
    vector_store = data.metadata.get("vector_store")
    if vector_store is None:
        return data.add_error(VECTOR_STORE_NOT_PROVIDED)
    embedding = data.metadata.get("query_embedding")
    if embedding is None:
        return data.add_error(QUERY_EMBEDDING_MISSING)
    try:
        top_k = data.metadata.get("top_k", 5)
        namespace = data.metadata.get("namespace") or "default"
        chunks = await _call_search(vector_store, embedding, top_k, namespace)
        record_metric("rag_chunks", len(chunks))
        return data.with_chunks(chunks)
    except Exception:
        _logger.exception("retrieve failed")
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("rerank")
async def rerank(data: PipelineData) -> PipelineData:
    """Rerank retrieved chunks by relevance and filter by threshold.

    If reranker is not configured (None), acts as transparent pass-through.

    Metadata contract:
        IN:  reranker (IReranker) — optional; if None, step is no-op.
             top_k (int) — optional, default 5.
             relevance_threshold (float) — optional, default 0.3.
        OUT: rerank_filtered_out (bool) — set True if all chunks filtered.
             rerank_scores (list[float]) — set if chunks survive filtering.
        DATA: chunks (list[Chunk]) — replaced with filtered subset.

    Errors added on failure:
        INTERNAL_SERVER_ERROR.
    """
    if not data.chunks:
        return data

    reranker = data.metadata.get("reranker")
    if reranker is None:
        return data

    try:
        _raw_query = data.query.text if data.query is not None else None
        query = _raw_query if _raw_query is not None else ""
        top_k = data.metadata.get("top_k", 5)
        threshold = data.metadata.get("relevance_threshold", 0.3)

        results = await reranker.rerank(query, data.chunks, top_k=top_k)

        filtered = [r for r in results if r.score >= threshold]

        if not filtered:
            new_metadata = {
                **data.metadata,
                "rerank_filtered_out": True,
            }
            return replace(data, chunks=[], metadata=new_metadata)
        else:
            new_metadata = {
                **data.metadata,
                "rerank_scores": [r.score for r in filtered],
            }
            return replace(
                data,
                chunks=[r.chunk for r in filtered],
                metadata=new_metadata,
            )

    except Exception:
        _logger.exception("rerank failed")
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("build_context")
async def build_context(data: PipelineData) -> PipelineData:
    """Build context string from retrieved (and reranked) chunks.

    Metadata contract:
        DATA: chunks (list[Chunk]) — read; context (str) — produced.
    """
    if not data.chunks:
        return data.with_context("")
    lines = [chunk.text for chunk in data.chunks if chunk.text]
    return data.with_context("\n\n".join(lines))


@step("generate")
async def generate(data: PipelineData) -> PipelineData:
    """Generate response using LLM with context.

    Metadata contract:
        IN:  llm (ILLM) — required.
             prompt_version (str) — required.
             prompt_name (str) — required.
             tool_registry (ToolRegistry) — optional.
        OUT: response (AssistantMessage) — written to PipelineData.response.
             Metrics "input_tokens", "output_tokens" recorded.
        DATA: query (UserMessage) — required; context (str) — used in prompt.

    Errors added on failure:
        LLM_NOT_PROVIDED, QUERY_MISSING, INTERNAL_SERVER_ERROR.
    """
    llm = data.metadata.get("llm")
    if llm is None:
        return data.add_error(LLM_NOT_PROVIDED)
    if data.query is None:
        return data.add_error(QUERY_MISSING)

    query_text = data.query.text or ""
    prompt_version = data.metadata["prompt_version"]
    prompt_name = data.metadata["prompt_name"]

    def _build_fallback_prompt() -> str:
        chunks_text = "\n".join(
            f"[{i + 1}] {c.text}" for i, c in enumerate(data.chunks)
        )
        return f"Context:\n{chunks_text}\n\nQuestion: {query_text}\nAnswer:"

    try:
        prompt = get_prompt(
            prompt_name,
            version=prompt_version,
            query=query_text,
            context=data.context,
        )
    except Exception:
        prompt = _build_fallback_prompt()

    record_metric("input_tokens", _estimate_tokens(prompt))

    max_ctx = _get_llm_context_limit(llm)
    if isinstance(max_ctx, int) and max_ctx > 0:
        prompt_tokens = _estimate_tokens(prompt)
        margin = max(256, int(max_ctx * 0.1))
        limit = max_ctx - margin
        current_data = data
        while current_data.chunks and prompt_tokens > limit:
            new_chunks = current_data.chunks[:-1]
            if not new_chunks:
                current_data = current_data.with_context("")
                break
            current_data = current_data.with_chunks(new_chunks)
            lines = [chunk.text for chunk in current_data.chunks if chunk.text]
            current_data = current_data.with_context("\n\n".join(lines))
            try:
                prompt = get_prompt(
                    prompt_name,
                    version=prompt_version,
                    query=query_text,
                    context=current_data.context,
                )
            except Exception:
                prompt = _build_fallback_prompt()
            prompt_tokens = _estimate_tokens(prompt)
        if prompt_tokens > limit:
            error_msg = (
                f"generate: prompt too long ({prompt_tokens} tokens) "
                f"exceeds limit ({limit})"
            )
            return current_data.add_error(error_msg).with_response(
                AssistantMessage(
                    text=(
                        "Sorry, the retrieved context is too large "
                        "to process. Please narrow your query."
                    )
                )
            )
        data = current_data

    original_image = data.query.image if data.query else None

    messages: list[Any] = [UserMessage(text=prompt, image=original_image)]
    response: AssistantMessage | None = None

    max_retries = 2  # 3 attempts total: initial + 2 retries
    base_delay = 1.0
    backoff = 2.0
    max_delay = 8.0

    for attempt in range(max_retries + 1):
        try:
            response = await llm.complete(messages)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.exception("generate failed (attempt %d)", attempt + 1)
            if attempt < max_retries:
                sleep_for = min(base_delay * (backoff**attempt), max_delay)
                sleep_for = random.uniform(sleep_for * 0.8, sleep_for * 1.2)
                await asyncio.sleep(sleep_for)
                continue
            return data.add_error(INTERNAL_SERVER_ERROR).with_response(
                AssistantMessage(
                    text=("Sorry, I encountered an error generating the response.")
                )
            )

        if not response or not response.tool_calls:
            break

        messages.append(response)

        tool_registry = data.metadata.get("tool_registry")
        if tool_registry:
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
                    result = await tool_registry.dispatch(tc)
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

    final_response = (
        response
        if response
        else AssistantMessage(text="Sorry, tool call loop exhausted.")
    )
    record_metric(
        "output_tokens",
        _estimate_tokens(final_response.text or ""),
    )
    return data.with_response(final_response)
