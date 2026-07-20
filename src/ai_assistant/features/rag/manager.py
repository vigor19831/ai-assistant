"""RAG manager — uses pipeline per namespace."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.domain.errors import ConfigurationError
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import STEP_REGISTRY
from ai_assistant.core.ports import (
    ILLM,
    IEmbedder,
    IReranker,
    ITokenizer,
    IVectorStore,
)

_logger = get_logger("rag.manager")


class IndexingManager:
    """Handles document ingestion: chunk + embed + store per namespace."""

    def __init__(
        self,
        chunker: Any,
        embedder: IEmbedder,
        vector_store: IVectorStore,
    ) -> None:
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store

    async def index_documents(
        self,
        documents: list[dict[str, Any]],
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Chunk, embed and upsert documents in namespace."""
        start = time.perf_counter()
        all_chunks: list[Chunk] = []
        errors: list[str] = []
        successful_docs = 0

        for doc in documents:
            doc_id = doc.get("id")
            if not doc_id:
                errors.append("Document missing 'id' field, skipped")
                continue

            try:
                document = Document(
                    id=doc_id,
                    content=doc.get("content", ""),
                    metadata=doc.get("metadata", {}),
                )
                doc_source_uri = document.metadata.get("source_uri")
                chunks = await self.chunker.chunk(document)
                for idx, chunk in enumerate(chunks):
                    chunk_source_uri = (
                        chunk.metadata.source_uri
                        if chunk.metadata and chunk.metadata.source_uri
                        else doc_source_uri
                    )
                    all_chunks.append(
                        replace(
                            chunk,
                            metadata=ChunkMetadata(
                                source=document.id,
                                index=idx,
                                total_chunks=len(chunks),
                                original_path=chunk.metadata.original_path if chunk.metadata else None,
                                source_uri=chunk_source_uri,
                                custom=chunk.metadata.custom if chunk.metadata else {},
                            ),
                        )
                    )
                successful_docs += 1
            except Exception:
                _logger.exception(
                    "Failed to chunk document",
                    extra={"doc_id": doc_id, "namespace": namespace},
                )
                errors.append(f"Failed to chunk document {doc_id}")

        if not all_chunks:
            return {
                "indexed_count": 0,
                "chunk_count": 0,
                "errors": errors or ["No chunks produced from documents"],
                "indexed_uris": {},
            }

        texts = [c.text for c in all_chunks]
        embeddings = await self.embedder.embed(texts)

        for i, emb in enumerate(embeddings):
            all_chunks[i] = replace(all_chunks[i], embedding=emb)

        await self.vector_store.upsert(all_chunks, namespace=namespace)

        indexed_uris: dict[str, list[str]] = {}
        for chunk in all_chunks:
            if chunk.metadata and chunk.metadata.source_uri:
                indexed_uris.setdefault(chunk.metadata.source_uri, []).append(chunk.id)

        duration_ms = int((time.perf_counter() - start) * 1000)
        _logger.info(
            "Documents indexed",
            extra={
                "namespace": namespace,
                "indexed_count": successful_docs,
                "chunk_count": len(all_chunks),
                "duration_ms": duration_ms,
            },
        )
        return {
            "indexed_count": successful_docs,
            "chunk_count": len(all_chunks),
            "errors": errors,
            "indexed_uris": indexed_uris,
        }


class RAGManager:
    """Handles RAG queries using the pipeline per namespace."""

    def __init__(
        self,
        llm: ILLM,
        vector_store: IVectorStore,
        embedder: IEmbedder,
        reranker: IReranker,
        token_margin_min: int = 256,
        token_margin_pct: float = 0.1,
        tokenizer: ITokenizer | None = None,
        rag_steps: list[str] | None = None,
        system_message: str | None = None,
    ) -> None:
        # Build pipeline from config step names, validating each against STEP_REGISTRY.
        # Default: full RAG pipeline with all steps.
        step_names = rag_steps if rag_steps is not None else [
            "embed_query",
            "retrieve",
            "rerank",
            "build_context",
            "generate",
        ]
        step_funcs = []
        for name in step_names:
            func = STEP_REGISTRY.get(name)
            if func is None:
                raise ConfigurationError(
                    f"Unknown pipeline step: {name!r}. "
                    f"Available: {list(STEP_REGISTRY.keys())}"
                )
            step_funcs.append(func)
        self.pipeline = RAGPipeline(step_funcs)
        self.llm = llm
        self.vector_store = vector_store
        self.embedder = embedder
        self.reranker = reranker
        self.token_margin_min = token_margin_min
        self.token_margin_pct = token_margin_pct
        self.tokenizer = tokenizer
        self.system_message = system_message

    async def query(
        self,
        query_text: str,
        top_k: int = 5,
        prompt_name: str = "rag_strict",
        prompt_version: str = "v1",
        namespace: str = "default",
    ) -> dict[str, Any]:
        """Run RAG pipeline for query."""
        start = time.perf_counter()
        from ai_assistant.core.domain.pipeline import PipelineConfig

        pipeline_config = PipelineConfig(
            top_k=top_k,
            namespace=namespace,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            token_margin_min=self.token_margin_min,
            token_margin_pct=self.token_margin_pct,
            system_message=self.system_message,
        )
        data = PipelineData(
            query=UserMessage(text=query_text),
            original_query=UserMessage(text=query_text),
            chat_history=(),
            llm=self.llm,
            embedder=self.embedder,
            vector_store=self.vector_store,
            reranker=self.reranker,
            pipeline_config=pipeline_config,
            tokenizer=self.tokenizer,
        )
        result = await self.pipeline.run(data)
        duration_ms = int((time.perf_counter() - start) * 1000)
        if result.errors:
            _logger.warning(
                "RAG pipeline completed with errors",
                extra={
                    "namespace": namespace,
                    "errors": list(result.errors),
                    "trace_id": data.trace_id,
                },
            )
        _logger.info(
            "RAG pipeline completed",
            extra={
                "namespace": namespace,
                "chunks_used": len(result.chunks),
                "duration_ms": duration_ms,
                "errors": len(result.errors),
            },
        )
        return {
            "answer": result.response.text if result.response else "",
            "sources": [
                {
                    "id": c.id,
                    "text": c.text,
                    "metadata": c.metadata,
                }
                for c in result.chunks
            ],
            "chunks_used": len(result.chunks),
            "errors": list(result.errors),
        }

    async def health(self) -> dict[str, Any]:
        """Return RAG health status."""
        index_path = self.vector_store.index_path
        index_loaded = False
        chunk_count = 0
        try:
            namespaces = await self.vector_store.list_namespaces(index_path)
            index_loaded = len(namespaces) > 0
            for ns in namespaces:
                chunks = await self.vector_store.list_by_filter({}, namespace=ns)
                chunk_count += len(chunks)
        except Exception:
            _logger.exception("Health check failed")
        return {
            "status": "ok" if index_loaded else "empty",
            "index_loaded": index_loaded,
            "chunk_count": chunk_count,
        }
