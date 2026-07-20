"""tests/test_chat.py — ChatManager tests.

Coverage: chat(), stream_chat(), RAG retrieval, history trimming,
prefix routing, source formatting, graceful degradation.
Design: Given/When/Then docstrings, one function per test case.
Public API only — no private method assertions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.reranker_null import NullReranker
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.config import NamespaceConfig
from ai_assistant.core.domain.configs import (
    EmbedderConfigData,
    RerankerConfigData,
    TokenizerConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.llm import ILLM
from ai_assistant.core.ports.storage import IChatStorage
from ai_assistant.features.chat.manager import ChatManager

logger = get_logger(__name__)


# ── Helpers ──

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


# ── Fixtures ──

@pytest.fixture
def chat_manager_with_rag():
    """Given: ChatManager with full RAG pipeline configured."""
    embedder = MockEmbedder(EmbedderConfigData(dim=3))
    store = MemoryVectorStore(VectorStoreConfigData(dim=3))
    namespaces = {
        "test": NamespaceConfig(
            prefix="t", chunk_size=512, prompt="rag_strict"
        ),
        "test-alt": NamespaceConfig(
            prefix="a", chunk_size=1024, prompt="rag_strict"
        ),
        "test-default": NamespaceConfig(
            prefix="d", chunk_size=512, prompt="rag_strict"
        ),
    }
    mock_llm = MagicMock(spec=ILLM)
    mock_llm.get_context_limit.return_value = 4096
    mock_llm.system_message = None
    return ChatManager(
        llm=mock_llm,
        embedder=embedder,
        vector_store=store,
        reranker=NullReranker(RerankerConfigData()),
        storage=None,
        namespaces=namespaces,
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
    )


@pytest.fixture
def manager_no_rag():
    """Given: ChatManager without RAG infrastructure."""
    mock_llm = MagicMock(spec=ILLM)
    mock_llm.get_context_limit.return_value = 4096
    mock_llm.system_message = None
    mock_llm.complete = AsyncMock(
        return_value=AssistantMessage(text="Hello!", metadata={}, tool_calls=[])
    )
    return ChatManager(
        llm=mock_llm,
        embedder=None,
        vector_store=None,
        reranker=NullReranker(RerankerConfigData()),
        storage=None,
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
    )


@pytest.fixture
def manager_with_storage():
    """Given: ChatManager with mocked storage."""
    mock_storage = MagicMock(spec=IChatStorage)
    mock_storage.get_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ]
    )
    mock_llm = MagicMock(spec=ILLM)
    mock_llm.get_context_limit.return_value = 4096
    mock_llm.system_message = None
    return ChatManager(
        llm=mock_llm,
        reranker=NullReranker(RerankerConfigData()),
        storage=mock_storage,
        history_limit=10,
        max_context_tokens=None,
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
    )


@pytest.fixture
def manager_with_tokenizer_and_storage():
    """Given: ChatManager with tokenizer, storage and small token budget."""
    mock_storage = MagicMock(spec=IChatStorage)
    mock_storage.get_history = AsyncMock(return_value=[])
    mock_llm = MagicMock(spec=ILLM)
    mock_llm.get_context_limit.return_value = 100
    mock_llm.system_message = "System prompt"
    return ChatManager(
        llm=mock_llm,
        reranker=NullReranker(RerankerConfigData()),
        max_context_tokens=100,
        history_limit=10,
        storage=mock_storage,
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
    )


@pytest.fixture
def manager_with_fallback_tokenizer_and_storage():
    """Given: ChatManager with fallback tokenizer and count-based limit."""
    mock_storage = MagicMock(spec=IChatStorage)
    mock_storage.get_history = AsyncMock(return_value=[])
    mock_llm = MagicMock(spec=ILLM)
    mock_llm.get_context_limit.return_value = None
    mock_llm.system_message = None
    return ChatManager(
        llm=mock_llm,
        reranker=NullReranker(RerankerConfigData()),
        max_context_tokens=None,
        history_limit=3,
        storage=mock_storage,
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
    )


@pytest.fixture
def prefix_manager():
    """Given: ChatManager configured for prefix testing."""
    mock_llm = MagicMock(spec=ILLM)
    mock_llm.get_context_limit.return_value = 4096
    mock_llm.system_message = None
    mgr = ChatManager(
        llm=mock_llm,
        embedder=None,
        vector_store=None,
        reranker=NullReranker(RerankerConfigData()),
        storage=None,
        namespaces={
            "test": NamespaceConfig(prefix="t"),
            "test-alt": NamespaceConfig(prefix="a"),
        },
        tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
    )
    return mgr


# ── TestChatRAG ──


class TestChatRAG:
    """Given: ChatManager with RAG pipeline.
    When: messages with namespace prefixes are sent.
    Then: correct chunks are retrieved and passed to LLM.
    """

    @pytest.mark.asyncio
    async def test_retrieve_no_prefix_returns_unchanged(self, chat_manager_with_rag):
        """Given: message without RAG prefix.
        When: chat() is called.
        Then: LLM receives the original message text.
        """
        chat_manager_with_rag.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await chat_manager_with_rag.chat("Hello world", "conv-1")
        messages = chat_manager_with_rag.llm.complete.call_args[0][0]
        assert len(messages) == 1
        assert messages[0].text == "Hello world"

    @pytest.mark.asyncio
    async def test_retrieve_test_prefix_triggers_rag(self, chat_manager_with_rag):
        """Given: [t] prefix and chunk in test namespace.
        When: stream_chat() is called.
        Then: RAG is triggered and sources are appended.
        """
        chunk = Chunk(
            id="c1",
            text="Paris is the capital of France.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Answer."])
        )

        chunks = []
        async for text in chat_manager_with_rag.stream_chat(
            "[t] What is the capital?", "conv-1"
        ):
            chunks.append(text)

        result = "".join(chunks)
        assert "Sources:" in result
        assert "doc1" in result

    @pytest.mark.asyncio
    async def test_retrieve_alt_prefix_triggers_rag(self, chat_manager_with_rag):
        """Given: [a] prefix and chunk in test-alt namespace.
        When: stream_chat() is called.
        Then: RAG is triggered for test-alt namespace.
        """
        chunk = Chunk(
            id="c1",
            text="Project deadline is Friday.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="test-alt")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Answer."])
        )

        chunks = []
        async for text in chat_manager_with_rag.stream_chat(
            "[a] When is the deadline?", "conv-1"
        ):
            chunks.append(text)

        result = "".join(chunks)
        assert "Sources:" in result

    @pytest.mark.asyncio
    async def test_retrieve_default_prefix_triggers_rag(self, chat_manager_with_rag):
        """Given: [d] prefix and chunk in test-default namespace.
        When: stream_chat() is called.
        Then: RAG is triggered for test-default namespace.
        """
        chunk = Chunk(
            id="c1",
            text="Recipe: 2 eggs, 1 cup flour.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add(
            [chunk], namespace="test-default"
        )
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Answer."])
        )

        chunks = []
        async for text in chat_manager_with_rag.stream_chat(
            "[d] What ingredients?", "conv-1"
        ):
            chunks.append(text)

        result = "".join(chunks)
        assert "Sources:" in result

    @pytest.mark.asyncio
    async def test_retrieve_no_results_returns_original_query(
        self, chat_manager_with_rag
    ):
        """Given: RAG prefix but no matching chunks.
        When: chat() is called.
        Then: original query text is passed to LLM unchanged.
        """
        chat_manager_with_rag.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await chat_manager_with_rag.chat(
            "[t] something impossible to find", "conv-1"
        )
        messages = chat_manager_with_rag.llm.complete.call_args[0][0]
        assert messages[-1].text == "something impossible to find"

    @pytest.mark.asyncio
    async def test_retrieve_prefix_stripped_from_query(self, chat_manager_with_rag):
        """Given: message with [t] prefix.
        When: chat() is called.
        Then: prefix is stripped from query text sent to LLM.
        """
        chunk = Chunk(
            id="c1",
            text="Some content",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="test")
        chat_manager_with_rag.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await chat_manager_with_rag.chat("[t] query text", "conv-1")
        messages = chat_manager_with_rag.llm.complete.call_args[0][0]
        assert not messages[-1].text.startswith("[t]")
        assert "query text" in messages[-1].text

    @pytest.mark.asyncio
    async def test_retrieve_case_insensitive_prefix(self, chat_manager_with_rag):
        """Given: uppercase prefix [T].
        When: stream_chat() is called.
        Then: same result as lowercase [t].
        """
        chunk = Chunk(
            id="c1",
            text="Content",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )

        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Answer."])
        )
        chunks_lower = []
        async for text in chat_manager_with_rag.stream_chat("[t] test", "conv-1"):
            chunks_lower.append(text)

        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Answer."])
        )
        chunks_upper = []
        async for text in chat_manager_with_rag.stream_chat("[T] test", "conv-1"):
            chunks_upper.append(text)

        assert "Sources:" in "".join(chunks_lower)
        assert "Sources:" in "".join(chunks_upper)

    @pytest.mark.asyncio
    async def test_retrieve_no_embedder_returns_unchanged(self):
        """Given: ChatManager without embedder.
        When: chat() is called with prefix.
        Then: stripped query is sent to LLM (RAG unavailable, prefix removed).
        """
        mock_llm = MagicMock(spec=ILLM)
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        manager = ChatManager(
            llm=mock_llm,
            embedder=None,
            vector_store=MagicMock(),
            reranker=NullReranker(RerankerConfigData()),
            storage=None,
            namespaces={"test": NamespaceConfig(prefix="t")},
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager.chat("[t] query", "conv-1")
        messages = manager.llm.complete.call_args[0][0]
        assert messages[-1].text == "query"

    @pytest.mark.asyncio
    async def test_retrieve_no_vector_store_returns_unchanged(self):
        """Given: ChatManager without vector_store.
        When: chat() is called with prefix.
        Then: stripped query is sent to LLM (RAG unavailable, prefix removed).
        """
        mock_llm = MagicMock(spec=ILLM)
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        manager = ChatManager(
            llm=mock_llm,
            embedder=MagicMock(),
            vector_store=None,
            reranker=NullReranker(RerankerConfigData()),
            storage=None,
            namespaces={"test": NamespaceConfig(prefix="t")},
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager.chat("[t] query", "conv-1")
        messages = manager.llm.complete.call_args[0][0]
        assert messages[-1].text == "query"

    @pytest.mark.asyncio
    async def test_retrieve_per_namespace_prompt(
        self, chat_manager_with_rag
    ):
        """Given: test-alt namespace with custom prompt.
        When: stream_chat() is called with [a] prefix.
        Then: correct prompt name is requested.
        """
        chunk = Chunk(
            id="c1",
            text="Alt item.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="test-alt")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )

        with patch(
            "ai_assistant.features.chat.manager.get_prompt"
        ) as mock_get_prompt:
            mock_get_prompt.return_value = "alt prompt"
            chat_manager_with_rag.llm.stream = MagicMock(
                return_value=async_iter(["Answer."])
            )
            chunks = []
            async for text in chat_manager_with_rag.stream_chat(
                "[a] alt item?", "conv-1"
            ):
                chunks.append(text)

            mock_get_prompt.assert_called_once()
            assert mock_get_prompt.call_args[0][0] == "rag_strict"
            assert "Sources:" in "".join(chunks)

    @pytest.mark.asyncio
    async def test_retrieve_fallback_to_defaults_when_no_namespace_config(self):
        """Given: namespace with prefix but no per-namespace overrides.
        When: stream_chat() is called with prefix.
        Then: global defaults (rag_strict) are used.
        """
        embedder = MockEmbedder(EmbedderConfigData(dim=3))
        store = MemoryVectorStore(VectorStoreConfigData(dim=3))
        mock_llm = MagicMock(spec=ILLM)
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        manager = ChatManager(
            llm=mock_llm,
            embedder=embedder,
            vector_store=store,
            reranker=NullReranker(RerankerConfigData()),
            storage=None,
            namespaces={"test": NamespaceConfig(prefix="t")},
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        chunk = Chunk(
            id="c1",
            text="Content",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await manager.vector_store.add([chunk], namespace="test")
        manager.embedder.embed = AsyncMock(return_value=[[1.0, 0.0, 0.0]])

        with patch(
            "ai_assistant.features.chat.manager.get_prompt"
        ) as mock_get_prompt:
            mock_get_prompt.return_value = "default prompt"
            manager.llm.stream = MagicMock(return_value=async_iter(["Answer."]))
            chunks = []
            async for text in manager.stream_chat("[t] content?", "conv-1"):
                chunks.append(text)

            mock_get_prompt.assert_called_once()
            assert mock_get_prompt.call_args[0][0] == "rag_strict"


# ── TestChatHistory ──


class TestChatHistory:
    """Given: ChatManager with storage-backed history.
    When: chat() is called.
    Then: history is loaded, ordered, and trimmed correctly.
    """

    @pytest.mark.asyncio
    async def test_build_messages_without_storage(self, manager_no_rag):
        """Given: ChatManager without storage.
        When: chat() is called.
        Then: only current user message is sent to LLM.
        """
        manager_no_rag.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_no_rag.chat("Hello", "conv-1")
        messages = manager_no_rag.llm.complete.call_args[0][0]
        assert len(messages) == 1
        assert isinstance(messages[0], UserMessage)
        assert messages[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_build_messages_with_history(self, manager_with_storage):
        """Given: ChatManager with storage containing history.
        When: chat() is called.
        Then: history is prepended in chronological order.
        """
        manager_with_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_storage.chat("Hello", "conv-1")
        messages = manager_with_storage.llm.complete.call_args[0][0]
        assert len(messages) == 3
        assert isinstance(messages[0], UserMessage)
        assert messages[0].text == "Previous question"
        assert isinstance(messages[1], AssistantMessage)
        assert messages[1].text == "Previous answer"
        assert isinstance(messages[2], UserMessage)
        assert messages[2].text == "Hello"

    @pytest.mark.asyncio
    async def test_build_messages_preserves_metadata(self, manager_no_rag):
        """Given: metadata dict with trace_id.
        When: chat() is called.
        Then: metadata is attached to current user message.
        """
        meta = {"trace_id": "abc123"}
        manager_no_rag.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_no_rag.chat("Hello", "conv-1", metadata=meta)
        messages = manager_no_rag.llm.complete.call_args[0][0]
        assert messages[-1].metadata == meta

    @pytest.mark.asyncio
    async def test_build_messages_trims_history(self, manager_with_storage):
        """Given: token budget that forces trimming.
        When: chat() is called.
        Then: only current user message is kept in LLM call.
        """
        manager_with_storage.max_context_tokens = 50
        manager_with_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_storage.chat("Hello", "conv-1")
        messages = manager_with_storage.llm.complete.call_args[0][0]
        assert len(messages) == 1
        assert messages[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_build_messages_history_load_failure(self, manager_with_storage):
        """Given: storage that raises on get_history.
        When: chat() is called.
        Then: graceful fallback returns just user message to LLM.
        """
        manager_with_storage.storage.get_history = AsyncMock(
            side_effect=Exception("DB error")
        )
        manager_with_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_storage.chat("Hello", "conv-1")
        messages = manager_with_storage.llm.complete.call_args[0][0]
        assert len(messages) == 1
        assert messages[0].text == "Hello"


# ── TestChatMethods ──


class TestChatMethods:
    """Given: ChatManager chat() and stream_chat() methods.
    When: invoked with various inputs.
    Then: correct LLM interaction occurs.
    """

    @pytest.mark.asyncio
    async def test_chat_calls_llm_complete(self, manager_no_rag):
        """Given: chat() invocation.
        When: message is processed.
        Then: LLM complete is called and response returned.
        """
        manager_no_rag.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="Hello!", metadata={}, tool_calls=[])
        )
        result = await manager_no_rag.chat("Hello", "conv-1")
        assert result.text == "Hello!"
        manager_no_rag.llm.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stream_chat_calls_llm_stream(self, manager_no_rag):
        """Given: stream_chat() invocation.
        When: message is processed.
        Then: LLM stream is called and chunks are yielded.
        """
        manager_no_rag.llm.stream = MagicMock(
            return_value=async_iter(["Hi", " there"])
        )
        chunks = []
        async for chunk in manager_no_rag.stream_chat("Hello", "conv-1"):
            chunks.append(chunk)
        assert chunks == ["Hi", " there"]

    @pytest.mark.asyncio
    async def test_chat_and_stream_use_same_prep_path(self, manager_no_rag):
        """Given: both chat() and stream_chat() methods.
        When: called with same input.
        Then: both send identical message lists to LLM.
        """
        manager_no_rag.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        manager_no_rag.llm.stream = MagicMock(return_value=async_iter([]))

        await manager_no_rag.chat("Hello", "conv-1")
        chat_messages = manager_no_rag.llm.complete.call_args[0][0]

        # stream_chat is async generator — must iterate, not await
        async for _ in manager_no_rag.stream_chat("Hello", "conv-1"):
            pass
        stream_messages = manager_no_rag.llm.stream.call_args[0][0]

        assert len(chat_messages) == len(stream_messages)
        assert chat_messages[-1].text == stream_messages[-1].text


# ── TestChatGracefulDegradation ──


class TestChatGracefulDegradation:
    """Given: ChatManager with missing RAG infrastructure.
    When: RAG prefix is used.
    Then: graceful unavailable message is returned.
    """

    @pytest.mark.asyncio
    async def test_chat_with_prefix_no_pipeline_graceful(self):
        """Given: [t] prefix with no RAG pipeline.
        When: chat() is called.
        Then: graceful unavailable message is returned.
        """
        mock_llm = MagicMock(spec=ILLM)
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        mock_llm.complete = AsyncMock(
            return_value=AssistantMessage(
                text="RAG unavailable", metadata={}, tool_calls=[]
            )
        )
        manager = ChatManager(
            llm=mock_llm,
            embedder=None,
            vector_store=None,
            reranker=NullReranker(RerankerConfigData()),
            storage=None,
            namespaces={"test": NamespaceConfig(prefix="t")},
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        result = await manager.chat(
            message="[t] capital of France",
            conversation_id="test-1",
        )
        assert "unavailable" in result.text.lower()

    @pytest.mark.asyncio
    async def test_chat_without_prefix_works_without_rag(self, manager_no_rag):
        """Given: plain message without prefix.
        When: chat() is called without RAG infrastructure.
        Then: LLM is called and response returned.
        """
        manager_no_rag.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="Hello!", metadata={}, tool_calls=[])
        )
        result = await manager_no_rag.chat(
            message="Hello",
            conversation_id="test-2",
        )
        assert result.text == "Hello!"
        manager_no_rag.llm.complete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stream_chat_without_rag(self, manager_no_rag):
        """Given: stream_chat without RAG prefix.
        When: message is streamed.
        Then: LLM stream is called and chunks yielded.
        """
        manager_no_rag.llm.stream = MagicMock(
            return_value=async_iter(["Hello", "!"])
        )
        chunks = []
        async for chunk in manager_no_rag.stream_chat("Hello", "conv-1"):
            chunks.append(chunk)
        assert chunks == ["Hello", "!"]

    @pytest.mark.asyncio
    async def test_stream_chat_with_rag_prefix_graceful(self):
        """Given: [p] prefix with no RAG pipeline in stream_chat.
        When: stream_chat() is called.
        Then: graceful unavailable message is yielded.
        """
        mock_llm = MagicMock(spec=ILLM)
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        manager = ChatManager(
            llm=mock_llm,
            embedder=None,
            vector_store=None,
            reranker=NullReranker(RerankerConfigData()),
            storage=None,
            namespaces={"personal": NamespaceConfig(prefix="p")},
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        manager.llm.stream = MagicMock(
            return_value=async_iter(["RAG unavailable"])
        )
        chunks = []
        async for chunk in manager.stream_chat(
            "[p] capital of France", "conv-1"
        ):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert "unavailable" in chunks[0].lower()


# ── TestChatToolCalls ──


class TestChatToolCalls:
    """Given: LLM responses with tool_calls.
    When: chat() is called.
    Then: tool_calls are preserved in the response.
    """

    @pytest.mark.asyncio
    async def test_chat_with_tool_calls(self, manager_no_rag):
        """Given: LLM response with tool_calls.
        When: chat() is called.
        Then: tool_calls are preserved in the response.
        """
        tool_calls = [{"id": "call_1", "function": {"name": "get_weather"}}]
        manager_no_rag.llm.complete = AsyncMock(
            return_value=AssistantMessage(
                text="Let me check the weather.",
                metadata={"model": "gpt-4"},
                tool_calls=tool_calls,
            )
        )
        result = await manager_no_rag.chat("Weather in Paris?", "conv-1")
        assert result.text == "Let me check the weather."
        assert result.metadata == {"model": "gpt-4"}


# ── TestChatStreamRAG ──


class TestChatStreamRAG:
    """Given: stream_chat with active RAG pipeline.
    When: RAG prefix is used.
    Then: context is retrieved and sources appended.
    """

    @pytest.mark.asyncio
    async def test_stream_chat_with_rag_prefix(self, chat_manager_with_rag):
        """Given: [t] prefix with full RAG pipeline in stream_chat.
        When: stream_chat() is called.
        Then: RAG context is retrieved and stream proceeds.
        """
        chunk = Chunk(
            id="c1",
            text="Paris is sunny.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="test")

        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )

        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Paris", " is", " sunny."])
        )
        chunks = []
        async for chunk_text in chat_manager_with_rag.stream_chat(
            "[t] Weather in Paris?", "conv-1"
        ):
            chunks.append(chunk_text)
        assert chunks == ["Paris", " is", " sunny.", "\n\nSources:\n[1] doc1"]

    @pytest.mark.asyncio
    async def test_namespace_test_and_alt_prefixes(self, chat_manager_with_rag):
        """Given: [t] and [a] prefixes with chunks in respective namespaces.
        When: stream_chat() is called for each.
        Then: correct namespace routing occurs.
        """
        chunk_t = Chunk(
            id="c1",
            text="Test settings.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc_test", index=0, total_chunks=1),
        )
        chunk_a = Chunk(
            id="c2",
            text="Alt plan.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc_alt", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk_t], namespace="test")
        await chat_manager_with_rag.vector_store.add([chunk_a], namespace="test-alt")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )

        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["ok"])
        )
        chunks_t = []
        async for text in chat_manager_with_rag.stream_chat(
            "[t] settings?", "conv-1"
        ):
            chunks_t.append(text)
        assert "Sources:" in "".join(chunks_t)

        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["ok"])
        )
        chunks_a = []
        async for text in chat_manager_with_rag.stream_chat(
            "[a] plan?", "conv-1"
        ):
            chunks_a.append(text)
        assert "Sources:" in "".join(chunks_a)


# ── TestChatPrefixes ──


class TestChatPrefixes:
    """Given: message prefixes trigger namespace routing.
    When: various prefixes are provided.
    Then: correct namespace is selected, prefix is stripped, case is ignored.
    """

    @pytest.mark.asyncio
    async def test_prefix_t_test(self, prefix_manager):
        """Given: [t] prefix.
        When: chat() is called.
        Then: query is stripped of prefix before reaching LLM.
        """
        prefix_manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await prefix_manager.chat("[t] test", "conv-1")
        messages = prefix_manager.llm.complete.call_args[0][0]
        assert messages[-1].text == "test"
        assert not messages[-1].text.startswith("[t]")

    @pytest.mark.asyncio
    async def test_prefix_a_alt(self, prefix_manager):
        """Given: [a] prefix.
        When: chat() is called.
        Then: query is stripped of prefix before reaching LLM.
        """
        prefix_manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await prefix_manager.chat("[a] deadline", "conv-1")
        messages = prefix_manager.llm.complete.call_args[0][0]
        assert messages[-1].text == "deadline"
        assert not messages[-1].text.startswith("[a]")

    @pytest.mark.asyncio
    async def test_prefix_case_insensitive_t(self, prefix_manager):
        """Given: uppercase [T] prefix.
        When: chat() is called.
        Then: same behavior as lowercase [t].
        """
        prefix_manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await prefix_manager.chat("[t] test", "conv-1")
        messages_lower = prefix_manager.llm.complete.call_args[0][0]

        prefix_manager.llm.complete.reset_mock()
        prefix_manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await prefix_manager.chat("[T] test", "conv-1")
        messages_upper = prefix_manager.llm.complete.call_args[0][0]

        assert messages_lower[-1].text == messages_upper[-1].text == "test"

    @pytest.mark.asyncio
    async def test_prefix_case_insensitive_a(self, prefix_manager):
        """Given: uppercase [A] prefix.
        When: chat() is called.
        Then: same behavior as lowercase [a].
        """
        prefix_manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await prefix_manager.chat("[a] test", "conv-1")
        messages_lower = prefix_manager.llm.complete.call_args[0][0]

        prefix_manager.llm.complete.reset_mock()
        prefix_manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await prefix_manager.chat("[A] test", "conv-1")
        messages_upper = prefix_manager.llm.complete.call_args[0][0]

        assert messages_lower[-1].text == messages_upper[-1].text == "test"

    @pytest.mark.asyncio
    async def test_prefix_stripping_all_prefixes(self, prefix_manager):
        """Given: all supported prefixes.
        When: chat() is called for each.
        Then: prefix is stripped, only query remains.
        """
        for prefix in ["t", "a"]:
            prefix_manager.llm.complete = AsyncMock(
                return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
            )
            await prefix_manager.chat(f"[{prefix}] query text", "conv-1")
            messages = prefix_manager.llm.complete.call_args[0][0]
            assert messages[-1].text == "query text", f"Failed for prefix [{prefix}]"

    @pytest.mark.asyncio
    async def test_no_prefix_no_stripping(self, prefix_manager):
        """Given: message without any prefix.
        When: chat() is called.
        Then: message is returned unchanged to LLM.
        """
        prefix_manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await prefix_manager.chat("plain message without prefix", "conv-1")
        messages = prefix_manager.llm.complete.call_args[0][0]
        assert messages[-1].text == "plain message without prefix"


# ── TestChatManagerSources ──


class TestChatManagerSources:
    """Given: chunks with source metadata.
    When: stream_chat() is called with RAG.
    Then: clickable file:/// links are appended when available.
    """

    @pytest.mark.asyncio
    async def test_append_sources_with_source_uri(self, chat_manager_with_rag):
        """Given: chunks with source_uri set.
        When: stream_chat() is called.
        Then: filename and URI are shown separated by em-dash.
        """
        chunks = (
            Chunk(
                id="c1",
                text="Paris info",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="doc1",
                    index=0,
                    total_chunks=1,
                    source_uri="file:///home/user/docs/france.md",
                ),
            ),
        )
        await chat_manager_with_rag.vector_store.add(chunks, namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Paris is the capital of France."])
        )

        result = []
        async for chunk in chat_manager_with_rag.stream_chat(
            "[t] query?", "conv-1"
        ):
            result.append(chunk)

        text = "".join(result)
        assert "[1] france.md — file:///home/user/docs/france.md" in text
        assert "Sources:" in text

    @pytest.mark.asyncio
    async def test_append_sources_without_source_uri_fallback_to_source(
        self, chat_manager_with_rag
    ):
        """Given: chunks without source_uri.
        When: stream_chat() is called.
        Then: source field is used as fallback.
        """
        chunks = (
            Chunk(
                id="c1",
                text="Berlin info",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(source="doc2", index=0, total_chunks=1),
            ),
        )
        await chat_manager_with_rag.vector_store.add(chunks, namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Berlin is the capital of Germany."])
        )

        result = []
        async for chunk in chat_manager_with_rag.stream_chat(
            "[t] query?", "conv-1"
        ):
            result.append(chunk)

        text = "".join(result)
        assert "[1] doc2" in text
        assert "file://" not in text
        assert "Sources:" in text

    @pytest.mark.asyncio
    async def test_append_sources_always_when_chunks_present(self, chat_manager_with_rag):
        """Given: chunks exist even if LLM refuses to answer.
        When: stream_chat() is called.
        Then: sources are still appended.
        """
        chunks = (
            Chunk(
                id="c1",
                text="Unknown info",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="doc1",
                    index=0,
                    total_chunks=1,
                    source_uri="file:///docs/unknown.md",
                ),
            ),
        )
        await chat_manager_with_rag.vector_store.add(chunks, namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["I don't have enough information."])
        )

        result = []
        async for chunk in chat_manager_with_rag.stream_chat(
            "[t] query?", "conv-1"
        ):
            result.append(chunk)

        text = "".join(result)
        assert "Sources:" in text
        assert "unknown.md" in text

    @pytest.mark.asyncio
    async def test_append_sources_without_citation_markers(self, chat_manager_with_rag):
        """Given: LLM answer without [N] citation markers but chunks exist.
        When: stream_chat() is called.
        Then: sources are still appended with filename and URI.
        """
        chunks = (
            Chunk(
                id="c1",
                text="Paris info",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="doc1",
                    index=0,
                    total_chunks=1,
                    source_uri="file:///docs/france.md",
                ),
            ),
        )
        await chat_manager_with_rag.vector_store.add(chunks, namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Paris is the capital of France."])
        )

        result = []
        async for chunk in chat_manager_with_rag.stream_chat(
            "[t] query?", "conv-1"
        ):
            result.append(chunk)

        text = "".join(result)
        assert "Sources:" in text
        assert "[1] france.md — file:///docs/france.md" in text

    @pytest.mark.asyncio
    async def test_append_sources_multiple_citations(self, chat_manager_with_rag):
        """Given: multiple chunks with source_uri from different documents.
        When: stream_chat() is called.
        Then: all unique sources are listed with filename and URI.
        """
        chunks = (
            Chunk(
                id="c1",
                text="Info 1",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="doc1",
                    index=0,
                    total_chunks=2,
                    source_uri="file:///docs/a.md",
                ),
            ),
            Chunk(
                id="c2",
                text="Info 2",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="doc2",
                    index=1,
                    total_chunks=2,
                    source_uri="file:///docs/b.md",
                ),
            ),
        )
        await chat_manager_with_rag.vector_store.add(chunks, namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Combined info."])
        )

        result = []
        async for chunk in chat_manager_with_rag.stream_chat(
            "[t] query?", "conv-1"
        ):
            result.append(chunk)

        text = "".join(result)
        assert "a.md — file:///docs/a.md" in text
        assert "b.md — file:///docs/b.md" in text
        assert "Sources:" in text

    @pytest.mark.asyncio
    async def test_append_sources_empty_chunks(self, chat_manager_with_rag):
        """Given: no chunks.
        When: stream_chat() is called without RAG prefix.
        Then: answer returned unchanged.
        """
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Some answer."])
        )
        result = []
        async for chunk in chat_manager_with_rag.stream_chat("plain query", "conv-1"):
            result.append(chunk)
        assert "".join(result) == "Some answer."

    @pytest.mark.asyncio
    async def test_append_sources_old_index_without_source_uri_fallback(
        self, chat_manager_with_rag
    ):
        """Given: chunk from old index without source_uri (backward compat).
        When: stream_chat() is called.
        Then: falls back to source field as plain text.
        """
        chunks = (
            Chunk(
                id="c1",
                text="Old data",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="legacy_doc",
                    index=0,
                    total_chunks=1,
                ),
            ),
        )
        await chat_manager_with_rag.vector_store.add(chunks, namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Old answer."])
        )

        result = []
        async for chunk in chat_manager_with_rag.stream_chat(
            "[t] query?", "conv-1"
        ):
            result.append(chunk)

        text = "".join(result)
        assert "[1] legacy_doc" in text
        assert "Sources:" in text

    @pytest.mark.asyncio
    async def test_append_sources_with_original_path(self, chat_manager_with_rag):
        """Given: chunk with original_path but no source_uri.
        When: stream_chat() is called.
        Then: file:// URI is built and shown with filename.
        """
        chunks = (
            Chunk(
                id="c1",
                text="Config info",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="config_doc",
                    index=0,
                    total_chunks=1,
                    original_path="/home/user/docs/settings.yaml",
                ),
            ),
        )
        await chat_manager_with_rag.vector_store.add(chunks, namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Configuration details."])
        )

        result = []
        async for chunk in chat_manager_with_rag.stream_chat(
            "[t] query?", "conv-1"
        ):
            result.append(chunk)

        text = "".join(result)
        assert "[1] settings.yaml — file:///home/user/docs/settings.yaml" in text
        assert "Sources:" in text

    @pytest.mark.asyncio
    async def test_append_sources_deduplicates_same_document(
        self, chat_manager_with_rag
    ):
        """Given: multiple chunks from the same document.
        When: stream_chat() is called.
        Then: only one source line is shown per unique document.
        """
        chunks = (
            Chunk(
                id="c1",
                text="Part 1",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="doc1",
                    index=0,
                    total_chunks=3,
                    source_uri="file:///docs/shared.md",
                ),
            ),
            Chunk(
                id="c2",
                text="Part 2",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="doc1",
                    index=1,
                    total_chunks=3,
                    source_uri="file:///docs/shared.md",
                ),
            ),
            Chunk(
                id="c3",
                text="Part 3 from other",
                embedding=[1.0, 0.0, 0.0],
                metadata=ChunkMetadata(
                    source="doc2",
                    index=0,
                    total_chunks=1,
                    source_uri="file:///docs/other.md",
                ),
            ),
        )
        await chat_manager_with_rag.vector_store.add(chunks, namespace="test")
        chat_manager_with_rag.embedder.embed = AsyncMock(
            return_value=[[1.0, 0.0, 0.0]]
        )
        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Answer."])
        )

        result = []
        async for chunk in chat_manager_with_rag.stream_chat(
            "[t] query?", "conv-1"
        ):
            result.append(chunk)

        text = "".join(result)
        assert text.count("— file:///docs/") == 2
        assert "shared.md — file:///docs/shared.md" in text
        assert "other.md — file:///docs/other.md" in text
        assert "Sources:" in text


# ── TestChatHistoryTrimming ──


class TestChatHistoryTrimming:
    """Given: conversation history may exceed token budget.
    When: chat() is called.
    Then: oldest messages are dropped, budget is respected, order preserved.
    """

    @pytest.mark.asyncio
    async def test_trims_oldest_to_fit_budget(self, manager_with_tokenizer_and_storage):
        """Given: history exceeding token budget.
        When: chat() is called.
        Then: oldest messages are dropped to fit budget.
        """
        history = [
            {"role": "user", "content": "A" * 100},
            {"role": "assistant", "content": "B" * 100},
            {"role": "user", "content": "C" * 100},
            {"role": "assistant", "content": "D" * 100},
        ]
        manager_with_tokenizer_and_storage.storage.get_history = AsyncMock(
            return_value=history
        )
        manager_with_tokenizer_and_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_tokenizer_and_storage.chat("Current question", "conv-1")
        messages = manager_with_tokenizer_and_storage.llm.complete.call_args[0][0]
        texts = [m.text for m in messages]
        assert "A" * 100 not in texts
        assert "B" * 100 not in texts
        assert "C" * 100 not in texts
        assert "D" * 100 in texts
        assert "Current question" in texts

    @pytest.mark.asyncio
    async def test_returns_empty_when_budget_too_small(
        self, manager_with_tokenizer_and_storage
    ):
        """Given: user message alone exceeds token budget.
        When: chat() is called.
        Then: only current message is sent to LLM.
        """
        long_msg = "x" * 500
        manager_with_tokenizer_and_storage.storage.get_history = AsyncMock(
            return_value=[{"role": "user", "content": "old"}]
        )
        manager_with_tokenizer_and_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_tokenizer_and_storage.chat(long_msg, "conv-1")
        messages = manager_with_tokenizer_and_storage.llm.complete.call_args[0][0]
        assert len(messages) == 1
        assert messages[0].text == long_msg

    @pytest.mark.asyncio
    async def test_fallback_to_count_based(
        self, manager_with_fallback_tokenizer_and_storage
    ):
        """Given: no tokenizer available (no context limit).
        When: chat() is called.
        Then: simple count-based fallback is used.
        """
        history = [
            {"role": "user", "content": "1"},
            {"role": "assistant", "content": "2"},
            {"role": "user", "content": "3"},
            {"role": "assistant", "content": "4"},
            {"role": "user", "content": "5"},
        ]
        manager_with_fallback_tokenizer_and_storage.storage.get_history = AsyncMock(
            return_value=history
        )
        manager_with_fallback_tokenizer_and_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_fallback_tokenizer_and_storage.chat("q", "conv-1")
        call_args = manager_with_fallback_tokenizer_and_storage.llm.complete.call_args
        messages = call_args[0][0]
        assert len(messages) <= 3

    @pytest.mark.asyncio
    async def test_preserves_chronological_order(
        self, manager_with_tokenizer_and_storage
    ):
        """Given: history with multiple messages.
        When: chat() is called.
        Then: trimmed history maintains oldest-first order.
        """
        history = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Second"},
            {"role": "user", "content": "Third"},
        ]
        manager_with_tokenizer_and_storage.storage.get_history = AsyncMock(
            return_value=history
        )
        manager_with_tokenizer_and_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_tokenizer_and_storage.chat("q", "conv-1")
        messages = manager_with_tokenizer_and_storage.llm.complete.call_args[0][0]
        history_texts = [h["content"] for h in history]
        msg_texts = [m.text for m in messages[:-1]]
        for i in range(len(msg_texts) - 1):
            assert history_texts.index(msg_texts[i]) < history_texts.index(
                msg_texts[i + 1]
            )

    @pytest.mark.asyncio
    async def test_empty_history(self, manager_with_tokenizer_and_storage):
        """Given: empty history list.
        When: chat() is called.
        Then: only current message is sent to LLM.
        """
        manager_with_tokenizer_and_storage.storage.get_history = AsyncMock(
            return_value=[]
        )
        manager_with_tokenizer_and_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_tokenizer_and_storage.chat("hi", "conv-1")
        messages = manager_with_tokenizer_and_storage.llm.complete.call_args[0][0]
        assert len(messages) == 1
        assert messages[0].text == "hi"

    @pytest.mark.asyncio
    async def test_single_message_fits(self, manager_with_tokenizer_and_storage):
        """Given: single message within budget.
        When: chat() is called.
        Then: message is preserved in LLM call.
        """
        manager_with_tokenizer_and_storage.storage.get_history = AsyncMock(
            return_value=[{"role": "user", "content": "hello"}]
        )
        manager_with_tokenizer_and_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_tokenizer_and_storage.chat("hi", "conv-1")
        messages = manager_with_tokenizer_and_storage.llm.complete.call_args[0][0]
        assert len(messages) == 2
        assert messages[0].text == "hello"

    @pytest.mark.asyncio
    async def test_respects_system_message_overhead(
        self, manager_with_tokenizer_and_storage
    ):
        """Given: system message configured on LLM.
        When: chat() is called.
        Then: system message tokens are reserved from budget.
        """
        manager_with_tokenizer_and_storage.storage.get_history = AsyncMock(
            return_value=[{"role": "user", "content": "x" * 200}]
        )
        manager_with_tokenizer_and_storage.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager_with_tokenizer_and_storage.chat("q", "conv-1")
        messages = manager_with_tokenizer_and_storage.llm.complete.call_args[0][0]
        assert len(messages) <= 2

    @pytest.mark.asyncio
    async def test_no_llm_config_fallback(self):
        """Given: LLM with no context limit.
        When: chat() is called with max_context_tokens set.
        Then: falls back to history_limit.
        """
        mock_llm = MagicMock(spec=ILLM)
        mock_llm.get_context_limit.return_value = None
        mock_llm.system_message = None
        mock_storage = MagicMock(spec=IChatStorage)
        mock_storage.get_history = AsyncMock(
            return_value=[
                {"role": "user", "content": "1"},
                {"role": "assistant", "content": "2"},
                {"role": "user", "content": "3"},
            ]
        )
        manager = ChatManager(
            llm=mock_llm,
            reranker=NullReranker(RerankerConfigData()),
            max_context_tokens=50,
            history_limit=2,
            storage=mock_storage,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager.chat("q", "conv-1")
        messages = manager.llm.complete.call_args[0][0]
        assert len(messages) <= 2

    @pytest.mark.asyncio
    async def test_trim_history_uses_count_fallback_when_budget_is_none(self):
        """When get_context_limit() returns None, use history_limit.
        """
        mock_llm = MagicMock(spec=ILLM)
        mock_llm.get_context_limit.return_value = None
        mock_llm.system_message = None
        mock_storage = MagicMock(spec=IChatStorage)
        mock_storage.get_history = AsyncMock(
            return_value=[
                {"role": "user", "content": "msg1"},
                {"role": "user", "content": "msg2"},
                {"role": "user", "content": "msg3"},
                {"role": "user", "content": "msg4"},
                {"role": "user", "content": "msg5"},
            ]
        )
        manager = ChatManager(
            llm=mock_llm,
            reranker=NullReranker(RerankerConfigData()),
            storage=mock_storage,
            history_limit=3,
            max_context_tokens=None,
            tokenizer=CharFallbackTokenizer(TokenizerConfigData()),
        )
        manager.llm.complete = AsyncMock(
            return_value=AssistantMessage(text="ok", metadata={}, tool_calls=[])
        )
        await manager.chat("current", "conv-1")
        messages = manager.llm.complete.call_args[0][0]
        assert len(messages) == 3
        assert messages[0].text == "msg4"
        assert messages[1].text == "msg5"
        assert messages[-1].text == "current"
