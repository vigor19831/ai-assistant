"""Single-command project health check."""

import sys
import asyncio
from pathlib import Path
from dataclasses import replace
from contextlib import contextmanager

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@contextmanager
def _project_path():
    """Temporarily add src/ to sys.path for clean imports."""
    src = str(PROJECT_ROOT / "src")
    inserted = False
    if src not in sys.path:
        sys.path.insert(0, src)
        inserted = True
    try:
        yield
    finally:
        if inserted:
            sys.path.remove(src)


errors = []
warnings = []


def error(msg: str) -> None:
    errors.append(msg)
    print("   FAIL " + msg)


def warn(msg: str) -> None:
    warnings.append(msg)
    print("   WARN " + msg)


def _run_async(coro):
    """Run coroutine safely, handling both sync and async contexts."""
    try:
        loop = asyncio.get_running_loop()
        # Already in async context — schedule and wait
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop — use asyncio.run directly
        return asyncio.run(coro)


print("=" * 60)
print("PROJECT HEALTH CHECK")
print("=" * 60)

# ===================================================================
# 1. BASIC IMPORTS
# ===================================================================
print("\n[1/10] Checking imports...")

with _project_path():
    try:
        from ai_assistant.core.config import load_config, AppConfig, RAGStep, EmbedderConfig, VectorStoreConfig
        from ai_assistant.core.constants import RAG_NS_MAP, RAG_PREFIX_RE
        from ai_assistant.core.domain.pipeline import PipelineData
        from ai_assistant.core.domain.messages import UserMessage, AssistantMessage
        from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
        from ai_assistant.core.pipeline_steps import STEP_REGISTRY, embed_query, retrieve, build_context, generate, rerank
        from ai_assistant.features.chat.manager import ChatManager
        from ai_assistant.features.rag.manager import RAGManager, IndexingManager
        from ai_assistant.adapters.factory import create_adapter
        from ai_assistant.main import create_app
        from ai_assistant.core.ports.reranker import RerankResult
        print("   OK: core imports")
    except Exception as e:
        error("Imports broken: " + str(e))
        print("=" * 60)
        print("FATAL: cannot continue without core imports")
        print("=" * 60)
        sys.exit(2)

# ===================================================================
# 2. CONFIG
# ===================================================================
print("\n[2/10] Checking config.yaml...")

try:
    cfg = load_config(PROJECT_ROOT / "config.yaml")
    print("   OK: config loaded")
except Exception as e:
    error("Config failed to load: " + str(e))
    cfg = None

if cfg:
    # dim match
    if cfg.embedder.dim != cfg.vector_store.dim:
        error(
            f"embedder.dim ({cfg.embedder.dim}) != vector_store.dim ({cfg.vector_store.dim})"
        )
    else:
        print(f"   OK: dim match ({cfg.embedder.dim})")

    # namespace consistency
    config_ns = set(cfg.namespaces.keys())
    map_ns = set(RAG_NS_MAP.values())
    if config_ns != map_ns:
        error("Namespace mismatch:")
        error(f"  config.yaml: {sorted(config_ns)}")
        error(f"  constants.py: {sorted(map_ns)}")
    else:
        print(f"   OK: namespaces match ({len(config_ns)})")

    # RAG steps registered
    for step in cfg.rag.steps:
        if step.value not in STEP_REGISTRY:
            error(f"Pipeline step not registered: {step.value}")
        else:
            print(f"   OK: step '{step.value}' registered")

    # Check required adapters can be created (mock mode)
    print("\n[3/10] Checking adapter creation (mock)...")

    try:
        mock_emb_cfg = EmbedderConfig(
            dim=cfg.embedder.dim,
            timeout=1.0,
            model="mock",
            api_base="",
            api_key=None,
        )
        emb = create_adapter("embedder", "mock", mock_emb_cfg)
        print(f"   OK: mock embedder (dim={emb.dimension})")
    except Exception as e:
        error(f"Mock embedder failed: {e}")

    try:
        mock_vs_cfg = VectorStoreConfig(
            dim=cfg.vector_store.dim,
            metric="l2",
            max_chunks=1000,
        )
        vs = create_adapter("vector_store", "memory", mock_vs_cfg)
        print("   OK: memory vector store")
    except Exception as e:
        error(f"Memory vector store failed: {e}")

# ===================================================================
# 3. TEMPLATES
# ===================================================================
print("\n[4/10] Checking templates...")

prompts_dir = PROJECT_ROOT / "src" / "ai_assistant" / "core" / "prompts" / "v1"
required_templates = ["rag_strict", "rag_creative", "rag_default"]

for name in required_templates:
    template = prompts_dir / (name + ".j2")
    if not template.exists():
        error(f"Template missing: {template}")
    else:
        content = template.read_text(encoding="utf-8")
        if "{{ context }}" in content:
            print(f"   OK: {name}.j2 uses {{ context }}")
        elif "{{ chunks }}" in content:
            error(f"Template {name}.j2 uses DEPRECATED {{ chunks }} — use {{ context }}")
        else:
            warn(f"Template {name}.j2 uses neither context nor chunks")

# ===================================================================
# 4. LIFESPAN
# ===================================================================
print("\n[5/10] Checking lifespan.py...")

lifespan = PROJECT_ROOT / "src" / "ai_assistant" / "api" / "lifespan.py"
if lifespan.exists():
    content = lifespan.read_text()
    has_load = "vector_store.load" in content or "await state.vector_store.load" in content
    has_save = "vector_store.save" in content or "await state.vector_store.save" in content

    if has_load:
        print("   OK: lifespan loads indices (.load)")
    else:
        error("lifespan.py does NOT load indices on startup!")

    if has_save:
        print("   OK: lifespan saves indices (.save)")
    else:
        error("lifespan.py does NOT save indices on shutdown!")

