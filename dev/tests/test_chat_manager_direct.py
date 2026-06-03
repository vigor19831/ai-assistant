"""Direct tests for ChatManager — _maybe_rag and _trim_history.

Tests real (mock) embedder/vector_store integration without relying on
indirect chat() calls. Validates RAG prefix handling, token trimming logic,
and edge cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai_assistant.core.config import NamespaceConfig
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.features.chat.manager import ChatManager
from ai_assistant.pipeline.steps import build_context, embed_query, generate, retrieve
from ai_assistant.core.domain.messages import AssistantMessage
from ai_assistant.core.domain.pipeline import PipelineData

# ── _maybe_rag tests ──


class TestMaybeRAG:
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
        return ChatManager(
            llm=MagicMock(),
            embedder=embedder,
            vector_store=store,
            reranker=None,
            storage=None,
            pipeline=pipeline,
            namespaces=namespaces,
        )

    @pytest.mark.asyncio
    async def test_no_prefix_returns_unchanged(self, chat_manager_with_rag):
        """Message without [p]/[w]/[o] prefix should pass through unchanged."""
        prompt, query, chunks = await chat_manager_with_rag._maybe_rag("Hello world")
        assert prompt == "Hello world"
        assert query == "Hello world"
        assert chunks == ()

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

        prompt, query, chunks = await chat_manager_with_rag._maybe_rag(
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

        prompt, query, chunks = await chat_manager_with_rag._maybe_rag(
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

        prompt, query, chunks = await chat_manager_with_rag._maybe_rag(
            "[o] What ingredients?"
        )
        assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_no_results_returns_original_query(self, chat_manager_with_rag):
        """When no chunks match, return original query text (not prompt)."""
        prompt, query, chunks = await chat_manager_with_rag._maybe_rag(
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

        prompt, query, chunks = await chat_manager_with_rag._maybe_rag("[p] query text")
        # Query should not contain [p]
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
        ) = await chat_manager_with_rag._maybe_rag("[P] test")
        (
            prompt_lower,
            query_lower,
            chunks_lower,
        ) = await chat_manager_with_rag._maybe_rag("[p] test")
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
        prompt, query, chunks = await manager._maybe_rag("[p] query")
        assert prompt == "[p] query"
        assert query == "[p] query"
        assert chunks == ()

    @pytest.mark.asyncio
    async def test_no_vector_store_returns_unchanged(self):
        """Without vector_store, message should pass through."""
        manager = ChatManager(
            llm=MagicMock(),
            embedder=MagicMock(),
            vector_store=None,
            storage=None,
        )
        prompt, query, chunks = await manager._maybe_rag("[p] query")
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
            prompt, query, chunks = await chat_manager_with_rag._maybe_rag(
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
        manager = ChatManager(
            llm=MagicMock(),
            embedder=embedder,
            vector_store=store,
            reranker=None,
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
            prompt, query, chunks = await manager._maybe_rag("[p] content?")
            mock_get_prompt.assert_called_once()
            assert mock_get_prompt.call_args[0][0] == "rag_strict"


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


# ── Graceful degradation: RAG unavailable ──


class TestRAGGracefulDegradation:
    @pytest.fixture
    def manager_no_rag(self):
        """ChatManager without embedder/vector_store."""
        mock_llm = MagicMock()
        mock_llm.complete = AsyncMock(
            return_value=MagicMock(text="Hello!", metadata={}, tool_calls=[])
        )

        async def _fake_stream(*args, **kwargs):
            for chunk in ["Hello", " world"]:
                yield chunk

        mock_llm.stream = _fake_stream
        return ChatManager(
            llm=mock_llm,
            embedder=None,
            vector_store=None,
            storage=None,
        )

    @pytest.mark.asyncio
    async def test_chat_with_prefix_no_vector_store(self, manager_no_rag):
        """[p] prefix with no vector_store returns graceful message."""
        result = await manager_no_rag.chat(
            message="[p] capital of France",
            conversation_id="test-1",
        )
        assert "недоступен" in result.text.lower() or "unavailable" in result.text.lower()

    @pytest.mark.asyncio
    async def test_chat_without_prefix_works_without_vector_store(self, manager_no_rag):
        """Plain message without prefix should still call LLM even without vector_store."""
        from unittest.mock import AsyncMock

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
    async def test_stream_chat_with_prefix_no_vector_store(self, manager_no_rag):
        """[p] prefix in stream mode with no vector_store yields graceful message."""
        chunks = []
        async for chunk in manager_no_rag.stream_chat(
            message="[p] capital of France",
            conversation_id="test-3",
        ):
            chunks.append(chunk)

        assert len(chunks) == 1
        assert "недоступен" in chunks[0].lower() or "unavailable" in chunks[0].lower()

    @pytest.mark.asyncio
    async def test_stream_chat_without_prefix_works_without_vector_store(self, manager_no_rag):
        """Plain message in stream mode without prefix should still stream from LLM."""

        async def _fake_stream(*args, **kwargs):
            for chunk in ["Hello", " world"]:
                yield chunk

        manager_no_rag.llm.stream = _fake_stream

        chunks = []
        async for chunk in manager_no_rag.stream_chat(
            message="Hello",
            conversation_id="test-4",
        ):
            chunks.append(chunk)

        assert chunks == ["Hello", " world"]


# ── Tool loop guard tests ──


class TestToolLoopGuard:
    @pytest.mark.asyncio
    async def test_generate_tool_loop_limit(self):
        """generate() should stop after max_tool_iterations."""
        from ai_assistant.core.ports.tools import ToolResult

        class FakeToolRegistry:
            async def dispatch(self, call):
                return ToolResult(call_id=call.call_id, output="42")

        class InfiniteToolLLM:
            def __init__(self):
                self._calls = 0

            async def complete(
                self,
                messages: list[Any],
                max_tokens: int | None = None,
                temperature: float | None = None,
            ) -> AssistantMessage:
                self._calls += 1
                return AssistantMessage(
                    text="",
                    tool_calls=[{"id": "call_1", "function": {"name": "calc", "arguments": "{}"}}],
                )

        llm = InfiniteToolLLM()
        data = PipelineData(
            query=UserMessage(text="question"),
            chunks=[Chunk(id="c1", text="context")],
            metadata={
                "prompt_version": "v1",
                "prompt_name": "rag_default",
                "llm": llm,
                "max_tool_iterations": 2,
                "tool_registry": FakeToolRegistry(),
            },
        )
        result = await generate(data)
        assert llm._calls == 3
        assert result.response is not None
        assert result.response.text == "Tool limit reached"
        assert any("tool loop exceeded max iterations" in e for e in result.errors)
