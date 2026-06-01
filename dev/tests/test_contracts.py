from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from ai_assistant.api.deps import init_adapters
from ai_assistant.core.config import load_config
from ai_assistant.core.ports import (
    IChatStorage,
    IChunker,
    IEmbedder,
    ILLM,
    ILongTermMemory,
    IReranker,
    IVisionProcessor,
    IVoiceRecognizer,
    IVoiceSynthesizer,
    IVectorStore,
)
from ai_assistant.features.chat.manager import ChatManager
from ai_assistant.features.chat.schemas import (
    ChatRequest,
    ChatResponse,
    OAIChatCompletionRequest,
)
from ai_assistant.features.rag.manager import RAGManager
from ai_assistant.features.rag.schemas import IndexRequest, QueryRequest, QueryResponse


class TestChatContracts:
    def test_chat_request_validation(self):
        valid = {"message": "test"}
        assert ChatRequest(**valid)
        # Empty message is allowed in current schema (no min_length constraint)
        assert ChatRequest(message="")

    def test_oai_chat_request_strict(self):
        valid = {"messages": [{"role": "user", "content": "hi"}]}
        assert OAIChatCompletionRequest(**valid)
        # content=None is allowed (str | None)
        assert OAIChatCompletionRequest(messages=[{"role": "user", "content": None}])

    def test_chat_response_structure(self, client):
        with patch.object(
            ChatManager,
            "chat",
            new_callable=AsyncMock,
            return_value=MagicMock(text="ok", metadata={}, tool_calls=[]),
        ):
            resp = client.post(
                "/api/v1/chat",
                json={"message": "contract test", "conversation_id": "t1"},
            )
            assert resp.status_code == 200
            ChatResponse(**resp.json())  # strict pydantic validation


class TestRAGContracts:
    def test_query_request_validation(self):
        valid = {"query": "test"}
        assert QueryRequest(**valid)

        with pytest.raises(ValidationError):
            QueryRequest(query="test", top_k=0)  # ge=1 constraint

        with pytest.raises(ValidationError):
            QueryRequest(query="test", top_k=51)  # le=50 constraint

    def test_index_request_validation(self):
        valid = {"documents": [{"id": "1", "content": "text"}]}
        assert IndexRequest(**valid)
        # dict[str, Any] has no required keys validation for inner dicts
        assert IndexRequest(documents=[{"id": "1"}])

    def test_rag_query_response_structure(self, client, mock_state):
        with patch.object(
            RAGManager,
            "query",
            new_callable=AsyncMock,
            return_value={
                "answer": "ok",
                "sources": [],
                "chunks_used": 0,
                "errors": [],
            },
        ):
            resp = client.post("/api/v1/rag/query", json={"query": "test"})
            assert resp.status_code == 200
            QueryResponse(**resp.json())


class TestSSEContract:
    def test_sse_format_compliance(self, client):
        async def _fake_stream(*args, **kwargs):
            yield "hello"

        with patch.object(ChatManager, "stream_chat", _fake_stream):
            resp = client.post(
                "/api/v1/chat/stream",
                json={"message": "sse test", "conversation_id": "t1"},
            )
            assert resp.status_code == 200
            assert "text/event-stream" in resp.headers["content-type"]

            lines = resp.text.strip().splitlines()
            for line in lines:
                if line.startswith("data:"):
                    # Validate SSE data payload isn't raw text leak
                    assert line[5:].strip(), "Empty SSE data chunk"


