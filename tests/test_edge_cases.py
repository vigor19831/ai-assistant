"""Edge case and stress tests — Part 1: Data and State.

Covers:
- 12.1 Unicode & Special Characters
- 12.2 Very Long Documents
- 12.4 Empty System State
"""

from __future__ import annotations

import pytest

from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.adapters.reranker_null import NullReranker
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    LLMConfigData,
    RerankerConfigData,
    TokenizerConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.domain.errors import (
    QUERY_EMBEDDING_MISSING,
    QUERY_TEXT_MISSING,
)
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineConfig, PipelineData
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import (
    build_context,
    embed_query,
    generate,
    rerank,
    retrieve,
)
from ai_assistant.core.query_parser import build_prefix_map, parse_rag_query
from ai_assistant.features.chat.manager import ChatManager
from ai_assistant.features.rag.manager import IndexingManager, RAGManager


# ============================================================================
# 12.1 Unicode & Special Characters
# ============================================================================


class TestUnicodeChunker:
    """SimpleChunker must handle any Unicode without corruption."""

    @pytest.fixture
    def chunker(self):
        return SimpleChunker(ChunkerConfigData(chunk_size=50, chunk_overlap=5))

    @pytest.mark.asyncio
    async def test_cyrillic_text(self, chunker):
        """Cyrillic characters must not be split mid-grapheme."""
        text = (
            "Привет, мир! Это тестовый документ на русском языке. "
            "Он содержит несколько предложений для проверки чанкера."
        )
        doc = Document(id="doc-cyr", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) > 0
        # All original text must be present in at least one chunk
        for char in text:
            assert any(char in ch.text for ch in chunks), f"Char {char!r} lost"

    @pytest.mark.asyncio
    async def test_chinese_text(self, chunker):
        """CJK characters must be handled correctly (each char counts)."""
        text = "这是一个中文测试文档。它包含多个句子，用于测试分块器。"
        doc = Document(id="doc-cjk", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) > 0
        for ch in chunks:
            assert len(ch.text) <= chunker.chunk_size

    @pytest.mark.asyncio
    async def test_emoji_and_mixed_scripts(self, chunker):
        """Emoji and mixed scripts must not cause errors."""
        text = (
            "Hello 👋 World 🌍! "
            "こんにちは世界 🗾 "
            "مرحبا بالعالم 🌙 "
            "Привет мир 🪆"
        )
        doc = Document(id="doc-emoji", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) > 0
        # Every original emoji must survive in at least one chunk
        for emoji in ("👋", "🌍", "🗾", "🌙", "🪆"):
            assert any(emoji in ch.text for ch in chunks), f"Emoji {emoji} lost"

    @pytest.mark.asyncio
    async def test_special_characters_in_text(self, chunker):
        """Quotes, backslashes, code snippets must survive chunking."""
        text = (
            'He said: "quoted text" and \\ escaped backslash. '
            "Code: x = y + z; print(\"hello\")"
        )
        doc = Document(id="doc-special", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) > 0
        full = "".join(c.text for c in chunks)
        assert "quoted text" in full
        assert "x = y + z" in full


