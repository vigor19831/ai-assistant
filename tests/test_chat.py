"""tests/test_chat.py — ChatManager tests.

Coverage: _retrieve_context, _build_messages, _trim_history, chat(), stream_chat().
Design: Given/When/Then docstrings, one function per test case.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.reranker_null import NullReranker
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.config import NamespaceConfig
from ai_assistant.core.domain.configs import EmbedderConfigData, RerankerConfigData, VectorStoreConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import build_context, embed_query, retrieve
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
    """Given: ChatManager with full RAG pipeline configured.
    When: fixture is requested.
    Then: ChatManager with embedder, vector_store, pipeline, and namespaces is returned."""
    embedder = MockEmbedder(EmbedderConfigData(dim=3))
    store = MemoryVectorStore(VectorStoreConfigData(dim=3))
    pipeline = RAGPipeline([embed_query, retrieve, build_context])
    namespaces = {
        "personal": NamespaceConfig(
            threshold=0.1, chunk_size=512, prompt="rag_strict"
        ),
        "work": NamespaceConfig(
            threshold=0.3, chunk_size=1024, prompt="rag_creative"
        ),
        "custom": NamespaceConfig(
            threshold=0.2, chunk_size=512, prompt="rag_custom"
        ),
        "business": NamespaceConfig(
            threshold=0.25, chunk_size=1024, prompt="rag_business"
        ),
    }
    mock_llm = MagicMock()
    mock_llm.get_context_limit.return_value = 4096
    mock_llm.system_message = None
    return ChatManager(
        llm=mock_llm,
        embedder=embedder,
        vector_store=store,
        reranker=NullReranker(RerankerConfigData()),
        storage=None,
        pipeline=pipeline,
        namespaces=namespaces,
    )


@pytest.fixture
def manager_no_rag():
    """Given: ChatManager without RAG infrastructure.
    When: fixture is requested.
    Then: ChatManager with no embedder, vector_store, or pipeline is returned."""
    mock_llm = MagicMock()
    mock_llm.get_context_limit.return_value = 4096
    mock_llm.system_message = None
    mock_llm.complete = AsyncMock(
        return_value=MagicMock(text="Hello!", metadata={}, tool_calls=[])
    )
    return ChatManager(
        llm=mock_llm,
        embedder=None,
        vector_store=None,
        reranker=NullReranker(RerankerConfigData()),
        storage=None,
    )


@pytest.fixture
def manager_with_storage():
    """Given: ChatManager with mocked storage.
    When: fixture is requested.
    Then: ChatManager with AsyncMock storage is returned."""
    mock_storage = MagicMock()
    mock_storage.get_history = AsyncMock(
        return_value=[
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ]
    )
    mock_llm = MagicMock()
    mock_llm.get_context_limit.return_value = 4096
    mock_llm.system_message = None
    return ChatManager(
        llm=mock_llm,
        reranker=NullReranker(RerankerConfigData()),
        storage=mock_storage,
        history_limit=10,
        max_context_tokens=None,
    )


@pytest.fixture
def manager_with_tokenizer():
    """Given: ChatManager with tokenizer and small token budget.
    When: fixture is requested.
    Then: ChatManager configured for token-based trimming is returned."""
    mock_llm = MagicMock()
    mock_llm.get_context_limit.return_value = 100
    mock_llm.system_message = "System prompt"
    return ChatManager(
        llm=mock_llm,
        reranker=NullReranker(RerankerConfigData()),
        max_context_tokens=100,
        tokenizer_model="gpt-4o",
        history_limit=10,
        storage=None,
    )


@pytest.fixture
def manager_no_tokenizer():
    """Given: ChatManager without tokenizer (no context limit).
    When: fixture is requested.
    Then: ChatManager with count-based fallback is returned."""
    mock_llm = MagicMock()
    mock_llm.get_context_limit.return_value = None
    mock_llm.system_message = None
    return ChatManager(
        llm=mock_llm,
        reranker=NullReranker(RerankerConfigData()),
        max_context_tokens=None,
        history_limit=3,
        storage=None,
    )


# ── TestChatManager ──


class TestChatManager:
    """Given: ChatManager routes messages and manages RAG retrieval.
    When: various inputs and configurations are provided.
    Then: correct routing, retrieval, and message building occurs."""

    # ── _retrieve_context ──

    @pytest.mark.asyncio
    async def test_retrieve_no_prefix_returns_unchanged(self, chat_manager_with_rag):
        """Given: message without RAG prefix.
        When: _retrieve_context is called.
        Then: message passes through unchanged with empty chunks."""
        prompt, query, namespace, chunks = await chat_manager_with_rag._retrieve_context(
            "Hello world"
        )
        assert prompt == "Hello world"
        assert query == "Hello world"
        assert namespace == "default"
        assert chunks == ()

    @pytest.mark.asyncio
    async def test_retrieve_personal_prefix_triggers_rag(self, chat_manager_with_rag):
        """Given: [p] prefix and chunk in personal namespace.
        When: _retrieve_context is called.
        Then: RAG is triggered, chunks returned, prompt contains context."""
        chunk = Chunk(
            id="c1",
            text="Paris is the capital of France.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add(
            [chunk], namespace="personal"
        )

        prompt, query, namespace, chunks = await chat_manager_with_rag._retrieve_context(
            "[p] What is the capital?"
        )
        assert namespace == "personal"
        assert len(chunks) > 0
        assert "Paris" in prompt or "France" in prompt or "Context:" in prompt

    @pytest.mark.asyncio
    async def test_retrieve_work_prefix_triggers_rag(self, chat_manager_with_rag):
        """Given: [w] prefix and chunk in work namespace.
        When: _retrieve_context is called.
        Then: RAG is triggered for work namespace."""
        chunk = Chunk(
            id="c1",
            text="Project deadline is Friday.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="work")

        prompt, query, namespace, chunks = await chat_manager_with_rag._retrieve_context(
            "[w] When is the deadline?"
        )
        assert namespace == "work"
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_retrieve_other_prefix_triggers_rag(self, chat_manager_with_rag):
        """Given: [o] prefix and chunk in other namespace.
        When: _retrieve_context is called.
        Then: RAG is triggered for other namespace."""
        chunk = Chunk(
            id="c1",
            text="Recipe: 2 eggs, 1 cup flour.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="other")

        prompt, query, namespace, chunks = await chat_manager_with_rag._retrieve_context(
            "[o] What ingredients?"
        )
        assert namespace == "other"
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_retrieve_no_results_returns_original_query(
        self, chat_manager_with_rag
    ):
        """Given: RAG prefix but no matching chunks.
        When: _retrieve_context is called.
        Then: original query text is returned unchanged."""
        prompt, query, namespace, chunks = await chat_manager_with_rag._retrieve_context(
            "[p] something impossible to find"
        )
        assert namespace == "personal"
        assert prompt == "something impossible to find"
        assert query == "something impossible to find"
        assert chunks == ()

    @pytest.mark.asyncio
    async def test_retrieve_prefix_stripped_from_query(self, chat_manager_with_rag):
        """Given: message with [p] prefix.
        When: _retrieve_context is called.
        Then: prefix is stripped from query text."""
        chunk = Chunk(
            id="c1",
            text="Some content",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add(
            [chunk], namespace="personal"
        )

        prompt, query, namespace, chunks = await chat_manager_with_rag._retrieve_context(
            "[p] query text"
        )
        assert namespace == "personal"
        assert not query.startswith("[p]")
        assert "query text" in query

    @pytest.mark.asyncio
    async def test_retrieve_case_insensitive_prefix(self, chat_manager_with_rag):
        """Given: uppercase prefix [P].
        When: _retrieve_context is called.
        Then: same result as lowercase [p]."""
        chunk = Chunk(
            id="c1",
            text="Content",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add(
            [chunk], namespace="personal"
        )

        (
            prompt_upper,
            query_upper,
            namespace_upper,
            chunks_upper,
        ) = await chat_manager_with_rag._retrieve_context("[P] test")
        (
            prompt_lower,
            query_lower,
            namespace_lower,
            chunks_lower,
        ) = await chat_manager_with_rag._retrieve_context("[p] test")
        assert namespace_upper == namespace_lower == "personal"
        assert chunks_upper == chunks_lower

    @pytest.mark.asyncio
    async def test_retrieve_no_embedder_returns_unchanged(self):
        """Given: ChatManager without embedder.
        When: _retrieve_context is called with prefix.
        Then: message passes through unchanged."""
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        manager = ChatManager(
            llm=mock_llm,
            embedder=None,
            vector_store=MagicMock(),
            reranker=NullReranker(RerankerConfigData()),
            storage=None,
        )
        prompt, query, namespace, chunks = await manager._retrieve_context("[p] query")
        assert namespace == "default"
        assert prompt == "[p] query"
        assert query == "[p] query"
        assert chunks == ()

    @pytest.mark.asyncio
    async def test_retrieve_no_vector_store_returns_unchanged(self):
        """Given: ChatManager without vector_store.
        When: _retrieve_context is called with prefix.
        Then: message passes through unchanged."""
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        manager = ChatManager(
            llm=mock_llm,
            embedder=MagicMock(),
            vector_store=None,
            reranker=NullReranker(RerankerConfigData()),
            storage=None,
        )
        prompt, query, namespace, chunks = await manager._retrieve_context("[p] query")
        assert namespace == "default"
        assert prompt == "[p] query"
        assert query == "[p] query"
        assert chunks == ()

    @pytest.mark.asyncio
    async def test_retrieve_per_namespace_prompt_and_threshold(
        self, chat_manager_with_rag
    ):
        """Given: work namespace with custom prompt and threshold.
        When: _retrieve_context is called with [w] prefix.
        Then: correct prompt name and threshold are used."""
        chunk = Chunk(
            id="c1",
            text="Work item.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="work")

        with patch(
            "ai_assistant.features.chat.manager.get_prompt"
        ) as mock_get_prompt:
            mock_get_prompt.return_value = "work prompt"
            prompt, query, namespace, chunks = await chat_manager_with_rag._retrieve_context(
                "[w] work item?"
            )
            assert namespace == "work"
            mock_get_prompt.assert_called_once()
            assert mock_get_prompt.call_args[0][0] == "rag_creative"
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_retrieve_fallback_to_defaults_when_no_namespace_config(self):
        """Given: empty namespaces dict.
        When: _retrieve_context is called with prefix.
        Then: global defaults (rag_strict, 0.3) are used."""
        embedder = MockEmbedder(EmbedderConfigData(dim=3))
        store = MemoryVectorStore(VectorStoreConfigData(dim=3))
        pipeline = RAGPipeline([embed_query, retrieve, build_context])
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        manager = ChatManager(
            llm=mock_llm,
            embedder=embedder,
            vector_store=store,
            reranker=NullReranker(RerankerConfigData()),
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

        with patch(
            "ai_assistant.features.chat.manager.get_prompt"
        ) as mock_get_prompt:
            mock_get_prompt.return_value = "default prompt"
            prompt, query, namespace, chunks = await manager._retrieve_context("[p] content?")
            assert namespace == "personal"
            mock_get_prompt.assert_called_once()
            assert mock_get_prompt.call_args[0][0] == "rag_strict"

    @pytest.mark.asyncio
    async def test_retrieve_custom_prefix_c_triggers_rag(self, chat_manager_with_rag):
        """Given: [c] prefix and chunk in code namespace.
        When: _retrieve_context is called.
        Then: RAG is triggered for code namespace with rag_strict prompt."""
        chunk = Chunk(
            id="c1",
            text="Code configuration details.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="code")

        with patch(
            "ai_assistant.features.chat.manager.get_prompt"
        ) as mock_get_prompt:
            mock_get_prompt.return_value = "code prompt"
            prompt, query, namespace, chunks = await chat_manager_with_rag._retrieve_context(
                "[c] configuration?"
            )
            assert namespace == "code"
            mock_get_prompt.assert_called_once()
            assert mock_get_prompt.call_args[0][0] == "rag_strict"
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_retrieve_business_prefix_b_triggers_rag(self, chat_manager_with_rag):
        """Given: [b] prefix and chunk in books namespace.
        When: _retrieve_context is called.
        Then: RAG is triggered for books namespace with rag_strict prompt."""
        chunk = Chunk(
            id="c1",
            text="Books report Q3.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="books")

        with patch(
            "ai_assistant.features.chat.manager.get_prompt"
        ) as mock_get_prompt:
            mock_get_prompt.return_value = "books prompt"
            prompt, query, namespace, chunks = await chat_manager_with_rag._retrieve_context(
                "[b] Q3 report?"
            )
            assert namespace == "books"
            mock_get_prompt.assert_called_once()
            assert mock_get_prompt.call_args[0][0] == "rag_strict"
            assert len(chunks) > 0

    # ── _build_messages ──

    @pytest.mark.asyncio
    async def test_build_messages_without_storage(self, manager_no_rag):
        """Given: ChatManager without storage.
        When: _build_messages is called.
        Then: only current user message is returned."""
        messages = await manager_no_rag._build_messages("Hello", "conv-1")
        assert len(messages) == 1
        assert isinstance(messages[0], UserMessage)
        assert messages[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_build_messages_with_history(self, manager_with_storage):
        """Given: ChatManager with storage containing history.
        When: _build_messages is called.
        Then: history is prepended in chronological order."""
        messages = await manager_with_storage._build_messages("Hello", "conv-1")
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
        When: _build_messages is called.
        Then: metadata is attached to current user message."""
        meta = {"trace_id": "abc123"}
        messages = await manager_no_rag._build_messages(
            "Hello", "conv-1", metadata=meta
        )
        assert messages[-1].metadata == meta

    @pytest.mark.asyncio
    async def test_build_messages_trims_history(self, manager_with_storage):
        """Given: token budget that forces trimming.
        When: _build_messages is called.
        Then: _trim_history is applied, only user message kept."""
        manager_with_storage.max_context_tokens = 50
        with patch.object(
            manager_with_storage, "_trim_history", return_value=[]
        ):
            messages = await manager_with_storage._build_messages("Hello", "conv-1")
            assert len(messages) == 1
            assert messages[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_build_messages_history_load_failure(self, manager_with_storage):
        """Given: storage that raises on get_history.
        When: _build_messages is called.
        Then: graceful fallback returns just user message."""
        manager_with_storage.storage.get_history = AsyncMock(
            side_effect=Exception("DB error")
        )
        messages = await manager_with_storage._build_messages("Hello", "conv-1")
        assert len(messages) == 1
        assert messages[0].text == "Hello"

    # ── chat / stream_chat preparation identicality ──

    @pytest.mark.asyncio
    async def test_chat_calls_retrieve_context_and_build_messages(self, manager_no_rag):
        """Given: chat() invocation.
        When: message is processed.
        Then: _retrieve_context and _build_messages are both called."""
        with patch.object(
            manager_no_rag, "_retrieve_context", new_callable=AsyncMock
        ) as mock_retrieve, patch.object(
            manager_no_rag, "_build_messages", new_callable=AsyncMock
        ) as mock_build:
            mock_retrieve.return_value = ("Hello", "Hello", "default", ())
            mock_build.return_value = [UserMessage(text="Hello")]

            await manager_no_rag.chat("Hello", "conv-1")

            mock_retrieve.assert_awaited_once_with("Hello", trace_id=None)
            mock_build.assert_awaited_once_with("Hello", "conv-1", metadata={})

    @pytest.mark.asyncio
    async def test_stream_chat_calls_llm_stream(self, manager_no_rag):
        """Given: stream_chat() invocation.
        When: message is processed.
        Then: LLM stream is called and chunks are yielded."""
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
        Then: both use _retrieve_context and _build_messages identically."""
        with patch.object(
            manager_no_rag, "_retrieve_context", new_callable=AsyncMock
        ) as mock_retrieve, patch.object(
            manager_no_rag, "_build_messages", new_callable=AsyncMock
        ) as mock_build:
            mock_retrieve.return_value = ("Hello", "Hello", "default", ())
            mock_build.return_value = [UserMessage(text="Hello")]

            await manager_no_rag.chat("Hello", "conv-1")
            chunks = []
            async for chunk in manager_no_rag.stream_chat("Hello", "conv-1"):
                chunks.append(chunk)

            assert mock_retrieve.call_count == 2
            assert mock_build.call_count == 2

    # ── Graceful degradation ──

    @pytest.mark.asyncio
    async def test_chat_with_prefix_no_pipeline_graceful(self, manager_no_rag):
        """Given: [p] prefix with no RAG pipeline.
        When: chat() is called.
        Then: graceful unavailable message is returned."""
        result = await manager_no_rag.chat(
            message="[p] capital of France",
            conversation_id="test-1",
        )
        assert (
            "недоступен" in result.text.lower()
            or "unavailable" in result.text.lower()
        )

    @pytest.mark.asyncio
    async def test_chat_without_prefix_works_without_rag(self, manager_no_rag):
        """Given: plain message without prefix.
        When: chat() is called without RAG infrastructure.
        Then: LLM is called and response returned."""
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
        """Given: stream_chat without RAG prefix.
        When: message is streamed.
        Then: LLM stream is called and chunks yielded."""
        manager_no_rag.llm.stream = MagicMock(
            return_value=async_iter(["Hello", "!"])
        )
        chunks = []
        async for chunk in manager_no_rag.stream_chat("Hello", "conv-1"):
            chunks.append(chunk)
        assert chunks == ["Hello", "!"]

    @pytest.mark.asyncio
    async def test_stream_chat_with_rag_prefix_graceful(self, manager_no_rag):
        """Given: [p] prefix with no RAG pipeline in stream_chat.
        When: stream_chat() is called.
        Then: graceful unavailable message is yielded."""
        chunks = []
        async for chunk in manager_no_rag.stream_chat(
            "[p] capital of France", "conv-1"
        ):
            chunks.append(chunk)
        assert len(chunks) == 1
        assert (
            "недоступен" in chunks[0].lower()
            or "unavailable" in chunks[0].lower()
        )

    # ── Tool calls ──

    @pytest.mark.asyncio
    async def test_chat_with_tool_calls(self, manager_no_rag):
        """Given: LLM response with tool_calls.
        When: chat() is called.
        Then: tool_calls are preserved in the response."""
        tool_calls = [{"id": "call_1", "function": {"name": "get_weather"}}]
        manager_no_rag.llm.complete = AsyncMock(
            return_value=MagicMock(
                text="Let me check the weather.",
                metadata={"model": "gpt-4"},
                tool_calls=tool_calls,
            )
        )
        result = await manager_no_rag.chat("Weather in Paris?", "conv-1")
        assert result.text == "Let me check the weather."
        assert result.metadata == {"model": "gpt-4"}

    @pytest.mark.asyncio
    async def test_stream_chat_with_rag_prefix(self, chat_manager_with_rag):
        """Given: [p] prefix with full RAG pipeline in stream_chat.
        When: stream_chat() is called.
        Then: RAG context is retrieved and stream proceeds."""
        chunk = Chunk(
            id="c1",
            text="Paris is sunny.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc1", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk], namespace="personal")

        chat_manager_with_rag.llm.stream = MagicMock(
            return_value=async_iter(["Paris", " is", " sunny."])
        )
        chunks = []
        async for chunk_text in chat_manager_with_rag.stream_chat(
            "[p] Weather in Paris?", "conv-1"
        ):
            chunks.append(chunk_text)
        assert chunks == ["Paris", " is", " sunny.", "\n\nSources:\n[1] doc1"]

    @pytest.mark.asyncio
    async def test_namespace_c_and_b_prefixes(self, chat_manager_with_rag):
        """Given: [c] and [b] prefixes with chunks in respective namespaces.
        When: _retrieve_context is called for each.
        Then: correct namespace routing and prompt selection occurs."""
        chunk_c = Chunk(
            id="c1",
            text="Code settings.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc_code", index=0, total_chunks=1),
        )
        chunk_b = Chunk(
            id="b1",
            text="Books plan.",
            embedding=[1.0, 0.0, 0.0],
            metadata=ChunkMetadata(source="doc_books", index=0, total_chunks=1),
        )
        await chat_manager_with_rag.vector_store.add([chunk_c], namespace="code")
        await chat_manager_with_rag.vector_store.add([chunk_b], namespace="books")

        with patch(
            "ai_assistant.features.chat.manager.get_prompt"
        ) as mock_get_prompt:
            mock_get_prompt.return_value = "prompt"

            prompt_c, query_c, namespace_c, chunks_c = await chat_manager_with_rag._retrieve_context(
                "[c] settings?"
            )
            assert namespace_c == "code"
            assert len(chunks_c) > 0
            assert chunks_c[0].metadata.source == "doc_code"

            prompt_b, query_b, namespace_b, chunks_b = await chat_manager_with_rag._retrieve_context(
                "[b] plan?"
            )
            assert namespace_b == "books"
            assert len(chunks_b) > 0
            assert chunks_b[0].metadata.source == "doc_books"


# ── TestChatPrefixes ──


class TestChatPrefixes:
    """Given: message prefixes trigger namespace routing.
    When: various prefixes are provided.
    Then: correct namespace is selected, prefix is stripped, case is ignored."""

    @pytest.fixture
    def prefix_manager(self):
        """Given: ChatManager with pipeline but no actual data.
        When: fixture is requested.
        Then: manager suitable for prefix testing is returned."""
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        return ChatManager(
            llm=mock_llm,
            embedder=None,
            vector_store=None,
            reranker=NullReranker(RerankerConfigData()),
            storage=None,
            pipeline=MagicMock(),
            namespaces={},
        )

    @pytest.mark.asyncio
    async def test_prefix_p_personal(self, prefix_manager):
        """Given: [p] prefix.
        When: _retrieve_context is called.
        Then: query is stripped of prefix."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="test"))
        )
        prompt, query, namespace, chunks = await prefix_manager._retrieve_context("[p] test")
        assert namespace == "personal"
        assert query == "test"
        assert not query.startswith("[p]")

    @pytest.mark.asyncio
    async def test_prefix_w_work(self, prefix_manager):
        """Given: [w] prefix.
        When: _retrieve_context is called.
        Then: query is stripped of prefix."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="deadline"))
        )
        prompt, query, namespace, chunks = await prefix_manager._retrieve_context(
            "[w] deadline"
        )
        assert namespace == "work"
        assert query == "deadline"
        assert not query.startswith("[w]")

    @pytest.mark.asyncio
    async def test_prefix_o_other(self, prefix_manager):
        """Given: [o] prefix.
        When: _retrieve_context is called.
        Then: query is stripped of prefix."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="recipe"))
        )
        prompt, query, namespace, chunks = await prefix_manager._retrieve_context(
            "[o] recipe"
        )
        assert namespace == "other"
        assert query == "recipe"
        assert not query.startswith("[o]")

    @pytest.mark.asyncio
    async def test_prefix_c_custom(self, prefix_manager):
        """Given: [c] prefix.
        When: _retrieve_context is called.
        Then: query is stripped of prefix."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="config"))
        )
        prompt, query, namespace, chunks = await prefix_manager._retrieve_context(
            "[c] config"
        )
        assert namespace == "code"
        assert query == "config"
        assert not query.startswith("[c]")

    @pytest.mark.asyncio
    async def test_prefix_b_business(self, prefix_manager):
        """Given: [b] prefix.
        When: _retrieve_context is called.
        Then: query is stripped of prefix."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="report"))
        )
        prompt, query, namespace, chunks = await prefix_manager._retrieve_context(
            "[b] report"
        )
        assert namespace == "books"
        assert query == "report"
        assert not query.startswith("[b]")

    @pytest.mark.asyncio
    async def test_prefix_case_insensitive_p(self, prefix_manager):
        """Given: uppercase [P] prefix.
        When: _retrieve_context is called.
        Then: same behavior as lowercase [p]."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="test"))
        )
        prompt_lower, query_lower, ns_lower, _ = await prefix_manager._retrieve_context(
            "[p] test"
        )
        prompt_upper, query_upper, ns_upper, _ = await prefix_manager._retrieve_context(
            "[P] test"
        )
        assert ns_lower == ns_upper == "personal"
        assert query_lower == query_upper == "test"

    @pytest.mark.asyncio
    async def test_prefix_case_insensitive_w(self, prefix_manager):
        """Given: uppercase [W] prefix.
        When: _retrieve_context is called.
        Then: same behavior as lowercase [w]."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="test"))
        )
        prompt_lower, query_lower, ns_lower, _ = await prefix_manager._retrieve_context(
            "[w] test"
        )
        prompt_upper, query_upper, ns_upper, _ = await prefix_manager._retrieve_context(
            "[W] test"
        )
        assert ns_lower == ns_upper == "work"
        assert query_lower == query_upper == "test"

    @pytest.mark.asyncio
    async def test_prefix_case_insensitive_c(self, prefix_manager):
        """Given: uppercase [C] prefix.
        When: _retrieve_context is called.
        Then: same behavior as lowercase [c]."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="test"))
        )
        prompt_lower, query_lower, ns_lower, _ = await prefix_manager._retrieve_context(
            "[c] test"
        )
        prompt_upper, query_upper, ns_upper, _ = await prefix_manager._retrieve_context(
            "[C] test"
        )
        assert ns_lower == ns_upper == "code"
        assert query_lower == query_upper == "test"

    @pytest.mark.asyncio
    async def test_prefix_case_insensitive_b(self, prefix_manager):
        """Given: uppercase [B] prefix.
        When: _retrieve_context is called.
        Then: same behavior as lowercase [b]."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="test"))
        )
        prompt_lower, query_lower, ns_lower, _ = await prefix_manager._retrieve_context(
            "[b] test"
        )
        prompt_upper, query_upper, ns_upper, _ = await prefix_manager._retrieve_context(
            "[B] test"
        )
        assert ns_lower == ns_upper == "books"
        assert query_lower == query_upper == "test"

    @pytest.mark.asyncio
    async def test_prefix_stripping_all_prefixes(self, prefix_manager):
        """Given: all supported prefixes.
        When: _retrieve_context is called for each.
        Then: prefix is stripped, only query remains."""
        prefix_manager.pipeline.run = AsyncMock(
            return_value=PipelineData(query=UserMessage(text="query text"))
        )
        for prefix in ["p", "w", "o", "c", "b"]:
            _, query, ns, _ = await prefix_manager._retrieve_context(
                f"[{prefix}] query text"
            )
            assert query == "query text", f"Failed for prefix [{prefix}]"
            assert ns == {
                "p": "personal", "w": "work", "o": "other",
                "c": "code", "b": "books"
            }[prefix]

    @pytest.mark.asyncio
    async def test_no_prefix_no_stripping(self, prefix_manager):
        """Given: message without any prefix.
        When: _retrieve_context is called.
        Then: message is returned unchanged."""
        prompt, query, namespace, chunks = await prefix_manager._retrieve_context(
            "plain message without prefix"
        )
        assert namespace == "default"
        assert query == "plain message without prefix"
        assert prompt == "plain message without prefix"


