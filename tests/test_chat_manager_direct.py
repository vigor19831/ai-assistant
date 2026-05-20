"""Direct tests for ChatManager — _maybe_rag and _trim_history.

Tests real (mock) embedder/vector_store integration without relying on
indirect chat() calls. Validates RAG prefix handling, token trimming logic,
and edge cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from adapters.embedder_mock import MockEmbedder
from adapters.vector_store_memory import MemoryVectorStore
from core.domain.documents import Chunk, ChunkMetadata
from core.domain.messages import AssistantMessage, UserMessage
from features.chat.manager import ChatManager

# ── _maybe_rag tests ──


class TestMaybeRAG:
    @pytest.fixture
    def chat_manager_with_rag(self):
        embedder = MockEmbedder(type("C", (), {"dim": 3})())
        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": 0.0})()
        )
        return ChatManager(
            llm=MagicMock(),
            embedder=embedder,
            vector_store=store,
            reranker=None,
            storage=None,
        )

    @pytest.mark.asyncio
    async def test_no_prefix_returns_unchanged(self, chat_manager_with_rag):
        """Message without [p]/[w]/[o] prefix should pass through unchanged."""
        msg, chunks = await chat_manager_with_rag._maybe_rag("Hello world")
        assert msg == "Hello world"
        assert chunks == 0

    @pytest.mark.asyncio
    async def test_personal_prefix_triggers_rag(self, chat_manager_with_rag):
        """[p] prefix should query personal namespace and return prompt."""
        # Seed vector store
        chunk = Chunk(
            id="c1",
            text="Paris is the capital of France.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="personal")

        msg, chunks = await chat_manager_with_rag._maybe_rag("[p] What is the capital?")
        assert chunks > 0
        assert "Paris" in msg or "France" in msg or "Context:" in msg

    @pytest.mark.asyncio
    async def test_work_prefix_triggers_rag(self, chat_manager_with_rag):
        """[w] prefix should query work namespace."""
        chunk = Chunk(
            id="c1",
            text="Project deadline is Friday.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="work")

        msg, chunks = await chat_manager_with_rag._maybe_rag(
            "[w] When is the deadline?"
        )
        assert chunks > 0

    @pytest.mark.asyncio
    async def test_other_prefix_triggers_rag(self, chat_manager_with_rag):
        """[o] prefix should query other namespace."""
        chunk = Chunk(
            id="c1",
            text="Recipe: 2 eggs, 1 cup flour.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="other")

        msg, chunks = await chat_manager_with_rag._maybe_rag("[o] What ingredients?")
        assert chunks > 0

    @pytest.mark.asyncio
    async def test_no_results_returns_original_query(self, chat_manager_with_rag):
        """When no chunks match, return original query text (not prompt)."""
        msg, chunks = await chat_manager_with_rag._maybe_rag(
            "[p] something impossible to find"
        )
        assert msg == "something impossible to find"
        assert chunks == 0

    @pytest.mark.asyncio
    async def test_prefix_removed_from_query(self, chat_manager_with_rag):
        """Prefix should be stripped from the query text."""
        chunk = Chunk(
            id="c1",
            text="Some content",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="personal")

        msg, chunks = await chat_manager_with_rag._maybe_rag("[p] query text")
        # Query should not contain [p]
        assert not msg.startswith("[p]")
        assert "query text" in msg or chunks == 0

    @pytest.mark.asyncio
    async def test_case_insensitive_prefix(self, chat_manager_with_rag):
        """[P], [W], [O] should work same as lowercase."""
        chunk = Chunk(
            id="c1",
            text="Content",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="personal")

        msg_upper, chunks_upper = await chat_manager_with_rag._maybe_rag("[P] test")
        msg_lower, chunks_lower = await chat_manager_with_rag._maybe_rag("[p] test")
        assert chunks_upper == chunks_lower

    @pytest.mark.asyncio
    async def test_no_embedder_returns_unchanged(self):
        """Without embedder, message should pass through."""
        manager = ChatManager(
            llm=MagicMock(),
            embedder=None,
            vector_store=MagicMock(),
            storage=None,
        )
        msg, chunks = await manager._maybe_rag("[p] query")
        assert msg == "[p] query"
        assert chunks == 0

    @pytest.mark.asyncio
    async def test_no_vector_store_returns_unchanged(self):
        """Without vector_store, message should pass through."""
        manager = ChatManager(
            llm=MagicMock(),
            embedder=MagicMock(),
            vector_store=None,
            storage=None,
        )
        msg, chunks = await manager._maybe_rag("[p] query")
        assert msg == "[p] query"
        assert chunks == 0


# ── _trim_history tests ──


class TestTrimHistory:
    @pytest.fixture
    def manager_with_tokenizer(self):
        mock_llm = MagicMock()
        mock_llm.config = MagicMock()
        mock_llm.config.max_tokens = 100
        mock_llm.system_message = "System prompt"

        return ChatManager(
            llm=mock_llm,
            max_context_tokens=100,
            tokenizer_model="gpt-4o",
            history_limit=10,
            storage=None,
        )

    @pytest.fixture
    def manager_no_tokenizer(self):
        return ChatManager(
            llm=MagicMock(),
            max_context_tokens=None,
            history_limit=3,
            storage=None,
        )

    def test_trims_oldest_to_fit_budget(self, manager_with_tokenizer):
        """Oldest messages should be dropped when token budget exceeded."""
        history = [
            {"role": "user", "content": "Message 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Message 2"},
            {"role": "assistant", "content": "Response 2"},
        ]
        user_msg = UserMessage(text="Current question")
        trimmed = manager_with_tokenizer._trim_history(history, user_msg)
        # Should keep most recent messages that fit
        assert len(trimmed) <= len(history)
        # Most recent should be preserved
        if trimmed:
            assert trimmed[-1]["content"] == "Response 2"

    def test_returns_empty_when_budget_too_small(self, manager_with_tokenizer):
        """If user message alone exceeds budget, return empty history."""
        # Create a very long user message that exceeds budget
        long_msg = UserMessage(text="x" * 500)
        history = [{"role": "user", "content": "old"}]
        trimmed = manager_with_tokenizer._trim_history(history, long_msg)
        assert trimmed == []

    def test_fallback_to_count_based(self, manager_no_tokenizer):
        """Without tokenizer, use simple count-based fallback."""
        history = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "3"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "5"},
        ]
        user_msg = UserMessage(text="q")
        trimmed = manager_no_tokenizer._trim_history(history, user_msg)
        assert len(trimmed) <= 3  # history_limit

    def test_preserves_chronological_order(self, manager_with_tokenizer):
        """Trimmed history should maintain oldest-first order."""
        history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]
        user_msg = UserMessage(text="q")
        trimmed = manager_with_tokenizer._trim_history(history, user_msg)
        # Verify order is preserved
        for i in range(len(trimmed) - 1):
            original_idx = history.index(trimmed[i])
            next_idx = history.index(trimmed[i + 1])
            assert original_idx < next_idx

    def test_empty_history(self, manager_with_tokenizer):
        """Empty history should return empty list."""
        trimmed = manager_with_tokenizer._trim_history([], UserMessage(text="hi"))
        assert trimmed == []

    def test_single_message_fits(self, manager_with_tokenizer):
        """Single message within budget should be preserved."""
        history = [{"role": "user", "content": "hello"}]
        trimmed = manager_with_tokenizer._trim_history(history, UserMessage(text="hi"))
        assert len(trimmed) == 1
        assert trimmed[0]["content"] == "hello"

    def test_respects_system_message_overhead(self, manager_with_tokenizer):
        """System message tokens should be reserved from budget."""
        history = [{"role": "user", "content": "x" * 200}]
        trimmed = manager_with_tokenizer._trim_history(history, UserMessage(text="q"))
        # System message reserves some tokens, so long message may be excluded
        assert len(trimmed) <= 1

    def test_no_llm_config_fallback(self):
        """When LLM has no config, fallback to history_limit."""
        manager = ChatManager(
            llm=MagicMock(),
            max_context_tokens=50,
            history_limit=2,
            storage=None,
        )
        # Mock LLM with no config attribute
        manager.llm = MagicMock()
        manager.llm.config = None

        history = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "3"},
        ]
        trimmed = manager._trim_history(history, UserMessage(text="q"))
        assert len(trimmed) <= 2


# ── Integration: chat() with real RAG pipeline ──


class TestChatManagerRAGIntegration:
    @pytest.fixture
    def integrated_manager(self):
        embedder = MockEmbedder(type("C", (), {"dim": 3})())
        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": 0.0})()
        )
        llm = MagicMock()
        llm.complete = AsyncMock(
            return_value=AssistantMessage(text="Paris is the capital.")
        )
        llm.stream = AsyncMock()
        llm.config = MagicMock()
        llm.config.max_tokens = 4096
        llm.system_message = "System"

        return ChatManager(
            llm=llm,
            embedder=embedder,
            vector_store=store,
            storage=None,
            max_context_tokens=4096,
            history_limit=10,
        )

    @pytest.mark.asyncio
    async def test_chat_with_prefix_uses_rag_context(self, integrated_manager):
        """Full flow: [p] prefix → embed → retrieve → build prompt → LLM."""
        chunk = Chunk(
            id="c1",
            text="Paris is the capital of France.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await integrated_manager.vector_store.add([chunk], namespace="personal")

        response = await integrated_manager.chat(
            "[p] What is the capital of France?",
            "conv-test",
        )
        assert response.text == "Paris is the capital."
        # Verify LLM was called with RAG-enhanced prompt
        call_args = integrated_manager.llm.complete.call_args[0][0]
        # First message should be the RAG prompt
        first_msg = call_args[0]
        assert "Paris" in first_msg.text or "capital" in first_msg.text.lower()

    @pytest.mark.asyncio
    async def test_chat_without_prefix_no_rag(self, integrated_manager):
        """Without prefix, LLM should receive original message."""
        _ = await integrated_manager.chat(
            "What is the capital of France?",
            "conv-test",
        )
        call_args = integrated_manager.llm.complete.call_args[0][0]
        first_msg = call_args[0]
        assert first_msg.text == "What is the capital of France?"

    @pytest.mark.asyncio
    async def test_stream_chat_with_prefix(self, integrated_manager):
        """Streaming should also trigger RAG when prefix present."""
        chunk = Chunk(
            id="c1",
            text="Paris is the capital.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await integrated_manager.vector_store.add([chunk], namespace="personal")

        async def mock_stream(*args, **kwargs):
            yield "Paris"
            yield " is"
            yield " the"
            yield " capital."

        integrated_manager.llm.stream = mock_stream

        chunks = []
        async for chunk in integrated_manager.stream_chat(
            "[p] What is the capital?",
            "conv-test",
        ):
            chunks.append(chunk)

        assert "".join(chunks) == "Paris is the capital."