class TestUnicodeQueryParser:
    """parse_rag_query must handle Unicode prefixes and queries."""

    def test_cyrillic_prefix_query(self):
        """Query with Cyrillic after prefix must parse correctly."""
        prefix_map = {"t": "test", "a": "test-alt"}
        clean, ns = parse_rag_query("[t] Привет мир", prefix_map)
        assert ns == "test"
        assert clean == "Привет мир"

    def test_quoted_text_with_brackets(self):
        """Quoted text containing brackets must not confuse parser."""
        prefix_map = {"t": "test"}
        clean, ns = parse_rag_query(
            '[t] "quoted text with [brackets] inside"', prefix_map
        )
        assert ns == "test"
        assert clean == '"quoted text with [brackets] inside"'

    def test_code_snippet_in_query(self):
        """Code with operators must not break prefix parsing."""
        prefix_map = {"t": "test", "d": "default"}
        clean, ns = parse_rag_query("[d] x = y + z", prefix_map)
        assert ns == "default"
        assert clean == "x = y + z"

    def test_emoji_in_query(self):
        """Emoji in query text must be preserved after prefix strip."""
        prefix_map = {"t": "test"}
        clean, ns = parse_rag_query("[t] Hello 👋 World 🌍", prefix_map)
        assert ns == "test"
        assert "👋" in clean
        assert "🌍" in clean

    def test_no_prefix_unicode_passthrough(self):
        """Unicode without prefix must return (text, None)."""
        prefix_map = {"t": "test"}
        text = "Привет мир без префикса"
        clean, ns = parse_rag_query(text, prefix_map)
        assert ns is None
        assert clean == text


class TestUnicodeMockLLM:
    """MockLLM must echo Unicode input without corruption."""

    @pytest.fixture
    def llm(self):
        return MockLLM(
            LLMConfigData(
                model="mock", api_base="", api_key="", max_tokens=100, temperature=0.7
            )
        )

    @pytest.mark.asyncio
    async def test_cyrillic_echo(self, llm):
        """Cyrillic input must be echoed in response."""
        msg = UserMessage(text="Привет мир")
        resp = await llm.complete([msg])
        assert "Привет мир" in resp.text

    @pytest.mark.asyncio
    async def test_emoji_echo(self, llm):
        """Emoji input must survive round-trip."""
        msg = UserMessage(text="Hello 👋")
        resp = await llm.complete([msg])
        assert "👋" in resp.text

    @pytest.mark.asyncio
    async def test_mixed_scripts_echo(self, llm):
        """Mixed scripts must all be present in echo."""
        msg = UserMessage(text="Hello 你好 Привет")
        resp = await llm.complete([msg])
        assert "Hello" in resp.text
        assert "你好" in resp.text
        assert "Привет" in resp.text


class TestUnicodeEmbedder:
    """MockEmbedder must accept Unicode text without error."""

    @pytest.fixture
    def embedder(self):
        return MockEmbedder(
            EmbedderConfigData(model="mock", dim=384, api_base="", api_key="")
        )

    @pytest.mark.asyncio
    async def test_cyrillic_embedding(self, embedder):
        """Cyrillic text must produce embedding vector."""
        result = await embedder.embed(["Привет мир"])
        assert len(result) == 1
        assert len(result[0]) == 384

    @pytest.mark.asyncio
    async def test_emoji_embedding(self, embedder):
        """Emoji text must produce embedding vector."""
        result = await embedder.embed(["Hello 👋 World 🌍"])
        assert len(result) == 1
        assert len(result[0]) == 384

    @pytest.mark.asyncio
    async def test_mixed_batch_embedding(self, embedder):
        """Batch with mixed scripts must all succeed."""
        texts = ["English", "Русский", "中文", "日本語", "👋🌍"]
        result = await embedder.embed(texts)
        assert len(result) == 5
        for vec in result:
            assert len(vec) == 384


