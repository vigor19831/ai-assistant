#!/usr/bin/env python3
"""Unified smoke check — imports, config, state, HTTP, RAG, chat, tools, security, lifespan.

Runs all checks sequentially. Returns 0 if all pass, 1 otherwise.
"""

import asyncio
import json
import sys
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

# ── Path setup ───────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@contextmanager
def _project_path():
    """Temporarily add src/ to sys.path for src-layout imports."""
    src = str(_PROJECT_ROOT / "src")
    inserted = False
    if src not in sys.path:
        sys.path.insert(0, src)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            sys.path.remove(src)


# ── Windows UTF-8 ────────────────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


# ── Imports (lazy, inside _project_path) ───────────────────────────────────
with _project_path():
    from ai_assistant.adapters.chunker_simple import SimpleChunker
    from ai_assistant.adapters.embedder_mock import MockEmbedder
    from ai_assistant.adapters.llm_mock import MockLLM
    from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
    from ai_assistant.api.deps import InitializedAppState, init_adapters
    from ai_assistant.api.security import get_expected_api_key, set_api_key
    from ai_assistant.core.config import (
        AppConfig,
        ChunkerConfig,
        EmbedderConfig,
        LLMConfig,
        RAGConfig,
        SecurityConfig,
        StorageConfig,
        VectorStoreConfig,
        load_config,
    )
    from ai_assistant.core.constants import RAG_NS_MAP
    from ai_assistant.core.domain.documents import Chunk, Document
    from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
    from ai_assistant.core.domain.pipeline import PipelineData
    from ai_assistant.core.pipeline_steps import embed_query, retrieve, build_context
    from ai_assistant.core.ports.tools import ToolResult
    from ai_assistant.features.chat.manager import ChatManager
    from ai_assistant.main import create_app


# ── Result types ─────────────────────────────────────────────────────────────
@dataclass
class CheckResult:
    name: str
    status: str
    details: str = ""
    error: str = ""


_results: list[CheckResult] = []


def _run_check(name: str, fn) -> None:
    try:
        detail = fn()
        _results.append(
            CheckResult(
                name=name, status="PASS", details=str(detail) if detail else "OK"
            )
        )
    except Exception as e:
        import traceback

        _results.append(
            CheckResult(
                name=name,
                status="FAIL",
                error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )
        )


# ── Async runner ─────────────────────────────────────────────────────────────
def _run_async(coro):
    """Run coroutine in a fresh event loop."""
    return asyncio.run(coro)


# ── Checks ───────────────────────────────────────────────────────────────────
def _check_imports() -> str:
    from ai_assistant.adapters.factory import create_adapter

    try:
        create_adapter("llm", "__nonexistent__", {})
        raise AssertionError("Should fail on invalid adapter")
    except ValueError:
        pass
    return "factory works, invalid adapter blocked"


def _check_config() -> str:
    cfg = load_config(str(_PROJECT_ROOT / "tests" / "config.test.yaml"))
    assert isinstance(cfg, AppConfig)
    assert cfg.embedder.dim == cfg.vector_store.dim
    return f"dim={cfg.embedder.dim}, steps={len(cfg.rag.steps)}"


def _check_structure() -> str:
    import ai_assistant

    pkg = Path(ai_assistant.__file__).parent
    required = [
        pkg / "core/ports",
        pkg / "adapters",
        pkg / "features",
        pkg / "api",
    ]
    missing = [str(p.relative_to(pkg.parent)) for p in required if not p.exists()]
    if not (_PROJECT_ROOT / "config.yaml").exists():
        missing.append("config.yaml")
    if missing:
        raise FileNotFoundError(f"Missing: {missing}")
    return f"{len(required) + 1} core paths present"


def _check_app_state() -> str:
    cfg = load_config(str(_PROJECT_ROOT / "tests" / "config.test.yaml"))

    async def _init():
        return await init_adapters(cfg)

    state = _run_async(_init())
    assert state.pipeline is not None

    # Idempotency: second init with same config
    state2 = _run_async(_init())
    assert state2.pipeline is not None
    assert state2 is not state

    return json.dumps(
        {
            "llm": type(state.llm).__name__,
            "embedder": type(state.embedder).__name__,
            "pipeline_steps": len(state.pipeline.steps),
            "chat_manager": type(state.chat_manager).__name__,
        }
    )