# ===================================================================
# 5. PIPELINE DATA (immutability)
# ===================================================================
print("\n[6/10] Checking PipelineData...")

try:
    d1 = PipelineData(query=UserMessage(text="test"))
    d2 = d1.with_context("hello")

    if d1.context == "" and d2.context == "hello":
        print("   OK: PipelineData immutable (with_context)")
    else:
        error("PipelineData mutates!")

    d3 = d2.add_error("err")
    if len(d3.errors) == 1 and len(d2.errors) == 0:
        print("   OK: PipelineData immutable (add_error)")
    else:
        error("add_error mutates!")

except Exception as e:
    error(f"PipelineData check broken: {e}")

# ===================================================================
# 6. RAG PREFIX REGEX
# ===================================================================
print("\n[7/10] Checking RAG_PREFIX_RE...")

test_cases = [
    ("[p] hello", "p", "hello"),
    ("[w] work", "w", "work"),
    ("[c] code", "c", "code"),
    ("[b] books", "b", "books"),
    ("[o] other", "o", "other"),
    ("no prefix", None, None),
    ("p] missing bracket", None, None),
]

for text, expected_short, expected_query in test_cases:
    m = RAG_PREFIX_RE.match(text)
    if expected_short:
        if m and m.group(1).lower() == expected_short and m.group(2) == expected_query:
            print(f"   OK: '{text}' -> ns={expected_short}")
        else:
            error(f"RAG_PREFIX_RE fails: '{text}'")
    else:
        if m is None:
            print(f"   OK: '{text}' -> no match (correct)")
        else:
            error(f"RAG_PREFIX_RE false positive: '{text}'")

# ===================================================================
# 7. MOCK PIPELINE RUN
# ===================================================================
print("\n[8/10] Mock pipeline run...")

# Pre-declare fakes to avoid lazy imports inside methods
class FakeEmbedder:
    dimension = 384

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 384 for _ in texts]


class FakeVectorStore:
    async def search(
        self, emb: list[float], top_k: int = 5, namespace: str = "default"
    ) -> list[Chunk]:
        return [
            Chunk(
                id="c1",
                text="answer: blue",
                metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
            )
        ]


class FakeReranker:
    async def rerank(
        self, query: str, chunks: list[Chunk], top_k: int | None = None
    ) -> list[RerankResult]:
        return [RerankResult(chunk=c, score=0.9) for c in chunks]


class FakeLLM:
    def get_context_limit(self) -> int:
        return 4096

    async def complete(
        self,
        messages: list,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantMessage:
        return AssistantMessage(text="blue")


async def test_pipeline() -> None:
    data = PipelineData(query=UserMessage(text="what color"))
    data = data.with_metadata(
        {
            "embedder": FakeEmbedder(),
            "vector_store": FakeVectorStore(),
            "llm": FakeLLM(),
            "reranker": FakeReranker(),
            "top_k": 5,
            "namespace": "personal",
            "prompt_version": "v1",
            "prompt_name": "rag_strict",
            "relevance_threshold": 0.3,
        }
    )

    try:
        data = await embed_query(data)
        print("   OK: embed_query")
    except Exception as e:
        error(f"embed_query failed: {e}")
        return

    try:
        data = await retrieve(data)
        if len(data.chunks) > 0:
            print(f"   OK: retrieve -> {len(data.chunks)} chunks")
        else:
            error("retrieve returned 0 chunks!")
            return
    except Exception as e:
        error(f"retrieve failed: {e}")
        return

    try:
        data = await rerank(data)
        if data.metadata.get("rerank_filtered_out"):
            warn("rerank filtered out all chunks")
        else:
            print(f"   OK: rerank -> {len(data.chunks)} chunks")
    except Exception as e:
        error(f"rerank failed: {e}")
        return

    try:
        data = await build_context(data)
        if len(data.context) > 0:
            print(f"   OK: build_context -> {len(data.context)} chars")
        else:
            error("build_context returned empty string!")
            return
    except Exception as e:
        error(f"build_context failed: {e}")
        return

    try:
        data = await generate(data)
        if data.response and data.response.text:
            print(f"   OK: generate -> '{data.response.text}'")
        else:
            error("generate returned empty response!")
    except Exception as e:
        error(f"generate failed: {e}")


_run_async(test_pipeline())

# ===================================================================
# 8. SOURCE FOLDERS
# ===================================================================
print("\n[9/10] Checking sources/...")

sources_root = PROJECT_ROOT / "sources"
expected_folders = list(RAG_NS_MAP.values())

for folder in expected_folders:
    path = sources_root / folder
    if path.exists():
        files = list(path.iterdir())
        print(f"   OK: {folder}/ ({len(files)} files)")
    else:
        warn(f"sources/{folder}/ does not exist")

# ===================================================================
# 9. INDICES
# ===================================================================
print("\n[10/10] Checking data/indices/...")

indices_root = PROJECT_ROOT / "data" / "indices"
if indices_root.exists():
    for idx_dir in indices_root.iterdir():
        if idx_dir.is_dir():
            files = list(idx_dir.iterdir())
            print(f"   OK: indices/{idx_dir.name}/ ({len(files)} files)")
else:
    warn("data/indices/ does not exist — indices not created")

# ===================================================================
# RESULT
# ===================================================================
print("\n" + "=" * 60)
if errors:
    print(f"ERRORS ({len(errors)}) — fix required:")
    for e in errors:
        print(f"  FAIL {e}")
if warnings:
    print(f"WARNINGS ({len(warnings)}):")
    for w in warnings:
        print(f"  WARN {w}")
if not errors and not warnings:
    print("ALL OK")
print("=" * 60)

sys.exit(1 if errors else 0)
