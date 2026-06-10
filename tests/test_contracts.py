from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from ai_assistant.api.deps import InitializedAppState, init_adapters
from ai_assistant.core.config import load_config, LLMConfig
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.core.ports import (
    IChatStorage,
    IChunker,
    IClosable,
    IEmbedder,
    ILLM,
    IReranker,
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
        Path(__file__).parent.parent
        / "src"
        / "ai_assistant"
        / "core"
        / "pipeline_steps.py"
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
    async def test_init_adapters_returns_initialized_state(self) -> None:
        """Real init_adapters must produce InitializedAppState with non-None core adapters."""
        config = load_config()
        state = await init_adapters(config)

        assert isinstance(state, InitializedAppState)
        assert state.llm is not None
        assert state.embedder is not None
        assert state.vector_store is not None
        assert isinstance(state.chunker, IChunker)
        assert isinstance(state.reranker, IReranker)
        assert state.storage is not None
        assert state.pipeline is not None


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


def test_vector_store_relevance_threshold_backward_compatible():
    """Removed field vector_store.relevance_threshold is migrated to rag."""
    from ai_assistant.core.config import AppConfig

    # When rag lacks the field, vector_store value is migrated
    cfg = AppConfig(
        vector_store={"relevance_threshold": 0.5, "dim": 384},
    )
    assert cfg.rag.relevance_threshold == 0.5
    assert not hasattr(cfg.vector_store, "relevance_threshold")

    # When rag already has the field, it wins
    cfg2 = AppConfig(
        vector_store={"relevance_threshold": 0.5, "dim": 384},
        rag={"relevance_threshold": 0.2},
    )
    assert cfg2.rag.relevance_threshold == 0.2

def test_load_config_rejects_unknown_yaml_key(tmp_path):
    """AppConfig uses extra='forbid': unknown YAML keys raise ValidationError."""
    from pydantic import ValidationError

    yaml_file = tmp_path / "config.yaml"
    yaml_file.write_text("debug: false\nunknown_key: 123\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="extra_forbidden"):
        load_config(str(yaml_file))


# Env-var strict check requires CORE CHANGE (extra="forbid" on AppConfig).
# Pydantic-settings filters unknown env vars before extra="forbid" sees them,
# making a reliable warning impossible without fragile internals traversal.
# Defer to ADR-XXX if strict env-var validation is needed.


from pathlib import Path

PORTS_DIR = (
    Path(__file__).parent.parent / "src" / "ai_assistant" / "core" / "ports"
)


def test_registry_removed() -> None:
    """Phase 4.4: registry.py must be physically deleted."""
    from pathlib import Path
    core_dir = Path(__file__).parent.parent / "src" / "ai_assistant" / "core"
    assert not (core_dir / "registry.py").exists()


def test_illm_has_get_context_limit():
    """Verify ILLM port declares get_context_limit abstract method."""
    assert hasattr(ILLM, 'get_context_limit')
    assert callable(getattr(ILLM, 'get_context_limit'))


def test_mock_llm_get_context_limit_returns_int():
    cfg = LLMConfig(model="test", max_tokens=2048)
    llm = MockLLM(cfg)
    assert llm.get_context_limit() == 2048


def test_mock_llm_get_context_limit_fallback():
    cfg = LLMConfig(model="test")
    llm = MockLLM(cfg)
    assert llm.get_context_limit() == 4096


class TestVectorStorePort:
    """IVectorStore port contract tests — index_path property."""

    def test_index_path_property_exists(self):
        """All vector store adapters must expose index_path as a str property."""
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
        from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
        from ai_assistant.core.config import VectorStoreConfig

        cfg = VectorStoreConfig(index_path="./data/test_indices", dim=384)

        faiss_store = FaissVectorStore(cfg)
        assert faiss_store.index_path == "./data/test_indices"
        assert isinstance(faiss_store.index_path, str)

        mem_store = MemoryVectorStore(cfg)
        assert mem_store.index_path == "./data/test_indices"
        assert isinstance(mem_store.index_path, str)

    def test_index_path_default_for_memory(self):
        """MemoryVectorStore provides a sensible default when index_path is absent."""
        from ai_assistant.adapters.vector_store_memory import MemoryVectorStore

        class _MinimalConfig:
            dim = 384
            # no index_path attribute

        store = MemoryVectorStore(_MinimalConfig())
        assert isinstance(store.index_path, str)
        assert store.index_path == "./data/indices/memory"

    def test_index_path_default_for_faiss(self):
        """FaissVectorStore provides a sensible default when index_path is absent."""
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        class _MinimalConfig:
            dim = 384
            metric = "l2"
            # no index_path attribute

        store = FaissVectorStore(_MinimalConfig())
        assert isinstance(store.index_path, str)
        assert store.index_path == "./data/indices/faiss"


def test_message_type_alias_excludes_dict():
    """Message alias must be UserMessage | AssistantMessage | ToolMessage, no dict fallback."""
    from typing import get_args, get_origin

    from ai_assistant.core.ports.llm import Message
    from ai_assistant.core.domain.messages import (
        AssistantMessage,
        ToolMessage,
        UserMessage,
    )

    args = get_args(Message)
    assert UserMessage in args
    assert AssistantMessage in args
    assert ToolMessage in args
    assert not any(get_origin(arg) is dict for arg in args)


def test_ireranker_is_closable():
    """IReranker must inherit IClosable so lifespan can call shutdown()."""
    from ai_assistant.core.ports.closable import IClosable

    assert issubclass(IReranker, IClosable)
    assert callable(getattr(IReranker, "shutdown", None))