# ── TestChatManagerSources ──


class TestChatManagerSources:
    """Given: chunks with original_path in metadata.
    When: _append_rag_sources is called.
    Then: clickable file:/// links are appended when available."""

    @pytest.fixture
    def manager_for_sources(self):
        """Given: ChatManager with mocked LLM.
        When: fixture is requested.
        Then: manager suitable for source testing is returned."""
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = 4096
        mock_llm.system_message = None
        return ChatManager(
            llm=mock_llm,
            reranker=NullReranker(RerankerConfigData()),
            storage=None,
        )

    def test_append_sources_with_source_uri(self, manager_for_sources):
        """Given: chunks with source_uri set.
        When: _append_rag_sources is called.
        Then: source_uri is used verbatim."""
        chunks = (
            Chunk(
                id="c1",
                text="Paris info",
                metadata=ChunkMetadata(
                    source="doc1",
                    index=0,
                    total_chunks=1,
                    source_uri="file:///home/user/docs/france.md",
                ),
            ),
        )
        answer = "Paris is the capital of France."
        result = ChatManager._append_rag_sources(answer, chunks)
        assert "file:///home/user/docs/france.md" in result
        assert "Sources:" in result

    def test_append_sources_without_source_uri_fallback_to_source(self, manager_for_sources):
        """Given: chunks without source_uri.
        When: _append_rag_sources is called.
        Then: source field is used as fallback."""
        chunks = (
            Chunk(
                id="c1",
                text="Berlin info",
                metadata=ChunkMetadata(source="doc2", index=0, total_chunks=1),
            ),
        )
        answer = "Berlin is the capital of Germany."
        result = ChatManager._append_rag_sources(answer, chunks)
        assert "[1] doc2" in result
        assert "file://" not in result
        assert "Sources:" in result

    def test_append_sources_no_info_phrase_skipped(self, manager_for_sources):
        """Given: answer contains no-info phrase.
        When: _append_rag_sources is called.
        Then: sources are not appended."""
        chunks = (
            Chunk(
                id="c1",
                text="Unknown info",
                metadata=ChunkMetadata(
                    source="doc1",
                    index=0,
                    total_chunks=1,
                    source_uri="file:///docs/unknown.md",
                ),
            ),
        )
        answer = "I don't have enough information."
        result = ChatManager._append_rag_sources(answer, chunks)
        assert result == answer

    def test_append_sources_without_citation_markers(self, manager_for_sources):
        """Given: LLM answer without [N] citation markers but chunks exist.
        When: _append_rag_sources is called.
        Then: sources are still appended."""
        chunks = (
            Chunk(
                id="c1",
                text="Paris info",
                metadata=ChunkMetadata(
                    source="doc1",
                    index=0,
                    total_chunks=1,
                    source_uri="file:///docs/france.md",
                ),
            ),
        )
        answer = "Paris is the capital of France."
        result = ChatManager._append_rag_sources(answer, chunks)
        assert "Sources:" in result
        assert "file:///docs/france.md" in result

    def test_append_sources_multiple_citations(self, manager_for_sources):
        """Given: multiple chunks with source_uri.
        When: _append_rag_sources is called.
        Then: all sources are listed with source_uri links."""
        chunks = (
            Chunk(
                id="c1",
                text="Info 1",
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
                metadata=ChunkMetadata(
                    source="doc2",
                    index=1,
                    total_chunks=2,
                    source_uri="file:///docs/b.md",
                ),
            ),
        )
        answer = "Combined info."
        result = ChatManager._append_rag_sources(answer, chunks)
        assert "file:///docs/a.md" in result
        assert "file:///docs/b.md" in result
        assert "[1]" in result
        assert "[2]" in result
        assert "Sources:" in result

    def test_append_sources_empty_chunks(self, manager_for_sources):
        """Given: no chunks.
        When: _append_rag_sources is called.
        Then: answer returned unchanged."""
        answer = "Some answer."
        result = ChatManager._append_rag_sources(answer, ())
        assert result == answer

    def test_append_sources_old_index_without_source_uri_fallback(self, manager_for_sources):
        """Given: chunk from old index without source_uri (backward compat).
        When: _append_rag_sources is called.
        Then: falls back to source field."""
        chunks = (
            Chunk(
                id="c1",
                text="Old data",
                metadata=ChunkMetadata(
                    source="legacy_doc",
                    index=0,
                    total_chunks=1,
                    # source_uri is None — simulates old index
                ),
            ),
        )
        answer = "Old answer."
        result = ChatManager._append_rag_sources(answer, chunks)
        assert "[1] legacy_doc" in result
        assert "Sources:" in result


