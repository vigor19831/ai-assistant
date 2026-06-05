"""RAG managers — indexing and querying with namespace and reranker support."""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING, Any

from ai_assistant.core.constants import FROZEN_NO_INFO_PHRASES
from ai_assistant.core.domain.documents import Chunk, Document
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger

if TYPE_CHECKING:
    from ai_assistant.core.pipeline import RAGPipeline
    from ai_assistant.core.ports import (
        ILLM,
        IChunker,
        IEmbedder,
        IReranker,
        IVectorStore,
    )

__all__ = ["IndexingManager", "RAGManager"]

_logger = get_logger("rag.manager")


class IndexingManager:
    """Handles document ingestion: chunk + embed + store per namespace."""

    def __init__(
        self,
        chunker: IChunker,
        embedder: IEmbedder,
        vector_store: IVectorStore,
    ) -> None:
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store

    async def index_documents(
        self, documents: list[dict[str, Any]], namespace: str = "default"
    ) -> dict[str, Any]:
        all_chunks: list[Chunk] = []
        errors: list[str] = []
        indexed = 0

        for raw in documents:
            doc_id = raw.get("id") or str(uuid.uuid4())
            doc = Document(
                id=doc_id,
                content=raw.get("content", ""),
                metadata=raw.get("metadata", {}),
            )
            if not doc.content.strip():
                errors.append(f"Document {doc_id} has empty content")
                continue

            try:
                chunks = await self.chunker.chunk(doc)
            except Exception as e:
                errors.append(f"Chunking failed for {doc_id}: {e}")
                continue

            if not chunks:
                errors.append(f"No chunks produced for {doc_id}")
                continue

            texts = [c.text for c in chunks if c.text]
            try:
                embeddings = await self.embedder.embed(texts)
            except Exception as e:
                errors.append(f"Embedding failed for {doc_id}: {e}")
                continue

            embedded_chunks = []
            for i, chunk in enumerate(chunks):
                if i < len(embeddings):
                    embedded_chunks.append(
                        Chunk(
                            id=chunk.id,
                            text=chunk.text,
                            embedding=embeddings[i],
                            metadata=chunk.metadata,
                        )
                    )

            all_chunks.extend(embedded_chunks)
            indexed += 1

        if all_chunks:
            try:
                await self.vector_store.add(all_chunks, namespace=namespace)
            except Exception as e:
                errors.append(f"Vector store add failed: {e}")

        return {
            "indexed_count": indexed,
            "chunk_count": len(all_chunks),
            "errors": errors,
        }


class RAGManager:
    """Handles RAG queries using the pipeline per namespace."""

    def __init__(
        self,
        pipeline: RAGPipeline,
        llm: ILLM,
        vector_store: IVectorStore,
        embedder: IEmbedder | None = None,
        reranker: IReranker | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.llm = llm
        self.vector_store = vector_store
        self.embedder = embedder
        self.reranker = reranker

    def _is_no_info_answer(self, answer: str | None) -> bool:
        """Check if answer indicates insufficient information."""
        if answer is None:
            return True
        answer_lower = answer.lower()
        return any(phrase in answer_lower for phrase in FROZEN_NO_INFO_PHRASES)

    async def query(
        self,
        query_text: str,
        top_k: int,
        prompt_name: str,
        prompt_version: str,
        namespace: str | None,
        relevance_threshold: float = 0.3,
    ) -> dict[str, Any]:
        if not namespace:
            namespace = "default"

        # Single namespace query — use pipeline
        data = PipelineData(
            query=UserMessage(text=query_text),
            metadata={
                "top_k": top_k,
                "prompt_name": prompt_name,
                "prompt_version": prompt_version,
                "namespace": namespace,
                "relevance_threshold": relevance_threshold,
            },
        )
        # Inject pipeline dependencies into metadata
        deps = {
            "embedder": self.embedder,
            "vector_store": self.vector_store,
            "reranker": self.reranker,
            "llm": self.llm,
        }
        result = await self.pipeline.run(data, metadata=deps)

        answer: str = (result.response.text or "") if result.response else " "

        # Post-process: map citations [N] to real sources
        sources: list[dict[str, Any]] = []
        if result.chunks and not self._is_no_info_answer(answer):
            cited_indices: set[int] = set()
            for m in re.finditer(r"\[(\d+)\]", answer):
                try:
                    cited_indices.add(int(m.group(1)) - 1)
                except (ValueError, IndexError):
                    continue

            src_lines: list[str] = []
            for idx in sorted(cited_indices):
                if 0 <= idx < len(result.chunks):
                    chunk = result.chunks[idx]
                    src = (
                        chunk.metadata.source
                        if chunk.metadata is not None
                        else "unknown"
                    )  # type: ignore[union-attr]
                    src_lines.append(f"[{idx + 1}] {src}")

            if src_lines:
                answer += "\n\nSources:\n" + "\n".join(src_lines)

            sources = [
                {
                    "chunk_id": c.id,
                    "text_preview": c.text[:200] if c.text else " ",
                    "metadata": c.metadata.custom if c.metadata else {},
                }
                for c in result.chunks
            ]

        return {
            "answer": answer,
            "sources": sources,
            "chunks_used": len(result.chunks),
            "errors": result.errors,
        }

    async def health(self) -> dict[str, Any]:
        # Count chunks across ALL namespaces
        total_chunks = 0
        try:
            index_path = self.vector_store.config.index_path
            namespaces = await self.vector_store.list_namespaces(index_path)
            for ns in namespaces:
                chunks = await self.vector_store.list_by_filter({}, namespace=ns)
                total_chunks += len(chunks)
        except Exception as exc:
            _logger.debug("RAG health check failed: %s", exc)

        return {
            "status": "ok",
            "index_loaded": total_chunks > 0,
            "chunk_count": total_chunks,
        }
