"""RAG pipeline steps with namespace and rerank support.

All steps return new PipelineData instances via dataclasses.replace().
No in-place mutation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.metrics import record_metric
from ai_assistant.core.ports.tools import ToolCall
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.utils import count_tokens, get_context_limit
from ai_assistant.pipeline.decorators import step

if TYPE_CHECKING:
    from ai_assistant.core.domain.pipeline import PipelineData
    from ai_assistant.core.ports.embedder import IEmbedder
    from ai_assistant.core.ports.llm import ILLM
    from ai_assistant.core.ports.reranker import IReranker
    from ai_assistant.core.ports.vector_store import IVectorStore
    from ai_assistant.core.tool_registry import ToolRegistry

__all__: list[str] = [
    "StepContext",
    "build_context",
    "embed_query",
    "generate",
    "rerank",
    "retrieve",
]


@dataclass
class StepContext:
    """Typed container for step dependencies."""

    embedder: IEmbedder | None = None
    vector_store: IVectorStore | None = None
    reranker: IReranker | None = None
    llm: ILLM | None = None
    tool_registry: ToolRegistry | None = None


_logger = get_logger("pipeline.steps")


def _estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    return count_tokens(text, model)


def _get_llm_context_limit(llm: Any) -> int | None:
    return get_context_limit(llm)


@step("embed_query")
async def embed_query(data: PipelineData, ctx: StepContext) -> PipelineData:
    """Embed the user query text."""
    if ctx.embedder is None:
        return data.add_error("embed_query: embedder not provided")
    if data.query is None or not data.query.text:
        return data.add_error("embed_query: no query text")
    try:
        embeddings = await ctx.embedder.embed([data.query.text])
        new_metadata = {**data.metadata, "query_embedding": embeddings[0]}
        return replace(data, metadata=new_metadata)
    except Exception:
        _logger.exception("embed_query failed")
        return data.add_error("Internal server error")


@step("retrieve")
async def retrieve(data: PipelineData, ctx: StepContext) -> PipelineData:
    """Retrieve relevant chunks from vector store (namespace-aware)."""
    if ctx.vector_store is None:
        return data.add_error("retrieve: vector_store not provided")
    embedding = data.metadata.get("query_embedding")
    if embedding is None:
        return data.add_error("retrieve: no query embedding")
    try:
        top_k = data.metadata.get("top_k", 5)
        namespace = data.metadata.get("namespace") or "default"
        chunks = await ctx.vector_store.search(embedding, top_k=top_k, namespace=namespace)
        record_metric("rag_chunks", len(chunks))
        return data.with_chunks(chunks)
    except Exception:
        _logger.exception("retrieve failed")
        return data.add_error("Internal server error")


@step("rerank")
async def rerank(data: PipelineData, ctx: StepContext) -> PipelineData:
    """Rerank retrieved chunks by relevance and filter by threshold.

    If reranker is not configured (None), acts as transparent pass-through.
    """
    if not data.chunks:
        return data

    if ctx.reranker is None:
        return data

    try:
        query = data.query.text if data.query else ""
        top_k = data.metadata.get("top_k", 5)
        threshold = data.metadata.get("relevance_threshold", 0.3)

        results = await ctx.reranker.rerank(query, data.chunks, top_k=top_k)

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
        return data.add_error("Internal server error")


@step("build_context")
async def build_context(data: PipelineData, ctx: StepContext) -> PipelineData:
    """Build context string from retrieved (and reranked) chunks."""
    if not data.chunks:
        return data.with_context("")
    lines = [chunk.text for chunk in data.chunks if chunk.text]
    return data.with_context("\n\n".join(lines))


@step("generate")
async def generate(data: PipelineData, ctx: StepContext) -> PipelineData:
    """Generate response using LLM with context."""
    if ctx.llm is None:
        return data.add_error("generate: llm not provided")
    if data.query is None:
        return data.add_error("generate: no query")

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

    max_ctx = _get_llm_context_limit(ctx.llm)
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

    for _ in range(3):
        try:
            response = await ctx.llm.complete(messages)
        except Exception:
            _logger.exception("generate failed")
            return data.add_error("Internal server error").with_response(
                AssistantMessage(
                    text=("Sorry, I encountered an error generating the response.")
                )
            )

        if not response or not response.tool_calls:
            break

        messages.append(response)

        if ctx.tool_registry:
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
                    result = await ctx.tool_registry.dispatch(tc)
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
