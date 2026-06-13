"""tests/test_rag.py — RAG feature tests + reranker regression (P0.6)."""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline_steps import rerank
from ai_assistant.features.rag.indexing import index_folder
from ai_assistant.features.rag.manager import IndexingManager, RAGManager

_logger = get_logger(__name__)


# ── RAGManager ──

class TestRAGManager:
    """RAGManager — query pipeline and health checks."""

    @pytest.mark.asyncio
    async def test_query_pipeline_success(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: pipeline returns answer with sources.
        When: RAGManager.query is called.
        Then: response contains answer, sources and chunk count."""
        from ai_assistant.core.pipeline import RAGPipeline

        pipeline = MagicMock(spec=RAGPipeline)
        pipeline.run = AsyncMock(return_value=MagicMock(
            response=MagicMock(text="Paris"),
            chunks=[
                Chunk(
                    id="c1",
                    text="Paris is the capital of France.",
                    metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
                )
            ],
            errors=[],
        ))

        mgr = RAGManager(
            pipeline=pipeline,
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
        )
        result = await mgr.query("What is the capital of France?")
        assert result["answer"] == "Paris"
        assert result["chunks_used"] == 1
        assert len(result["sources"]) == 1
        assert result["sources"][0]["id"] == "c1"

    @pytest.mark.asyncio
    async def test_query_namespace_routing(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: namespace is set to 'work'.
        When: RAGManager.query called with namespace='work'.
        Then: pipeline metadata contains namespace='work'."""
        from ai_assistant.core.pipeline import RAGPipeline

        pipeline = MagicMock(spec=RAGPipeline)
        pipeline.run = AsyncMock(return_value=MagicMock(
            response=MagicMock(text=""),
            chunks=[],
            errors=[],
        ))

        mgr = RAGManager(
            pipeline=pipeline,
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
        )
        await mgr.query("test", namespace="work")

        metadata = pipeline.run.call_args.kwargs["metadata"]
        assert metadata["namespace"] == "work"

    @pytest.mark.asyncio
    async def test_query_prompt_and_threshold_override(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: custom prompt name, version and relevance threshold.
        When: RAGManager.query called with overrides.
        Then: pipeline metadata contains overridden values."""
        from ai_assistant.core.pipeline import RAGPipeline

        pipeline = MagicMock(spec=RAGPipeline)
        pipeline.run = AsyncMock(return_value=MagicMock(
            response=MagicMock(text=""),
            chunks=[],
            errors=[],
        ))

        mgr = RAGManager(
            pipeline=pipeline,
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
        )
        await mgr.query(
            "test",
            prompt_name="rag_creative",
            prompt_version="v2",
            relevance_threshold=0.5,
        )

        metadata = pipeline.run.call_args.kwargs["metadata"]
        assert metadata["prompt_name"] == "rag_creative"
        assert metadata["prompt_version"] == "v2"
        assert metadata["relevance_threshold"] == 0.5

    @pytest.mark.asyncio
    async def test_query_empty_results_handling(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: no relevant chunks found.
        When: RAGManager.query is called.
        Then: answer is returned and sources list is empty."""
        from ai_assistant.core.pipeline import RAGPipeline

        pipeline = MagicMock(spec=RAGPipeline)
        pipeline.run = AsyncMock(return_value=MagicMock(
            response=MagicMock(text="I don't have enough information."),
            chunks=[],
            errors=[],
        ))

        mgr = RAGManager(
            pipeline=pipeline,
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
        )
        result = await mgr.query("obscure topic")
        assert result["answer"] == "I don't have enough information."
        assert result["chunks_used"] == 0
        assert result["sources"] == []
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_health_index_loaded(self, mock_vector_store):
        """Given: vector store has namespaces with chunks.
        When: RAGManager.health is called.
        Then: status is 'ok', index_loaded=True, chunk_count > 0."""
        mock_vector_store.index_path = "./data/indices"
        mock_vector_store.list_namespaces = AsyncMock(return_value=["default", "work"])
        mock_vector_store.list_by_filter = AsyncMock(return_value=[("c1", {}), ("c2", {})])

        mgr = RAGManager(
            pipeline=MagicMock(),
            llm=MagicMock(),
            vector_store=mock_vector_store,
            embedder=MagicMock(),
            reranker=MagicMock(),
        )
        health = await mgr.health()
        assert health["status"] == "ok"
        assert health["index_loaded"] is True
        assert health["chunk_count"] == 4

    @pytest.mark.asyncio
    async def test_health_empty_index(self, mock_vector_store):
        """Given: vector store has no namespaces.
        When: RAGManager.health is called.
        Then: status is 'empty', index_loaded=False, chunk_count is 0."""
        mock_vector_store.index_path = "./data/indices"
        mock_vector_store.list_namespaces = AsyncMock(return_value=[])

        mgr = RAGManager(
            pipeline=MagicMock(),
            llm=MagicMock(),
            vector_store=mock_vector_store,
            embedder=MagicMock(),
            reranker=MagicMock(),
        )
        health = await mgr.health()
        assert health["status"] == "empty"
        assert health["index_loaded"] is False
        assert health["chunk_count"] == 0


# ── Indexing ──

class TestRAGIndexing:
    """IndexingManager and index_folder — ingestion, deletion, reindex."""

    @pytest.mark.asyncio
    async def test_add_documents(self, mock_chunker, mock_embedder, mock_vector_store):
        """Given: list of documents with content.
        When: IndexingManager.index_documents is called.
        Then: documents are chunked, embedded and stored; counts are returned."""
        mgr = IndexingManager(
            chunker=mock_chunker,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
        )
        docs = [
            {
                "id": "d1",
                "content": "hello world",
                "metadata": {"source": "test.txt"},
            }
        ]
        result = await mgr.index_documents(docs, namespace="test")
        assert result["indexed_count"] == 1
        assert result["chunk_count"] == 1
        mock_vector_store.add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_by_chunk_id(self, mock_vector_store):
        """Given: existing chunk IDs.
        When: vector_store.delete is called with those IDs.
        Then: delete is invoked exactly once with correct arguments."""
        mock_vector_store.delete = AsyncMock(return_value=None)

        await mock_vector_store.delete(["c1", "c2"], namespace="test")
        mock_vector_store.delete.assert_awaited_once_with(["c1", "c2"], namespace="test")

    @pytest.mark.asyncio
    async def test_delete_by_document_id(self, mock_vector_store):
        """Given: document IDs that map to multiple chunks.
        When: chunks are listed by filter and matching ones are deleted.
        Then: only chunks belonging to those documents are removed."""
        mock_vector_store.list_by_filter = AsyncMock(
            return_value=[
                ("c1", {"source": "d1"}),
                ("c2", {"source": "d1"}),
                ("c3", {"source": "d2"}),
            ]
        )
        mock_vector_store.delete = AsyncMock(return_value=None)

        doc_ids = ["d1"]
        existing = await mock_vector_store.list_by_filter({}, namespace="test")
        to_delete = [cid for cid, meta in existing if meta.get("source") in doc_ids]

        await mock_vector_store.delete(to_delete, namespace="test")
        assert len(to_delete) == 2
        mock_vector_store.delete.assert_awaited_once_with(["c1", "c2"], namespace="test")

    @pytest.mark.asyncio
    async def test_reindex_background_task(self, tmp_path, mock_chunker, mock_embedder, mock_vector_store):
        """Given: markdown files in tmp_path/sources/personal.
        When: index_folder is called with folder='personal'.
        Then: documents are indexed and namespace 'personal' appears in results."""
        from ai_assistant.features.rag import indexing as indexing_module

        sources = tmp_path / "sources"
        personal = sources / "personal"
        personal.mkdir(parents=True)
        (personal / "notes.md").write_text("# Hello\nThis is a test note.")

        # Prevent auto-save from triggering on mock config
        mock_vector_store.config.index_path = None

        with patch.object(indexing_module, "DOCUMENTS_ROOT", sources):
            result = await index_folder(
                folder="personal",
                clear=False,
                chunker=mock_chunker,
                embedder=mock_embedder,
                vector_store=mock_vector_store,
            )
            assert result["success"] is True
            assert "personal" in result["results"]
            assert result["results"]["personal"]["indexed"] == 1

    def test_status_polling(self):
        """Given: a reindex task was started and recorded in _reindex_status.
        When: status is polled from the global dict.
        Then: correct status and timestamps are returned."""
        from ai_assistant.features.rag import handlers as rag_handlers

        task_id = "task-123"
        rag_handlers._reindex_status[task_id] = {
            "status": "running",
            "started_at": time.time(),
        }

        status = rag_handlers._reindex_status.get(task_id, {})
        assert status["status"] == "running"
        assert "started_at" in status

        # Cleanup so other tests are not affected
        rag_handlers._reindex_status.clear()

    @pytest.mark.asyncio
    async def test_ttl_cleanup(self):
        """Given: expired and fresh entries in _reindex_status.
        When: _cleanup_reindex_status is called.
        Then: expired entries are removed, fresh entries survive."""
        from ai_assistant.features.rag import handlers as rag_handlers

        now = time.time()
        ttl = rag_handlers._REINDEX_STATUS_TTL_SECONDS

        rag_handlers._reindex_status["old"] = {
            "status": "completed",
            "started_at": now - ttl - 100,
            "finished_at": now - ttl - 50,
        }
        rag_handlers._reindex_status["fresh"] = {
            "status": "running",
            "started_at": now - 10,
        }

        await rag_handlers._cleanup_reindex_status()

        assert "old" not in rag_handlers._reindex_status
        assert "fresh" in rag_handlers._reindex_status

        rag_handlers._reindex_status.clear()


# ── Reranker Regression ──

class TestRerankerRegression:
    """REGRESSION P0.6: reranker must be present in metadata for [p] prefix queries."""

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_reranker_passed_in_metadata_on_p_prefix(self, mock_state, mock_embedder, mock_vector_store):
        """Given: chat message with [p] prefix and working retrieval pipeline.
        When: ChatManager._retrieve_context is called.
        Then: metadata reaching the rerank step contains the reranker instance."""
        from dataclasses import replace
        from ai_assistant.features.chat.manager import ChatManager
        from ai_assistant.core.pipeline import RAGPipeline
        from ai_assistant.core.domain.pipeline import PipelineData

        captured = {}

        async def fake_embed_query(data: PipelineData) -> PipelineData:
            """Fake embed_query step — stores embedding in metadata."""
            new_metadata = {**data.metadata, "query_embedding": [0.1] * 384}
            return replace(data, metadata=new_metadata)

        async def fake_retrieve(data: PipelineData) -> PipelineData:
            """Fake retrieve step — reads embedding, returns chunks."""
            return data.with_chunks([
                Chunk(
                    id="c1",
                    text="test chunk",
                    embedding=[0.1] * 384,
                    metadata=ChunkMetadata(source="s", index=0, total_chunks=1),
                )
            ])

        async def capture_rerank(data: PipelineData) -> PipelineData:
            """Capture reranker from metadata and return data unchanged."""
            captured["reranker"] = data.metadata.get("reranker")
            return data

        pipeline = RAGPipeline([fake_embed_query, fake_retrieve, capture_rerank])

        mgr = ChatManager(
            llm=mock_state.llm,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
            reranker=mock_state.reranker,
            pipeline=pipeline,
        )

        await mgr._retrieve_context("[p] test query")

        assert captured.get("reranker") is mock_state.reranker

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_reranker_missing_raises_assertion(self):
        """Given: PipelineData has chunks but no reranker in metadata.
        When: rerank pipeline step executes.
        Then: AssertionError is raised."""
        data = PipelineData(
            query=UserMessage(text="test"),
            chunks=[
                Chunk(
                    id="c1",
                    text="chunk",
                    metadata=ChunkMetadata(source="s", index=0, total_chunks=1),
                )
            ],
            metadata={},  # reranker intentionally omitted
        )
        with pytest.raises(AssertionError):
            await rerank(data)
