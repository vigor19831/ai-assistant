"""RAG manager — uses pipeline per namespace."""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger

if TYPE_CHECKING:
    from ai_assistant.core.pipeline import RAGPipeline
    from ai_assistant.core.ports import ILLM, IEmbedder, IReranker, IVectorStore

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
        """Chunk, embed and store documents in namespace."""
        start = time.perf_counter()
        all_chunks: list[Chunk] = []
        for doc in documents:
            document = Document(
                id=doc.get("id", str(uuid.uuid4())),
                content=doc.get("content", ""),
                metadata=doc.get("metadata", {}),
            )
            chunks = await self.chunker.chunk(document)
            for idx, chunk in enumerate(chunks):
                chunk = replace(
                    chunk,
                    metadata=ChunkMetadata(
                        source=document.id,
                        index=idx,
                        total_chunks=len(chunks),
                    ),
                )
                all_chunks.append(chunk)

        if not all_chunks:
            return {
                "indexed_count": 0,
                "chunk_count": 0,
                "errors": ["No chunks produced from documents"],
            }

        texts = [c.text for c in all_chunks]
        embeddings = await self.embedder.embed(texts)
        for i, emb in enumerate(embeddings):
            all_chunks[i] = replace(all_chunks[i], embedding=emb)

        await self.vector_store.add(all_chunks, namespace=namespace)
        duration_ms = int((time.perf_counter() - start) * 1000)
        _logger.info(
            "Documents indexed",
            extra={
                "namespace": namespace,
                "indexed_count": len(documents),
                "chunk_count": len(all_chunks),
                "duration_ms": duration_ms,
            },
        )
        return {
            "indexed_count": len(documents),
            "chunk_count": len(all_chunks),
        }


class RAGManager:
    """Handles RAG queries using the pipeline per namespace."""

    def __init__(
        self,
        pipeline: RAGPipeline,
        llm: ILLM,
        vector_store: IVectorStore,
        embedder: IEmbedder,
        reranker: IReranker,
    ) -> None:
        self.pipeline = pipeline
        self.llm = llm
        self.vector_store = vector_store
        self.embedder = embedder
        self.reranker = reranker

    async def query(
        self,
        query_text: str,
        top_k: int = 5,
        prompt_name: str = "rag_strict",
        prompt_version: str = "v1",
        namespace: str = "default",
        relevance_threshold: float = 0.3,
    ) -> dict[str, Any]:
        """Run RAG pipeline for query."""
        start = time.perf_counter()
        data = PipelineData(
            query=UserMessage(text=query_text),
        )
        metadata = {
            "llm": self.llm,
            "embedder": self.embedder,
            "vector_store": self.vector_store,
            "reranker": self.reranker,
            "top_k": top_k,
            "namespace": namespace,
            "relevance_threshold": relevance_threshold,
            "prompt_name": prompt_name,
            "prompt_version": prompt_version,
        }
        result = await self.pipeline.run(data, metadata=metadata)
        duration_ms = int((time.perf_counter() - start) * 1000)
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
        """Return RAG health status.

        Uses vector_store.index_path (port contract) instead of
        vector_store.config.index_path to avoid breaking custom adapters
        that do not store config as a public attribute.
        """
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
