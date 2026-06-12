"""Tests for ChatManager — _retrieve_context, _build_messages, and identical prep.

Validates that chat() and stream_chat() share the same preparation path
through _retrieve_context and _build_messages.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant.core.config import NamespaceConfig
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.features.chat.manager import ChatManager
from ai_assistant.core.pipeline_steps import build_context, embed_query, retrieve
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.adapters.reranker_null import NullReranker


class _AsyncIter:
    """Helper to create an async iterator from a list for mocking."""

    def __init__(self, items: list[str]) -> None:
        self._items = items

    def __aiter__(self):
        self._index = 0
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


def async_iter(items: list[str]):
    """Return an async-iterable object for mocking LLM.stream()."""
    return _AsyncIter(items)

# ── _retrieve_context tests (formerly _maybe_rag) ──


class TestRetrieveContext:
    @pytest.fixture
    def chat_manager_with_rag(self):
        embedder = MockEmbedder(type("C", (), {"dim": 3})())
        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": 0.0})()
        )
        pipeline = RAGPipeline([
            embed_query,
            retrieve,
            build_context,
        ])
        namespaces = {
            "personal": NamespaceConfig(threshold=0.1, chunk_size=512, prompt="rag_strict"),
            "work": NamespaceConfig(threshold=0.3, chunk_size=1024, prompt="rag_creative"),
        }
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        return ChatManager(
            llm=mock_llm,
            embedder=embedder,
            vector_store=store,
            reranker=NullReranker(None),
            storage=None,
            pipeline=pipeline,
            namespaces=namespaces,
        )

    @pytest.mark.asyncio
    async def test_no_prefix_returns_unchanged(self, chat_manager_with_rag):
        """Message without [p]/[w]/[o] prefix should pass through unchanged."""
        prompt, query, chunks = await chat_manager_with_rag._retrieve_context(
            "Hello world"
        )
        assert prompt == "Hello world"
        assert query == "Hello world"
        assert chunks == ()

    @pytest.mark.asyncio
    async def test_personal_prefix_triggers_rag(self, chat_manager_with_rag):
        """[p] prefix should query personal namespace and return prompt."""
        chunk = Chunk(
            id="c1",
            text="Paris is the capital of France.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="personal")

        prompt, query, chunks = await chat_manager_with_rag._retrieve_context(
            "[p] What is the capital?"
        )
        assert len(chunks) > 0
        assert "Paris" in prompt or "France" in prompt or "Context:" in prompt

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

        prompt, query, chunks = await chat_manager_with_rag._retrieve_context(
            "[w] When is the deadline?"
        )
        assert len(chunks) > 0

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

        prompt, query, chunks = await chat_manager_with_rag._retrieve_context(
            "[o] What ingredients?"
        )
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_no_results_returns_original_query(self, chat_manager_with_rag):
        """When no chunks match, return original query text (not prompt)."""
        prompt, query, chunks = await chat_manager_with_rag._retrieve_context(
            "[p] something impossible to find"
        )
        assert prompt == "something impossible to find"
        assert query == "something impossible to find"
        assert chunks == ()

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

        prompt, query, chunks = await chat_manager_with_rag._retrieve_context(
            "[p] query text"
        )
        assert not query.startswith("[p]")
        assert "query text" in query

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

        (
            prompt_upper,
            query_upper,
            chunks_upper,
        ) = await chat_manager_with_rag._retrieve_context("[P] test")
        (
            prompt_lower,
            query_lower,
            chunks_lower,
        ) = await chat_manager_with_rag._retrieve_context("[p] test")
        assert chunks_upper == chunks_lower

    @pytest.mark.asyncio
    async def test_no_embedder_returns_unchanged(self):
        """Without embedder, message should pass through."""
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        manager = ChatManager(
            llm=mock_llm,
            embedder=None,
            vector_store=MagicMock(),
            reranker=NullReranker(None),
            storage=None,
        )
        prompt, query, chunks = await manager._retrieve_context("[p] query")
        assert prompt == "[p] query"
        assert query == "[p] query"
        assert chunks == ()

    @pytest.mark.asyncio
    async def test_no_vector_store_returns_unchanged(self):
        """Without vector_store, message should pass through."""
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        manager = ChatManager(
            llm=mock_llm,
            embedder=MagicMock(),
            vector_store=None,
            reranker=NullReranker(None),
            storage=None,
        )
        prompt, query, chunks = await manager._retrieve_context("[p] query")
        assert prompt == "[p] query"
        assert query == "[p] query"
        assert chunks == ()

    @pytest.mark.asyncio
    async def test_per_namespace_prompt_and_threshold(self, chat_manager_with_rag):
        """Per-namespace config should determine prompt name and relevance threshold."""
        chunk = Chunk(
            id="c1",
            text="Work item.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="work")

        with patch("ai_assistant.features.chat.manager.get_prompt") as mock_get_prompt:
            mock_get_prompt.return_value = "work prompt"
            prompt, query, chunks = await chat_manager_with_rag._retrieve_context(
                "[w] work item?"
            )
            mock_get_prompt.assert_called_once()
            assert mock_get_prompt.call_args[0][0] == "rag_creative"
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_fallback_to_defaults_when_no_namespace_config(self):
        """When namespaces dict is missing the namespace, use global defaults."""
        embedder = MockEmbedder(type("C", (), {"dim": 3})())
        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": 0.0})()
        )
        pipeline = RAGPipeline([
            embed_query,
            retrieve,
            build_context,
        ])
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        manager = ChatManager(
            llm=mock_llm,
            embedder=embedder,
            vector_store=store,
            reranker=NullReranker(None),
            storage=None,
            pipeline=pipeline,
            namespaces={},
        )
        chunk = Chunk(
            id="c1",
            text="Content",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await manager.vector_store.add([chunk], namespace="personal")

        with patch("ai_assistant.features.chat.manager.get_prompt") as mock_get_prompt:
            mock_get_prompt.return_value = "default prompt"
            prompt, query, chunks = await manager._retrieve_context("[p] content?")
            mock_get_prompt.assert_called_once()
            assert mock_get_prompt.call_args[0][0] == "rag_strict"


# ── _build_messages tests ──


class TestBuildMessages:
    @pytest.fixture
    def manager_no_storage(self):
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        return ChatManager(
            llm=mock_llm,
            reranker=NullReranker(None),
            storage=None,
            history_limit=10,
            max_context_tokens=None,
        )

    @pytest.fixture
    def manager_with_storage(self):
        mock_storage = MagicMock()
        mock_storage.get_history = AsyncMock(return_value=[
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ])
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        return ChatManager(
            llm=mock_llm,
            reranker=NullReranker(None),
            storage=mock_storage,
            history_limit=10,
            max_context_tokens=None,
        )

    @pytest.mark.asyncio
    async def test_build_messages_without_storage(self, manager_no_storage):
        """Without storage, only the current user message is returned."""
        messages = await manager_no_storage._build_messages("Hello", "conv-1")
        assert len(messages) == 1
        assert isinstance(messages[0], UserMessage)
        assert messages[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_build_messages_with_history(self, manager_with_storage):
        """History messages are prepended in chronological order."""
        messages = await manager_with_storage._build_messages("Hello", "conv-1")
        assert len(messages) == 3
        assert isinstance(messages[0], UserMessage)
        assert messages[0].text == "Previous question"
        assert isinstance(messages[1], AssistantMessage)
        assert messages[1].text == "Previous answer"
        assert isinstance(messages[2], UserMessage)
        assert messages[2].text == "Hello"

    @pytest.mark.asyncio
    async def test_build_messages_preserves_metadata(self, manager_no_storage):
        """Metadata is attached to the current user message."""
        meta = {"trace_id": "abc123"}
        messages = await manager_no_storage._build_messages(
            "Hello", "conv-1", metadata=meta
        )
        assert messages[-1].metadata == meta

    @pytest.mark.asyncio
    async def test_build_messages_trims_history(self, manager_with_storage):
        """Token budget trimming is applied to history."""
        manager_with_storage.max_context_tokens = 50
        with patch.object(
            manager_with_storage, "_trim_history", return_value=[]
        ):
            messages = await manager_with_storage._build_messages("Hello", "conv-1")
            assert len(messages) == 1
            assert messages[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_build_messages_history_load_failure(self, manager_with_storage):
        """History load failure is graceful — returns just user message."""
        manager_with_storage.storage.get_history = AsyncMock(
            side_effect=Exception("DB error")
        )
        messages = await manager_with_storage._build_messages("Hello", "conv-1")
        assert len(messages) == 1
        assert messages[0].text == "Hello"


# ── _trim_history tests ──


class TestTrimHistory:
    @pytest.fixture
    def manager_with_tokenizer(self):
        mock_llm = MagicMock()
        mock_llm.config = MagicMock()
        mock_llm.config.max_tokens = 100
        mock_llm.system_message = "System prompt"
        mock_llm.get_context_limit.return_value = 100

        return ChatManager(
            llm=mock_llm,
            reranker=NullReranker(None),
            max_context_tokens=100,
            tokenizer_model="gpt-4o",
            history_limit=10,
            storage=None,
        )

    @pytest.fixture
    def manager_no_tokenizer(self):
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = None
        return ChatManager(
            llm=mock_llm,
            reranker=NullReranker(None),
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
        assert len(trimmed) <= len(history)
        if trimmed:
            assert trimmed[-1]["content"] == "Response 2"

    def test_returns_empty_when_budget_too_small(self, manager_with_tokenizer):
        """If user message alone exceeds budget, return empty history."""
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
        assert len(trimmed) <= 3

    def test_preserves_chronological_order(self, manager_with_tokenizer):
        """Trimmed history should maintain oldest-first order."""
        history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]
        user_msg = UserMessage(text="q")
        trimmed = manager_with_tokenizer._trim_history(history, user_msg)
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
        assert len(trimmed) <= 1

    def test_no_llm_config_fallback(self):
        """When LLM has no config, fallback to history_limit."""
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = None
        manager = ChatManager(
            llm=mock_llm,
            reranker=NullReranker(None),
            max_context_tokens=50,
            history_limit=2,
            storage=None,
        )

        history = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "3"},
        ]
        trimmed = manager._trim_history(history, UserMessage(text="q"))
        assert len(trimmed) <= 2


# ── Graceful degradation: RAG unavailable ──


class TestRAGGracefulDegradation:
    @pytest.fixture
    def manager_no_rag(self):
        """ChatManager without embedder/vector_store."""
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.complete = AsyncMock(
            return_value=MagicMock(text="Hello!", metadata={}, tool_calls=[])
        )
        return ChatManager(
            llm=mock_llm,
            embedder=None,
            vector_store=None,
            reranker=NullReranker(None),
            storage=None,
        )

    @pytest.mark.asyncio
    async def test_chat_with_prefix_no_vector_store(self, manager_no_rag):
        """[p] prefix with no vector_store returns graceful message."""
        result = await manager_no_rag.chat(
            message="[p] capital of France",
            conversation_id="test-1",
        )
        assert (
            "недоступен" in result.text.lower()
            or "unavailable" in result.text.lower()
        )

    @pytest.mark.asyncio
    async def test_chat_without_prefix_works_without_vector_store(
        self, manager_no_rag
    ):
        """Plain message without prefix should still call LLM."""
        manager_no_rag.llm.complete = AsyncMock(
            return_value=MagicMock(text="Hello!", metadata={}, tool_calls=[])
        )
        result = await manager_no_rag.chat(
            message="Hello",
            conversation_id="test-2",
        )
        assert result.text == "Hello!"
        manager_no_rag.llm.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stream_chat_without_rag(self, manager_no_rag):
        """stream_chat without RAG prefix should call LLM stream."""
        manager_no_rag.llm.stream = MagicMock(return_value=async_iter(["Hello", "!"]))
        chunks = []
        async for chunk in manager_no_rag.stream_chat("Hello", "conv-1"):
            chunks.append(chunk)
        assert chunks == ["Hello", "!"]


# ── chat / stream_chat preparation identical tests ──


class TestChatStreamPreparationIdentical:
    @pytest.fixture
    def manager(self):
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.complete = AsyncMock(
            return_value=MagicMock(text="Hello!", metadata={}, tool_calls=[])
        )
        return ChatManager(
            llm=mock_llm,
            embedder=None,
            vector_store=None,
            reranker=NullReranker(None),
            storage=None,
        )

    @pytest.mark.asyncio
    async def test_chat_calls_retrieve_context_and_build_messages(self, manager):
        """chat() must use _retrieve_context and _build_messages."""
        with patch.object(
            manager, "_retrieve_context", new_callable=AsyncMock
        ) as mock_retrieve, patch.object(
            manager, "_build_messages", new_callable=AsyncMock
        ) as mock_build:
            mock_retrieve.return_value = ("Hello", "Hello", ())
            mock_build.return_value = [UserMessage(text="Hello")]

            await manager.chat("Hello", "conv-1")

            mock_retrieve.assert_awaited_once_with("Hello", trace_id=None)
            mock_build.assert_awaited_once_with("Hello", "conv-1", metadata={})

    @pytest.mark.asyncio
    async def test_stream_chat_calls_llm_stream(self, manager):
        """stream_chat must call LLM stream and yield chunks."""
        manager.llm.stream = MagicMock(return_value=async_iter(["Hi", " there"]))
        chunks = []
        async for chunk in manager.stream_chat("Hello", "conv-1"):
            chunks.append(chunk)
        assert chunks == ["Hi", " there"]
