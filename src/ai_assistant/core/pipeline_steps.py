"""
RAG pipeline steps with namespace and rerank support.
All steps return new PipelineData instances via dataclasses.replace().
No in-place mutation.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import TYPE_CHECKING

from ai_assistant.core.domain.configs import RetryConfig
from ai_assistant.core.domain.errors import (
    EMBEDDER_NOT_PROVIDED,
    INTERNAL_SERVER_ERROR,
    LLM_NOT_PROVIDED,
    LLM_UNAVAILABLE,
    QUERY_EMBEDDING_MISSING,
    QUERY_MISSING,
    QUERY_TEXT_MISSING,
    VECTOR_STORE_NOT_PROVIDED,
    AdapterError,
    ConfigurationError,
)
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineConfig, PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.metrics import increment_counter
from ai_assistant.core.ports.tokenizer import ITokenizer
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.retry import retry_with_config

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_assistant.core.domain.documents import Chunk
    from ai_assistant.core.domain.pipeline import PipelineData
    from ai_assistant.core.ports.embedder import IEmbedder
    from ai_assistant.core.ports.llm import ILLM, Message
    from ai_assistant.core.ports.reranker import IReranker, RerankResult
    from ai_assistant.core.ports.tokenizer import ITokenizer
    from ai_assistant.core.ports.vector_store import IVectorStore

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


def _get_config(data: PipelineData) -> PipelineConfig:
    """Return pipeline config, raising if missing.

    RAGPipeline.run() pre-check guarantees this never raises in normal
    execution. The explicit check exists for type narrowing (mypy) and
    for direct step calls in tests.
    """
    cfg = data.pipeline_config
    if cfg is None:
        raise ConfigurationError("pipeline_config is required in PipelineData")
    return cfg


async def _estimate_tokens(text: str, tokenizer: ITokenizer) -> int:
    return await asyncio.to_thread(tokenizer.count, text, tokenizer.model_name)


# --- retry helpers for network calls ----------------------------------------


async def _call_embed(embedder: IEmbedder, text: str, config: RetryConfig) -> list[list[float]]:
    """Embed a single text with retry."""
    return await retry_with_config(lambda: embedder.embed([text]), config)


async def _call_search(
    vector_store: IVectorStore,
    embedding: list[float],
    top_k: int,
    namespace: str,
    config: RetryConfig,
) -> list[Chunk]:
    """Search vector store with retry."""
    return await retry_with_config(
        lambda: vector_store.search(embedding, top_k=top_k, namespace=namespace),
        config,
    )


async def _call_llm(
    llm: ILLM, messages: list[Message], config: RetryConfig
) -> AssistantMessage:
    """Call LLM with retry."""
    return await retry_with_config(lambda: llm.complete(messages), config)


async def _call_rerank(
    reranker: IReranker,
    query: str,
    chunks: tuple[Chunk, ...],
    top_k: int,
    config: RetryConfig,
) -> list[RerankResult]:
    """Rerank chunks with retry."""
    return await retry_with_config(
        lambda: reranker.rerank(query, list(chunks), top_k=top_k),
        config,
    )


@step("embed_query")
async def embed_query(data: PipelineData) -> PipelineData:
    """Embed the user query text.

    Field contract:
        IN:  embedder (IEmbedder) — required.
        OUT: query_embedding (list[float]) — produced on success.
        DATA: query.text (str) — must be non-empty.

    Errors added on failure:
        EMBEDDER_NOT_PROVIDED, QUERY_TEXT_MISSING, INTERNAL_SERVER_ERROR.
    """
    _logger.debug("embed_query start", extra={"trace_id": data.trace_id})
    embedder = data.embedder
    if embedder is None:
        _logger.warning("embed_query: no embedder", extra={"trace_id": data.trace_id})
        return data.add_error(EMBEDDER_NOT_PROVIDED)
    if data.query is None or not data.query.text:
        _logger.warning("embed_query: no query text", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_TEXT_MISSING)
    cfg = _get_config(data)
    retry_cfg = cfg.retry if cfg.retry is not None else RetryConfig()
    try:
        embeddings = await _call_embed(embedder, data.query.text, retry_cfg)
        if not embeddings:
            _logger.warning(
                "embed_query: empty embedding response",
                extra={"trace_id": data.trace_id},
            )
            return data.add_error(INTERNAL_SERVER_ERROR)
        _logger.debug("embed_query done", extra={"trace_id": data.trace_id})
        return data.with_query_embedding(embeddings[0])
    except Exception:
        _logger.exception("embed_query failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("retrieve")
async def retrieve(data: PipelineData) -> PipelineData:
    """Retrieve relevant chunks from vector store (namespace-aware).

    Field contract:
        IN:  vector_store (IVectorStore) — required.
             query_embedding (list[float]) — produced by embed_query.
             pipeline_config (PipelineConfig) — provides top_k, namespace.
        OUT: chunks (tuple[Chunk, ...]) — written to PipelineData.chunks.
             Metric "rag_chunks" recorded.

    Errors added on failure:
        VECTOR_STORE_NOT_PROVIDED, QUERY_EMBEDDING_MISSING, INTERNAL_SERVER_ERROR.
    """
    _logger.debug("retrieve start", extra={"trace_id": data.trace_id})
    vector_store = data.vector_store
    if vector_store is None:
        _logger.warning("retrieve: no vector_store", extra={"trace_id": data.trace_id})
        return data.add_error(VECTOR_STORE_NOT_PROVIDED)
    embedding = data.query_embedding
    if embedding is None:
        _logger.warning("retrieve: no embedding", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_EMBEDDING_MISSING)
    try:
        cfg = _get_config(data)
        top_k = cfg.top_k
        namespace = cfg.namespace
        retry_cfg = cfg.retry if cfg.retry is not None else RetryConfig()
        chunks = await _call_search(vector_store, embedding, top_k, namespace, retry_cfg)
        increment_counter(
            "ai_assistant_rag_retrieve_total",
            labels={"namespace": namespace},
        )
        _logger.debug(
            "retrieve done", extra={"trace_id": data.trace_id, "chunks": len(chunks)}
        )
        return data.with_chunks(chunks)
    except Exception:
        _logger.exception("retrieve failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("rerank")
async def rerank(data: PipelineData) -> PipelineData:
    """Rerank retrieved chunks by relevance and filter by threshold.

    Field contract:
        IN:  reranker (IReranker) — required, never None (NullReranker if disabled).
             pipeline_config (PipelineConfig) — provides top_k, relevance_threshold.
        OUT: rerank_filtered_out (bool) — set True if all chunks filtered.
             rerank_scores (list[float]) — set if chunks survive filtering.
        DATA: chunks (tuple[Chunk, ...]) — replaced with filtered subset.

    Errors added on failure:
        INTERNAL_SERVER_ERROR.
    """
    _logger.debug(
        "rerank start", extra={"trace_id": data.trace_id, "chunks": len(data.chunks)}
    )
    if not data.chunks:
        return replace(data)

    reranker = data.reranker
    if reranker is None:
        _logger.warning("rerank: no reranker", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)

    try:
        _raw_query = data.query.text if data.query is not None else None
        query = _raw_query if _raw_query is not None else " "
        cfg = _get_config(data)
        top_k = cfg.top_k
        threshold = cfg.relevance_threshold
        retry_cfg = cfg.retry if cfg.retry is not None else RetryConfig()

        results = await _call_rerank(reranker, query, data.chunks, top_k, retry_cfg)

        filtered = [r for r in results if r.score >= threshold]

        if not filtered:
            _logger.debug(
                "rerank: all chunks filtered out", extra={"trace_id": data.trace_id}
            )
            return data.with_chunks(()).with_rerank_filtered_out(True)
        else:
            _logger.debug(
                "rerank done",
                extra={"trace_id": data.trace_id, "chunks": len(filtered)},
            )
            return (
                data.with_chunks(tuple(r.chunk for r in filtered))
                .with_rerank_scores([r.score for r in filtered])
            )

    except Exception:
        _logger.exception("rerank failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("build_context")
async def build_context(data: PipelineData) -> PipelineData:
    """Build context string from retrieved (and reranked) chunks.

    Field contract:
        DATA: chunks (tuple[Chunk, ...]) — read; context (str) — produced.
    """
    _logger.debug(
        "build_context start",
        extra={"trace_id": data.trace_id, "chunks": len(data.chunks)},
    )
    if not data.chunks:
        return data.with_context("")
    lines = [chunk.text for chunk in data.chunks if chunk.text]
    context = "\n\n".join(lines)
    _logger.debug(
        "build_context done",
        extra={"trace_id": data.trace_id, "chars": len(context)},
    )
    return data.with_context(context)


def _build_fallback_prompt(chunks: tuple[Chunk, ...], query_text: str) -> str:
    """Build a minimal RAG prompt from chunks when template lookup fails."""
    chunks_text = "\n".join(f"[{i + 1}] {c.text}" for i, c in enumerate(chunks))
    return f"Context:\n{chunks_text}\n\nQuestion: {query_text}\nAnswer:"


async def _truncate_to_fit(
    data: PipelineData,
    prompt: str,
    prompt_name: str,
    prompt_version: str,
    query_text: str,
    limit: int,
    tokenizer: ITokenizer,
) -> tuple[PipelineData, str]:
    """Remove chunks from the end until prompt fits in the token limit.

    Returns:
        (updated_data, updated_prompt). If all chunks are exhausted and
        the prompt still exceeds the limit, updated_data will have empty
        chunks and updated_prompt will reflect the last attempted context.
    """
    prompt_tokens = await _estimate_tokens(prompt, tokenizer=tokenizer)
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
        prompt_tokens = await _estimate_tokens(prompt, tokenizer=tokenizer)
    return current_data, prompt


@step("generate")
async def generate(data: PipelineData) -> PipelineData:
    """Generate response from context using LLM.

    Field contract:
        IN:  llm (ILLM) — required.
             pipeline_config (PipelineConfig) — provides prompt_name,
                 prompt_version, token_margin_min, token_margin_pct.
             tokenizer (ITokenizer) — required; model_name used for token estimation.
        DATA: query (UserMessage), context (str), chunks (tuple[Chunk, ...]).
        OUT: response (AssistantMessage).
    """
    _logger.debug("generate start", extra={"trace_id": data.trace_id})
    llm = data.llm
    if llm is None:
        _logger.warning("generate: no llm", extra={"trace_id": data.trace_id})
        return data.add_error(LLM_NOT_PROVIDED)
    if data.query is None or not data.query.text:
        _logger.warning("generate: no query", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_MISSING)

    query_text = data.query.text
    cfg = _get_config(data)
    prompt_version = cfg.prompt_version
    prompt_name = cfg.prompt_name
    retry_cfg = cfg.retry if cfg.retry is not None else RetryConfig()

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
    if max_ctx is None:
        error_msg = "generate: LLM context limit unknown"
        _logger.error(error_msg, extra={"trace_id": data.trace_id})
        return data.add_error(error_msg).with_response(
            AssistantMessage(
                text="Sorry, the model's context limit is not configured. "
                "Please set server_context_size in the LLM configuration."
            )
        )

    tokenizer = data.tokenizer
    if tokenizer is None:
        _logger.error(
            "tokenizer missing in PipelineData",
            extra={"trace_id": data.trace_id},
        )
        return data.add_error("tokenizer missing in PipelineData")
    prompt_tokens = await _estimate_tokens(prompt, tokenizer=tokenizer)
    margin = max(cfg.token_margin_min, int(max_ctx * cfg.token_margin_pct))
    limit = max_ctx - margin

    if prompt_tokens > limit:
        data, prompt = await _truncate_to_fit(
            data, prompt, prompt_name, prompt_version, query_text, limit,
            tokenizer=tokenizer,
        )
        prompt_tokens = await _estimate_tokens(prompt, tokenizer=tokenizer)
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
        response = await _call_llm(llm, messages, retry_cfg)
    except AdapterError as exc:
        _logger.exception("LLM unavailable", extra={"trace_id": data.trace_id})
        return data.add_error(f"{LLM_UNAVAILABLE} ({exc})").with_response(
            AssistantMessage(
                text="LLM service temporarily unavailable. Please try again later."
            )
        )
    except Exception:
        _logger.exception(
            "generate failed after retries", extra={"trace_id": data.trace_id}
        )
        return data.add_error(INTERNAL_SERVER_ERROR).with_response(
            AssistantMessage(
                text="Sorry, I encountered an error generating the response. "
            )
        )

    _logger.debug("generate done", extra={"trace_id": data.trace_id})
    return data.with_response(response)


@step("hyde_query")
async def hyde_query(data: PipelineData) -> PipelineData:
    """Hypothetical Document Embedding (HyDE).

    Generates a hypothetical answer to the query, embeds it,
    and stores the embedding in PipelineData for downstream retrieval.
    """
    _logger.debug("hyde_query start", extra={"trace_id": data.trace_id})
    embedder = data.embedder
    llm = data.llm
    if embedder is None:
        _logger.warning("hyde_query: no embedder", extra={"trace_id": data.trace_id})
        return data.add_error(EMBEDDER_NOT_PROVIDED)
    if llm is None:
        _logger.warning("hyde_query: no llm", extra={"trace_id": data.trace_id})
        return data.add_error(LLM_NOT_PROVIDED)
    if data.query is None or not data.query.text:
        _logger.warning("hyde_query: no query text", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_TEXT_MISSING)

    cfg = _get_config(data)
    retry_cfg = cfg.retry if cfg.retry is not None else RetryConfig()

    # Generate hypothetical answer
    hyde_messages: list[Message] = [
        UserMessage(
            text=f"Write a short passage that answers this question: {data.query.text}"
        )
    ]
    try:
        hyde_resp: AssistantMessage = await _call_llm(llm, hyde_messages, retry_cfg)
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
        embeddings = await _call_embed(embedder, hyde_text, retry_cfg)
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

    _logger.debug("hyde_query done", extra={"trace_id": data.trace_id})
    return data.with_query_embedding(embeddings[0])
