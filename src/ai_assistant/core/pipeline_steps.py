"""RAG pipeline steps with namespace and rerank support.
All steps return new PipelineData instances via dataclasses.replace().
No in-place mutation.
"""

from __future__ import annotations

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
    AdapterError,
)
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.metrics import increment_counter
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import count_tokens

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Sequence

    from ai_assistant.core.domain.documents import Chunk
    from ai_assistant.core.domain.pipeline import PipelineData
    from ai_assistant.core.ports.llm import Message

__all__: list[str] = [
    "build_context",
    "embed_query",
    "generate",
    "rerank",
    "retrieve",
    "STEP_REGISTRY",
    "step",
]

_logger = get_logger("pipeline.steps")

STEP_REGISTRY: dict[str, Callable[[PipelineData], Awaitable[PipelineData]]] = {}

# --- Token budget constants for generate() ---------------------------------
TOKEN_MARGIN_MIN = 256  # absolute minimum tokens reserved for response
TOKEN_MARGIN_PCT = 0.1  # fraction of context window reserved for response


def step(
    name: str,
) -> Callable[
    [Callable[[PipelineData], Awaitable[PipelineData]]],
    Callable[[PipelineData], Awaitable[PipelineData]],
]:
    """Register a pipeline step by its config name."""

    def decorator(
        func: Callable[[PipelineData], Awaitable[PipelineData]],
    ) -> Callable[[PipelineData], Awaitable[PipelineData]]:
        STEP_REGISTRY[name] = func
        return func

    return decorator


def _estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    return count_tokens(text, model)


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