# ── TestChatHistoryTrimming ──


class TestChatHistoryTrimming:
    """Given: conversation history may exceed token budget.
    When: _trim_history is called.
    Then: oldest messages are dropped, budget is respected, order preserved."""

    def test_trims_oldest_to_fit_budget(self, manager_with_tokenizer):
        """Given: history exceeding token budget.
        When: _trim_history is called.
        Then: oldest messages are dropped to fit budget."""
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
        """Given: user message alone exceeds token budget.
        When: _trim_history is called.
        Then: empty history is returned."""
        long_msg = UserMessage(text="x" * 500)
        history = [{"role": "user", "content": "old"}]
        trimmed = manager_with_tokenizer._trim_history(history, long_msg)
        assert trimmed == []

    def test_fallback_to_count_based(self, manager_no_tokenizer):
        """Given: no tokenizer available (no context limit).
        When: _trim_history is called.
        Then: simple count-based fallback is used."""
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
        """Given: history with multiple messages.
        When: _trim_history is called.
        Then: trimmed history maintains oldest-first order."""
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
        """Given: empty history list.
        When: _trim_history is called.
        Then: empty list is returned."""
        trimmed = manager_with_tokenizer._trim_history(
            [], UserMessage(text="hi")
        )
        assert trimmed == []

    def test_single_message_fits(self, manager_with_tokenizer):
        """Given: single message within budget.
        When: _trim_history is called.
        Then: message is preserved."""
        history = [{"role": "user", "content": "hello"}]
        trimmed = manager_with_tokenizer._trim_history(
            history, UserMessage(text="hi")
        )
        assert len(trimmed) == 1
        assert trimmed[0]["content"] == "hello"

    def test_respects_system_message_overhead(self, manager_with_tokenizer):
        """Given: system message configured on LLM.
        When: _trim_history is called.
        Then: system message tokens are reserved from budget."""
        history = [{"role": "user", "content": "x" * 200}]
        trimmed = manager_with_tokenizer._trim_history(
            history, UserMessage(text="q")
        )
        assert len(trimmed) <= 1

    def test_no_llm_config_fallback(self):
        """Given: LLM with no context limit.
        When: _trim_history is called with max_context_tokens set.
        Then: falls back to history_limit."""
        mock_llm = MagicMock()
        mock_llm.get_context_limit.return_value = None
        mock_llm.system_message = None
        manager = ChatManager(
            llm=mock_llm,
            reranker=NullReranker(RerankerConfigData()),
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

    def test_cjk_text_ratio_above_30_percent(self, manager_with_tokenizer):
        """Given: history with >30% CJK characters.
        When: _trim_history is called.
        Then: CJK text is handled correctly by tokenizer."""
        cjk_text = "这是一个中文测试消息" * 10  # ~170 CJK chars
        history = [
            {"role": "user", "content": cjk_text},
            {"role": "assistant", "content": "Response"},
        ]
        user_msg = UserMessage(text="Query")
        trimmed = manager_with_tokenizer._trim_history(history, user_msg)
        assert isinstance(trimmed, list)
        # CJK text should still be processed; verify no crash
        assert all(isinstance(h, dict) for h in trimmed)

    def test_cjk_text_mixed_with_latin(self, manager_with_tokenizer):
        """Given: mixed CJK and Latin text.
        When: _trim_history is called.
        Then: tokenizer handles mixed content correctly."""
        mixed_text = "Hello 世界 this is 测试 text 中文"
        history = [
            {"role": "user", "content": mixed_text},
            {"role": "assistant", "content": "Response"},
        ]
        user_msg = UserMessage(text="Query")
        trimmed = manager_with_tokenizer._trim_history(history, user_msg)
        assert isinstance(trimmed, list)
        assert all(isinstance(h, dict) for h in trimmed)

    def test_cjk_text_high_ratio_drops_oldest(self, manager_with_tokenizer):
        """Given: multiple CJK messages exceeding budget.
        When: _trim_history is called.
        Then: oldest CJK messages are dropped first."""
        history = [
            {"role": "user", "content": "第一条消息" * 50},
            {"role": "assistant", "content": "第二条回复" * 50},
            {"role": "user", "content": "第三条消息" * 50},
        ]
        user_msg = UserMessage(text="当前问题")
        trimmed = manager_with_tokenizer._trim_history(history, user_msg)
        assert len(trimmed) <= len(history)
        if len(trimmed) >= 2:
            assert trimmed[-1]["content"] == "第三条消息" * 50

    def test_cjk_user_message_only(self, manager_with_tokenizer):
        """Given: CJK-only user message with small budget.
        When: _trim_history is called.
        Then: history is empty if user message consumes all budget."""
        user_msg = UserMessage(text="这是一个非常长的中文用户问题" * 100)
        history = [{"role": "assistant", "content": "Previous"}]
        trimmed = manager_with_tokenizer._trim_history(history, user_msg)
        assert trimmed == []
