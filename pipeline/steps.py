"""RAG pipeline steps with namespace and rerank support."""

from __future__ import annotations

import json
from typing import Any

from core.domain.messages import AssistantMessage, UserMessage
from core.domain.pipeline import PipelineData
from core.metrics import record_metric
from core.ports.tools import ToolCall
from core.prompts import get_prompt
from core.utils import count_tokens, get_context_limit
from pipeline.decorators import step


def _estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    return count_tokens(text, model)


def _get_llm_context_limit(llm: Any) -> int | None:
    return get_context_limit(llm)


@step("embed_query")
async def embed_query(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Embed the user query text."""
    embedder = kwargs.get("embedder")
    if embedder is None:
        data.errors.append("embed_query: embedder not provided")
        return data
    if data.query is None or not data.query.text:
        data.errors.append("embed_query: no query text")
        return data
    try:
        embeddings = await embedder.embed([data.query.text])
        data.metadata["query_embedding"] = embeddings[0]
    except Exception as e:
        data.errors.append(f"embed_query failed: {e}")
    return data


@step("retrieve")
async def retrieve(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Retrieve relevant chunks from vector store (namespace-aware)."""
    vector_store = kwargs.get("vector_store")
    if vector_store is None:
        data.errors.append("retrieve: vector_store not provided")
        return data
    embedding = data.metadata.get("query_embedding")
    if embedding is None:
        data.errors.append("retrieve: no query embedding")
        return data
    try:
        top_k = data.metadata["top_k"]
        namespace = data.metadata.get("namespace") or "default"
        chunks = await vector_store.search(embedding, top_k=top_k, namespace=namespace)
        data.chunks = chunks
        record_metric("rag_chunks", len(chunks))
    except Exception as e:
        data.errors.append(f"retrieve failed: {e}")
    return data


@step("rerank")
async def rerank(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Rerank retrieved chunks by relevance and filter by threshold.

    If reranker is not configured (None), acts as transparent pass-through.
    """
    if not data.chunks:
        return data

    reranker = kwargs.get("reranker")
    if reranker is None:
        return data

    try:
        query = data.query.text if data.query else ""
        top_k = data.metadata.get("top_k", 5)
        threshold = data.metadata.get("relevance_threshold", 0.3)

        results = await reranker.rerank(query, data.chunks, top_k=top_k)

        filtered = [r for r in results if r.score >= threshold]

        if not filtered:
            data.chunks = []
            data.metadata["rerank_filtered_out"] = True
        else:
            data.chunks = [r.chunk for r in filtered]
            data.metadata["rerank_scores"] = [r.score for r in filtered]

    except Exception as e:
        data.errors.append(f"rerank failed: {e}")

    return data


@step("build_context")
async def build_context(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Build context string from retrieved (and reranked) chunks."""
    data.rebuild_context()
    return data


@step("generate")
async def generate(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Generate response using LLM with context."""
    llm = kwargs.get("llm")
    tool_registry = kwargs.get("tool_registry")
    if llm is None:
        data.errors.append("generate: llm not provided")
        return data
    if data.query is None:
        data.errors.append("generate: no query")
        return data

    prompt_version = data.metadata["prompt_version"]
    prompt_name = data.metadata["prompt_name"]

    try:
        prompt = get_prompt(
            prompt_name,
            version=prompt_version,
            query=data.query.text or "",
            context=data.context,
        )
    except Exception:
        chunks_text = "\n".join(
            [f"[{i + 1}] {c.text}" for i, c in enumerate(data.chunks)]
        )
        prompt = (
            f"Context:\n{chunks_text}\n\nQuestion: {data.query.text or ''}\nAnswer:"
        )

    record_metric("input_tokens", _estimate_tokens(prompt))

    max_ctx = _get_llm_context_limit(llm)
    if isinstance(max_ctx, int) and max_ctx > 0:
        prompt_tokens = _estimate_tokens(prompt)
        margin = max(256, int(max_ctx * 0.1))
        limit = max_ctx - margin
        while data.chunks and prompt_tokens > limit:
            data.chunks = data.chunks[:-1]
            if not data.chunks:
                data.context = ""
                break
            data.rebuild_context()
            try:
                prompt = get_prompt(
                    prompt_name,
                    version=prompt_version,
                    query=data.query.text or "",
                    context=data.context,
                )
            except Exception:
                chunks_text = "\n".join(
                    [f"[{i + 1}] {c.text}" for i, c in enumerate(data.chunks)]
                )
                prompt = (
                    f"Context:\n{chunks_text}\n\n"
                    f"Question: {data.query.text or ''}\nAnswer:"
                )
            prompt_tokens = _estimate_tokens(prompt)
        if prompt_tokens > limit:
            data.errors.append(
                f"generate: prompt too long ({prompt_tokens} tokens) "
                f"exceeds limit ({limit})"
            )
            data.response = AssistantMessage(
                text="Sorry, the retrieved context is too large to process. "
                "Please narrow your query."
            )
            return data

    original_image = data.query.image if data.query else None

    messages: list[Any] = [UserMessage(text=prompt, image=original_image)]
    response: AssistantMessage | None = None

    for _ in range(3):
        try:
            response = await llm.complete(messages)
        except Exception as e:
            data.errors.append(f"generate failed: {e}")
            data.response = AssistantMessage(
                text="Sorry, I encountered an error generating the response."
            )
            return data

        if not response.tool_calls:
            break

        messages.append(response)

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

    data.response = (
        response
        if response
        else AssistantMessage(text="Sorry, tool call loop exhausted.")
    )
    record_metric("output_tokens", _estimate_tokens(data.response.text or ""))
    return data
