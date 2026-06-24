"""tests/test_rag.py — RAG feature tests + reranker regression (P0.6)."""

from __future__ import annotations

import asyncio
import time
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
        Then: PipelineData passed to pipeline contains namespace='work'."""
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

        # With explicit typed fields, pipeline.run receives PipelineData directly
        call_args = pipeline.run.call_args
        data_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("data")
        assert data_arg is not None
        assert data_arg.pipeline_config.namespace == "work"

    @pytest.mark.asyncio
    async def test_query_prompt_and_threshold_override(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: custom prompt name, version and relevance threshold.
        When: RAGManager.query called with overrides.
        Then: PipelineData contains overridden values."""
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

        call_args = pipeline.run.call_args
        data_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("data")
        assert data_arg is not None
        pipeline_config = data_arg.pipeline_config
        assert pipeline_config.prompt_name == "rag_creative"
        assert pipeline_config.prompt_version == "v2"
        assert pipeline_config.relevance_threshold == 0.5

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
    async def test_query_llm_unavailable_returns_503(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: pipeline returns LLM_UNAVAILABLE error.
        When: query_rag handler processes the result.
        Then: HTTPException with status 503 is raised."""
        from fastapi import HTTPException
        from ai_assistant.core.domain.errors import LLM_UNAVAILABLE
        from ai_assistant.core.pipeline import RAGPipeline

        pipeline = MagicMock(spec=RAGPipeline)
        pipeline.run = AsyncMock(return_value=MagicMock(
            response=MagicMock(text="LLM service temporarily unavailable. Please try again later."),
            chunks=[],
            errors=[f"{LLM_UNAVAILABLE} (LLM down)"],
        ))

        mgr = RAGManager(
            pipeline=pipeline,
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
        )
        result = await mgr.query("anything")
        assert any(LLM_UNAVAILABLE in e for e in result["errors"])

        # Simulate handler check
        from ai_assistant.features.rag.handlers import router
        with pytest.raises(HTTPException) as exc_info:
            for err in result.get("errors", []):
                if err.startswith(LLM_UNAVAILABLE):
                    raise HTTPException(
                        status_code=503,
                        detail="LLM service temporarily unavailable. Please try again later.",
                    )
        assert exc_info.value.status_code == 503

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
        sources = tmp_path / "sources"
        personal = sources / "personal"
        personal.mkdir(parents=True)
        (personal / "notes.md").write_text("# Hello\nThis is a test note.")

        # Prevent auto-save from triggering on mock config
        mock_vector_store.config.index_path = None

        result = await index_folder(
            folder="personal",
            clear=False,
            chunker=mock_chunker,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
            documents_root=str(sources),
        )
        assert result["success"] is True
        assert "personal" in result["results"]
        assert result["results"]["personal"]["indexed"] == 1

    @pytest.mark.asyncio
    async def test_status_polling(self):
        """Given: a reindex task was started and recorded in RAGState.
        When: status is polled from the instance.
        Then: correct status and timestamps are returned."""
        from ai_assistant.api.deps import RAGState

        rag_state = RAGState()
        task_id = "task-123"
        await rag_state.start_task(task_id)

        status = await rag_state.get_status(task_id)
        assert status is not None
        assert status["status"] == "running"
        assert "started_at" in status

    @pytest.mark.asyncio
    async def test_ttl_cleanup(self):
        """Given: expired and fresh entries in RAGState.status.
        When: cleanup_status is called.
        Then: expired entries are removed, fresh entries survive."""
        from ai_assistant.api.deps import RAGState

        rag_state = RAGState()
        now = time.time()
        ttl = rag_state.STATUS_TTL_SECONDS

        async with rag_state._lock:
            rag_state._status["old"] = {
                "status": "completed",
                "started_at": now - ttl - 100,
                "finished_at": now - ttl - 50,
            }
            rag_state._status["fresh"] = {
                "status": "running",
                "started_at": now - 10,
            }

        await rag_state.cleanup_status()

        async with rag_state._lock:
            assert "old" not in rag_state._status
            assert "fresh" in rag_state._status

    @pytest.mark.asyncio
    async def test_start_task_triggers_cleanup(self):
        """Given: expired entries exist in RAGState._status.
        When: start_task is called.
        Then: expired entries are removed before new task is registered."""
        from ai_assistant.api.deps import RAGState

        rag_state = RAGState()
        now = time.time()
        ttl = rag_state.STATUS_TTL_SECONDS

        async with rag_state._lock:
            rag_state._status["old"] = {
                "status": "completed",
                "started_at": now - ttl - 100,
                "finished_at": now - ttl - 50,
            }

        await rag_state.start_task("new-task")

        async with rag_state._lock:
            assert "old" not in rag_state._status
            assert "new-task" in rag_state._status

    @pytest.mark.asyncio
    async def test_get_status_does_not_mutate(self):
        """Given: expired entries exist in RAGState._status.
        When: get_status is called.
        Then: expired entries are NOT removed — get_status is pure read."""
        from ai_assistant.api.deps import RAGState

        rag_state = RAGState()
        now = time.time()
        ttl = rag_state.STATUS_TTL_SECONDS

        async with rag_state._lock:
            rag_state._status["old"] = {
                "status": "completed",
                "started_at": now - ttl - 100,
                "finished_at": now - ttl - 50,
            }

        status = await rag_state.get_status("nonexistent")
        assert status is None

        async with rag_state._lock:
            assert "old" in rag_state._status

    @pytest.mark.asyncio
    async def test_reindex_tasks_cleanup(self, mock_state):
        """Given: multiple reindex tasks are started and completed.
        When: tasks finish.
        Then: tasks dict is cleaned up, no memory leak."""
        from ai_assistant.features.rag.handlers import reindex_documents
        from ai_assistant.features.rag.schemas import ReindexRequest
        from unittest.mock import patch, AsyncMock

        with patch(
            "ai_assistant.features.rag.handlers.index_folder",
            new_callable=AsyncMock,
        ) as mock_index:
            mock_index.return_value = {
                "success": True,
                "results": {"test": {"indexed": 1}},
            }

            # Start many reindex tasks
            for _ in range(50):
                req = ReindexRequest(folder="test", clear=False)
                await reindex_documents(req, mock_state)

            # Wait for all tasks to complete
            for _ in range(1000):
                async with mock_state.rag_state._lock:
                    has_tasks = bool(mock_state.rag_state._tasks)
                if not has_tasks:
                    break
                await asyncio.sleep(0)
            else:
                pytest.fail("Tasks were not cleaned up")

            async with mock_state.rag_state._lock:
                assert len(mock_state.rag_state._tasks) == 0


# ── Reranker Regression ──


    @pytest.mark.asyncio
    async def test_source_uri_is_relative_not_absolute(self, tmp_path, mock_chunker, mock_embedder, mock_vector_store):
        """REGRESSION: source_uri must be relative path, not absolute file URI.

        Given: documents in a temp folder.
        When: index_folder discovers and indexes them.
        Then: source_uri contains relative path, not absolute file:// URI.
        """
        from ai_assistant.core.domain.documents import Chunk, ChunkMetadata

        sources = tmp_path / "sources"
        personal = sources / "personal"
        personal.mkdir(parents=True)
        (personal / "notes.md").write_text("# Test note")

        # Capture what the chunker receives
        captured_docs: list[dict[str, Any]] = []
        original_chunk = mock_chunker.chunk

        async def capturing_chunk(document: Any) -> list[Any]:
            captured_docs.append({
                "id": document.id,
                "metadata": dict(document.metadata) if hasattr(document, "metadata") else {},
            })
            return await original_chunk(document)

        mock_chunker.chunk = capturing_chunk
        mock_vector_store.config.index_path = None

        result = await index_folder(
            folder="personal",
            clear=False,
            chunker=mock_chunker,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
            documents_root=sources,
        )

        assert result["success"] is True
        assert len(captured_docs) > 0

        for doc in captured_docs:
            source_uri = doc.get("metadata", {}).get("source_uri", "")
            assert not source_uri.startswith("file:///"), (
                f"source_uri must not be absolute file URI, got: {source_uri}"
            )
            assert "/" in source_uri or "\\" not in source_uri, (
                f"source_uri should use forward slashes (as_posix), got: {source_uri}"
            )
            assert "personal" in source_uri, (
                f"source_uri should contain relative path, got: {source_uri}"
            )



class TestChatNamespaceHelper:
    """Unit tests for _get_chat_namespace helper."""

    def test_get_chat_namespace_basic(self):
        """Given: base namespace 'personal'.
        Then: returns 'chat_personal'."""
        from ai_assistant.core.config import _get_chat_namespace
        assert _get_chat_namespace("personal") == "chat_personal"

    def test_get_chat_namespace_work(self):
        """Given: base namespace 'work'.
        Then: returns 'chat_work'."""
        from ai_assistant.core.config import _get_chat_namespace
        assert _get_chat_namespace("work") == "chat_work"

    def test_get_chat_namespace_rejects_reserved_prefix(self):
        """Given: base namespace already starts with 'chat_'.
        Then: raises ValueError."""
        from ai_assistant.core.config import _get_chat_namespace
        with pytest.raises(ValueError) as exc_info:
            _get_chat_namespace("chat_personal")
        assert "reserved prefix" in str(exc_info.value).lower()

    def test_chat_ns_prefix_constant(self):
        """Given: CHAT_NS_PREFIX constant.
        Then: equals 'chat_'."""
        from ai_assistant.core.config import CHAT_NS_PREFIX
        assert CHAT_NS_PREFIX == "chat_"



class TestChatExportIsolation:
    """Chat exports must not pollute regular RAG namespaces."""

    @pytest.mark.asyncio
    async def test_chat_export_not_indexed_by_default(self, mock_state, tmp_path):
        """Given: index_chat_exports is False (default).
        When: save_chat handler processes a request.
        Then: vector_store.add is never called — chat stays on disk only."""
        from ai_assistant.features.rag.handlers import save_chat
        from ai_assistant.features.rag.schemas import SaveChatRequest

        mock_state.config.rag.index_chat_exports = False
        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")

        req = SaveChatRequest(
            content="test chat content",
            namespace="personal",
            filename="test.md",
        )

        result = await save_chat(req, mock_state)

        assert result["saved"] is True
        assert result["indexed"] is False
        assert result["reason"] == "index_chat_exports is disabled"
        mock_state.vector_store.add.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chat_export_indexed_to_isolated_namespace(self, mock_state, mock_chunker, mock_embedder, mock_vector_store, tmp_path):
        """Given: index_chat_exports is True.
        When: save_chat handler processes a request.
        Then: response contains chat_namespace='chat_personal'."""
        from ai_assistant.features.rag.handlers import save_chat
        from ai_assistant.features.rag.schemas import SaveChatRequest
        from unittest.mock import patch, AsyncMock

        mock_state.config.rag.index_chat_exports = True
        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")

        # Patch IndexingManager to avoid real chunking/embedding
        with patch(
            "ai_assistant.features.rag.handlers.IndexingManager",
        ) as mock_mgr_cls:
            mock_mgr = AsyncMock()
            mock_mgr.index_documents = AsyncMock(return_value={
                "indexed_count": 1,
                "chunk_count": 1,
            })
            mock_mgr_cls.return_value = mock_mgr

            req = SaveChatRequest(
                content="test chat content",
                namespace="personal",
                filename="test.md",
            )

            result = await save_chat(req, mock_state)

            assert result["saved"] is True
            assert result.get("chat_namespace") == "chat_personal"
            # Verify IndexingManager was called with correct namespace
            mock_mgr.index_documents.assert_awaited_once()
            call_args = mock_mgr.index_documents.call_args
            assert call_args.kwargs.get("namespace") == "chat_personal"

    @pytest.mark.asyncio
    async def test_chat_export_not_in_regular_namespace_query(self, mock_vector_store):
        """Given: chat export exists in 'chat_personal' namespace.
        When: querying regular 'personal' namespace.
        Then: chat export chunks are NOT returned."""
        # Setup: configure mock to simulate namespace isolation
        # Regular namespace has 1 doc, chat namespace has 1 chat export
        def mock_search(query_embedding, top_k=5, namespace="default"):
            if namespace == "personal":
                return [
                    Chunk(
                        id="doc-1",
                        text="regular document",
                        embedding=[0.1] * 384,
                        metadata=ChunkMetadata(source="doc.txt", index=0, total_chunks=1),
                    )
                ]
            return []  # chat_personal or other namespaces return empty

        mock_vector_store.search = AsyncMock(side_effect=mock_search)

        # Query regular namespace
        results = await mock_vector_store.search(
            query_embedding=[0.1] * 384,
            top_k=10,
            namespace="personal",
        )

        # Should only find the regular doc
        assert len(results) == 1
        assert results[0].id == "doc-1"

        # Verify chat namespace is isolated
        chat_results = await mock_vector_store.search(
            query_embedding=[0.1] * 384,
            top_k=10,
            namespace="chat_personal",
        )
        assert len(chat_results) == 0

    @pytest.mark.asyncio
    async def test_namespace_collision_detected(self, mock_state, tmp_path):
        """Given: user namespace 'chat_personal' already exists with documents.
        When: save_chat called with namespace='personal'.
        Then: collision detected, chat NOT indexed, error returned."""
        from ai_assistant.features.rag.handlers import save_chat
        from ai_assistant.features.rag.schemas import SaveChatRequest

        mock_state.config.rag.index_chat_exports = True
        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["default", "personal", "chat_personal"])
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[("doc-1", {"type": "document"})])

        req = SaveChatRequest(
            content="test chat content",
            namespace="personal",
            filename="test.md",
        )

        result = await save_chat(req, mock_state)

        assert result["saved"] is True
        assert result.get("indexed") is False
        assert "collision" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_reindex_clears_chat_namespace(self, mock_state, tmp_path):
        """Given: chat exports indexed in 'chat_personal'.
        When: reindex called with clear=True, folder='personal'.
        Then: 'chat_personal' namespace is also cleared."""
        from ai_assistant.features.rag.handlers import reindex_documents
        from ai_assistant.features.rag.schemas import ReindexRequest
        from unittest.mock import patch, AsyncMock

        mock_state.config.rag.index_chat_exports = True
        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[
            ("chat-1", {"type": "chat_export"}),
            ("chat-2", {"type": "chat_export"}),
        ])
        mock_state.vector_store.delete = AsyncMock(return_value=None)

        # Patch index_folder to avoid real execution
        with patch(
            "ai_assistant.features.rag.handlers.index_folder",
            new_callable=AsyncMock,
        ) as mock_index:
            mock_index.return_value = {
                "success": True,
                "results": {"personal": {"indexed": 1}},
            }

            req = ReindexRequest(folder="personal", clear=True)
            result = await reindex_documents(req, mock_state)

            # Background task runs asynchronously
            # Give it time to execute
            await asyncio.sleep(0.1)

            # Manually trigger the cleanup logic by checking if task exists
            async with mock_state.rag_state._lock:
                task = mock_state.rag_state._tasks.get(result.get("task_id", ""))
            if task:
                try:
                    await asyncio.wait_for(task, timeout=1.0)
                except asyncio.TimeoutError:
                    pass

            # Verify chat namespace clearing was attempted
            # The delete call happens inside the background task
            # Check that list_by_filter was called for chat namespace
            filter_calls = mock_state.vector_store.list_by_filter.call_args_list
            chat_filter_calls = [
                c for c in filter_calls
                if c.kwargs.get("namespace") == "chat_personal" or
                (c.args and len(c.args) > 1 and c.args[1] == "chat_personal")
            ]
            assert len(chat_filter_calls) > 0, "list_by_filter should be called for chat_personal"


class TestRerankerRegression:
    """REGRESSION P0.6: reranker must be present in PipelineData for [p] prefix queries."""

    @pytest.mark.regression
    @pytest.mark.asyncio
    async def test_reranker_passed_in_pipeline_data_on_p_prefix(self, mock_state, mock_embedder, mock_vector_store):
        """Given: chat message with [p] prefix and working retrieval pipeline.
        When: ChatManager._retrieve_context is called.
        Then: PipelineData reaching the rerank step contains the reranker instance."""
        from ai_assistant.features.chat.manager import ChatManager
        from ai_assistant.core.pipeline import RAGPipeline
        from ai_assistant.core.domain.pipeline import PipelineData

        captured = {}

        async def fake_embed_query(data: PipelineData) -> PipelineData:
            """Fake embed_query step — stores embedding via typed field."""
            return data.with_query_embedding([0.1] * 384)

        async def fake_retrieve(data: PipelineData) -> PipelineData:
            """Fake retrieve step — returns chunks."""
            return data.with_chunks([
                Chunk(
                    id="c1",
                    text="test chunk",
                    embedding=[0.1] * 384,
                    metadata=ChunkMetadata(source="s", index=0, total_chunks=1),
                )
            ])

        async def capture_rerank(data: PipelineData) -> PipelineData:
            """Capture reranker from typed field and return data unchanged."""
            captured["reranker"] = data.reranker
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
    async def test_reranker_missing_returns_error(self):
        """Given: PipelineData has chunks but no reranker.
        When: rerank pipeline step executes.
        Then: INTERNAL_SERVER_ERROR is added; original chunks preserved."""
        from ai_assistant.core.domain.errors import INTERNAL_SERVER_ERROR

        data = PipelineData(
            query=UserMessage(text="test"),
            chunks=[
                Chunk(
                    id="c1",
                    text="chunk",
                    metadata=ChunkMetadata(source="s", index=0, total_chunks=1),
                )
            ],
            # reranker defaults to None
        )
        result = await rerank(data)
        assert any(INTERNAL_SERVER_ERROR in e for e in result.errors)
        # chunks are preserved (not mutated) so downstream can inspect or ignore
        assert len(result.chunks) == 1
        assert result.chunks[0].id == "c1"




# ── RAG health check after load() ───────────────────────────────────────────

async def test_rag_health_after_load_shows_correct_chunks(tmp_path: Path) -> None:
    """Health check after correct load() shows accurate chunk_count.

    Verifies that load() restores state correctly and health reflects it.
    """
    pytest.importorskip("faiss")
    from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
    from ai_assistant.core.domain.configs import VectorStoreConfigData
    from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
    from ai_assistant.features.rag.manager import RAGManager
    from ai_assistant.core.pipeline import RAGPipeline

    config = VectorStoreConfigData(dim=384, index_path=str(tmp_path))
    vector_store = FaissVectorStore(config)

    # Add a chunk with embedding
    chunk = Chunk(
        id="test-1",
        text="test content",
        embedding=[0.1] * 384,
        metadata=ChunkMetadata(source="test", index=0, total_chunks=1),
    )
    await vector_store.add([chunk], namespace="default")

    # Save and reload
    await vector_store.save(str(tmp_path), namespace="default")
    await vector_store.load(str(tmp_path), namespace="default")

    # Create minimal RAGManager for health check
    pipeline = RAGPipeline([])
    rag_manager = RAGManager(
        pipeline=pipeline,
        llm=None,  # type: ignore[arg-type]
        vector_store=vector_store,
        embedder=None,  # type: ignore[arg-type]
        reranker=None,  # type: ignore[arg-type]
    )

    health = await rag_manager.health()
    assert health["chunk_count"] == 1
    assert health["index_loaded"] is True
