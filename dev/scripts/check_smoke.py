#!/usr/bin/env python3
"""Unified smoke check — imports, config, state, HTTP, RAG, chat,
tools, security, lifespan."""

import asyncio
import json
import os
import sys
import traceback
from dataclasses import dataclass
from pathlib import Path

# Ensure project root is on path (works from any cwd)
_DEV_ROOT = Path(__file__).resolve().parent.parent
_PROJECT_ROOT = _DEV_ROOT.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Windows: force UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


@dataclass
class CheckResult:
    name: str
    status: str
    details: str = ""
    error: str = ""


results: list[CheckResult] = []


def run_check(name: str, fn) -> None:
    try:
        detail = fn()
        results.append(
            CheckResult(
                name=name, status="PASS", details=str(detail) if detail else "OK"
            )
        )
    except Exception as e:
        results.append(
            CheckResult(
                name=name,
                status="FAIL",
                error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            )
        )


# Helpers
def make_mock_state():
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock.config.llm.provider = "mock"
    mock.config.llm.model = "gpt-4o-mini"
    mock.config.chat.history_limit = 10
    mock.config.chat.tokenizer_model = "gpt-4o"
    mock.config.rag.default_namespace = "default"
    mock.config.rag.top_k = 3
    mock.config.vector_store.provider = "memory"
    mock.config.vector_store.dim = 384
    mock.config.storage.provider = "sqlite"
    mock.config.storage.db_path = "./data/test_storage.db"
    mock.config.voice.enabled = False
    mock.config.vision.enabled = False
    mock.llm = MagicMock()
    mock.llm.complete = lambda msgs: MagicMock(text="ok", metadata={}, tool_calls=[])
    mock.llm.stream = lambda msgs: (yield "ok")
    mock.embedder = MagicMock()
    mock.embedder.embed = lambda texts: [[0.1] * 384]
    mock.embedder.dimension = 384
    mock.vector_store = MagicMock()
    mock.vector_store.add = lambda *a, **k: None
    mock.vector_store.search = lambda *a, **k: []
    mock.chunker = MagicMock()
    mock.chunker.chunk = lambda doc: []
    mock.reranker = None
    mock.pipeline = MagicMock()
    mock.pipeline.run = lambda data: MagicMock(
        chunks=[], response=MagicMock(text="answer"), errors=[]
    )
    mock.storage = MagicMock()
    mock.storage.get_history = lambda *a, **k: []
    mock.storage.save_message = lambda *a, **k: None
    mock.vision = None
    mock.voice_recognizer = None
    mock.voice_synthesizer = None
    mock.tool_registry = MagicMock()
    mock.tool_registry.register = lambda t: None
    mock.tool_registry.list_tools = lambda: []
    mock.tool_registry.execute = lambda c: MagicMock(output="tool", is_error=False)

    # Bypass API key check for smoke tests (no auth required)
    os.environ["AI_API_KEY"] = ""
    from ai_assistant.api.security import reset_security_state

    reset_security_state()

    return mock


# Checks
def check_imports_registry() -> str:
    from ai_assistant.core.registry import create, list_adapters

    assert isinstance(list_adapters(), dict)
    try:
        create("llm", "__nonexistent__", {})
        raise AssertionError("Should fail on invalid adapter")
    except ValueError:
        pass
    return "imports OK, registry works, invalid adapter blocked"


def check_config() -> str:
    from ai_assistant.core.config import AppConfig, load_config

    cfg = load_config(str(_DEV_ROOT / "tests" / "config.test.yaml"))
    assert isinstance(cfg, AppConfig)
    assert cfg.embedder.dim == cfg.vector_store.dim
    return f"config parsed, dim={cfg.embedder.dim}, steps={len(cfg.rag.steps)}"


def check_file_structure() -> str:
    import ai_assistant

    pkg = Path(ai_assistant.__file__).parent
    required = [
        pkg / "core/ports",
        pkg / "adapters",
        pkg / "features",
        pkg / "pipeline",
        pkg / "api",
    ]
    missing = [str(p.relative_to(pkg.parent)) for p in required if not p.exists()]
    if not (_PROJECT_ROOT / "config.yaml").exists():
        missing.append("config.yaml")
    if missing:
        raise FileNotFoundError(f"Missing critical paths: {missing}")
    return f"all {len(required) + 1} core dirs/files present"