def _check_http() -> str:
    from fastapi.testclient import TestClient

    from ai_assistant.api.security import require_api_key

    cfg = load_config(str(_PROJECT_ROOT / "tests" / "config.test.yaml"))

    # Build async mocks that satisfy port contracts
    mock_llm = AsyncMock()
    mock_llm.complete = AsyncMock(return_value=AssistantMessage(text="ok"))
    mock_llm.shutdown = AsyncMock()

    async def _fake_stream(*_a, **_k):
        yield "ok"

    mock_llm.stream = _fake_stream

    mock_embedder = AsyncMock()
    mock_embedder.embed = AsyncMock(return_value=[[0.1] * cfg.embedder.dim])
    mock_embedder.dimension = cfg.embedder.dim
    mock_embedder.shutdown = AsyncMock()

    mock_vs = AsyncMock()
    mock_vs.search = AsyncMock(return_value=[])
    mock_vs.add = AsyncMock()
    mock_vs.delete = AsyncMock()
    mock_vs.save = AsyncMock()
    mock_vs.load = AsyncMock()
    mock_vs.list_namespaces = AsyncMock(return_value=[])
    mock_vs.list_by_filter = AsyncMock(return_value=[])
    mock_vs.shutdown = AsyncMock()

    mock_chunker = AsyncMock()
    mock_chunker.chunk = AsyncMock(return_value=[])

    mock_storage = AsyncMock()
    mock_storage.get_history = AsyncMock(return_value=[])
    mock_storage.save_message = AsyncMock()
    mock_storage.init_db = AsyncMock()

    mock_pipeline = AsyncMock()
    mock_pipeline.run = AsyncMock(
        return_value=PipelineData(
            response=AssistantMessage(text="answer"),
            chunks=(),
            errors=(),
        )
    )

    mock_chat = AsyncMock()
    mock_chat.chat = AsyncMock(return_value=AssistantMessage(text="ok"))

    async def _fake_chat_stream(*_a, **_k):
        yield "ok"

    mock_chat.stream_chat = _fake_chat_stream

    state = InitializedAppState(
        config=cfg,
        llm=mock_llm,
        embedder=mock_embedder,
        vector_store=mock_vs,
        chunker=mock_chunker,
        pipeline=mock_pipeline,
        storage=mock_storage,
        chat_manager=mock_chat,
        reranker=None,
        limiter=None,
    )

    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    app = create_app(state=state, lifespan=_noop_lifespan)
    # Bypass API key enforcement for this smoke test
    # NOTE: override value must be a plain callable, NOT a dependency signature.
    # FastAPI dependency_overrides expects the *return value*, not a DI function.
    app.dependency_overrides[require_api_key] = lambda: None

    with TestClient(app) as client:
        r_models = client.get("/v1/models")
        assert r_models.status_code == 200, f"models: {r_models.status_code}"

        r_chat = client.post(
            "/api/v1/chat",
            json={"message": "hi", "conversation_id": "t1"},
        )
        assert r_chat.status_code == 200, f"chat: {r_chat.status_code}"

        r_stream = client.post(
            "/api/v1/chat/stream",
            json={"message": "hi", "conversation_id": "t2"},
        )
        assert r_stream.status_code == 200, f"stream: {r_stream.status_code}"

        r_rag = client.post(
            "/api/v1/rag/query",
            json={"query": "test"},
        )
        assert r_rag.status_code == 200, f"rag: {r_rag.status_code}"

        # Verify SSE format
        stream_text = r_stream.text
        has_data = all(
            line.startswith("data: ")
            for line in stream_text.strip().split("\n")
            if line.strip()
        )
        has_done = "data: [DONE]" in stream_text

    return (
        f"models={r_models.status_code}, chat={r_chat.status_code}, "
        f"stream={r_stream.status_code}, sse_ok={has_data}, done_ok={has_done}, "
        f"rag={r_rag.status_code}"
    )


def _check_rag_pipeline() -> str:
    async def _run():
        chunker = SimpleChunker(
            ChunkerConfig(chunk_size=100, chunk_overlap=5)
        )
        embedder = MockEmbedder(
            EmbedderConfig(dim=3, model="mock", api_base="", api_key=None)
        )
        store = MemoryVectorStore(
            VectorStoreConfig(dim=3, metric="l2", max_chunks=1000)
        )

        doc = Document(id="d1", content="Paris is capital. France has Eiffel Tower.")
        chunks = await chunker.chunk(doc)
        embs = await embedder.embed([c.text for c in chunks])

        for i, c in enumerate(chunks):
            c.embedding = embs[i]

        await store.add(chunks, namespace="test")

        qemb = await embedder.embed(["capital?"])
        found = await store.search(qemb[0], top_k=3, namespace="test")

        return (
            f"chunks={len(chunks)}, found={len(found)}, "
            f"has_paris={'Paris' in found[0].text if found else False}"
        )

    return _run_async(_run())