class TestHasattrBan:
    """AST-level contract: api/deps and api/lifespan must not use hasattr() to bypass ports."""

    def _find_hasattr_calls(self, source: str, filename: str) -> list[tuple[int, str]]:
        import ast

        tree = ast.parse(source)
        hits: list[tuple[int, str]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "hasattr":
                    hits.append((node.lineno, ast.unparse(node)))
        return hits

    def test_api_deps_no_hasattr(self):
        import inspect
        from ai_assistant.api import deps

        source = inspect.getsource(deps)
        hits = self._find_hasattr_calls(source, "deps.py")
        assert not hits, f"hasattr() found in api/deps.py at lines: {hits}"

    def test_api_lifespan_no_hasattr(self):
        import inspect
        from ai_assistant.api import lifespan

        source = inspect.getsource(lifespan)
        hits = self._find_hasattr_calls(source, "lifespan.py")
        assert not hits, f"hasattr() found in api/lifespan.py at lines: {hits}"


def test_pipeline_steps_no_kwargs() -> None:
    """AST check: pipeline step functions must not use **kwargs."""
    import ast
    from pathlib import Path

    steps_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "ai_assistant"
        / "pipeline"
        / "steps.py"
    )
    source = steps_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef):
            is_step = any(
                (isinstance(d, ast.Call) and getattr(d.func, "id", None) == "step")
                or (isinstance(d, ast.Name) and d.id == "step")
                for d in node.decorator_list
            )
            if is_step and node.args.kwarg is not None:
                pytest.fail(
                    f"Step function {node.name!r} uses **kwargs. "
                    f"Use StepContext instead."
                )


class TestInitAdaptersContracts:
    async def test_init_adapters_returns_typed_state(self) -> None:
        """Real init_adapters must produce instances that comply with port types."""
        config = load_config()
        state = await init_adapters(config)

        assert state.llm is None or isinstance(state.llm, ILLM)
        assert state.embedder is None or isinstance(state.embedder, IEmbedder)
        assert state.vector_store is None or isinstance(
            state.vector_store, IVectorStore
        )
        assert state.chunker is None or isinstance(state.chunker, IChunker)
        assert state.reranker is None or isinstance(state.reranker, IReranker)
        assert state.storage is None or isinstance(state.storage, IChatStorage)
        assert state.voice_recognizer is None or isinstance(
            state.voice_recognizer, IVoiceRecognizer
        )
        assert state.voice_synthesizer is None or isinstance(
            state.voice_synthesizer, IVoiceSynthesizer
        )
        assert state.vision is None or isinstance(state.vision, IVisionProcessor)
        assert state.long_term_memory is None or isinstance(
            state.long_term_memory, ILongTermMemory
        )


def test_llm_config_rejects_unknown_fields():
    """With extra='forbid', LLMConfig must reject typos like temperatur."""
    from pydantic import ValidationError
    from ai_assistant.core.config import LLMConfig

    with pytest.raises(ValidationError, match="temperatur"):
        LLMConfig(temperatur=0.5)


def test_embedder_config_rejects_unknown_fields():
    """With extra='forbid', EmbedderConfig must reject typos like chunck_size."""
    from pydantic import ValidationError
    from ai_assistant.core.config import EmbedderConfig

    with pytest.raises(ValidationError, match="chunck_size"):
        EmbedderConfig(chunck_size=512)


from pathlib import Path

PORTS_DIR = (
    Path(__file__).parent.parent.parent / "src" / "ai_assistant" / "core" / "ports"
)


def test_dead_ports_removed() -> None:
    """Phase 4.2: events.py and modality.py must be physically deleted."""
    assert not (PORTS_DIR / "events.py").exists()
    assert not (PORTS_DIR / "modality.py").exists()


class TestToolRegistryContracts:
    async def test_dispatch_propagates_cancelled_error(self):
        """asyncio.CancelledError must propagate, not be swallowed as ToolResult."""
        import asyncio

        from ai_assistant.core.ports.tools import ITool, ToolCall, ToolSpec
        from ai_assistant.core.tool_registry import ToolRegistry

        registry = ToolRegistry()

        mock_tool = MagicMock(spec=ITool)
        mock_tool.spec = ToolSpec(name="test_tool", description="test", parameters={})
        mock_tool.execute = AsyncMock(side_effect=asyncio.CancelledError("cancelled"))

        registry.register(mock_tool)

        call = ToolCall(tool_name="test_tool", arguments={}, call_id="test-1")
        with pytest.raises(asyncio.CancelledError):
            await registry.dispatch(call)
