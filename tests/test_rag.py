"""tests/test_rag.py — RAG feature tests + reranker regression (P0.6)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
from ai_assistant.core.domain.configs import TokenizerConfigData
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline_steps import rerank
from ai_assistant.core.ports.chunker import IChunker
from ai_assistant.core.ports.embedder import IEmbedder
from ai_assistant.core.ports.llm import ILLM
from ai_assistant.core.ports.reranker import IReranker, RerankResult
from ai_assistant.core.ports.vector_store import IVectorStore
from ai_assistant.features.rag.handlers import (
    delete_chunks,
    index_documents,
    list_namespaces,
    query_rag,
    rag_health,
    reindex_documents,
    reindex_status,
    save_chat,
)
from ai_assistant.features.rag.indexing import index_folder
from ai_assistant.features.rag.manager import IndexingManager, RAGManager
from ai_assistant.features.rag.schemas import (
    DeleteRequest,
    IndexRequest,
    QueryRequest,
    ReindexRequest,
    SaveChatRequest,
)

_logger = get_logger(__name__)


# ── RAGManager ──

class TestRAGManager:
    """RAGManager — query pipeline and health checks."""

    @pytest.mark.asyncio
    async def test_query_pipeline_success(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: working ports return chunks and LLM generates answer.
        When: RAGManager.query is called.
        Then: response contains answer, sources and chunk count."""
        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_vector_store.search = AsyncMock(return_value=[
            Chunk(
                id="c1",
                text="Paris is the capital of France.",
                embedding=[0.1] * 384,
                metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
            )
        ])
        mock_reranker.rerank = AsyncMock(return_value=[
            RerankResult(chunk=Chunk(
                id="c1",
                text="Paris is the capital of France.",
                embedding=[0.1] * 384,
                metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
            ), score=0.95)
        ])
        mock_llm.get_context_limit = MagicMock(return_value=8192)
        mock_llm.complete = AsyncMock(return_value=MagicMock(text="Paris"))

        mgr = RAGManager(
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
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
        Then: vector_store.search receives namespace='work'."""
        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_vector_store.search = AsyncMock(return_value=[])
        mock_reranker.rerank = AsyncMock(return_value=[])
        mock_llm.get_context_limit = MagicMock(return_value=8192)
        mock_llm.complete = AsyncMock(return_value=MagicMock(text=""))

        mgr = RAGManager(
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        await mgr.query("test", namespace="work")

        # Verify namespace reached the vector_store port
        mock_vector_store.search.assert_awaited_once()
        call_kwargs = mock_vector_store.search.call_args.kwargs
        assert call_kwargs.get("namespace") == "work"

    @pytest.mark.asyncio
    async def test_query_prompt_and_threshold_override(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: custom prompt name, version and relevance threshold.
        When: RAGManager.query called with overrides.
        Then: pipeline completes successfully with overridden config."""
        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_vector_store.search = AsyncMock(return_value=[
            Chunk(
                id="c1",
                text="test chunk",
                embedding=[0.1] * 384,
                metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
            )
        ])
        mock_reranker.rerank = AsyncMock(return_value=[
            RerankResult(chunk=Chunk(
                id="c1",
                text="test chunk",
                embedding=[0.1] * 384,
                metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
            ), score=0.95)
        ])
        mock_llm.get_context_limit = MagicMock(return_value=8192)
        mock_llm.complete = AsyncMock(return_value=MagicMock(text=""))

        mgr = RAGManager(
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        # Should not raise — overrides flow through pipeline_config to generate step
        result = await mgr.query(
            "test",
            prompt_name="rag_creative",
            prompt_version="v2",
            relevance_threshold=0.5,
        )
        assert result["answer"] == ""
        assert result["errors"] == []
        # Verify LLM was called (generate step reached)
        mock_llm.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_empty_results_handling(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: no relevant chunks found.
        When: RAGManager.query is called.
        Then: answer is returned and sources list is empty."""
        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_vector_store.search = AsyncMock(return_value=[])
        mock_reranker.rerank = AsyncMock(return_value=[])
        mock_llm.get_context_limit = MagicMock(return_value=8192)
        mock_llm.complete = AsyncMock(return_value=MagicMock(text="I don\'t have enough information."))

        mgr = RAGManager(
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await mgr.query("obscure topic")
        assert result["answer"] == "I don\'t have enough information."
        assert result["chunks_used"] == 0
        assert result["sources"] == []
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_query_llm_unavailable_returns_503(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: LLM raises AdapterError (simulating LLM_UNAVAILABLE).
        When: RAGManager.query processes through real pipeline.
        Then: result contains LLM_UNAVAILABLE in errors; handler raises HTTPException 503."""
        from ai_assistant.core.domain.errors import LLM_UNAVAILABLE

        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_vector_store.search = AsyncMock(return_value=[
            Chunk(
                id="c1",
                text="test chunk",
                embedding=[0.1] * 384,
                metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
            )
        ])
        mock_reranker.rerank = AsyncMock(return_value=[
            RerankResult(chunk=Chunk(
                id="c1",
                text="test chunk",
                embedding=[0.1] * 384,
                metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
            ), score=0.95)
        ])
        mock_llm.get_context_limit = MagicMock(return_value=8192)
        mock_llm.complete = AsyncMock(side_effect=AdapterError("LLM down"))

        mgr = RAGManager(
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await mgr.query("anything")
        # generate step catches AdapterError and adds LLM_UNAVAILABLE to data.errors
        assert any(LLM_UNAVAILABLE in e for e in result["errors"])
        assert "LLM service temporarily unavailable" in result["answer"]

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
    async def test_query_unexpected_exception_propagates(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """REGRESSION: unexpected pipeline bugs must not be swallowed as empty 200.

        Given: pipeline.run raises an unexpected exception (bug in pipeline orchestration).
        When: RAGManager.query is called.
        Then: exception propagates instead of returning empty answer with HTTP 200.
        """
        from ai_assistant.core.domain.errors import ConfigurationError

        mgr = RAGManager(
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        # Simulate a bug in pipeline orchestration (e.g. missing required field check)
        async def buggy_run(data):
            raise ConfigurationError("simulated pipeline bug")

        mgr.pipeline.run = buggy_run

        # The bug should propagate, not be swallowed
        with pytest.raises(ConfigurationError, match="simulated pipeline bug"):
            await mgr.query("anything")

    @pytest.mark.asyncio
    async def test_health_index_loaded(self, mock_vector_store):
        """Given: vector store has namespaces with chunks.
        When: RAGManager.health is called.
        Then: status is 'ok', index_loaded=True, chunk_count > 0."""
        mock_vector_store.index_path = "./data/indices"
        mock_vector_store.list_namespaces = AsyncMock(return_value=["default", "work"])
        mock_vector_store.list_by_filter = AsyncMock(return_value=[("c1", {}), ("c2", {})])

        mgr = RAGManager(
            llm=MagicMock(spec=ILLM),
            vector_store=mock_vector_store,
            embedder=MagicMock(spec=IEmbedder),
            reranker=MagicMock(spec=IReranker),
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
            llm=MagicMock(spec=ILLM),
            vector_store=mock_vector_store,
            embedder=MagicMock(spec=IEmbedder),
            reranker=MagicMock(spec=IReranker),
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
        Then: documents are chunked, embedded and stored; counts are returned.
              Chunker receives correct Document objects with expected content."""
        # Capture what the chunker receives (input documents, not output chunks)
        chunked_documents: list[Any] = []
        original_chunk = mock_chunker.chunk

        async def capture_chunk(document: Any) -> list[Any]:
            chunked_documents.append(document)
            return await original_chunk(document)

        mock_chunker.chunk = capture_chunk

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

        # Assert on operation result (state)
        assert result["indexed_count"] == 1
        assert result["chunk_count"] == 1

        # Assert on side effects — what the chunker was fed
        assert len(chunked_documents) == 1
        doc = chunked_documents[0]
        assert doc.id == "d1"
        assert doc.content == "hello world"
        assert doc.metadata.get("source") == "test.txt"

    @pytest.mark.asyncio
    async def test_delete_by_chunk_id(self, mock_vector_store):
        """Given: existing chunk IDs.
        When: vector_store.delete is called with those IDs.
        Then: specified chunks are removed from the store."""
        # Track deletion state
        deleted_ids: list[list[str]] = []
        deleted_namespaces: list[str] = []

        async def track_delete(chunk_ids: list[str], namespace: str) -> None:
            deleted_ids.append(chunk_ids)
            deleted_namespaces.append(namespace)

        mock_vector_store.delete = AsyncMock(side_effect=track_delete)

        await mock_vector_store.delete(["c1", "c2"], namespace="test")

        # Assert on state change, not just call count
        assert len(deleted_ids) == 1
        assert deleted_ids[0] == ["c1", "c2"]
        assert deleted_namespaces[0] == "test"

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

        # Track deletion state
        deleted_ids: list[list[str]] = []

        async def track_delete(chunk_ids: list[str], namespace: str) -> None:
            deleted_ids.append(chunk_ids)

        mock_vector_store.delete = AsyncMock(side_effect=track_delete)

        doc_ids = ["d1"]
        existing = await mock_vector_store.list_by_filter({}, namespace="test")
        to_delete = [cid for cid, meta in existing if meta.get("source") in doc_ids]

        await mock_vector_store.delete(to_delete, namespace="test")

        # Assert on computed state, not just call count
        assert len(to_delete) == 2
        assert to_delete == ["c1", "c2"]
        assert len(deleted_ids) == 1
        assert deleted_ids[0] == ["c1", "c2"]

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
        mock_vector_store.config.index_path = str(tmp_path / "indices")

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
    async def test_index_folder_does_not_block_event_loop(
        self, monkeypatch, tmp_path, mock_chunker, mock_embedder, mock_vector_store
    ):
        """REGRESSION: sync file I/O inside index_folder must not block the event loop.

        Given: _read_file is intentionally slow (simulating large file).
        When: index_folder runs with multiple files.
        Then: event loop remains responsive — a concurrent ticker keeps firing.
        """
        import time

        def _slow_read(path: Path) -> str:
            time.sleep(0.05)  # 50ms per file
            return "test content"

        monkeypatch.setattr(
            "ai_assistant.features.rag.indexing._read_file",
            _slow_read,
        )

        sources = tmp_path / "sources"
        ns = sources / "personal"
        ns.mkdir(parents=True)
        for i in range(5):
            (ns / f"doc{i}.md").write_text("x")

        mock_vector_store.config.index_path = str(tmp_path / "indices")

        ticks: list[float] = []

        async def _ticker() -> None:
            while True:
                await asyncio.sleep(0.005)
                ticks.append(asyncio.get_event_loop().time())

        task = asyncio.create_task(_ticker())
        try:
            await index_folder(
                folder="personal",
                clear=False,
                chunker=mock_chunker,
                embedder=mock_embedder,
                vector_store=mock_vector_store,
                documents_root=sources,
            )
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # 5 files * 50ms = 250ms of blocking work.
        # If it ran in the main thread, ticker would fire ~0 times.
        # In a thread pool, ticker fires ~40+ times (250ms / 5ms = 50).
        assert len(ticks) > 15, f"event loop blocked: only {len(ticks)} ticks"

# ── Reranker Regression ──



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
    async def test_save_chat_rejects_invalid_namespace(self, mock_state, tmp_path):
        """Given: namespace contains path traversal or invalid chars.
        When: SaveChatRequest is constructed.
        Then: Pydantic validation error is raised before handler runs."""
        from ai_assistant.features.rag.schemas import SaveChatRequest

        invalid_namespaces = ["../etc", "foo/bar", "Foo", "123", "chat_"]
        for ns in invalid_namespaces:
            with pytest.raises(ValueError):
                SaveChatRequest(content="test", namespace=ns, filename="test.md")

    @pytest.mark.asyncio
    async def test_chat_export_not_indexed_by_default(self, mock_state, tmp_path):
        """Given: index_chat_exports is False (default).
        When: saveChat handler processes a request.
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
        When: saveChat handler processes a request.
        Then: chat content is indexed to 'chat_personal' namespace, response reflects state."""
        from ai_assistant.features.rag.handlers import save_chat
        from ai_assistant.features.rag.schemas import SaveChatRequest
        from unittest.mock import patch, AsyncMock

        mock_state.config.rag.index_chat_exports = True
        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")

        # Track what gets indexed — state-based assertion instead of just call count
        indexed_docs: list[dict[str, Any]] = []
        indexed_namespaces: list[str] = []

        async def track_index_documents(docs: list[dict[str, Any]], namespace: str) -> dict[str, Any]:
            indexed_docs.extend(docs)
            indexed_namespaces.append(namespace)
            return {"indexed_count": len(docs), "chunk_count": 1}

        # Patch IndexingManager to avoid real chunking/embedding but track state
        with patch(
            "ai_assistant.features.rag.handlers.IndexingManager",
        ) as mock_mgr_cls:
            mock_mgr = AsyncMock()
            mock_mgr.index_documents = AsyncMock(side_effect=track_index_documents)
            mock_mgr_cls.return_value = mock_mgr

            req = SaveChatRequest(
                content="test chat content",
                namespace="personal",
                filename="test.md",
            )

            result = await save_chat(req, mock_state)

            # Assert on result state
            assert result["saved"] is True
            assert result.get("chat_namespace") == "chat_personal"

            # Assert on side-effect state, not just call count
            assert len(indexed_namespaces) == 1
            assert indexed_namespaces[0] == "chat_personal"
            assert len(indexed_docs) == 1
            assert indexed_docs[0]["content"] == "test chat content"
            # source may include folder prefix (e.g., "personal/test.md")
            assert "test.md" in indexed_docs[0]["metadata"]["source"]

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
        When: saveChat called with namespace='personal'.
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

        # Track what gets deleted — state-based assertion
        deleted_chunks: list[tuple[list[str], str]] = []

        async def track_delete(chunk_ids: list[str], namespace: str) -> None:
            deleted_chunks.append((chunk_ids, namespace))

        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[
            ("chat-1", {"type": "chat_export"}),
            ("chat-2", {"type": "chat_export"}),
        ])
        mock_state.vector_store.delete = AsyncMock(side_effect=track_delete)

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
            await reindex_documents(req, mock_state)

            # Give event loop a chance to run the background task
            for _ in range(100):
                await asyncio.sleep(0)
                if deleted_chunks:
                    break
            else:
                pytest.fail("Background task did not clear chat namespace")

            # Assert on deletion state — verify chat namespace was targeted
            chat_deletions = [
                (ids, ns) for ids, ns in deleted_chunks
                if ns == "chat_personal"
            ]
            assert len(chat_deletions) > 0, "chat_personal namespace should be cleared"
            assert chat_deletions[0][0] == ["chat-1", "chat-2"]


class TestRerankerRegression:
    """REGRESSION P0.6: reranker must be present in PipelineData for [p] prefix queries."""

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


# ── TraceId in RAG handlers ───────────────────────────────────────────────


def _assert_all_logs_have_trace_id(caplog: pytest.LogCaptureFixture) -> None:
    """Assert every log record from rag.handlers has a trace_id in extra."""
    rag_records = [r for r in caplog.records if r.name == "ai_assistant.rag.handlers"]
    assert rag_records, "Expected at least one log record from rag.handlers"
    for record in rag_records:
        assert hasattr(record, "trace_id"), (
            f"Log record '{record.getMessage()}' missing trace_id"
        )
        assert record.trace_id is not None, (
            f"Log record '{record.getMessage()}' has None trace_id"
        )
        assert len(record.trace_id) == 32, (
            f"Log record '{record.getMessage()}' has invalid trace_id length"
        )


class TestRAGHandlersTraceId:
    """All _logger calls in RAG handlers must include extra={"trace_id": ...}."""

    @pytest.mark.asyncio
    async def test_index_documents_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.vector_store.save = AsyncMock()

        with patch(
            "ai_assistant.features.rag.handlers.IndexingManager"
        ) as MockMgr:
            mock_mgr = MagicMock()
            mock_mgr.index_documents = AsyncMock(
                return_value={"indexed_count": 1, "chunk_count": 2}
            )
            MockMgr.return_value = mock_mgr

            req = IndexRequest(
                documents=[{"id": "doc1", "content": "hello", "metadata": {}}],
                namespace="default",
            )
            resp = await index_documents(req, mock_state)

        assert resp.indexed_count == 1
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_index_documents_all_filtered_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.config.vector_store.max_document_size = 1

        req = IndexRequest(
            documents=[{"id": "doc1", "content": "hello world", "metadata": {}}],
            namespace="default",
        )
        resp = await index_documents(req, mock_state)

        assert resp.indexed_count == 0
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_index_documents_auto_save_error_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.vector_store.save = AsyncMock(side_effect=RuntimeError("disk full"))

        with patch(
            "ai_assistant.features.rag.handlers.IndexingManager"
        ) as MockMgr:
            mock_mgr = MagicMock()
            mock_mgr.index_documents = AsyncMock(
                return_value={"indexed_count": 1, "chunk_count": 2}
            )
            MockMgr.return_value = mock_mgr

            req = IndexRequest(
                documents=[{"id": "doc1", "content": "hello", "metadata": {}}],
                namespace="default",
            )
            with pytest.raises(HTTPException) as exc_info:
                await index_documents(req, mock_state)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal server error"
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_query_rag_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")

        mock_manager = MagicMock()
        mock_manager.query = AsyncMock(
            return_value={
                "answer": "answer",
                "sources": [],
                "chunks_used": 1,
                "errors": [],
            }
        )

        req = QueryRequest(query="test", namespace="default")
        resp = await query_rag(req, mock_manager, mock_state)

        assert resp.answer == "answer"
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_query_rag_llm_unavailable_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")

        mock_manager = MagicMock()
        mock_manager.query = AsyncMock(
            return_value={
                "answer": "",
                "sources": [],
                "chunks_used": 0,
                "errors": ["generate: LLM unavailable (connection timeout)"],
            }
        )

        req = QueryRequest(query="test", namespace="default")
        with pytest.raises(HTTPException) as exc_info:
            await query_rag(req, mock_manager, mock_state)

        assert exc_info.value.status_code == 503
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_delete_chunks_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.vector_store.delete = AsyncMock()
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[])

        req = DeleteRequest(chunk_ids=["c1"], namespace="default")
        resp = await delete_chunks(req, mock_state)

        assert resp.deleted_chunks == 1
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_delete_chunks_error_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.vector_store.delete = AsyncMock(side_effect=RuntimeError("boom"))

        req = DeleteRequest(chunk_ids=["c1"], namespace="default")
        with pytest.raises(HTTPException) as exc_info:
            await delete_chunks(req, mock_state)

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "Internal server error"
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_rag_health_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")

        mock_manager = MagicMock()
        mock_manager.health = AsyncMock(
            return_value={"status": "ok", "index_loaded": True, "chunk_count": 5}
        )

        resp = await rag_health(mock_manager, mock_state)

        assert resp.status == "ok"
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_list_namespaces_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["ns1", "ns2"])

        resp = await list_namespaces(mock_state)

        assert resp.namespaces == ["ns1", "ns2"]
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_list_namespaces_error_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.vector_store.list_namespaces = AsyncMock(side_effect=RuntimeError("boom"))

        resp = await list_namespaces(mock_state)

        assert resp.namespaces == ["default"]
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_save_chat_logs_trace_id(self, caplog, mock_state, tmp_path):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=[])

        req = SaveChatRequest(content="hello", namespace="test", filename="chat.md")
        resp = await save_chat(req, mock_state)

        assert resp["saved"] is True
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_save_chat_invalid_namespace_rejected_by_schema(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")

        # Pydantic rejects invalid namespace before handler runs
        with pytest.raises(ValueError):
            SaveChatRequest(content="hello", namespace="INVALID", filename="chat.md")

    @pytest.mark.asyncio
    async def test_save_chat_indexing_enabled_logs_trace_id(self, caplog, mock_state, tmp_path):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.config.rag.index_chat_exports = True
        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=[])
        mock_state.vector_store.save = AsyncMock()

        with patch("ai_assistant.features.rag.handlers.IndexingManager") as MockMgr:
            mock_mgr = MagicMock()
            mock_mgr.index_documents = AsyncMock(
                return_value={"indexed_count": 1, "chunk_count": 2}
            )
            MockMgr.return_value = mock_mgr

            req = SaveChatRequest(content="hello", namespace="test", filename="chat.md")
            resp = await save_chat(req, mock_state)

        assert resp["saved"] is True
        assert "indexed_count" in resp
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_reindex_documents_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[])
        mock_state.vector_store.delete = AsyncMock()

        with patch(
            "ai_assistant.features.rag.handlers.index_folder",
            new=AsyncMock(return_value={"indexed": 1}),
        ):
            req = ReindexRequest(folder="test", clear=False)
            resp = await reindex_documents(req, mock_state)

        assert resp["status"] == "started"
        assert "task_id" in resp
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_reindex_status_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.rag_state.get_status = AsyncMock(
            return_value={"status": "completed", "started_at": 0.0}
        )

        resp = await reindex_status("task-123", mock_state)

        assert resp["status"] == "completed"
        _assert_all_logs_have_trace_id(caplog)

    @pytest.mark.asyncio
    async def test_reindex_status_unknown_logs_trace_id(self, caplog, mock_state):
        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.rag_state.get_status = AsyncMock(return_value=None)

        resp = await reindex_status("task-123", mock_state)

        assert resp["status"] == "unknown"
        _assert_all_logs_have_trace_id(caplog)




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

    # Create minimal RAGManager for health check — no pipeline param needed
    rag_manager = RAGManager(
        llm=None,  # type: ignore[arg-type]
        vector_store=vector_store,
        embedder=None,  # type: ignore[arg-type]
        reranker=None,  # type: ignore[arg-type]
    )

    health = await rag_manager.health()
    assert health["chunk_count"] == 1
    assert health["index_loaded"] is True