def _check_chat_manager() -> str:
    async def _run():
        llm = MockLLM(LLMConfig(model="mock", api_base="", api_key=None))
        embedder = MockEmbedder(
            EmbedderConfig(dim=3, model="mock", api_base="", api_key=None)
        )
        store = MemoryVectorStore(
            VectorStoreConfig(dim=3, metric="l2", max_chunks=1000)
        )

        await store.add(
            [Chunk(id="c1", text="Paris is capital.", embedding=[0.1] * 3)],
            namespace="personal",
        )

        # Proper async storage mock
        mock_storage = AsyncMock()
        mock_storage.get_history = AsyncMock(return_value=[])
        mock_storage.save_message = AsyncMock()
        mock_storage.init_db = AsyncMock()

        mgr = ChatManager(
            llm=llm,
            embedder=embedder,
            vector_store=store,
            storage=mock_storage,
            history_limit=10,
            max_context_tokens=4096,
            tokenizer_model="gpt-4o",
            reranker=None,
            pipeline=None,
            namespaces={},
            prompt_version="v1",
            top_k=3,
        )

        r1 = await mgr.chat("Hello", "c1")
        # Do not test RAG prefix when pipeline is None; test plain chat only
        return f"no_rag='{r1.text[:30]}...'"

    return _run_async(_run())


def _check_tools() -> str:
    from ai_assistant.core.ports.tools import ITool, ToolSpec

    class _AddTool(ITool):
        def __init__(self, config: Any) -> None:
            super().__init__(config)

        @property
        def spec(self) -> ToolSpec:
            return ToolSpec(
                name="add",
                description="Add two numbers",
                parameters={
                    "type": "object",
                    "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                },
                required=["a", "b"],
            )

        async def execute(self, call_id: str, arguments: dict) -> ToolResult:
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            return ToolResult(call_id=call_id, output=str(a + b), is_error=False)

    tool = _AddTool({})
    result = _run_async(tool.execute("call-1", {"a": 2, "b": 3}))

    return f"add_ok={result.is_error is False}, output={result.output}"


def _check_security() -> str:
    import os

    original = os.environ.get("AI_API_KEY")
    try:
        os.environ["AI_API_KEY"] = "test-smoke"
        key = get_expected_api_key()
        return f"key_resolved={key == 'test-smoke'}"
    finally:
        if original is None:
            os.environ.pop("AI_API_KEY", None)
        else:
            os.environ["AI_API_KEY"] = original


def _check_lifespan() -> str:
    from unittest.mock import AsyncMock, patch

    from ai_assistant.api.lifespan import lifespan
    from fastapi import FastAPI

    async def _run():
        cfg = AppConfig(
            debug=False,
            security=SecurityConfig(api_key=None),
            llm=LLMConfig(model="mock", api_base="", api_key=None),
            vector_store=VectorStoreConfig(provider="memory", dim=384),
            storage=StorageConfig(provider="sqlite", db_path="./data/test.db"),
        )

        mock_llm = AsyncMock()
        mock_llm.shutdown = AsyncMock()

        mock_vs = AsyncMock()
        mock_vs.save = AsyncMock()
        mock_vs.list_namespaces = AsyncMock(return_value=[])
        mock_vs.shutdown = AsyncMock()

        class _FakeState:
            llm = mock_llm
            embedder = None
            vector_store = mock_vs

        app = FastAPI()

        with patch("ai_assistant.api.lifespan._load_config", return_value=cfg):
            with patch(
                "ai_assistant.api.lifespan.init_adapters", new_callable=AsyncMock
            ) as mock_init:
                mock_init.return_value = _FakeState()

                async with lifespan(app):
                    pass

        return f"shutdown_called={mock_llm.shutdown.await_count}"

    return _run_async(_run())


# ── Main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    global _results
    _results = []

    WIDTH = 60

    print("\n" + " Unified Smoke Check ".center(WIDTH, "="))

    _run_check("imports", _check_imports)
    _run_check("structure", _check_structure)
    _run_check("config", _check_config)
    _run_check("app_state", _check_app_state)
    _run_check("http", _check_http)
    _run_check("rag_pipeline", _check_rag_pipeline)
    _run_check("chat_manager", _check_chat_manager)
    _run_check("tools", _check_tools)
    _run_check("security", _check_security)
    _run_check("lifespan", _check_lifespan)

    passed = sum(1 for r in _results if r.status == "PASS")
    failed = sum(1 for r in _results if r.status == "FAIL")

    print()
    for r in _results:
        icon = "[+]" if r.status == "PASS" else "[!]"
        print(f"  {icon} {r.name:<20} {r.status}")
        if r.details:
            print(f"      {r.details}")
        if r.error:
            print(f"      ERROR: {r.error.splitlines()[0]}")

    print("-" * WIDTH)
    if failed == 0:
        print(f"  ALL OK ({passed}/{passed})")
    else:
        print(f"  FAIL: {failed} failed, {passed} passed")
    print("-" * WIDTH)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