def check_app_state() -> str:
    import asyncio

    from ai_assistant.api.deps import init_adapters
    from ai_assistant.core.config import load_config

    cfg = load_config(str(_DEV_ROOT / "tests" / "config.test.yaml"))
    state = asyncio.run(init_adapters(cfg))
    state2 = asyncio.run(init_adapters(cfg))
    assert state is state2, "init_adapters not idempotent"
    return json.dumps(
        {
            "llm": type(state.llm).__name__,
            "embedder": type(state.embedder).__name__,
            "pipeline_steps": len(state.pipeline.steps),
            "tool_registry": type(state.tool_registry).__name__,
        }
    )


def check_http_endpoints() -> str:
    from fastapi.testclient import TestClient

    from ai_assistant.api.deps import get_state
    from ai_assistant.main import app

    mock = make_mock_state()
    app.state.app_state = mock
    app.dependency_overrides[get_state] = lambda: mock
    try:
        client = TestClient(app)
        r1 = client.get("/health")
        r2 = client.get("/info")
        r3 = client.post("/api/v1/chat", json={"message": "hi", "conversation_id": "t1"})
        r4 = client.post(
            "/api/v1/chat", json={"message": "hi"}, headers={"Authorization": "Bearer test"}
        )
        r5 = client.get("/v1/models")
        r6 = client.post("/api/v1/rag/query", json={"query": "test"})
        r7 = client.post("/api/v1/chat", json={"bad": "field"})
        return (
            f"health={r1.status_code}, info={r2.status_code}, "
            f"chat_no_auth={r3.status_code}, chat_auth={r4.status_code}, "
            f"models={r5.status_code}, rag={r6.status_code}, bad_req={r7.status_code}"
        )
    finally:
        app.dependency_overrides.clear()


def check_sse_format() -> str:
    from fastapi.testclient import TestClient

    from ai_assistant.api.deps import get_state
    from ai_assistant.main import app

    async def fake_stream(*a, **k):
        yield "Hello"
        yield " world"

    mock = make_mock_state()
    mock.llm.stream = fake_stream
    app.state.app_state = mock
    app.dependency_overrides[get_state] = lambda: mock
    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/chat/stream", json={"message": "hi", "conversation_id": "t1"}
        )
        lines = [line for line in r.text.strip().split("\n") if line.strip()]
        has_data = all(line.startswith("data: ") for line in lines)
        has_done = "data: [DONE]" in r.text
        return f"status={r.status_code}, sse_ok={has_data}, done_ok={has_done}"
    finally:
        app.dependency_overrides.clear()


def check_rag_pipeline() -> str:
    from dataclasses import replace

    from ai_assistant.adapters.chunker_simple import SimpleChunker
    from ai_assistant.adapters.embedder_mock import MockEmbedder
    from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
    from ai_assistant.core.domain.documents import Document

    async def run():
        chunker = SimpleChunker(
            type("C", (), {"chunk_size": 100, "chunk_overlap": 5})()
        )
        embedder = MockEmbedder(type("C", (), {"dim": 3})())
        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": 0.0})()
        )
        doc = Document(id="d1", content="Paris is capital. France has Eiffel Tower.")
        chunks = await chunker.chunk(doc)
        embs = await embedder.embed([c.text for c in chunks])
        await store.add(
            [replace(c, embedding=embs[i]) for i, c in enumerate(chunks)],
            namespace="test",
        )
        qemb = await embedder.embed(["capital?"])
        found = await store.search(qemb[0], top_k=3, namespace="test")
        return (
            f"chunks={len(chunks)}, found={len(found)}, "
            f"Paris={'Paris' in found[0].text if found else False}"
        )

    return asyncio.run(run())


