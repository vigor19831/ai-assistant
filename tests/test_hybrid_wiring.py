"""Hybrid wiring tests — stage 4b.

Contracts: init_adapters creates the lexical adapter iff the config
section is present (absent = None = dense-only); RAGManager and
ChatManager pass the leg into the pipeline; the /rag/delete handler
mirrors all three selectors across both stores.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.lexical_bm25 import LexicalBm25Index
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.adapters.reranker_null import NullReranker
from ai_assistant.adapters.storage_sqlite import SQLiteStorage
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.api.deps import InitializedAppState, RAGState, init_adapters
from ai_assistant.core.config import (
    AppConfig,
    LexicalIndexConfig,
    NamespaceConfig,
    RAGStep,
    StorageConfig,
    TokenizerConfig,
)
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    LexicalIndexConfigData,
    LLMConfigData,
    RerankerConfigData,
    StorageConfigData,
    TokenizerConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.task_registry import TaskRegistry
from ai_assistant.features.chat.manager import ChatManager
from ai_assistant.features.rag.handlers import delete_chunks
from ai_assistant.features.rag.manager import RAGManager
from ai_assistant.features.rag.schemas import DeleteRequest


def _chunk(chunk_id: str, text: str, source: str) -> Chunk:
    return Chunk(
        id=chunk_id,
        text=text,
        metadata=ChunkMetadata(
            source=source, index=0, total_chunks=1, source_uri=source
        ),
    )


def _lexical(tmp_path: Path) -> LexicalBm25Index:
    return LexicalBm25Index(
        LexicalIndexConfigData(index_path=str(tmp_path / "lex"))
    )


def _vector_store(tmp_path: Path) -> MemoryVectorStore:
    return MemoryVectorStore(
        VectorStoreConfigData(index_path=str(tmp_path / "vec"))
    )


async def _add_to_store(
    store: MemoryVectorStore, chunks: list[Chunk], namespace: str
) -> None:
    embedder = MockEmbedder(EmbedderConfigData())
    vectors = await embedder.embed([c.text for c in chunks])
    embedded = [
        replace(c, embedding=v) for c, v in zip(chunks, vectors, strict=True)
    ]
    await store.add(embedded, namespace=namespace)


def _handler_state(
    tmp_path: Path,
    lexical: LexicalBm25Index | None,
    vector_store: MemoryVectorStore,
) -> InitializedAppState:
    return InitializedAppState(
        config=AppConfig(
            storage=StorageConfig(db_path=str(tmp_path / "s.db"))
        ),
        task_registry=TaskRegistry(),
        llm=MockLLM(LLMConfigData()),
        embedder=MockEmbedder(EmbedderConfigData()),
        vector_store=vector_store,
        storage=SQLiteStorage(
            StorageConfigData(db_path=str(tmp_path / "s.db"))
        ),
        chunker=SimpleChunker(ChunkerConfigData()),
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        reranker=NullReranker(RerankerConfigData()),
        rag_state=RAGState(),
        lexical_index=lexical,
    )


class TestInitAdaptersLexical:
    """Given: init_adapters with and without a lexical_index section.
    When: adapters initialize.
    Then: the adapter exists iff the section is present."""

    @staticmethod
    async def _shutdown(state: InitializedAppState) -> None:
        for adapter in (
            state.lexical_index,
            state.llm,
            state.embedder,
            state.vector_store,
            state.storage,
            state.reranker,
            state.chunker,
            state.tokenizer,
        ):
            if adapter is not None:
                await adapter.shutdown()

    async def test_section_present_creates_adapter(
        self, tmp_path: Path
    ) -> None:
        config = AppConfig(
            storage=StorageConfig(db_path=str(tmp_path / "storage.db")),
            tokenizer=TokenizerConfig(provider="char_fallback"),
            lexical_index=LexicalIndexConfig(index_path=str(tmp_path / "lex")),
        )
        state = await init_adapters(config)
        try:
            assert isinstance(state.lexical_index, LexicalBm25Index)
            assert state.lexical_index.index_path == str(tmp_path / "lex")
        finally:
            await self._shutdown(state)

    async def test_section_absent_is_none(self, tmp_path: Path) -> None:
        config = AppConfig(
            storage=StorageConfig(db_path=str(tmp_path / "storage.db")),
            tokenizer=TokenizerConfig(provider="char_fallback"),
        )
        state = await init_adapters(config)
        try:
            assert state.lexical_index is None
        finally:
            await self._shutdown(state)


class TestRagManagerLexicalLeg:
    """Given: a RAGManager whose vector store is empty but whose
    lexical index holds a chunk. When: a query runs.
    Then: the lexical leg retrieves it; without the leg — nothing.
    Steps omit generate: no LLM call, deterministic assertion on
    sources."""

    @staticmethod
    def _manager(tmp_path: Path, lexical: LexicalBm25Index | None) -> RAGManager:
        return RAGManager(
            llm=MockLLM(LLMConfigData()),
            vector_store=_vector_store(tmp_path),
            embedder=MockEmbedder(EmbedderConfigData()),
            reranker=NullReranker(RerankerConfigData()),
            lexical_index=lexical,
            rag_steps=[
                RAGStep.EMBED_QUERY,
                RAGStep.RETRIEVE,
                RAGStep.BUILD_CONTEXT,
            ],
        )

    async def test_lexical_only_chunk_is_retrieved(
        self, tmp_path: Path
    ) -> None:
        lexical = _lexical(tmp_path)
        await lexical.add(
            [_chunk("c1", "The Keenetic Extra router was bought", "k.md")],
            namespace="ns",
        )
        result = await self._manager(tmp_path, lexical).query(
            query_text="Keenetic Extra", top_k=5, namespace="ns"
        )
        assert result["chunks_used"] == 1
        assert result["sources"][0]["id"] == "c1"

    async def test_without_leg_nothing_is_retrieved(
        self, tmp_path: Path
    ) -> None:
        result = await self._manager(tmp_path, None).query(
            query_text="Keenetic Extra", top_k=5, namespace="ns"
        )
        assert result["sources"] == []
        assert result["chunks_used"] == 0


class TestChatManagerLexicalLeg:
    """Given: a ChatManager whose vector store is empty but whose
    lexical index holds a chunk. When: a prefixed message arrives.
    Then: the lexical leg feeds the context.

    _retrieve_context is called directly (same direct-helper
    precedent as _sanitize_history tests): it is the retrieval wiring
    point and returns the chunks tuple, avoiding coupling to the
    mock LLM's answer shape.
    """

    async def test_retrieve_context_uses_leg(self, tmp_path: Path) -> None:
        lexical = _lexical(tmp_path)
        await lexical.add(
            [_chunk("c1", "The Keenetic Extra router was bought", "k.md")],
            namespace="default",
        )
        chat = ChatManager(
            llm=MockLLM(LLMConfigData()),
            reranker=NullReranker(RerankerConfigData()),
            embedder=MockEmbedder(EmbedderConfigData()),
            vector_store=_vector_store(tmp_path),
            lexical_index=lexical,
            namespaces={"default": NamespaceConfig(prefix="d")},
            rag_steps=[
                RAGStep.EMBED_QUERY,
                RAGStep.RETRIEVE,
                RAGStep.BUILD_CONTEXT,
            ],
        )
        _prompt, _original, namespace, chunks = await chat._retrieve_context(
            "[d] Keenetic Extra", history=None, trace_id="t"
        )
        assert namespace == "default"
        assert [c.id for c in chunks] == ["c1"]


class TestDeleteHandlerMirror:
    """Given: both stores holding chunks. When: /rag/delete runs.
    Then: all three selectors mirror; each store lists its OWN
    contents (stale ids on one side are caught by that side)."""

    async def test_clear_deletes_both_stores(self, tmp_path: Path) -> None:
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        await _add_to_store(store, [_chunk("c1", "alpha", "a.md")], "ns")
        await lexical.add([_chunk("c1", "alpha", "a.md")], namespace="ns")
        state = _handler_state(tmp_path, lexical, store)
        response = await delete_chunks(
            DeleteRequest(clear=True, namespace="ns"), state
        )
        assert response.deleted_chunks == 1
        assert await store.list_by_filter({}, namespace="ns") == []
        assert await lexical.list_by_filter({}, namespace="ns") == []

    async def test_chunk_ids_delete_both_stores(self, tmp_path: Path) -> None:
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        await _add_to_store(
            store,
            [_chunk("c1", "alpha", "a.md"), _chunk("c2", "beta", "b.md")],
            "ns",
        )
        await lexical.add(
            [_chunk("c1", "alpha", "a.md"), _chunk("c2", "beta", "b.md")],
            namespace="ns",
        )
        state = _handler_state(tmp_path, lexical, store)
        response = await delete_chunks(
            DeleteRequest(chunk_ids=["c1"], namespace="ns"), state
        )
        assert response.deleted_chunks == 1
        assert await lexical.search("beta", namespace="ns")
        remaining = await store.list_by_filter({}, namespace="ns")
        assert [cid for cid, _ in remaining] == ["c2"]

    async def test_document_ids_catch_stale_lexical_ids(
        self, tmp_path: Path
    ) -> None:
        # Crash-between-writes shape (hybrid 4a): the lexical side
        # still holds the OLD chunk id for a.md; only its own listing
        # sees it. A shared vector-computed list would miss it forever.
        lexical = _lexical(tmp_path)
        store = _vector_store(tmp_path)
        await _add_to_store(
            store,
            [_chunk("c2", "new alpha", "a.md"), _chunk("c3", "beta", "b.md")],
            "ns",
        )
        await lexical.add(
            [_chunk("c1", "old alpha", "a.md"), _chunk("c3", "beta", "b.md")],
            namespace="ns",
        )
        state = _handler_state(tmp_path, lexical, store)
        response = await delete_chunks(
            DeleteRequest(document_ids=["a.md"], namespace="ns"), state
        )
        assert response.deleted_chunks == 1
        # a.md gone from BOTH sides (including the stale c1)...
        assert await lexical.search("alpha", namespace="ns") == []
        # ...b.md survives on both.
        assert await lexical.search("beta", namespace="ns")
        remaining = await store.list_by_filter({}, namespace="ns")
        assert [cid for cid, _ in remaining] == ["c3"]