class TestUnicodeVectorStore:
    """MemoryVectorStore must store and retrieve Unicode chunks."""

    @pytest.fixture
    def store(self, tmp_path):
        return MemoryVectorStore(
            VectorStoreConfigData(dim=384, index_path=str(tmp_path / "vs"))
        )

    @pytest.mark.asyncio
    async def test_cyrillic_chunk_storage(self, store):
        """Cyrillic chunk text must survive add/search round-trip."""
        chunk = Chunk(
            id="c1",
            text="Привет мир",
            embedding=[0.1] * 384,
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        await store.add([chunk], namespace="test")
        results = await store.search([0.1] * 384, top_k=1, namespace="test")
        assert len(results) == 1
        assert results[0].text == "Привет мир"

    @pytest.mark.asyncio
    async def test_emoji_chunk_storage(self, store):
        """Emoji chunk text must survive add/search round-trip."""
        chunk = Chunk(
            id="c2",
            text="Hello 👋",
            embedding=[0.2] * 384,
            metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
        )
        await store.add([chunk], namespace="test")
        results = await store.search([0.2] * 384, top_k=1, namespace="test")
        assert len(results) == 1
        assert "👋" in results[0].text


# ============================================================================
# 12.2 Very Long Documents
# ============================================================================


class TestVeryLongDocuments:
    """Chunker must handle documents exceeding chunk_size gracefully."""

    @pytest.fixture
    def chunker(self):
        return SimpleChunker(ChunkerConfigData(chunk_size=512, chunk_overlap=50))

    @pytest.mark.asyncio
    async def test_100k_character_document(self, chunker):
        """100K+ character document must be chunked without overflow."""
        text = "A" * 100_000
        doc = Document(id="doc-100k", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) > 100  # ~100K / 512 ≈ 195 chunks
        # All chunks except possibly last must be <= chunk_size
        for ch in chunks[:-1]:
            assert len(ch.text) <= 512
        # Due to overlap, total reconstructed length > 100K, but every
        # original char must appear in at least one chunk
        full = ""
        for i, c in enumerate(chunks):
            if i == 0:
                full += c.text
            else:
                full += c.text[chunker.chunk_overlap:]
        assert len(full) >= 100_000
        for char in set(text):
            assert any(char in ch.text for ch in chunks), f"Char {char!r} lost"

    @pytest.mark.asyncio
    async def test_single_chunk_exceeds_chunk_size(self, chunker):
        """Document with one long word > chunk_size must still chunk."""
        text = "A" * 600  # single "word" exceeding chunk_size
        doc = Document(id="doc-long-word", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) >= 1
        # The long word must be split across chunks
        all_text = "".join(c.text for c in chunks)
        assert "A" * 600 in all_text

    @pytest.mark.asyncio
    async def test_overlap_logic_preserves_content(self, chunker):
        """Overlap must not lose content at chunk boundaries."""
        # Create text where boundary content is identifiable
        parts = [f"SECTION_{i:03d}_" + "x" * 400 for i in range(10)]
        text = "".join(parts)
        doc = Document(id="doc-overlap", content=text)
        chunks = await chunker.chunk(doc)
        # Every section marker must appear in at least one chunk
        for i in range(10):
            marker = f"SECTION_{i:03d}_"
            assert any(marker in c.text for c in chunks), f"Marker {marker} lost"

    @pytest.mark.asyncio
    async def test_chunk_count_metadata(self, chunker):
        """total_chunks metadata must reflect actual chunk count."""
        text = "word " * 500  # ~2500 chars -> ~5-6 chunks
        doc = Document(id="doc-meta", content=text)
        chunks = await chunker.chunk(doc)
        assert len(chunks) > 1
        for ch in chunks:
            assert ch.metadata is not None
            assert ch.metadata.total_chunks == len(chunks)


# ============================================================================
# 12.4 Empty System State
# ============================================================================


class TestEmptySystemState:
    """Fresh install with no indices or documents must degrade gracefully."""

    @pytest.fixture
    def fresh_store(self, tmp_path):
        """Return a MemoryVectorStore with empty temp directory."""
        return MemoryVectorStore(
            VectorStoreConfigData(dim=384, index_path=str(tmp_path / "fresh"))
        )

    @pytest.fixture
    def fresh_rag_manager(self, fresh_store):
        """Return RAGManager with empty store and minimal deps."""
        llm = MockLLM(
            LLMConfigData(
                model="mock", api_base="", api_key="", max_tokens=100, temperature=0.7
            )
        )
        embedder = MockEmbedder(
            EmbedderConfigData(model="mock", dim=384, api_base="", api_key="")
        )
        reranker = NullReranker(RerankerConfigData())
        tokenizer = CharFallbackTokenizer(TokenizerConfigData())
        return RAGManager(
            llm=llm,
            vector_store=fresh_store,
            embedder=embedder,
            reranker=reranker,
            tokenizer=tokenizer,
        )

    @pytest.mark.asyncio
    async def test_health_returns_zero_chunks(self, fresh_rag_manager):
        """Health check on fresh system must report chunk_count=0."""
        health = await fresh_rag_manager.health()
        assert health["chunk_count"] == 0
        assert health["index_loaded"] is False
        assert health["status"] == "empty"

    @pytest.mark.asyncio
    async def test_query_empty_store_returns_no_info(self, fresh_rag_manager):
        """Query on empty store returns response from LLM general knowledge."""
        result = await fresh_rag_manager.query(
            query_text="What is AI?",
            top_k=5,
            namespace="default",
        )
        assert result["chunks_used"] == 0
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_search_empty_namespace_returns_empty(self, fresh_store):
        """Search on empty namespace must return empty list, not crash."""
        results = await fresh_store.search(
            query_embedding=[0.1] * 384,
            top_k=5,
            namespace="default",
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_list_namespaces_empty_path(self, fresh_store, tmp_path):
        """list_namespaces on non-existent path must return empty list."""
        namespaces = await fresh_store.list_namespaces(str(tmp_path / "does_not_exist"))
        assert namespaces == []

    @pytest.mark.asyncio
    async def test_list_by_filter_empty_namespace(self, fresh_store):
        """list_by_filter on empty namespace must return empty list."""
        results = await fresh_store.list_by_filter({}, namespace="default")
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_from_empty_namespace_no_crash(self, fresh_store):
        """Delete from empty namespace must not raise."""
        await fresh_store.delete(["non-existent-id"], namespace="default")
        # If we get here without exception, test passes

    @pytest.mark.asyncio
    async def test_pipeline_steps_on_empty_data(self, fresh_store):
        """Individual pipeline steps must handle empty data gracefully."""
        embedder = MockEmbedder(
            EmbedderConfigData(model="mock", dim=384, api_base="", api_key="")
        )
        llm = MockLLM(
            LLMConfigData(
                model="mock", api_base="", api_key="", max_tokens=100, temperature=0.7
            )
        )
        tokenizer = CharFallbackTokenizer(TokenizerConfigData())
        reranker = NullReranker(RerankerConfigData())

        cfg = PipelineConfig(
            top_k=5,
            namespace="default",
            threshold=0.3,
        )

        # embed_query on empty text
        data = PipelineData(
            query=UserMessage(text=""),
            embedder=embedder,
            pipeline_config=cfg,
        )
        result = await embed_query(data)
        assert QUERY_TEXT_MISSING in result.errors

        # retrieve with no embedding
        data2 = PipelineData(
            query=UserMessage(text="test"),
            vector_store=fresh_store,
            pipeline_config=cfg,
        )
        result2 = await retrieve(data2)
        assert QUERY_EMBEDDING_MISSING in result2.errors

        # build_context with empty chunks
        data3 = PipelineData(chunks=(), pipeline_config=cfg)
        result3 = await build_context(data3)
        assert result3.context == ""

        # generate with empty context (should return non-empty response)
        data4 = PipelineData(
            query=UserMessage(text="What is AI?"),
            llm=llm,
            pipeline_config=cfg,
            tokenizer=tokenizer,
        )
        result4 = await generate(data4)
        assert result4.response is not None
        assert isinstance(result4.response.text, str)
        assert len(result4.response.text) > 0

    @pytest.mark.asyncio
    async def test_indexing_manager_empty_documents(self, fresh_store):
        """Indexing empty documents must return zero counts."""
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=100, chunk_overlap=0))
        embedder = MockEmbedder(
            EmbedderConfigData(model="mock", dim=384, api_base="", api_key="")
        )
        manager = IndexingManager(
            chunker=chunker,
            embedder=embedder,
            vector_store=fresh_store,
        )
        result = await manager.index_documents([], namespace="default")
        assert result["indexed_count"] == 0
        assert result["chunk_count"] == 0

    @pytest.mark.asyncio
    async def test_chat_manager_no_rag_prefix_routes_to_llm(self):
        """Chat without RAG prefix on empty system must route directly to LLM."""
        llm = MockLLM(
            LLMConfigData(
                model="mock", api_base="", api_key="", max_tokens=100, temperature=0.7
            )
        )
        reranker = NullReranker(RerankerConfigData())
        manager = ChatManager(
            llm=llm,
            reranker=reranker,
            embedder=None,
            vector_store=None,
        )
        response = await manager.chat(
            message="Hello without prefix",
            conversation_id="test-conv",
        )
        assert "[MOCK LLM] Echo:" in response.text