def check_chat_manager() -> str:
    from dataclasses import replace

    from ai_assistant.adapters.embedder_mock import MockEmbedder
    from ai_assistant.adapters.llm_mock import MockLLM
    from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
    from ai_assistant.core.domain.documents import Chunk
    from ai_assistant.features.chat.manager import ChatManager

    async def run():
        llm = MockLLM({})
        embedder = MockEmbedder(type("C", (), {"dim": 3})())
        store = MemoryVectorStore(
            type("C", (), {"dim": 3, "relevance_threshold": 0.0})()
        )
        await store.add(
            [replace(Chunk(id="c1", text="Paris is capital."), embedding=[0.1] * 3)],
            namespace="personal",
        )
        mgr = ChatManager(
            llm=llm, embedder=embedder, vector_store=store, history_limit=10
        )
        r1 = await mgr.chat("Hello", "c1")
        r2 = await mgr.chat("[p] capital?", "c2")
        return f"no_rag='{r1.text[:30]}...', rag='{r2.text[:40]}...'"

    return asyncio.run(run())


def check_tools() -> str:
    from ai_assistant.adapters.tools_calculator import CalculatorTool

    async def run():
        tool = CalculatorTool()
        ok = await tool.execute("call-1", {"operation": "add", "a": 2, "b": 3})
        err = await tool.execute("call-2", {"operation": "divide", "a": 1, "b": 0})
        return f"add_ok={ok.is_error is False}, div0_err={err.is_error is True}"

    return asyncio.run(run())


def check_security() -> str:
    from ai_assistant.api.security import SecurityLimiter, get_expected_api_key

    limiter = SecurityLimiter()
    ip = "127.0.0.1"
    allowed = sum(1 for _ in range(110) if limiter.is_allowed(ip))
    os.environ["AI_API_KEY"] = "test-smoke"
    key = get_expected_api_key()
    return f"allowed={allowed}/110, key_resolved={key is not None}"


def check_lifespan() -> str:
    from unittest.mock import AsyncMock, MagicMock, patch

    from ai_assistant.api.lifespan import lifespan

    async def run():
        class MinimalApp:
            def __init__(self):
                self.state = MinimalState()

        class MinimalState:
            pass

        class MinimalLLM:
            shutdown = AsyncMock()

        class MinimalVS:
            save = AsyncMock()
            list_namespaces = AsyncMock(return_value=[])

        app = MinimalApp()

        st = MinimalState()
        st.llm = MinimalLLM()
        st.embedder = None
        st.vector_store = MinimalVS()
        st.llm_server_manager = None

        with patch("ai_assistant.api.lifespan._load_config") as mock_cfg:
            cfg = type(
                "C",
                (),
                {
                    "debug": False,
                    "llm": type(
                        "LLM",
                        (),
                        {
                            "server_bin": None,
                            "model_path": None,
                            "server_context_size": 4096,
                            "n_gpu_layers": 0,
                        },
                    )(),
                    "vector_store": type("VS", (), {"index_path": None})(),
                },
            )()
            mock_cfg.return_value = cfg

            with patch(
                "ai_assistant.api.lifespan.init_adapters", new_callable=AsyncMock
            ) as mock_init:
                mock_init.return_value = st

                with patch("ai_assistant.api.lifespan.get_metrics_logger") as mock_met:
                    mock_met.return_value.start = MagicMock()
                    mock_met.return_value.stop = AsyncMock()

                    async with lifespan(app) as _:
                        pass

        return f"shutdown_called={MinimalLLM.shutdown.await_count}"

    return asyncio.run(run())


# Runner
def main() -> int:
    print("\n" + " Unified Smoke Check ".center(60, "="))

    run_check("imports_registry", check_imports_registry)
    run_check("file_structure", check_file_structure)
    run_check("config_parse", check_config)
    run_check("app_state", check_app_state)
    run_check("http_endpoints", check_http_endpoints)
    run_check("sse_format", check_sse_format)
    run_check("rag_pipeline", check_rag_pipeline)
    run_check("chat_manager", check_chat_manager)
    run_check("tools_exec", check_tools)
    run_check("security_rate", check_security)
    run_check("lifespan_shutdown", check_lifespan)

    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")

    print()
    for r in results:
        icon = "✓" if r.status == "PASS" else "✗"
        print(f"  {icon} {r.name:<20} {r.status}")
        if r.details:
            print(f"      {r.details}")
        if r.error:
            print(f"      ERROR: {r.error.splitlines()[0]}")

    print("-" * 60)
    print(f"  Total: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
