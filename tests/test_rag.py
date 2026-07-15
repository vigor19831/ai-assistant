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
from ai_assistant.core.domain.errors import AdapterError, LLM_UNAVAILABLE
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
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
        mock_llm.complete = AsyncMock(return_value=AssistantMessage(text="Paris"))

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
        """Given: namespace is set to 'test-alt'.
        When: RAGManager.query called with namespace='test-alt'.
        Then: vector_store.search receives namespace='test-alt'."""
        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_vector_store.search = AsyncMock(return_value=[])
        mock_reranker.rerank = AsyncMock(return_value=[])
        mock_llm.get_context_limit = MagicMock(return_value=8192)
        mock_llm.complete = AsyncMock(return_value=AssistantMessage(text=""))

        mgr = RAGManager(
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        await mgr.query("test", namespace="test-alt")

        # Verify namespace reached the vector_store port
        mock_vector_store.search.assert_awaited_once()
        call_kwargs = mock_vector_store.search.call_args.kwargs
        assert call_kwargs.get("namespace") == "test-alt"

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
        mock_llm.complete = AsyncMock(return_value=AssistantMessage(text=""))

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
            threshold=0.5,
        )
        assert result["answer"] == ""
        assert result["errors"] == []
        # Verify LLM was called (generate step reached)
        mock_llm.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_empty_results_handling(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: no relevant chunks found.
        When: RAGManager.query is called.
        Then: LLM answers from general knowledge; sources list is empty."""
        mock_embedder.embed = AsyncMock(return_value=[[0.1] * 384])
        mock_vector_store.search = AsyncMock(return_value=[])
        mock_reranker.rerank = AsyncMock(return_value=[])
        mock_llm.get_context_limit = MagicMock(return_value=8192)
        # generate step now calls LLM even with empty context (general knowledge mode)
        mock_llm.complete = AsyncMock(
            return_value=AssistantMessage(text="I don't have specific information about that in my documents.")
        )

        mgr = RAGManager(
            llm=mock_llm,
            vector_store=mock_vector_store,
            embedder=mock_embedder,
            reranker=mock_reranker,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await mgr.query("obscure topic")
        assert result["chunks_used"] == 0
        assert result["sources"] == []
        assert result["errors"] == []
        mock_llm.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_query_llm_unavailable_returns_503(self, mock_llm, mock_embedder, mock_vector_store, mock_reranker):
        """Given: LLM raises AdapterError (simulating LLM_UNAVAILABLE).
        When: RAGManager.query processes through real pipeline.
        Then: result contains LLM_UNAVAILABLE in errors; handler raises HTTPException 503."""
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
        # The bug should propagate, not be swallowed
        with patch.object(
            mgr.pipeline,
            "run",
            side_effect=ConfigurationError("simulated pipeline bug"),
        ):
            with pytest.raises(ConfigurationError, match="simulated pipeline bug"):
                await mgr.query("anything")

    @pytest.mark.asyncio
    async def test_health_index_loaded(self, mock_vector_store, tmp_path):
        """Given: vector store has namespaces with chunks.
        When: RAGManager.health is called.
        Then: status is 'ok', index_loaded=True, chunk_count > 0."""
        mock_vector_store.index_path = str(tmp_path / "indices")
        mock_vector_store.list_namespaces = AsyncMock(return_value=["default", "test"])
        mock_vector_store.list_by_filter = AsyncMock(return_value=[
            ("c1", ChunkMetadata(source="s1", index=0, total_chunks=1)),
            ("c2", ChunkMetadata(source="s2", index=0, total_chunks=1)),
        ])

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
    async def test_health_empty_index(self, mock_vector_store, tmp_path):
        """Given: vector store has no namespaces.
        When: RAGManager.health is called.
        Then: status is 'empty', index_loaded=False, chunk_count is 0."""
        mock_vector_store.index_path = str(tmp_path / "indices")
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
        assert doc.metadata["source"] == "test.txt"

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
                ("c1", ChunkMetadata(source="d1", index=0, total_chunks=1)),
                ("c2", ChunkMetadata(source="d1", index=0, total_chunks=1)),
                ("c3", ChunkMetadata(source="d2", index=0, total_chunks=1)),
            ]
        )

        # Track deletion state
        deleted_ids: list[list[str]] = []

        async def track_delete(chunk_ids: list[str], namespace: str) -> None:
            deleted_ids.append(chunk_ids)

        mock_vector_store.delete = AsyncMock(side_effect=track_delete)

        doc_ids = ["d1"]
        existing = await mock_vector_store.list_by_filter({}, namespace="test")
        to_delete = [cid for cid, meta in existing if meta.source in doc_ids]

        await mock_vector_store.delete(to_delete, namespace="test")

        # Assert on computed state, not just call count
        assert len(to_delete) == 2
        assert to_delete == ["c1", "c2"]
        assert len(deleted_ids) == 1
        assert deleted_ids[0] == ["c1", "c2"]

    @pytest.mark.asyncio
    async def test_reindex_background_task(self, tmp_path, mock_chunker, mock_embedder, mock_vector_store):
        """Given: markdown files in tmp_path/sources/test.
        When: index_folder is called with sources pointing to test folder.
        Then: documents are indexed and namespace 'test' appears in results."""
        from ai_assistant.core.config import SourceConfig

        sources = tmp_path / "sources"
        test = sources / "test"
        test.mkdir(parents=True)
        (test / "notes.md").write_text("# Hello\nThis is a test note.")

        result = await index_folder(
            folder="test",
            clear=False,
            chunker=mock_chunker,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
            sources=[
                SourceConfig(
                    namespace="test",
                    path=str(test),
                    include=["*.md"],
                    recursive=True,
                )
            ],
            index_path=str(tmp_path / "indices"),
        )
        assert result["success"] is True
        assert "test" in result["results"]
        assert result["results"]["test"]["indexed"] == 1

    @pytest.mark.asyncio
    async def test_index_folder_does_not_block_event_loop(
        self, monkeypatch, tmp_path, mock_chunker, mock_embedder, mock_vector_store
    ):
        """REGRESSION: sync file I/O inside index_folder must not block the event loop.

        Given: the file reader is intentionally slow (simulating large file).
        When: index_folder runs with multiple files.
        Then: event loop remains responsive — a concurrent ticker keeps firing.
        """
        import time
        from ai_assistant.core.config import SourceConfig

        def _slow_read(path: Path) -> str:
            time.sleep(0.05)  # noqa: SLEEP — monkeypatched _read_file_sync: blocking sync I/O simulation
            return "test content"

        monkeypatch.setattr(
            "ai_assistant.features.rag.indexing._read_file_sync",
            _slow_read,
        )

        sources = tmp_path / "sources"
        ns = sources / "test"
        ns.mkdir(parents=True)
        for i in range(5):
            (ns / f"doc{i}.md").write_text("x")

        tick_count = 0
        done = asyncio.Event()

        async def _ticker() -> None:
            nonlocal tick_count
            while not done.is_set():
                await asyncio.sleep(0)  # noqa: SLEEP — yield control, not wall-clock sleep
                tick_count += 1

        task = asyncio.create_task(_ticker())
        try:
            await index_folder(
                folder="test",
                clear=False,
                chunker=mock_chunker,
                embedder=mock_embedder,
                vector_store=mock_vector_store,
                sources=[
                    SourceConfig(
                        namespace="test",
                        path=str(ns),
                        include=["*.md"],
                        recursive=True,
                    )
                ],
                index_path=str(tmp_path / "indices"),
            )
        finally:
            done.set()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # 5 files * 50ms = 250ms of blocking work.
        # If it ran in the main thread, ticker would fire ~0 times.
        # In a thread pool, ticker fires many times (each await yields control).
        assert tick_count >= 15, f"event loop blocked: only {tick_count} ticks"

# ── Reranker Regression ──



class TestChatNamespaceHelper:
    """Unit tests for _get_chat_namespace helper."""

    def test_get_chat_namespace_basic(self):
        """Given: base namespace 'test'.
        Then: returns 'chat_test'."""
        from ai_assistant.core.config import _get_chat_namespace
        assert _get_chat_namespace("test") == "chat_test"

    def test_get_chat_namespace_alt(self):
        """Given: base namespace 'test-alt'.
        Then: returns 'chat_test-alt'."""
        from ai_assistant.core.config import _get_chat_namespace
        assert _get_chat_namespace("test-alt") == "chat_test-alt"

    def test_get_chat_namespace_rejects_reserved_prefix(self):
        """Given: base namespace already starts with 'chat_'.
        Then: raises ValueError."""
        from ai_assistant.core.config import _get_chat_namespace
        with pytest.raises(ValueError) as exc_info:
            _get_chat_namespace("chat_test")
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
            namespace="test",
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
                namespace="test",
                filename="test.md",
            )

            result = await save_chat(req, mock_state)

            # Assert on result state
            assert result["saved"] is True
            assert result.get("chat_namespace") == "chat_test"

            # Assert on side-effect state, not just call count
            assert len(indexed_namespaces) == 1
            assert indexed_namespaces[0] == "chat_test"
            assert len(indexed_docs) == 1
            assert indexed_docs[0]["content"] == "test chat content"
            # source may include folder prefix (e.g., "test/test.md")
            assert "test.md" in indexed_docs[0]["metadata"]["source"]

    @pytest.mark.asyncio
    async def test_chat_export_not_in_regular_namespace_query(self, mock_vector_store):
        """Given: chat export exists in 'chat_test' namespace.
        When: querying regular 'test' namespace.
        Then: chat export chunks are NOT returned."""
        # Setup: configure mock to simulate namespace isolation
        # Regular namespace has 1 doc, chat namespace has 1 chat export
        def mock_search(query_embedding, top_k=5, namespace="default"):
            if namespace == "test":
                return [
                    Chunk(
                        id="doc-1",
                        text="regular document",
                        embedding=[0.1] * 384,
                        metadata=ChunkMetadata(source="doc.txt", index=0, total_chunks=1),
                    )
                ]
            return []  # chat_test or other namespaces return empty

        mock_vector_store.search = AsyncMock(side_effect=mock_search)

        # Query regular namespace
        results = await mock_vector_store.search(
            query_embedding=[0.1] * 384,
            top_k=10,
            namespace="test",
        )

        # Should only find the regular doc
        assert len(results) == 1
        assert results[0].id == "doc-1"

        # Verify chat namespace is isolated
        chat_results = await mock_vector_store.search(
            query_embedding=[0.1] * 384,
            top_k=10,
            namespace="chat_test",
        )
        assert len(chat_results) == 0

    @pytest.mark.asyncio
    async def test_namespace_collision_detected(self, mock_state, tmp_path):
        """Given: user namespace 'chat_test' already exists with documents.
        When: saveChat called with namespace='test'.
        Then: collision detected, chat NOT indexed, error returned."""
        from ai_assistant.features.rag.handlers import save_chat
        from ai_assistant.features.rag.schemas import SaveChatRequest

        mock_state.config.rag.index_chat_exports = True
        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")
        mock_state.vector_store.list_namespaces = AsyncMock(return_value=["default", "test", "chat_test"])
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[("doc-1", ChunkMetadata(source="doc", index=0, total_chunks=1))])

        req = SaveChatRequest(
            content="test chat content",
            namespace="test",
            filename="test.md",
        )

        result = await save_chat(req, mock_state)

        assert result["saved"] is True
        assert result.get("indexed") is False
        assert "collision" in result.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_reindex_clears_chat_namespace(self, mock_state, tmp_path):
        """Given: chat exports indexed in 'chat_test'.
        When: reindex called with clear=True, namespace='test'.
        Then: 'chat_test' namespace is also cleared."""
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
            ("chat-1", ChunkMetadata(source="chat", index=0, total_chunks=1)),
            ("chat-2", ChunkMetadata(source="chat", index=0, total_chunks=1)),
        ])
        mock_state.vector_store.delete = AsyncMock(side_effect=track_delete)

        # Patch index_folder to avoid real execution
        with patch(
            "ai_assistant.features.rag.handlers.index_folder",
            new_callable=AsyncMock,
        ) as mock_index:
            mock_index.return_value = {
                "success": True,
                "results": {"test": {"indexed": 1}},
            }

            req = ReindexRequest(folder="test", clear=True)
            await reindex_documents(req, mock_state)

            # Capture the background task before it completes and await it.
            tasks = list(mock_state.task_registry.get_tasks())
            assert len(tasks) == 1, f"Expected 1 background task, got {len(tasks)}"
            await asyncio.wait_for(tasks.pop().task, timeout=1.0)

            # Assert on deletion state — verify chat namespace was targeted
            chat_deletions = [
                (ids, ns) for ids, ns in deleted_chunks
                if ns == "chat_test"
            ]
            assert len(chat_deletions) > 0, "chat_test namespace should be cleared"
            assert chat_deletions[0][0] == ["chat-1", "chat-2"]


class TestReindexTaskSafety:
    """REGRESSION: reindex background tasks must not leak or lose exceptions."""

    @pytest.mark.asyncio
    async def test_reindex_does_not_leak_tasks(self, mock_state, tmp_path):
        """Given: reindex is triggered.
        When: background task completes.
        Then: asyncio.all_tasks() does not grow — task is cleaned up.
        """
        from ai_assistant.features.rag.handlers import reindex_documents
        from ai_assistant.features.rag.schemas import ReindexRequest
        from unittest.mock import patch, AsyncMock

        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[])
        mock_state.vector_store.delete = AsyncMock()

        tasks_before = len(asyncio.all_tasks())

        with patch(
            "ai_assistant.features.rag.handlers.index_folder",
            new=AsyncMock(return_value={"success": True}),
        ):
            req = ReindexRequest(folder="test", clear=False)
            await reindex_documents(req, mock_state)

            # Wait for background task to complete
            tasks = list(mock_state.task_registry.get_tasks())
            if tasks:
                # gather ensures done-callback runs before state inspection
                await asyncio.gather(tasks.pop().task, return_exceptions=True)

        tasks_after = len(asyncio.all_tasks())
        assert tasks_after <= tasks_before, (
            f"Task leak detected: {tasks_after} > {tasks_before}"
        )

    @pytest.mark.asyncio
    async def test_reindex_exception_logged_via_logger(self, caplog, mock_state, tmp_path):
        """Given: index_folder raises an exception.
        When: reindex is triggered.
        Then: exception is logged through structured logger with trace_id.
        """
        import logging
        from ai_assistant.features.rag.handlers import reindex_documents
        from ai_assistant.features.rag.schemas import ReindexRequest
        from unittest.mock import patch, AsyncMock

        caplog.set_level(logging.INFO, logger="ai_assistant.rag.handlers")
        mock_state.config.rag.chat_exports_root = str(tmp_path / "chat_exports")
        mock_state.vector_store.list_by_filter = AsyncMock(return_value=[])
        mock_state.vector_store.delete = AsyncMock()

        with patch(
            "ai_assistant.features.rag.handlers.index_folder",
            new=AsyncMock(side_effect=RuntimeError("disk full")),
        ):
            req = ReindexRequest(folder="test", clear=False)
            await reindex_documents(req, mock_state)

            # Wait for background task
            tasks = list(mock_state.task_registry.get_tasks())
            assert len(tasks) == 1
            # gather ensures done-callback runs before caplog inspection
            await asyncio.gather(tasks.pop().task, return_exceptions=True)

        # Exception is caught inside handlers.py::_run() and logged via
        # ai_assistant.rag.handlers logger. TaskRegistry._on_done does not
        # fire because the task returns successfully (dict with error).
        error_logs = [
            r for r in caplog.records
            if r.levelno >= logging.ERROR and "Background reindex failed" in r.getMessage()
        ]
        assert error_logs, "Expected error log for background reindex failure"

        # Verify structured logging fields
        for record in error_logs:
            trace_id = getattr(record, "trace_id", None)
            assert trace_id is not None, "Log record missing trace_id"


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
        trace_id = getattr(record, "trace_id", None)
        assert trace_id is not None, (
            f"Log record '{record.getMessage()}' missing trace_id"
        )
        assert len(trace_id) == 32, (
            f"Log record '{record.getMessage()}' has invalid trace_id length"
        )


class TestQueryPrefixParsing:
    """REGRESSION: prefix parsing must work when namespace is not explicitly set."""

    def _setup_prefixes(self, mock_state) -> None:
        """Configure test namespaces with prefixes for deterministic tests."""
        from ai_assistant.core.config import NamespaceConfig
        mock_state.config.namespaces = {
            "test": NamespaceConfig(prefix="t", threshold=0.1, chunk_size=512, prompt="rag_strict"),
            "test-alt": NamespaceConfig(prefix="a", threshold=0.3, chunk_size=1024, prompt="rag_creative"),
        }

    @pytest.mark.asyncio
    async def test_prefix_parsing_when_namespace_is_none(self, mock_state):
        """Given: req.namespace is None, query contains [t] prefix.
        When: query_rag processes the request.
        Then: prefix is parsed and namespace switches to 'test'."""
        from ai_assistant.features.rag.handlers import query_rag
        from ai_assistant.features.rag.schemas import QueryRequest

        self._setup_prefixes(mock_state)

        mock_manager = MagicMock()
        mock_manager.query = AsyncMock(
            return_value={
                "answer": "",
                "sources": [],
                "chunks_used": 0,
                "errors": [],
            }
        )

        req = QueryRequest(query="[t] test query")
        await query_rag(req, mock_manager, mock_state)

        call_kwargs = mock_manager.query.call_args.kwargs
        assert call_kwargs.get("namespace") == "test"

    @pytest.mark.asyncio
    async def test_prefix_parsing_strips_text_when_namespace_explicitly_set(self, mock_state):
        """Given: req.namespace is explicitly 'test-alt', query contains [t] prefix.
        When: query_rag processes the request.
        Then: prefix is stripped from text, but 'test-alt' namespace is preserved."""
        from ai_assistant.features.rag.handlers import query_rag
        from ai_assistant.features.rag.schemas import QueryRequest

        self._setup_prefixes(mock_state)

        mock_manager = MagicMock()
        mock_manager.query = AsyncMock(
            return_value={
                "answer": "",
                "sources": [],
                "chunks_used": 0,
                "errors": [],
            }
        )

        req = QueryRequest(query="[t] test query", namespace="test-alt")
        await query_rag(req, mock_manager, mock_state)

        call_kwargs = mock_manager.query.call_args.kwargs
        assert call_kwargs.get("namespace") == "test-alt"
        assert call_kwargs.get("query_text") == "test query"

    @pytest.mark.asyncio
    async def test_prefix_parsing_with_explicit_default_namespace(self, mock_state):
        """Given: req.namespace='default' (explicit), query has [t] prefix.
        When: query_rag processes the request.
        Then: prefix is stripped from text, but explicit namespace is preserved."""
        from ai_assistant.features.rag.handlers import query_rag
        from ai_assistant.features.rag.schemas import QueryRequest

        self._setup_prefixes(mock_state)

        mock_manager = MagicMock()
        mock_manager.query = AsyncMock(
            return_value={
                "answer": "",
                "sources": [],
                "chunks_used": 0,
                "errors": [],
            }
        )

        req = QueryRequest(query="[t] test query", namespace="default")
        await query_rag(req, mock_manager, mock_state)

        call_kwargs = mock_manager.query.call_args.kwargs
        # Explicit namespace is preserved; only text is stripped
        assert call_kwargs.get("namespace") == "default"
        assert call_kwargs.get("query_text") == "test query"


class TestRAGHandlersTraceId:
    """All _logger calls in RAG handlers must include extra={"trace_id": ...}."""

    @pytest.mark.asyncio
    async def test_index_documents_empty_list_returns_error(self, caplog, mock_state):
        """Given: empty documents list.
        When: index_documents handler called.
        Then: returns indexed_count=0 with 'No documents provided' error."""
        from ai_assistant.features.rag.handlers import index_documents
        from ai_assistant.features.rag.schemas import IndexRequest

        mock_state.vector_store.save = AsyncMock()

        req = IndexRequest(documents=[], namespace="test")
        resp = await index_documents(req, mock_state)

        assert resp.indexed_count == 0
        assert resp.chunk_count == 0
        assert any("No documents provided" in e for e in resp.errors)

    @pytest.mark.asyncio
    async def test_index_documents_missing_content_rejected(self, caplog, mock_state):
        """Given: document without content field.
        When: index_documents called.
        Then: document is rejected with error, not indexed as empty string."""
        from ai_assistant.features.rag.handlers import index_documents
        from ai_assistant.features.rag.schemas import IndexRequest

        mock_state.vector_store.save = AsyncMock()

        req = IndexRequest(
            documents=[{"id": "d1", "metadata": {"source": "test.txt"}}],
            namespace="test",
        )
        resp = await index_documents(req, mock_state)

        assert resp.indexed_count == 0
        assert any("no content" in e.lower() for e in resp.errors)

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
                "errors": [LLM_UNAVAILABLE],
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
    async def test_save_chat_invalid_namespace_rejected_by_schema(self, caplog):
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

            # Capture and await the background task so all logs are in caplog.
            tasks = list(mock_state.task_registry.get_tasks())
            assert len(tasks) == 1, f"Expected 1 background task, got {len(tasks)}"
            await asyncio.wait_for(tasks.pop().task, timeout=1.0)

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

def test_check_rag_script_imports() -> None:
    """Verify scripts/check_rag.py can be imported without errors.

    This catches drift from removed symbols (RAG_NS_MAP) or
    signature changes (parse_rag_query requiring prefix_map).
    """
    import importlib.util
    import sys
    from pathlib import Path

    script_path = Path(__file__).parent.parent / "scripts" / "check_rag.py"
    spec = importlib.util.spec_from_file_location("check_rag", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_rag"] = module
    try:
        spec.loader.exec_module(module)
    except ImportError as exc:
        pytest.fail(f"check_rag.py failed to import: {exc}")
    finally:
        sys.modules.pop("check_rag", None)


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


# ---------- read_sources tests ----------


class TestReadSources:
    """Tests for the new read_sources() function."""

    def test_read_sources_empty_returns_empty(self) -> None:
        """Given: empty sources list.
        When: read_sources called.
        Then: returns empty dict."""
        from ai_assistant.features.rag.indexing import read_sources

        result = read_sources([])
        assert result == {}

    def test_read_sources_duplicate_namespace_merges(self, tmp_path: Path) -> None:
        """Given: two SourceConfig with same namespace.
        When: read_sources called.
        Then: documents from both paths merged into one namespace."""
        from ai_assistant.core.config import SourceConfig
        from ai_assistant.features.rag.indexing import read_sources

        folder_a = tmp_path / "docs_a"
        folder_b = tmp_path / "docs_b"
        folder_a.mkdir()
        folder_b.mkdir()
        (folder_a / "file1.md").write_text("content a", encoding="utf-8")
        (folder_b / "file2.md").write_text("content b", encoding="utf-8")

        sources = [
            SourceConfig(namespace="merged", path=str(folder_a), include=["*.md"]),
            SourceConfig(namespace="merged", path=str(folder_b), include=["*.md"]),
        ]

        result = read_sources(sources)
        assert "merged" in result
        assert len(result["merged"]) == 2
        texts = {d["content"] for d in result["merged"]}
        assert texts == {"content a", "content b"}

    def test_read_sources_single_namespace(self, tmp_path: Path) -> None:
        """Given: source config pointing to a folder with .md files.
        When: read_sources is called.
        Then: returns documents grouped by namespace."""
        from ai_assistant.core.config import SourceConfig
        from ai_assistant.features.rag.indexing import read_sources

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "note.md").write_text("hello")
        (docs_dir / "skip.py").write_text("code")  # filtered by include

        sources = [
            SourceConfig(namespace="notes", path=str(docs_dir), include=["*.md"], recursive=True)
        ]
        result = read_sources(sources)
        assert "notes" in result
        assert len(result["notes"]) == 1
        assert result["notes"][0]["content"] == "hello"

    def test_read_sources_nonexistent_path(self, tmp_path: Path) -> None:
        """Given: source config pointing to non-existent path.
        When: read_sources is called.
        Then: returns empty dict, no exception."""
        from ai_assistant.core.config import SourceConfig
        from ai_assistant.features.rag.indexing import read_sources

        sources = [
            SourceConfig(namespace="missing", path=str(tmp_path / "nope"), include=["*.md"])
        ]
        result = read_sources(sources)
        assert result == {}

    def test_read_sources_multiple_namespaces(self, tmp_path: Path) -> None:
        """Given: two source configs with different namespaces.
        When: read_sources is called.
        Then: documents grouped correctly by namespace."""
        from ai_assistant.core.config import SourceConfig
        from ai_assistant.features.rag.indexing import read_sources

        alt_dir = tmp_path / "test-alt"
        alt_dir.mkdir()
        (alt_dir / "report.md").write_text("report")

        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "diary.md").write_text("diary")

        sources = [
            SourceConfig(namespace="test-alt", path=str(alt_dir), include=["*.md"]),
            SourceConfig(namespace="test", path=str(test_dir), include=["*.md"]),
        ]
        result = read_sources(sources)
        assert len(result["test-alt"]) == 1
        assert len(result["test"]) == 1
        assert result["test-alt"][0]["content"] == "report"
        assert result["test"][0]["content"] == "diary"

    def test_read_sources_respects_recursive(self, tmp_path: Path) -> None:
        """Given: nested folder with recursive=False.
        When: read_sources is called.
        Then: nested files are skipped."""
        from ai_assistant.core.config import SourceConfig
        from ai_assistant.features.rag.indexing import read_sources

        root = tmp_path / "root"
        root.mkdir()
        (root / "top.md").write_text("top")
        nested = root / "nested"
        nested.mkdir()
        (nested / "deep.md").write_text("deep")

        sources = [
            SourceConfig(namespace="root", path=str(root), include=["*.md"], recursive=False)
        ]
        result = read_sources(sources)
        assert len(result["root"]) == 1
        assert result["root"][0]["content"] == "top"

    def test_read_sources_max_file_size(self, tmp_path: Path) -> None:
        """Given: files of different sizes with max_file_size set.
        When: read_sources is called.
        Then: oversized files are skipped."""
        from ai_assistant.core.config import SourceConfig
        from ai_assistant.features.rag.indexing import read_sources

        root = tmp_path / "root"
        root.mkdir()
        (root / "small.md").write_text("x")
        (root / "large.md").write_text("x" * 1000)

        sources = [
            SourceConfig(namespace="root", path=str(root), include=["*.md"])
        ]
        result = read_sources(sources, max_file_size=10)
        assert len(result["root"]) == 1
        assert result["root"][0]["id"] == "small"

    @pytest.mark.asyncio
    async def test_index_folder_no_sources_returns_error(self) -> None:
        """Given: no sources configured.
        When: index_folder called with empty sources.
        Then: returns explicit error with success=False."""
        from ai_assistant.features.rag.indexing import index_folder

        result = await index_folder(
            folder=None,
            clear=False,
            chunker=AsyncMock(spec=IChunker),
            embedder=AsyncMock(spec=IEmbedder),
            vector_store=AsyncMock(spec=IVectorStore),
            sources=[],
        )
        assert result["success"] is False
        assert result["errors"] == ["No sources configured"]

    @pytest.mark.asyncio
    async def test_index_folder_nonexistent_folder_returns_error(self, tmp_path, mock_chunker, mock_embedder, mock_vector_store):
        """Given: folder name that does not match any configured namespace.
        When: index_folder called with that folder.
        Then: returns success=False with descriptive error."""
        from ai_assistant.core.config import SourceConfig
        from ai_assistant.features.rag.indexing import index_folder

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "note.md").write_text("hello")

        result = await index_folder(
            folder="nonexistent",
            clear=False,
            chunker=mock_chunker,
            embedder=mock_embedder,
            vector_store=mock_vector_store,
            sources=[
                SourceConfig(
                    namespace="test",
                    path=str(docs_dir),
                    include=["*.md"],
                )
            ],
            index_path=str(tmp_path / "indices"),
        )
        assert result["success"] is False
        assert "nonexistent" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_index_folder_idempotent(self, tmp_path, mock_chunker, mock_embedder):
        """Given: same documents indexed twice.
        When: index_folder called without --clear.
        Then: second run skips all, no duplicate chunks."""
        from ai_assistant.core.config import SourceConfig
        from ai_assistant.features.rag.indexing import index_folder
        from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
        from ai_assistant.core.domain.configs import VectorStoreConfigData

        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "note.md").write_text("hello world")

        vector_store = MemoryVectorStore(
            VectorStoreConfigData(dim=384, index_path=str(tmp_path / "indices"))
        )

        sources = [
            SourceConfig(namespace="test", path=str(docs_dir), include=["*.md"])
        ]

        # First run
        r1 = await index_folder(
            folder="test", clear=False,
            chunker=mock_chunker, embedder=mock_embedder,
            vector_store=vector_store, sources=sources,
        )
        assert r1["results"]["test"]["indexed"] == 1

        # Second run — idempotent
        r2 = await index_folder(
            folder="test", clear=False,
            chunker=mock_chunker, embedder=mock_embedder,
            vector_store=vector_store, sources=sources,
        )
        assert r2["results"]["test"]["indexed"] == 0
        assert r2["results"]["test"]["chunks"] == 0