@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def _call_llm(llm: Any, messages: Sequence[Message]) -> AssistantMessage:
    """Call LLM with retry."""
    return await llm.complete(messages)


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
    _logger.info("embed_query start", extra={"trace_id": data.trace_id})
    embedder = data.metadata.get("embedder")
    if embedder is None:
        _logger.warning("embed_query: no embedder", extra={"trace_id": data.trace_id})
        return data.add_error(EMBEDDER_NOT_PROVIDED)
    if data.query is None or not data.query.text:
        _logger.warning("embed_query: no query text", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_TEXT_MISSING)
    try:
        embeddings = await _call_embed(embedder, data.query.text)
        if not embeddings:
            _logger.warning(
                "embed_query: empty embedding response",
                extra={"trace_id": data.trace_id},
            )
            return data.add_error(INTERNAL_SERVER_ERROR)
        new_metadata = {**data.metadata, "query_embedding": embeddings[0]}
        _logger.info("embed_query done", extra={"trace_id": data.trace_id})
        return replace(data, metadata=new_metadata)
    except Exception:
        _logger.exception("embed_query failed", extra={"trace_id": data.trace_id})
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
    _logger.info("retrieve start", extra={"trace_id": data.trace_id})
    vector_store = data.metadata.get("vector_store")
    if vector_store is None:
        _logger.warning("retrieve: no vector_store", extra={"trace_id": data.trace_id})
        return data.add_error(VECTOR_STORE_NOT_PROVIDED)
    embedding = data.metadata.get("query_embedding")
    if embedding is None:
        _logger.warning("retrieve: no embedding", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_EMBEDDING_MISSING)
    try:
        top_k = data.metadata.get("top_k", 5)
        namespace = data.metadata.get("namespace") or "default"
        chunks = await _call_search(vector_store, embedding, top_k, namespace)
        increment_counter(
            "ai_assistant_rag_retrieve_total",
            labels={"namespace": namespace},
        )
        _logger.info(
            "retrieve done: %d chunks", len(chunks), extra={"trace_id": data.trace_id}
        )
        return data.with_chunks(chunks)
    except Exception:
        _logger.exception("retrieve failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("rerank")
async def rerank(data: PipelineData) -> PipelineData:
    """Rerank retrieved chunks by relevance and filter by threshold.

    Metadata contract:
        IN:  reranker (IReranker) — required, never None (NullReranker if disabled).
             top_k (int) — optional, default 5.
             relevance_threshold (float) — optional, default 0.3.
        OUT: rerank_filtered_out (bool) — set True if all chunks filtered.
             rerank_scores (list[float]) — set if chunks survive filtering.
        DATA: chunks (list[Chunk]) — replaced with filtered subset.

    Errors added on failure:
        INTERNAL_SERVER_ERROR.
    """
    _logger.info(
        "rerank start: %d chunks", len(data.chunks), extra={"trace_id": data.trace_id}
    )
    if not data.chunks:
        return replace(data)

    reranker = data.metadata.get("reranker")
    assert reranker is not None  # ← FIX: api/deps guarantees NullReranker fallback
    # reranker is guaranteed non-None by api/deps (NullReranker fallback)
    # No branching on None — keeps pipeline pure.

    try:
        _raw_query = data.query.text if data.query is not None else None
        query = _raw_query if _raw_query is not None else " "
        top_k = data.metadata.get("top_k", 5)
        threshold = data.metadata.get("relevance_threshold", 0.3)

        results = await reranker.rerank(query, data.chunks, top_k=top_k)

        filtered = [r for r in results if r.score >= threshold]

        if not filtered:
            new_metadata = {
                **data.metadata,
                "rerank_filtered_out": True,
            }
            _logger.info(
                "rerank: all chunks filtered out", extra={"trace_id": data.trace_id}
            )
            return replace(data, chunks=(), metadata=new_metadata)
        else:
            new_metadata = {
                **data.metadata,
                "rerank_scores": [r.score for r in filtered],
            }
            _logger.info(
                "rerank done: %d chunks",
                len(filtered),
                extra={"trace_id": data.trace_id},
            )
            return replace(
                data,
                chunks=tuple(r.chunk for r in filtered),
                metadata=new_metadata,
            )

    except Exception:
        _logger.exception("rerank failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("build_context")
async def build_context(data: PipelineData) -> PipelineData:
    """Build context string from retrieved (and reranked) chunks.

    Metadata contract:
        DATA: chunks (list[Chunk]) — read; context (str) — produced.
    """
    _logger.info(
        "build_context start: %d chunks",
        len(data.chunks),
        extra={"trace_id": data.trace_id},
    )
    if not data.chunks:
        return data.with_context("")
    lines = [chunk.text for chunk in data.chunks if chunk.text]
    context = "\n\n".join(lines)
    _logger.info(
        "build_context done: %d chars", len(context), extra={"trace_id": data.trace_id}
    )
    return data.with_context(context)


def _build_fallback_prompt(chunks: tuple[Chunk, ...], query_text: str) -> str:
    """Build a minimal RAG prompt from chunks when template lookup fails."""
    chunks_text = "\n".join(f"[{i + 1}] {c.text}" for i, c in enumerate(chunks))
    return f"Context:\n{chunks_text}\n\nQuestion: {query_text}\nAnswer:"


def _truncate_to_fit(
    data: PipelineData,
    prompt: str,
    prompt_name: str,
    prompt_version: str,
    query_text: str,
    limit: int,
) -> tuple[PipelineData, str]:
    """Remove chunks from the end until prompt fits in the token limit.

    Returns:
        (updated_data, updated_prompt). If all chunks are exhausted and
        the prompt still exceeds the limit, updated_data will have empty
        chunks and updated_prompt will reflect the last attempted context.
    """
    prompt_tokens = _estimate_tokens(prompt)
    current_data = data
    while current_data.chunks and prompt_tokens > limit:
        new_chunks = current_data.chunks[:-1]
        if not new_chunks:
            current_data = current_data.with_chunks(()).with_context("")
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
            prompt = _build_fallback_prompt(current_data.chunks, query_text)
        prompt_tokens = _estimate_tokens(prompt)
    return current_data, prompt


@step("generate")
async def generate(data: PipelineData) -> PipelineData:
    _logger.info("generate start", extra={"trace_id": data.trace_id})
    llm = data.metadata.get("llm")
    if llm is None:
        _logger.warning("generate: no llm", extra={"trace_id": data.trace_id})
        return data.add_error(LLM_NOT_PROVIDED)
    if data.query is None:
        _logger.warning("generate: no query", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_MISSING)

    query_text = data.query.text or "  "
    prompt_version = data.metadata.get("prompt_version", "v1")
    prompt_name = data.metadata.get("prompt_name", "rag_strict")

    try:
        prompt = get_prompt(
            prompt_name,
            version=prompt_version,
            query=query_text,
            context=data.context,
        )
    except Exception:
        prompt = _build_fallback_prompt(data.chunks, query_text)

    max_ctx = llm.get_context_limit()
    if max_ctx is None or max_ctx <= 0:
        max_ctx = 4096

    prompt_tokens = _estimate_tokens(prompt)
    margin = max(TOKEN_MARGIN_MIN, int(max_ctx * TOKEN_MARGIN_PCT))
    limit = max_ctx - margin

    if prompt_tokens > limit:
        data, prompt = _truncate_to_fit(
            data, prompt, prompt_name, prompt_version, query_text, limit
        )
        prompt_tokens = _estimate_tokens(prompt)
        if prompt_tokens > limit:
            error_msg = (
                f"generate: prompt too long ({prompt_tokens} tokens)  "
                f"exceeds limit ({limit}) "
            )
            return data.add_error(error_msg).with_response(
                AssistantMessage(
                    text=(
                        "Sorry, the retrieved context is too large  "
                        "to process. Please narrow your query. "
                    )
                )
            )

    messages: list[Message] = [UserMessage(text=prompt)]
    response: AssistantMessage | None = None

    try:
        response = await _call_llm(llm, messages)
    except AdapterError:
        # Intentional bypass: LLM unavailability is a transient infrastructure
        # failure, not a pipeline logic error. The HTTP layer maps this to 503.
        _logger.exception("LLM unavailable", extra={"trace_id": data.trace_id})
        raise
    except Exception:
        _logger.exception(
            "generate failed after retries", extra={"trace_id": data.trace_id}
        )
        return data.add_error(INTERNAL_SERVER_ERROR).with_response(
            AssistantMessage(
                text="Sorry, I encountered an error generating the response. "
            )
        )

    _logger.info("generate done", extra={"trace_id": data.trace_id})
    return data.with_response(response)


@step("hyde_query")
async def hyde_query(data: PipelineData) -> PipelineData:
    """Hypothetical Document Embedding (HyDE).

    Generates a hypothetical answer to the query, embeds it,
    and stores the embedding in metadata for downstream retrieval.
    """
    _logger.info("hyde_query start", extra={"trace_id": data.trace_id})
    embedder = data.metadata.get("embedder")
    llm = data.metadata.get("llm")
    if embedder is None:
        _logger.warning("hyde_query: no embedder", extra={"trace_id": data.trace_id})
        return data.add_error(EMBEDDER_NOT_PROVIDED)
    if llm is None:
        _logger.warning("hyde_query: no llm", extra={"trace_id": data.trace_id})
        return data.add_error(LLM_NOT_PROVIDED)
    if data.query is None or not data.query.text:
        _logger.warning("hyde_query: no query text", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_TEXT_MISSING)

    # Generate hypothetical answer
    hyde_messages = [
        UserMessage(
            text=f"Write a short passage that answers this question: {data.query.text}"
        )
    ]
    try:
        hyde_resp: AssistantMessage = await _call_llm(llm, hyde_messages)
    except Exception:
        _logger.exception(
            "hyde_query: LLM call failed", extra={"trace_id": data.trace_id}
        )
        return data.add_error(INTERNAL_SERVER_ERROR)

    hyde_text = hyde_resp.text or ""
    if not hyde_text:
        return data.add_error("hyde_query: empty hypothetical answer")

    # Embed hypothetical answer
    try:
        embeddings = await _call_embed(embedder, hyde_text)
        if not embeddings:
            _logger.warning(
                "hyde_query: empty embedding response",
                extra={"trace_id": data.trace_id},
            )
            return data.add_error(INTERNAL_SERVER_ERROR)
    except Exception:
        _logger.exception(
            "hyde_query: embedding failed", extra={"trace_id": data.trace_id}
        )
        return data.add_error(INTERNAL_SERVER_ERROR)

    new_metadata = {**data.metadata, "query_embedding": embeddings[0]}
    _logger.info("hyde_query done", extra={"trace_id": data.trace_id})
    return replace(data, metadata=new_metadata)