# ============================================================================
# Integration: Unicode through full pipeline
# ============================================================================


class TestUnicodeFullPipeline:
    """Unicode content must survive full RAG pipeline."""

    @pytest.mark.asyncio
    async def test_cyrillic_document_query(self, tmp_path):
        """Index Cyrillic document, query in Cyrillic, get coherent response."""
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=384, index_path=str(tmp_path / "vs"))
        )
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=100, chunk_overlap=10))
        embedder = MockEmbedder(
            EmbedderConfigData(model="mock", dim=384, api_base="", api_key="")
        )
        llm = MockLLM(
            LLMConfigData(
                model="mock", api_base="", api_key="", max_tokens=100, temperature=0.7
            )
        )
        reranker = NullReranker(RerankerConfigData())

        # Index a Cyrillic document
        indexer = IndexingManager(
            chunker=chunker,
            embedder=embedder,
            vector_store=store,
        )
        await indexer.index_documents(
            [
                {
                    "id": "doc-ru",
                    "content": (
                        "Искусственный интеллект — это область компьютерных наук, "
                        "занимающаяся созданием систем, способных выполнять задачи, "
                        "требующие человеческого интеллекта."
                    ),
                    "metadata": {},
                }
            ],
            namespace="default",
        )

        # Query in Cyrillic
        tokenizer = CharFallbackTokenizer(TokenizerConfigData())
        rag = RAGManager(
            llm=llm,
            vector_store=store,
            embedder=embedder,
            reranker=reranker,
            tokenizer=tokenizer,
        )
        result = await rag.query(
            query_text="Что такое искусственный интеллект?",
            namespace="default",
        )
        # Should not crash; should return some response
        assert "answer" in result
        assert result["chunks_used"] >= 0

    @pytest.mark.asyncio
    async def test_emoji_document_query(self, tmp_path):
        """Index document with emoji, query with emoji, pipeline must complete."""
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=384, index_path=str(tmp_path / "vs"))
        )
        chunker = SimpleChunker(ChunkerConfigData(chunk_size=50, chunk_overlap=5))
        embedder = MockEmbedder(
            EmbedderConfigData(model="mock", dim=384, api_base="", api_key="")
        )
        llm = MockLLM(
            LLMConfigData(
                model="mock", api_base="", api_key="", max_tokens=100, temperature=0.7
            )
        )
        reranker = NullReranker(RerankerConfigData())

        indexer = IndexingManager(
            chunker=chunker,
            embedder=embedder,
            vector_store=store,
        )
        await indexer.index_documents(
            [{"id": "doc-emoji", "content": "Hello 👋 World 🌍! AI is great 🚀.", "metadata": {}}],
            namespace="default",
        )

        tokenizer = CharFallbackTokenizer(TokenizerConfigData())
        rag = RAGManager(
            llm=llm,
            vector_store=store,
            embedder=embedder,
            reranker=reranker,
            tokenizer=tokenizer,
        )
        result = await rag.query(
            query_text="Tell me about AI 👋",
            namespace="default",
        )
        assert "answer" in result
        assert isinstance(result["answer"], str)
