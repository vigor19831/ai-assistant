# AI Context
> **Generated:** 2026-06-09 10:01:00 UTC | **Mode:** `compact`
> **Metrics:** 176 files | 97 Python | 14,505 LOC
> **Full:** 47 | **Signatures:** 20 | **Listed:** 102

---

## 📋 Project Overview
```markdown
# AI Assistant

Модульный фреймворк для локальных LLM. Работает offline, поддерживает RAG, совместим с OpenAI API.

## Возможности

- 💬 Чат с памятью и контекстом
- 📚 RAG: поиск по документам с namespace'ами (`[p]ersonal`, `[w]ork`, `[o]ther`, `[c]ode`, `[b]ooks`)
- 🔌 Поддержка любых OpenAI-compatible серверов (llama.cpp, Ollama, vLLM)
- 🧠 Работает полностью offline (mock-режим)

## Быстрый старт

```bash
# 1. Установка
pip install -e ".[faiss]"

# 2. Настройка LLM-сервера
# Варианты:
# • llama-server: llama-server.exe -m model.gguf --port 8080
# • Ollama: ollama serve
# • vLLM: python -m vllm.entrypoints.openai.api_server --model ...

# 3. Конфиг
# Отредактируй config.yaml:
# llm.api_base: http://127.0.0.1:8080/v1
# llm.model: имя-модели-на-сервере

# 4. Запуск
python launcher.py        # интерактивный лаунчер
# Или напрямую:
python scripts/start.py
python main.py
uvicorn ai_assistant.main:app --host 0.0.0.0 --port 8000

# 5. UI
# Подключи любой OpenAI-compatible клиент к http://localhost:8000
# Рекомендуется: Page Assist (браузерное расширение)
```

## RAG — поиск по документам

```bash
# Индексация документов
python scripts/index_documents.py
```

В чате используй префиксы:

| Префикс | Namespace |
|---------|-----------|
| `[p]` | personal |
| `[w]` | work |
| `[o]` | other |
| `[c]` | code |
| `[b]` | books |

## Рекомендуемые модели

**LLM:**

- `gemma-3-4b-it` — быстрая, качественная, мультиязычная
- `qwen2.5-7b-instruct` — хороший баланс скорость/качество
- `llama-3.2-3b-instruct` — компактная, для слабых GPU

**Embedder:**

- `nomic-embed-text-v1.5` — размерность 768
- `mxbai-embed-large-v1` — размерность 1024

> ⚠️ **Важно:** `embedder.dim` в `config.yaml` **должен** совпадать с `vector_store.dim`.

## Требования

- Python 3.13+
- 8+ GB RAM (для CPU-режима)
- GPU опционально (CUDA/Metal/Vulkan)

---

All rights reserved. For personal use only.

```

---

## 🚨 AI Development Guidelines
> Auto-extracted from: `ai_rules.md`
```markdown
# AI Rules

## 0. Ground Truth

Only this document and `docs/context_build_*.md`. No previous conversations, no general best practices, no hallucinated APIs or config keys.

Hierarchy: code in `src/` > this file > README.

When code and rules conflict, code wins. If code violates a rule, that is known drift (see `docs/drift.md`). Propose fixing it, do not hallucinate stricter architecture.

## 1. Identity

You are an architecture enforcement agent. Output: code patches for a solo-maintained Python AI framework expected to survive decades.

Source tree: `src/ai_assistant/`
Layers: `core/` -> `adapters/` -> `features/` -> `api/`

Constraint priority: Absolute Constraints > Layer Boundaries > Core Protocol > Output Protocol.

## 2. Absolute Constraints

Never:
- `**kwargs` in port methods or PipelineData flow (except decorators, Jinja2 render)
- `hasattr()` / `isinstance()` on port objects in production code
- `try/except` around expected port behavior instead of fixing the contract
- Mutate PipelineData in-place. Always return new instances
- Adapter-specific branching (`if adapter_name == "x"`) in features or pipeline steps
- Cross-feature imports
- Import from `api/`, `features/`, `adapters/` into `core/`
- Pydantic in `core/domain/` -- stdlib dataclass only
- Lazy initialization (`dict[str, Callable]` AppState)
- `print()`, `pprint()`, `logging.basicConfig()` -- use `get_logger(name)` only
- Orphaned code -- remove callee if last caller removed

Never add: Redis, Celery, ARQ, event bus, WebSocket, gRPC, Lambda, subdirectories in `features/` (except grandfathered `chat/`, `rag/`), advanced FAISS indices (IVF/PQ) until 100k+ docs proven, LRU eviction in `MemoryVectorStore` until RAM pressure measured, prompt registry / semver until 5+ versions in active use.

## 3. Layer Boundaries

| Layer | May import from |
|-------|---------------|
| `core/` | stdlib only |
| `adapters/` | `core/*` only |
| `features/` | `api.deps`, `core/*`, self only |
| `api/` | `core/`, `adapters/`, `features/`, self |

Cross-feature data flows through `AppState` via `api.deps`, never direct import.

## 4. Core Change Protocol

`core/` changes only when physically impossible otherwise.

Allowed without discussion: new adapter in `adapters/`, new feature in `features/` (flat until 10+ features).

Requires `CORE CHANGE REQUIRED` + user confirmation: new port method/field, PipelineData schema change, config schema change (needs `config_version` bump + backward compat loader).

If core changes:
1. Update ALL adapters implementing the port
2. Update `tests/test_core_critical.py`, `tests/test_contracts.py`
3. Update `docs/error_taxonomy.md`
4. Run `python scripts/check_all.py`

## 5. PipelineData Immutability

Use: `data.with_chunks()`, `.with_context()`, `.with_response()`, `.add_error()`

Never:
```python
data.metadata["foo"] = "bar"
data.metadata.update({...})
data.context = "new"
data.chunks = [chunk]
data.errors.append("err")
data.errors += ["err"]
```

## 6. Adapter Discip
```

---

## ⚠️ Error Taxonomy
> Auto-extracted from: `error_taxonomy.md`
```markdown
## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-09 10:00 UTC
> **Rule:** Check this table before adding try/except or changing error handling.

| Component | Exception | Trigger | Severity | Line |
|-----------|-----------|---------|----------|------|
| `core.retry` | `SystemExit/KeyboardInterrupt` | raise | Critical | 49 |
| `adapters.chunker_simple` | `ValueError` | chunk_size must be > 0, got {...} | High | 22 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap must be >= 0, got {...} | High | 24 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap ({...}) must be < chunk_size ({...}) | High | 26 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Unexpected response shape from {...}: {...} | High | 26 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Dimension mismatch: expected {...}, got {...} for text[{...}... | High | 30 |
| `adapters.factory` | `ValueError` | No LLM adapter registered for '{...}' | High | 38 |
| `adapters.factory` | `ValueError` | No embedder adapter registered for '{...}' | High | 52 |
| `adapters.factory` | `ValueError` | faiss-cpu is not installed but vector_store.provider='faiss' | High | 64 |
| `adapters.factory` | `ValueError` | No vector_store adapter registered for '{...}' | High | 68 |
| `adapters.factory` | `ValueError` | No chunker adapter registered for '{...}' | High | 76 |
| `adapters.factory` | `ValueError` | sqlite3 not available but storage.provider='sqlite' | High | 84 |
| `adapters.factory` | `ValueError` | No storage adapter registered for '{...}' | High | 88 |
| `adapters.factory` | `ValueError` | No reranker adapter registered for '{...}' | High | 96 |
| `adapters.factory` | `ValueError` | Unknown port: {...} | High | 98 |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High | 159 |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High | 71 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High | 64 |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 254 |
| `adapters.vector_store_memory` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 149 |
| `api.admin` | `HTTPException` | Unknown error | High | 49 |
| `api.deps` | `RuntimeError` | LLM adapter failed to initialize | High | 162 |
| `api.deps` | `RuntimeError` | Embedder adapter failed to initialize | High | 164 |
| `api.deps` | `RuntimeError` | Vector store adapter failed to initialize | High | 166 |
| `api.deps` | `RuntimeError` | Pipeline failed to initialize | High | 168 |
| `api.deps` | `RuntimeError` | Storage adapter failed to initialize | High | 170 |
| `api.deps` | `RuntimeError` | Chunker adapter failed to initialize | High | 172 |
| `api.deps` | `RuntimeError` | Chat manager failed to initialize | High | 174 |
| `api.de
```

---

## ⚠️ Error Taxonomy
> Auto-extracted from: `DRIFT.md`
```markdown
# Known Architectural Drift

| ID | File | Broken Rule | Why | Fix | Priority |
|----|------|-------------|-----|-----|----------|
| 1 | core/pipeline_steps.py:~312 | getattr(llm, "config") -- ILLM has no config field | Need context window size | Add get_context_limit() to ILLM, implement in all adapters | Medium |
| 2 | core/pipeline_steps.py:rerank() | if reranker is None inside step | Reranker is optional by config | Make rerank optional in rag.steps, or NullReranker | Low |
| 3 | api/lifespan.py | getattr(config, "vector_store") | Defensive against bad config | Direct access, fail at validation | Low |

Rule: Do not add new drift if old pattern can be fixed properly.

```

---

## ⚠️ Error Taxonomy
> Auto-extracted from: `FUTURE.md`
```markdown
# Future Ideas -- Do Not Implement Without Discussion

| Feature | Status | Blocker | Target Location |
|---------|--------|---------|-----------------|
| TTS/STT | research | No local engine | adapters/stt_*.py, features/chat/handlers.py |
| Vision | research | No vision model, PipelineData needs attachments | adapters/llm_vision_*.py, core/domain/pipeline.py |
| MCP | planned | IToolRegistry has no implementation | adapters/mcp_client.py |
| Native function calling | blocked | Needs MCP first | core/pipeline_steps.py |
| Agents | research | Needs function calling + long-term memory | features/agents/ |
| Long-term memory | research | No storage format | core/ports/memory.py |
| Code sandbox | research | Needs security sandbox | adapters/code_sandbox.py |
| Web RAG (crawling) | research | No crawler | adapters/crawler_simple.py |
| Index sync (git/cloud) | research | FAISS is binary/large | scripts/sync_*.py |
| Plugin system | research | Conflicts with "no magic discovery" | adapters/plugin_loader.py |
| Prometheus metrics | research | Needs prometheus_client | api/metrics.py |
| A2A protocol | research | Spec is unstable | adapters/a2a_client.py |
| Obsidian/Notion RAG | research | Needs parsers + auth | adapters/source_*.py |
| Quantization routing | research | Needs complexity estimator | adapters/router_quantized.py |

Rule: If feature needs core/ change, discuss first. If solvable in adapters/, do it.

```

---

## 🗂️ Structure
```
    .gitattributes
    .gitignore
    README.md
    config.yaml
    launcher.py
    open_terminal.bat
    pyproject.toml
.hypothesis/
    .gitignore
    constants/
        00d08ecc206d19a2
        062da15881e1bbb7
        0a9a37d490bd2ac6
        0e1b7747ffb570b8
        0fea382fa0f49e77
        121d3a7af69b2e20
        1517471990e5338f
        176e90709ffa84f7
        1a2848e19324b132
        1f0c0635d7b70b2e
        1f3ca08de451d5fa
        2373115ed2705e46
        26210ca72a1b6627
        2662f70833eb6408
        26bbf6f8657ded2f
        2e0038433715aceb
        300be2b7c00adf58
        34ae9ae2a7915f47
        42c8d01dab10446b
        4bf5a448f35f8728
        53ddf82fba92383e
        547983fd2998eac5
        567fa9acd526ce98
        5a77869d21ccf7f0
        5d66fcc73a312cf6
        65af6fe9597bc739
        68badcc12bc11d16
        68e2d4459133caa9
        6b4e2be9f971086f
        72ba1bf5d8575399
        72ff6543086ffeab
        7aa6bbe0ad659d13
        82d84f628bfde547
        86119404a24cc8b5
        86783eff27f53448
        8aa58d636feff795
        8bfcfc15e19711e1
        8cb43f130c8f3a11
        8cfdcaffaa4b0f87
        9165caa579a5ca7a
        9bfda43d3142e126
        9dd7b7551596bfad
        a0f8740ab7f36456
        a4232c03c0a5df7d
        a541d6fdb5926928
        a9be3382e044cca6
        acbcc51f48b8db85
        b1ed91e5d16f251d
        bb1fe1dc12b93764
        bd3fbe66aa331706
        cd30ec032838cc80
        cdd098fb9d7cc65a
        de1cc2969519f477
        e47a51605024a02e
        eff07b744e4ce459
        fc0f735ee28793ba
        fcc7def15a753093
    tmp/
        tmphug7pvx0
    unicode_data/
        15.1.0/
            charmap.json.gz
            codec-utf-8.json.gz
docs/
    ai_rules.md
    drift.md
    error_taxonomy.md
    future.md
    readme_dev.md
    todo.md
    todo_done.md
scripts/
    audit_project.py
    check_all.py
    check_llm.py
    check_mutations.py
    check_mypy.py
    check_rag.py
    check_ruff.py
    check_smoke.py
    clean_cache.py
    context_build.py
    download_tokenizers.py
    error_taxonomy_build.py
    index_documents.py
    pre_commit_check.py
    run_all_tests.py
    start.py
    stop.py
    structure.py
src/
    ai_assistant/
        __init__.py
        main.py
        adapters/
            __init__.py
            chunker_simple.py
            embedder_mock.py
            embedder_openai_compatible.py
            factory.py
            llm_mock.py
            llm_openai_compatible.py
            reranker_api.py
            storage_sqlite.py
            vector_store_faiss.py
            vector_store_memory.py
        api/
            __init__.py
            admin.py
            deps.py
            lifespan.py
            middleware.py
            router.py
            security.py
            static.py
        core/
            __init__.py
            config.py
            constants.py
            io_utils.py
            logger.py
            metrics.py
            pipeline.py
            pipeline_steps.py
            retry.py
            utils.py
            domain/
                __init__.py
                documents.py
                errors.py
                messages.py
                pipeline.py
            ports/
                __init__.py
                chunker.py
                closable.py
                embedder.py
                initializable.py
                llm.py
                reranker.py
                storage.py
                tools.py
                vector_store.py
            prompts/
                __init__.py
                v1/
                    rag_creative.j2
                    rag_default.j2
                    rag_strict.j2
                    summarize.j2
        features/
            __init__.py
            chat/
                __init__.py
                handlers.py
                manager.py
                schemas.py
            rag/
                __init__.py
                handlers.py
                indexing.py
                manager.py
                schemas.py
tests/
    __init__.py
    config.test.yaml
    conftest.py
    test_adapters_integration.py
    test_api_deps.py
    test_api_e2e.py
    test_chat_manager_direct.py
    test_config.py
    test_contracts.py
    test_core_critical.py
    test_fuzz.py
    test_lifespan.py
    test_malformed_sse.py
    test_pipeline_frozen_compat.py
    test_rag_pipeline.py
    test_resilience.py
    test_router_compile.py
    test_scripts_and_platform.py
    test_security.py
    test_smoke_pyproject.py
    test_stress.py
    test_tokenizer.py
```

---

## 🔗 Dependencies

- `scripts/check_all.py`
  - → `ai_assistant.adapters.factory: create_adapter`
  - → `ai_assistant.core.config: load_config, AppConfig, RAGStep, EmbedderConfig, VectorStoreConfig`
  - → `ai_assistant.core.constants: RAG_NS_MAP, RAG_PREFIX_RE`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.messages: UserMessage, AssistantMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.pipeline_steps: STEP_REGISTRY, embed_query, retrieve, build_context, generate, rerank`
  - → `ai_assistant.core.ports.reranker: RerankResult`
  - → `ai_assistant.features.chat.manager: ChatManager`
  - → `ai_assistant.features.rag.manager: RAGManager, IndexingManager`
  - → `ai_assistant.main: create_app`
- `scripts/check_llm.py`
  - → `ai_assistant.core.config: load_config`
- `scripts/check_rag.py`
  - → `ai_assistant.adapters.factory: create_adapter`
  - → `ai_assistant.core.config: load_config, EmbedderConfig`
  - → `ai_assistant.core.constants: RAG_NS_MAP, RAG_PREFIX_RE`
  - → `ai_assistant.core.domain.messages: UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.pipeline_steps: build_context, embed_query, retrieve`
- `scripts/check_smoke.py`
  - → `ai_assistant`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.factory: create_adapter`
  - → `ai_assistant.adapters.llm_mock: MockLLM`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.api.deps: InitializedAppState, init_adapters`
  - → `ai_assistant.api.lifespan: lifespan`
  - → `ai_assistant.api.security: get_expected_api_key, set_api_key`
  - → `ai_assistant.api.security: require_api_key`
  - → `ai_assistant.core.config: AppConfig, ChunkerConfig, EmbedderConfig, LLMConfig, RAGConfig, SecurityConfig, StorageConfig, VectorStoreConfig, load_config`
  - → `ai_assistant.core.constants: RAG_NS_MAP`
  - → `ai_assistant.core.domain.documents: Chunk, Document`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.pipeline_steps: embed_query, retrieve, build_context`
  - → `ai_assistant.core.ports.tools: ITool, ToolSpec`
  - → `ai_assistant.core.ports.tools: ToolResult`
  - → `ai_assistant.features.chat.manager: ChatManager`
  - → `ai_assistant.main: create_app`
- `scripts/index_documents.py`
  - → `ai_assistant.api.deps: init_adapters`
  - → `ai_assistant.core.config: load_config`
  - → `ai_assistant.features.rag.indexing: index_folder`
- `src/ai_assistant/adapters/chunker_simple.py`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata, Document`
  - → `ai_assistant.core.ports.chunker: IChunker`
- `src/ai_assistant/adapters/embedder_mock.py`
  - → `ai_assistant.core.ports.embedder: IEmbedder`
- `src/ai_assistant/adapters/embedder_openai_compatible.py`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.ports.embedder: IEmbedder`
  - → `ai_assistant.core.retry: with_retry`
  - → `ai_assistant.core.utils: resolve_api_key`
- `src/ai_assistant/adapters/factory.py`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.embedder_openai_compatible: OpenAICompatibleEmbedder`
  - → `ai_assistant.adapters.llm_mock: MockLLM`
  - → `ai_assistant.adapters.llm_openai_compatible: OpenAICompatibleLLM`
  - → `ai_assistant.adapters.reranker_api: APIReranker`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
- `src/ai_assistant/adapters/llm_mock.py`
  - → `ai_assistant.core.domain.messages: AssistantMessage`
  - → `ai_assistant.core.ports.llm: ILLM, Message`
- `src/ai_assistant/adapters/llm_openai_compatible.py`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.domain.messages: AssistantMessage, MessageRole`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.ports.closable: IClosable`
  - → `ai_assistant.core.ports.llm: ILLM, Message`
  - → `ai_assistant.core.retry: with_retry`
  - → `ai_assistant.core.utils: resolve_api_key`
- `src/ai_assistant/adapters/reranker_api.py`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.ports.reranker: IReranker, RerankResult`
  - → `ai_assistant.core.retry: with_retry`
  - → `ai_assistant.core.utils: resolve_api_key`
- `src/ai_assistant/adapters/storage_sqlite.py`
  - → `ai_assistant.core.ports.initializable: IInitializable`
  - → `ai_assistant.core.ports.storage: IChatStorage, ISettingsStorage`
- `src/ai_assistant/adapters/vector_store_faiss.py`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.errors: AdapterError, VersionMismatchError`
  - → `ai_assistant.core.io_utils: atomic_write`
  - → `ai_assistant.core.ports.vector_store: IVectorStore`
- `src/ai_assistant/adapters/vector_store_memory.py`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.errors: VersionMismatchError`
  - → `ai_assistant.core.io_utils: atomic_write`
  - → `ai_assistant.core.ports.vector_store: IVectorStore`
- `src/ai_assistant/api/admin.py`
  - → `ai_assistant.api.deps: AppState, get_state`
  - → `ai_assistant.api.security: set_api_key`
- `src/ai_assistant/api/deps.py`
  - → `ai_assistant.adapters.factory: create_adapter`
  - → `ai_assistant.core.config: AppConfig, RAGStep`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.pipeline_steps: STEP_REGISTRY`
  - → `ai_assistant.core.ports: ILLM, IChatStorage, IChunker, IEmbedder, IReranker, IVectorStore`
  - → `ai_assistant.features.chat.manager: ChatManager`
- `src/ai_assistant/api/lifespan.py`
  - → `ai_assistant.api.deps: init_adapters`
  - → `ai_assistant.api.security: get_expected_api_key, set_api_key`
  - → `ai_assistant.api.static: _mount_static`
  - → `ai_assistant.core.config: AppConfig, load_config`
  - → `ai_assistant.core.logger: get_logger, setup_logging`
- `src/ai_assistant/api/middleware.py`
  - → `ai_assistant.core.metrics: increment_counter, observe_histogram`
- `src/ai_assistant/api/router.py`
  - → `ai_assistant.api.security: require_api_key`
  - → `ai_assistant.api: admin`
  - → `ai_assistant.features.chat: handlers`
  - → `ai_assistant.features.rag: handlers`
- `src/ai_assistant/api/security.py`
  - → `ai_assistant.core.logger: get_logger`
- `src/ai_assistant/core/pipeline.py`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
- `src/ai_assistant/core/pipeline_steps.py`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.domain.errors: EMBEDDER_NOT_PROVIDED, INTERNAL_SERVER_ERROR, LLM_NOT_PROVIDED, QUERY_EMBEDDING_MISSING, QUERY_MISSING, QUERY_TEXT_MISSING, VECTOR_STORE_NOT_PROVIDED, AdapterError`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.metrics: increment_counter`
  - → `ai_assistant.core.ports.tools: ToolCall`
  - → `ai_assistant.core.prompts: get_prompt`
  - → `ai_assistant.core.retry: with_retry`
  - → `ai_assistant.core.utils: count_tokens, get_context_limit`
- `src/ai_assistant/core/ports/chunker.py`
  - → `ai_assistant.core.domain.documents: Chunk, Document`
- `src/ai_assistant/core/ports/embedder.py`
  - → `ai_assistant.core.ports.closable: IClosable`
- `src/ai_assistant/core/ports/llm.py`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.ports.closable: IClosable`
- `src/ai_assistant/core/ports/reranker.py`
  - → `ai_assistant.core.domain.documents: Chunk`
- `src/ai_assistant/core/ports/storage.py`
  - → `ai_assistant.core.ports.initializable: IInitializable`
- `src/ai_assistant/core/ports/vector_store.py`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.ports.closable: IClosable`
- `src/ai_assistant/features/chat/handlers.py`
  - → `ai_assistant.api.deps: InitializedAppState, get_state`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.features.chat.schemas: ChatRequest, ChatResponse, OAIChatCompletion, OAIChatCompletionRequest, OAIChatMessage, OAIChoice, OAIDeltaChunk, OAIModel, OAIModelList`
- `src/ai_assistant/features/chat/manager.py`
  - → `ai_assistant.core.constants: FROZEN_NO_INFO_PHRASES`
  - → `ai_assistant.core.constants: RAG_NS_MAP`
  - → `ai_assistant.core.constants: RAG_PREFIX_RE`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.ports: ILLM, IChatStorage, IEmbedder, IReranker, IVectorStore`
  - → `ai_assistant.core.prompts: get_prompt`
  - → `ai_assistant.core.utils: count_tokens, get_context_limit`
- `src/ai_assistant/features/rag/handlers.py`
  - → `ai_assistant.adapters.factory: create_adapter`
  - → `ai_assistant.api.deps: InitializedAppState, get_state`
  - → `ai_assistant.core.constants: DOCUMENTS_ROOT`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.features.rag.indexing: index_folder`
  - → `ai_assistant.features.rag.manager: IndexingManager, RAGManager`
  - → `ai_assistant.features.rag.schemas: DeleteRequest, DeleteResponse, HealthResponse, IndexRequest, IndexResponse, NamespaceListResponse, QueryRequest, QueryResponse, SaveChatRequest`
- `src/ai_assistant/features/rag/indexing.py`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.features.rag.manager: IndexingManager`
- `src/ai_assistant/features/rag/manager.py`
  - → `ai_assistant.core.constants: FROZEN_NO_INFO_PHRASES`
  - → `ai_assistant.core.domain.documents: Chunk, Document`
  - → `ai_assistant.core.domain.messages: UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.ports: ILLM, IChunker, IEmbedder, IReranker, IVectorStore`
- `src/ai_assistant/main.py`
  - → `ai_assistant.api.deps: InitializedAppState, get_state`
  - → `ai_assistant.api.lifespan: lifespan`
  - → `ai_assistant.api.middleware: MetricsMiddleware`
  - → `ai_assistant.api.router: assemble_routers`
  - → `ai_assistant.core.metrics: get_metrics, get_metrics_json`
- `tests/conftest.py`
  - → `ai_assistant.api.deps: AppState`
  - → `ai_assistant.api.deps: get_state`
  - → `ai_assistant.core.config: load_config`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.ports.reranker: RerankResult`
  - → `ai_assistant.core: prompts`
  - → `ai_assistant.features.chat.manager: ChatManager`
  - → `ai_assistant.main: create_app`
- `tests/test_adapters_integration.py`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.embedder_openai_compatible: OpenAICompatibleEmbedder`
  - → `ai_assistant.adapters.llm_mock: MockLLM`
  - → `ai_assistant.adapters.llm_openai_compatible: OpenAICompatibleLLM`
  - → `ai_assistant.adapters.reranker_api: APIReranker`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.core.config: EmbedderConfig, LLMConfig`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata, Document`
  - → `ai_assistant.core.domain.errors: VersionMismatchError`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
- `tests/test_api_deps.py`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.api.deps: AppState, InitializedAppState, _STEP_MAP, get_state, init_adapters`
  - → `ai_assistant.core.config: AppConfig, RAGStep`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.pipeline_steps: STEP_REGISTRY`
  - → `ai_assistant.core.ports.storage: IChatStorage`
- `tests/test_api_e2e.py`
  - → `ai_assistant`
  - → `ai_assistant.core.config: AppConfig, NamespaceConfig`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.features.chat.manager: ChatManager`
  - → `ai_assistant.features.rag: handlers`
  - → `ai_assistant.features.rag: indexing`
  - → `ai_assistant.main: create_app`
- `tests/test_chat_manager_direct.py`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.core.config: NamespaceConfig`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.pipeline_steps: build_context, embed_query, retrieve`
  - → `ai_assistant.features.chat.manager: ChatManager`
- `tests/test_config.py`
  - → `ai_assistant.core.config: AppConfig`
- `tests/test_contracts.py`
  - → `ai_assistant.api.deps: InitializedAppState, init_adapters`
  - → `ai_assistant.api: deps`
  - → `ai_assistant.api: lifespan`
  - → `ai_assistant.core.config: AppConfig`
  - → `ai_assistant.core.config: EmbedderConfig`
  - → `ai_assistant.core.config: LLMConfig`
  - → `ai_assistant.core.config: load_config`
  - → `ai_assistant.core.ports: IChatStorage, IChunker, IClosable, IEmbedder, ILLM, IReranker, IVectorStore`
  - → `ai_assistant.features.chat.manager: ChatManager`
  - → `ai_assistant.features.chat.schemas: ChatRequest, ChatResponse, OAIChatCompletionRequest`
  - → `ai_assistant.features.rag.manager: RAGManager`
  - → `ai_assistant.features.rag.schemas: IndexRequest, QueryRequest, QueryResponse`
- `tests/test_core_critical.py`
  - → `ai_assistant.core.config: AppConfig`
  - → `ai_assistant.core.config: ChatConfig`
  - → `ai_assistant.core.config: ChunkerConfig`
  - → `ai_assistant.core.config: VectorStoreConfig`
  - → `ai_assistant.core.constants: FROZEN_NO_INFO_PHRASES`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.ports.tools: ToolResult`
  - → `ai_assistant.core.prompts: get_prompt`
  - → `ai_assistant.core: prompts`
- `tests/test_fuzz.py`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.domain.messages: UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.pipeline_steps: build_context`
- `tests/test_lifespan.py`
  - → `ai_assistant.api.deps: AppState, InitializedAppState, init_adapters`
  - → `ai_assistant.api.lifespan: _load_config, lifespan`
  - → `ai_assistant.core.config: AppConfig`
- `tests/test_malformed_sse.py`
  - → `ai_assistant.adapters.llm_openai_compatible: OpenAICompatibleLLM`
  - → `ai_assistant.api.deps: get_state`
  - → `ai_assistant.core.config: LLMConfig`
  - → `ai_assistant.core.domain.messages: UserMessage`
  - → `ai_assistant.main: create_app`
- `tests/test_pipeline_frozen_compat.py`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
- `tests/test_rag_pipeline.py`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.core.constants: RAG_NS_MAP`
  - → `ai_assistant.core.constants: RAG_NS_MAP, RAG_PREFIX_RE`
  - → `ai_assistant.core.constants: RAG_PREFIX_RE`
  - → `ai_assistant.core.domain.documents: Chunk, Document`
  - → `ai_assistant.core.domain.errors: EMBEDDER_NOT_PROVIDED, INTERNAL_SERVER_ERROR, LLM_NOT_PROVIDED, QUERY_EMBEDDING_MISSING, QUERY_MISSING, QUERY_TEXT_MISSING, VECTOR_STORE_NOT_PROVIDED`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.pipeline_steps: STEP_REGISTRY, build_context, embed_query, generate, hyde_query, rerank, retrieve, step`
  - → `ai_assistant.core.ports.reranker: RerankResult`
  - → `ai_assistant.core.ports.tools: ToolResult`
  - → `ai_assistant.core.prompts: _render, get_prompt`
- `tests/test_resilience.py`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.api.lifespan: _async_cleanup`
  - → `ai_assistant.api.lifespan: _load_config`
  - → `ai_assistant.core.config: AppConfig, load_config`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.domain.errors: VersionMismatchError`
  - → `ai_assistant.core.domain.messages: UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.pipeline_steps: embed_query`
  - → `ai_assistant.core.pipeline_steps: generate`
  - → `ai_assistant.core.ports.closable: IClosable`
  - → `ai_assistant.features.chat.handlers: chat`
  - → `ai_assistant.features.chat.handlers: openai_chat_completions`
  - → `ai_assistant.features.chat.manager: ChatManager`
  - → `ai_assistant.features.chat.schemas: ChatRequest`
  - → `ai_assistant.features.chat.schemas: OAIChatCompletionRequest, OAIChatMessage`
- `tests/test_router_compile.py`
  - → `ai_assistant.api.router: assemble_routers`
- `tests/test_security.py`
  - → `ai_assistant.api.admin: update_api_key, _UpdateApiKeyRequest`
  - → `ai_assistant.api.deps: AppState`
  - → `ai_assistant.api.security: SECURITY_MAX_BODY, check_request_size, get_expected_api_key, require_api_key, set_api_key`
- `tests/test_smoke_pyproject.py`
  - → `ai_assistant`
  - → `ai_assistant.api.static: _mount_static`
  - → `ai_assistant.api: deps`
  - → `ai_assistant.api: lifespan`
- `tests/test_stress.py`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.api.deps: get_state`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.main: create_app`
- `tests/test_tokenizer.py`
  - → `ai_assistant.core.utils: _resolve_tokenizer_dir, count_tokens, get_tokenizer`

---

## 📦 Files

### Full Content
- `.gitignore`
- `.hypothesis/.gitignore`
- `README.md`
- `config.yaml`
- `pyproject.toml`
- `src/ai_assistant/api/__init__.py`
- `src/ai_assistant/api/admin.py`
- `src/ai_assistant/api/deps.py`
- `src/ai_assistant/api/lifespan.py`
- `src/ai_assistant/api/middleware.py`
- `src/ai_assistant/api/router.py`
- `src/ai_assistant/api/security.py`
- `src/ai_assistant/api/static.py`
- `src/ai_assistant/core/__init__.py`
- `src/ai_assistant/core/config.py`
- `src/ai_assistant/core/constants.py`
- `src/ai_assistant/core/domain/__init__.py`
- `src/ai_assistant/core/domain/documents.py`
- `src/ai_assistant/core/domain/errors.py`
- `src/ai_assistant/core/domain/messages.py`
- `src/ai_assistant/core/domain/pipeline.py`
- `src/ai_assistant/core/io_utils.py`
- `src/ai_assistant/core/logger.py`
- `src/ai_assistant/core/metrics.py`
- `src/ai_assistant/core/pipeline.py`
- `src/ai_assistant/core/pipeline_steps.py`
- `src/ai_assistant/core/ports/__init__.py`
- `src/ai_assistant/core/ports/chunker.py`
- `src/ai_assistant/core/ports/closable.py`
- `src/ai_assistant/core/ports/embedder.py`
- `src/ai_assistant/core/ports/initializable.py`
- `src/ai_assistant/core/ports/llm.py`
- `src/ai_assistant/core/ports/reranker.py`
- `src/ai_assistant/core/ports/storage.py`
- `src/ai_assistant/core/ports/tools.py`
- `src/ai_assistant/core/ports/vector_store.py`
- `src/ai_assistant/core/prompts/__init__.py`
- `src/ai_assistant/core/prompts/v1/rag_creative.j2`
- `src/ai_assistant/core/prompts/v1/rag_default.j2`
- `src/ai_assistant/core/prompts/v1/rag_strict.j2`
- `src/ai_assistant/core/prompts/v1/summarize.j2`
- `src/ai_assistant/core/retry.py`
- `src/ai_assistant/core/utils.py`
- `src/ai_assistant/features/chat/handlers.py`
- `src/ai_assistant/features/chat/schemas.py`
- `src/ai_assistant/features/rag/handlers.py`
- `src/ai_assistant/features/rag/schemas.py`

### Signatures Only
- `launcher.py`
- `src/ai_assistant/__init__.py`
- `src/ai_assistant/adapters/__init__.py`
- `src/ai_assistant/adapters/chunker_simple.py`
- `src/ai_assistant/adapters/embedder_mock.py`
- `src/ai_assistant/adapters/embedder_openai_compatible.py`
- `src/ai_assistant/adapters/factory.py`
- `src/ai_assistant/adapters/llm_mock.py`
- `src/ai_assistant/adapters/llm_openai_compatible.py`
- `src/ai_assistant/adapters/reranker_api.py`
- `src/ai_assistant/adapters/storage_sqlite.py`
- `src/ai_assistant/adapters/vector_store_faiss.py`
- `src/ai_assistant/adapters/vector_store_memory.py`
- `src/ai_assistant/features/__init__.py`
- `src/ai_assistant/features/chat/__init__.py`
- `src/ai_assistant/features/chat/manager.py`
- `src/ai_assistant/features/rag/__init__.py`
- `src/ai_assistant/features/rag/indexing.py`
- `src/ai_assistant/features/rag/manager.py`
- `src/ai_assistant/main.py`

### Listed Only (no content)
- `.gitattributes`
- `.hypothesis/constants/00d08ecc206d19a2`
- `.hypothesis/constants/062da15881e1bbb7`
- `.hypothesis/constants/0a9a37d490bd2ac6`
- `.hypothesis/constants/0e1b7747ffb570b8`
- `.hypothesis/constants/0fea382fa0f49e77`
- `.hypothesis/constants/121d3a7af69b2e20`
- `.hypothesis/constants/1517471990e5338f`
- `.hypothesis/constants/176e90709ffa84f7`
- `.hypothesis/constants/1a2848e19324b132`
- `.hypothesis/constants/1f0c0635d7b70b2e`
- `.hypothesis/constants/1f3ca08de451d5fa`
- `.hypothesis/constants/2373115ed2705e46`
- `.hypothesis/constants/26210ca72a1b6627`
- `.hypothesis/constants/2662f70833eb6408`
- `.hypothesis/constants/26bbf6f8657ded2f`
- `.hypothesis/constants/2e0038433715aceb`
- `.hypothesis/constants/300be2b7c00adf58`
- `.hypothesis/constants/34ae9ae2a7915f47`
- `.hypothesis/constants/42c8d01dab10446b`
- `.hypothesis/constants/4bf5a448f35f8728`
- `.hypothesis/constants/53ddf82fba92383e`
- `.hypothesis/constants/547983fd2998eac5`
- `.hypothesis/constants/567fa9acd526ce98`
- `.hypothesis/constants/5a77869d21ccf7f0`
- `.hypothesis/constants/5d66fcc73a312cf6`
- `.hypothesis/constants/65af6fe9597bc739`
- `.hypothesis/constants/68badcc12bc11d16`
- `.hypothesis/constants/68e2d4459133caa9`
- `.hypothesis/constants/6b4e2be9f971086f`
- `.hypothesis/constants/72ba1bf5d8575399`
- `.hypothesis/constants/72ff6543086ffeab`
- `.hypothesis/constants/7aa6bbe0ad659d13`
- `.hypothesis/constants/82d84f628bfde547`
- `.hypothesis/constants/86119404a24cc8b5`
- `.hypothesis/constants/86783eff27f53448`
- `.hypothesis/constants/8aa58d636feff795`
- `.hypothesis/constants/8bfcfc15e19711e1`
- `.hypothesis/constants/8cb43f130c8f3a11`
- `.hypothesis/constants/8cfdcaffaa4b0f87`
- `.hypothesis/constants/9165caa579a5ca7a`
- `.hypothesis/constants/9bfda43d3142e126`
- `.hypothesis/constants/9dd7b7551596bfad`
- `.hypothesis/constants/a0f8740ab7f36456`
- `.hypothesis/constants/a4232c03c0a5df7d`
- `.hypothesis/constants/a541d6fdb5926928`
- `.hypothesis/constants/a9be3382e044cca6`
- `.hypothesis/constants/acbcc51f48b8db85`
- `.hypothesis/constants/b1ed91e5d16f251d`
- `.hypothesis/constants/bb1fe1dc12b93764`
- `.hypothesis/constants/bd3fbe66aa331706`
- `.hypothesis/constants/cd30ec032838cc80`
- `.hypothesis/constants/cdd098fb9d7cc65a`
- `.hypothesis/constants/de1cc2969519f477`
- `.hypothesis/constants/e47a51605024a02e`
- `.hypothesis/constants/eff07b744e4ce459`
- `.hypothesis/constants/fc0f735ee28793ba`
- `.hypothesis/constants/fcc7def15a753093`
- `.hypothesis/tmp/tmphug7pvx0`
- `.hypothesis/unicode_data/15.1.0/charmap.json.gz`
- `.hypothesis/unicode_data/15.1.0/codec-utf-8.json.gz`
- `open_terminal.bat`
- `scripts/audit_project.py`
- `scripts/check_all.py`
- `scripts/check_llm.py`
- `scripts/check_mutations.py`
- `scripts/check_mypy.py`
- `scripts/check_rag.py`
- `scripts/check_ruff.py`
- `scripts/check_smoke.py`
- `scripts/clean_cache.py`
- `scripts/context_build.py`
- `scripts/download_tokenizers.py`
- `scripts/error_taxonomy_build.py`
- `scripts/index_documents.py`
- `scripts/pre_commit_check.py`
- `scripts/run_all_tests.py`
- `scripts/start.py`
- `scripts/stop.py`
- `scripts/structure.py`
- `tests/__init__.py`
- `tests/config.test.yaml`
- `tests/conftest.py`
- `tests/test_adapters_integration.py`
- `tests/test_api_deps.py`
- `tests/test_api_e2e.py`
- `tests/test_chat_manager_direct.py`
- `tests/test_config.py`
- `tests/test_contracts.py`
- `tests/test_core_critical.py`
- `tests/test_fuzz.py`
- `tests/test_lifespan.py`
- `tests/test_malformed_sse.py`
- `tests/test_pipeline_frozen_compat.py`
- `tests/test_rag_pipeline.py`
- `tests/test_resilience.py`
- `tests/test_router_compile.py`
- `tests/test_scripts_and_platform.py`
- `tests/test_security.py`
- `tests/test_smoke_pyproject.py`
- `tests/test_stress.py`
- `tests/test_tokenizer.py`

---

## 🔑 Full Code

### `.gitignore`
```text
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
venv/
env/
ENV/
.venv

# IDE
.idea/
.vscode/
*.swp
*.swo
*~
.coverage
htmlcov/

# Data
data/
*.faiss
*.db
*.store.json

# Environment
.env
.env.local

# Logs
*.log

# User content (never commit)
sources/
vendor/

# src-layout build artifacts
src/*.egg-info/
src/**/*.egg-info/

# runtime
scripts/*.pid
scripts/*.log
tests/.pytest_cache/
docs/context_build_*.md
tests/tests_run_*.log
MagicMock/

```

### `.hypothesis/.gitignore`
```text
# This .gitignore file was automatically created by Hypothesis. Hypothesis gitignores
# .hypothesis by default, because we generally recommend that .hypothesis not be checked
# into version control.
#
# If you *would* like to check .hypothesis into version control, you should delete this
# file. Hypothesis will not re-create this .gitignore unless .hypothesis is deleted (and
# if it does, that's a bug - please report it!)

*

```

### `README.md`
```text
# AI Assistant

Модульный фреймворк для локальных LLM. Работает offline, поддерживает RAG, совместим с OpenAI API.

## Возможности

- 💬 Чат с памятью и контекстом
- 📚 RAG: поиск по документам с namespace'ами (`[p]ersonal`, `[w]ork`, `[o]ther`, `[c]ode`, `[b]ooks`)
- 🔌 Поддержка любых OpenAI-compatible серверов (llama.cpp, Ollama, vLLM)
- 🧠 Работает полностью offline (mock-режим)

## Быстрый старт

```bash
# 1. Установка
pip install -e ".[faiss]"

# 2. Настройка LLM-сервера
# Варианты:
# • llama-server: llama-server.exe -m model.gguf --port 8080
# • Ollama: ollama serve
# • vLLM: python -m vllm.entrypoints.openai.api_server --model ...

# 3. Конфиг
# Отредактируй config.yaml:
# llm.api_base: http://127.0.0.1:8080/v1
# llm.model: имя-модели-на-сервере

# 4. Запуск
python launcher.py        # интерактивный лаунчер
# Или напрямую:
python scripts/start.py
python main.py
uvicorn ai_assistant.main:app --host 0.0.0.0 --port 8000

# 5. UI
# Подключи любой OpenAI-compatible клиент к http://localhost:8000
# Рекомендуется: Page Assist (браузерное расширение)
```

## RAG — поиск по документам

```bash
# Индексация документов
python scripts/index_documents.py
```

В чате используй префиксы:

| Префикс | Namespace |
|---------|-----------|
| `[p]` | personal |
| `[w]` | work |
| `[o]` | other |
| `[c]` | code |
| `[b]` | books |

## Рекомендуемые модели

**LLM:**

- `gemma-3-4b-it` — быстрая, качественная, мультиязычная
- `qwen2.5-7b-instruct` — хороший баланс скорость/качество
- `llama-3.2-3b-instruct` — компактная, для слабых GPU

**Embedder:**

- `nomic-embed-text-v1.5` — размерность 768
- `mxbai-embed-large-v1` — размерность 1024

> ⚠️ **Важно:** `embedder.dim` в `config.yaml` **должен** совпадать с `vector_store.dim`.

## Требования

- Python 3.13+
- 8+ GB RAM (для CPU-режима)
- GPU опционально (CUDA/Metal/Vulkan)

---

All rights reserved. For personal use only.

```

### `config.yaml`
```text
# AI Assistant — Универсальная конфигурация
# Работает с любым OpenAI-compatible API: llama-server, Ollama, vLLM, OpenAI
# Переменные окружения с префиксом AI_* переопределяют значения ниже

# ── Приложение ──
app_name: ai-assistant
debug: false
host: 0.0.0.0
port: 8000
config_version: "1.5.0"

# ── CORS ──
cors:
  allow_origins:
    - "http://localhost"
    - "http://127.0.0.1"
    - "null"
  allow_credentials: true
  allow_methods: ["*"]
  allow_headers: ["*"]

# ── Chat ──
chat:
  history_limit: 10
  max_context_tokens: 4096
  tokenizer_model: "gpt-4o"
  tokenizer_local_dir: "./data/tokenizers"

# ── Chunker ──
chunker:
  provider: simple
  chunk_size: 512
  chunk_overlap: 50

# ── Embedder ──
embedder:
  provider: openai_compatible
  api_base: http://127.0.0.1:8081/v1
  api_key: "sk-local"
  model: embeddinggemma-300m-q8_0
  dim: 768
  timeout: 60.0
  n_gpu_layers: 0        # -1 = все слои на GPU, 0 = только CPU, 10 = 10 слоёв на GPU
  n_batch: 512            # размер батча для обработки
  n_ubatch: 64            # микро-батч
  mmap: true              # memory-mapped файлы (экономия RAM)
  mlock: false            # блокировка страниц в RAM (не выгружать в swap)

# ── LLM ──
llm:
  provider: openai_compatible
  api_base: http://127.0.0.1:8080/v1
  api_key: "sk-local"
  model: gemma-4-e2b-it
  available_models:
    - gemma-4-e2b-it
    - phi-4-mini-reasoning
    - qwen3.5-4b
  max_tokens: 4096
  temperature: 0.7
  top_p: 0.95
  top_k: 40
  min_p: 0.05
  repeat_penalty: 1.1
  presence_penalty: 0.0
  frequency_penalty: 0.0
  stop_sequences: []
  timeout: 300.0
  server_context_size: 4096

# ── Vector Store ──
vector_store:
  provider: faiss
  index_path: ./data/indices
  metric: l2
  dim: 768                # ← ОБЯЗАТЕЛЬНО равно embedder.dim

# ── Storage ──
storage:
  provider: sqlite
  db_path: ./data/storage.db


# ── Reranker ──
reranker:
  provider: null
  model: rerank-multilingual-v3.0
  api_base: https://api.cohere.com
  api_key: null
  timeout: 30.0
  threshold: 0.3

# ── RAG ──
rag:
  steps:
    - embed_query
    - retrieve
    - rerank
    - build_context
    - generate
  prompt_version: v1
  prompt_name: rag_strict
  top_k: 5
  default_namespace: "default"
  relevance_threshold: 0.1
  max_tool_iterations: 5

# ── Namespaces ──
namespaces:
  personal:
    threshold: 0.1
    chunk_size: 512
    prompt: rag_strict
  work:
    threshold: 0.3
    chunk_size: 1024
    prompt: rag_creative
  other:
    threshold: 0.1
    chunk_size: 512
    prompt: rag_strict
  code:
    threshold: 0.1
    chunk_size: 512
    prompt: rag_strict
  books:
    threshold: 0.1
    chunk_size: 512
    prompt: rag_strict

# ── Безопасность ──
security:
  api_key: sk-local-api-key
  rate_limit: "100/minute"
  max_body_size: 10485760
  allowed_hosts: ["localhost", "127.0.0.1"]

```

### `pyproject.toml`
```text
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ai-assistant"
version = "1.0.0"
description = "Модульный AI-фреймворк с неизменяемым ядром"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.110.0,<1.0.0",
    "uvicorn[standard]>=0.29.0,<1.0.0",
    "pydantic>=2.7.0,<3.0.0",
    "pydantic-settings>=2.2.0,<3.0.0",
    "pyyaml>=6.0.1,<7.0.0",
    "numpy>=1.26.0,<2.0.0",
    "httpx>=0.27.0,<1.0.0",
    "aiofiles>=23.2.1,<24.0.0",
    "tiktoken>=0.7.0,<1.0.0",
    "tokenizers>=0.19.0,<1.0.0",
    "jinja2>=3.1.3,<4.0.0",
    "sqlmodel>=0.0.18,<1.0.0",
    "sqlalchemy[asyncio]>=2.0.0,<3.0.0",
    "aiosqlite>=0.20.0,<1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0,<9.0.0",
    "pytest-asyncio>=0.23.0,<1.0.0",
    "respx>=0.21.0,<1.0.0",
    "ruff>=0.4.0,<1.0.0",
    "mypy>=1.10.0,<2.0.0",
    "types-PyYAML>=6.0.12,<7.0.0",
    "types-aiofiles>=23.2.0,<24.0.0",
    "pre-commit>=3.7.0,<4.0.0",
    "pytest-timeout>=2.3.0,<3.0.0",
    "mutmut>=2.4.0,<3.0.0",
    "hypothesis>=6.100.0,<7.0.0",
    "vulture>=2.11,<3.0.0",
]
faiss = [
    "faiss-cpu>=1.8.0,<2.0.0",
]

[tool.setuptools.packages.find]
where = ["src"]
include = ["ai_assistant*"]

[tool.ruff]
line-length = 88
target-version = "py313"
extend-exclude = ["scripts/", "tests/", "vendor/"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "ASYNC", "B", "SIM", "C4", "TCH"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.13"
strict = true
ignore_missing_imports = true
exclude = ["scripts/", "tests/", "vendor/"]
warn_return_any = false
disallow_untyped_calls = false
disallow_untyped_defs = false
warn_no_return = false
warn_unused_ignores = false

[[tool.mypy.overrides]]
module = [
    "ai_assistant.api.security",
    "ai_assistant.core.pipeline_steps",
    "ai_assistant.features.chat.manager",
    "ai_assistant.adapters.*",
    "ai_assistant.core.utils",
]
warn_return_any = false
disallow_untyped_defs = false
disallow_untyped_calls = false

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
timeout = 240
addopts = "-m 'not online'"

[tool.mutmut]
paths_to_mutate = ["src/ai_assistant/core/", "src/ai_assistant/adapters/", "src/ai_assistant/features/", "src/ai_assistant/api/", "src/ai_assistant/pipeline/"]
pytest_add_cli_args_test_selection = ["tests/"]
backup = false

```

### `src/ai_assistant/api/__init__.py`
```python
"""API layer — transport, DI, routing."""

```

### `src/ai_assistant/api/admin.py`
```python
"""Admin endpoints — diagnostics and runtime config updates."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ai_assistant.api.deps import AppState, get_state
from ai_assistant.api.security import set_api_key

__all__ = ["router"]

router = APIRouter(prefix="/admin", tags=["admin"])


class _CurrentModelResponse(BaseModel):
    model: str
    provider: str


class _UpdateApiKeyRequest(BaseModel):
    api_key: str | None = None


class _UpdateApiKeyResponse(BaseModel):
    updated: bool
    source: str


@router.get("/current-model", response_model=_CurrentModelResponse)
async def get_current_model(
    state: Annotated[AppState, Depends(get_state)],
) -> _CurrentModelResponse:
    cfg = state.config.llm
    return _CurrentModelResponse(
        model=getattr(cfg, "model", "unknown"),
        provider=cfg.provider,
    )


@router.post("/api-key", response_model=_UpdateApiKeyResponse)
async def update_api_key(
    req: _UpdateApiKeyRequest,
    state: Annotated[AppState, Depends(get_state)],
) -> _UpdateApiKeyResponse:
    if req.api_key is not None and not req.api_key:
        raise HTTPException(status_code=400, detail="api_key must be non-empty or None")
    set_api_key(req.api_key)
    source = "runtime_override" if req.api_key is not None else "env_var_or_none"
    return _UpdateApiKeyResponse(updated=True, source=source)

```

### `src/ai_assistant/api/deps.py`
```python
"""API dependencies — AppState, get_state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.core.config import AppConfig, RAGStep
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import STEP_REGISTRY
from ai_assistant.features.chat.manager import ChatManager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request

    from ai_assistant.core.domain.pipeline import PipelineData
    from ai_assistant.core.ports import (
        ILLM,
        IChatStorage,
        IChunker,
        IEmbedder,
        IReranker,
        IVectorStore,
    )

__all__ = [
    "AppState",
    "InitializedAppState",
    "get_state",
    "init_adapters",
]

_logger = get_logger("deps")


@dataclass
class AppState:
    """Application state container — pre-initialization, mutable for tests."""

    config: AppConfig
    llm: ILLM | None = None
    embedder: IEmbedder | None = None
    vector_store: IVectorStore | None = None
    chunker: IChunker | None = None
    reranker: IReranker | None = None
    pipeline: RAGPipeline | None = None
    storage: IChatStorage | None = None
    chat_manager: ChatManager | None = None
    limiter: object | None = None


@dataclass
class InitializedAppState:
    """Runtime application state — core adapters are guaranteed present."""

    config: AppConfig
    llm: ILLM
    embedder: IEmbedder
    vector_store: IVectorStore
    pipeline: RAGPipeline
    storage: IChatStorage
    chunker: IChunker
    chat_manager: ChatManager
    reranker: IReranker | None = None
    limiter: object | None = None


# ---------------------------------------------------------------------------
# Explicit step map — replaces mutable @step registry
# ---------------------------------------------------------------------------

_STEP_MAP: dict[RAGStep, Callable[[PipelineData], Awaitable[PipelineData]]] = {
    RAGStep(k): v for k, v in STEP_REGISTRY.items() if k in {m.value for m in RAGStep}
}


def _build_step_funcs(
    cfg: AppConfig,
    stop_at: RAGStep | None = None,
) -> list[Callable[[PipelineData], Awaitable[PipelineData]]]:
    """Build pipeline step functions. Stops before *stop_at* if provided."""
    step_funcs: list[Callable[[PipelineData], Awaitable[PipelineData]]] = []
    for step in cfg.rag.steps:
        if stop_at is not None and step == stop_at:
            break
        func = _STEP_MAP.get(step)
        if func is None:
            raise ValueError(f"Unknown step: {step}")
        step_funcs.append(func)
    return step_funcs


# ---------------------------------------------------------------------------
# Adapter initialization
# ---------------------------------------------------------------------------


async def init_adapters(config: AppConfig) -> InitializedAppState:
    """Initialize all adapters via factory and return populated InitializedAppState."""
    state = AppState(config=config)
    cfg = config

    state.chunker = create_adapter("chunker", cfg.chunker.provider, cfg.chunker)
    state.embedder = create_adapter("embedder", cfg.embedder.provider, cfg.embedder)
    state.llm = create_adapter("llm", cfg.llm.provider, cfg.llm)
    state.vector_store = create_adapter(
        "vector_store",
        cfg.vector_store.provider,
        cfg.vector_store,
    )

    if cfg.reranker is not None and cfg.reranker.provider is not None:
        try:
            state.reranker = create_adapter(
                "reranker",
                cfg.reranker.provider,
                cfg.reranker,
            )
        except ValueError:
            _logger.exception(
                "Reranker '%s' not available",
                cfg.reranker.provider,
            )

    try:
        state.storage = create_adapter("storage", cfg.storage.provider, cfg.storage)
    except (ValueError, ImportError):
        _logger.exception(
            "Storage adapter '%s' not available",
            cfg.storage.provider,
        )

    if state.storage is not None:
        await state.storage.init_db()

    step_funcs = _build_step_funcs(cfg)
    state.pipeline = RAGPipeline(step_funcs)

    retrieval_funcs = _build_step_funcs(cfg, stop_at=RAGStep.GENERATE)
    retrieval_pipeline = RAGPipeline(retrieval_funcs) if retrieval_funcs else None

    state.chat_manager = ChatManager(
        llm=state.llm,
        storage=state.storage,
        history_limit=cfg.chat.history_limit,
        max_context_tokens=cfg.chat.max_context_tokens,
        tokenizer_model=cfg.chat.tokenizer_model,
        embedder=state.embedder,
        vector_store=state.vector_store,
        reranker=state.reranker,
        pipeline=retrieval_pipeline,
        namespaces=cfg.namespaces,
        prompt_version=cfg.rag.prompt_version,
        top_k=cfg.rag.top_k,
    )

    if state.llm is None:
        raise RuntimeError("LLM adapter failed to initialize")
    if state.embedder is None:
        raise RuntimeError("Embedder adapter failed to initialize")
    if state.vector_store is None:
        raise RuntimeError("Vector store adapter failed to initialize")
    if state.pipeline is None:
        raise RuntimeError("Pipeline failed to initialize")
    if state.storage is None:
        raise RuntimeError("Storage adapter failed to initialize")
    if state.chunker is None:
        raise RuntimeError("Chunker adapter failed to initialize")
    if state.chat_manager is None:
        raise RuntimeError("Chat manager failed to initialize")
    return InitializedAppState(
        config=cfg,
        llm=state.llm,
        embedder=state.embedder,
        vector_store=state.vector_store,
        pipeline=state.pipeline,
        storage=state.storage,
        chunker=state.chunker,
        reranker=state.reranker,
        chat_manager=state.chat_manager,
        limiter=state.limiter,
    )


def get_state(request: Request) -> InitializedAppState:
    """Get initialized app state. Raises RuntimeError if missing."""
    app_state = getattr(request.app.state, "app_state", None)
    if app_state is None:
        raise RuntimeError("State not initialized")
    return app_state

```

### `src/ai_assistant/api/lifespan.py`
```python
"""Application lifespan — startup/shutdown with graceful cleanup."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from ai_assistant.api.deps import init_adapters
from ai_assistant.api.security import get_expected_api_key, set_api_key
from ai_assistant.core.config import AppConfig, load_config
from ai_assistant.core.logger import get_logger, setup_logging

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI

__all__ = ["lifespan"]

logger = get_logger("lifespan")


def _load_config() -> AppConfig:
    """Load config from YAML, fallback to env defaults."""
    config_path = os.getenv("AI_CONFIG_PATH", "config.yaml")
    return load_config(config_path)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle."""
    config = _load_config()
    app.state.config = config

    from ai_assistant.api.static import _mount_static

    _mount_static(app, config)

    log_file = config.log_file
    if log_file is None:
        log_file = "./data/app.log"
    setup_logging(
        level="DEBUG" if config.debug else "INFO",
        log_file=log_file,
    )

    if config.security.api_key and get_expected_api_key() is None:
        set_api_key(config.security.api_key)

    state = await init_adapters(config)
    app.state.app_state = state

    # Load persisted indices from disk
    index_path = config.vector_store.index_path if config.vector_store else None
    if index_path and state.vector_store is not None:
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
            for ns in namespaces:
                await state.vector_store.load(index_path, namespace=ns)
            logger.info(
                "Loaded %d namespace indices from %s", len(namespaces), index_path
            )
        except Exception:
            logger.exception("Index load failed on startup")

    pid_file = Path("data/server.pid")
    try:
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(pid_file.write_text, str(os.getpid()), encoding="utf-8")
    except OSError as exc:
        logger.warning("Failed to write PID file: %s", exc)

    try:
        yield
    finally:
        await _async_cleanup(app, config)
        _cleanup(app, config, pid_file)


def _cleanup(app: FastAPI, config: AppConfig, pid_file: Path) -> None:
    """Synchronous cleanup actions."""
    if pid_file.exists():
        try:
            pid_file.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Failed to remove PID file: %s", exc)


async def _async_cleanup(app: FastAPI, config: AppConfig) -> None:
    """Async cleanup actions."""
    try:
        state = app.state.app_state
    except AttributeError:
        logger.warning("No app state found during shutdown")
        return

    # 1. Persist indices FIRST — metrics/adapter shutdown may block/hang
    index_path = config.vector_store.index_path if config.vector_store else None
    if index_path and state.vector_store is not None:
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
            saved = 0
            for ns in namespaces:
                try:
                    await asyncio.wait_for(
                        state.vector_store.save(index_path, namespace=ns),
                        timeout=10.0,
                    )
                    logger.info("Index saved: %s/%s", index_path, ns)
                    saved += 1
                except TimeoutError:
                    logger.warning("Index save timed out: %s/%s", index_path, ns)
            logger.info("Indices persisted: %d/%d namespace(s)", saved, len(namespaces))
        except Exception:
            logger.exception("Index save failed")

    # 2. Graceful adapter shutdown — add new closable adapters here
    adapters = (
        (state.llm, "llm"),
        (state.embedder, "embedder"),
        (state.vector_store, "vector_store"),
        (state.storage, "storage"),
        (state.reranker, "reranker"),
        (state.chunker, "chunker"),
    )
    for adapter, name in adapters:
        if adapter is not None:
            try:
                shutdown = getattr(adapter, "shutdown", None)
                if shutdown is not None and callable(shutdown):
                    await shutdown()
            except Exception:
                logger.exception("%s shutdown failed", name)

```

### `src/ai_assistant/api/middleware.py`
```python
"""FastAPI middleware for request metrics."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

from ai_assistant.core.metrics import increment_counter, observe_histogram

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from fastapi import Request, Response

__all__ = ["MetricsMiddleware"]


class MetricsMiddleware(BaseHTTPMiddleware):
    """Count requests and record latency per path."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method
        path = request.url.path
        start = time.perf_counter()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.perf_counter() - start
            status = str(response.status_code) if response is not None else "500"
            increment_counter(
                "ai_assistant_requests_total",
                labels={"method": method, "path": path, "status": status},
            )
            observe_histogram(
                "ai_assistant_request_duration_seconds",
                value=duration,
                labels={"path": path},
            )

```

### `src/ai_assistant/api/router.py`
```python
"""Auto-discovery router assembly."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ai_assistant.api import admin
from ai_assistant.api.security import require_api_key

# Explicit feature handler imports — import errors surface at compile time
# instead of being deferred to the first HTTP request.
from ai_assistant.features.chat import handlers as _chat_handlers
from ai_assistant.features.rag import handlers as _rag_handlers

__all__ = ["assemble_routers"]

# Tag used to identify OpenAI-compatible routers (kept at root, no prefix).
_OAI_TAG = "chat-oai"

# Explicit router registry — missing handlers fail immediately at import time.
# Add new routers here when adding feature handlers.
_ROUTERS: list[APIRouter] = [
    admin.router,
    _chat_handlers.router,
    _chat_handlers.router_oai,
    _rag_handlers.router,
]


def assemble_routers() -> list[APIRouter]:
    """Collect routers from explicitly imported feature handlers + admin."""
    routers = list(_ROUTERS)

    # Wrap each router with API key dependency and apply /api/v1 prefix
    # OpenAI-compatible routers (tagged with _OAI_TAG) stay at root without wrapping
    wrapped: list[APIRouter] = []
    for router in routers:
        is_oai = _OAI_TAG in router.tags
        if is_oai:
            # OpenAI routers keep their original paths, no prefix, no extra wrapper
            wrapped.append(router)
        else:
            # Legacy routers get /api/v1 prefix + API key dependency via wrapper
            wrapper = APIRouter(dependencies=[Depends(require_api_key)])
            wrapper.include_router(router, prefix="/api/v1")
            wrapped.append(wrapper)

    return wrapped

```

### `src/ai_assistant/api/security.py`
```python
"""API security — API key enforcement via FastAPI dependency.

Security config is loaded ONCE at startup into AppState.config.security.
This module reads from AppState via request state or env var fallback.
No YAML reloading on hot path.
"""

from __future__ import annotations

import os
import threading

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ai_assistant.core.logger import get_logger

__all__ = [
    "check_request_size",
    "get_expected_api_key",
    "require_api_key",
    "SECURITY_MAX_BODY",
    "set_api_key",
]

_logger = get_logger("security")

SECURITY_MAX_BODY = 10_485_760
bearer_scheme = HTTPBearer(auto_error=False)

# Mutable state for rare runtime key rotation (admin endpoint)
_override_api_key: str | None = None
_lock = threading.Lock()


def get_expected_api_key() -> str | None:
    """Return API key from env var, runtime override, or None.

    Callers that have AppState should prefer state.config.security.api_key.
    This function exists for code paths without AppState access.
    """
    env_key = os.getenv("AI_API_KEY")
    if env_key is not None:
        return env_key or None
    with _lock:
        return _override_api_key


def set_api_key(key: str | None) -> None:
    """Runtime API key rotation — called from admin endpoint."""
    global _override_api_key
    with _lock:
        _override_api_key = key


async def check_request_size(request: Request) -> None:
    cl = request.headers.get("content-length")
    # Default max body size — can be overridden by caller with AppState
    max_sz = SECURITY_MAX_BODY
    if cl and int(cl) > int(max_sz):
        raise HTTPException(status_code=413, detail="Payload too large")


_bearer_dependency = Depends(bearer_scheme)


async def require_api_key(
    credentials: HTTPAuthorizationCredentials = _bearer_dependency,
) -> None:
    expected = get_expected_api_key()
    if not expected:
        raise HTTPException(status_code=401, detail="API key not configured")
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing API key")
    if credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

```

### `src/ai_assistant/api/static.py`
```python
"""Static file mounting — pure HTTP concern."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from fastapi.staticfiles import StaticFiles

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["_mount_static"]


def _mount_static(app: FastAPI, config: Any) -> None:
    """Mount /ui once, only if directory exists."""
    if getattr(app.state, "static_mounted", False):
        return
    ui_cfg = getattr(config, "ui", None)
    if ui_cfg is None:
        return
    static_dir = Path(ui_cfg.static_path)
    if not static_dir.is_absolute():
        static_dir = Path(__file__).parent.parent / static_dir
    if static_dir.exists():
        app.mount(
            "/ui",
            StaticFiles(directory=str(static_dir), html=True),
            name="static",
        )
        app.state.static_mounted = True

```

### `src/ai_assistant/core/__init__.py`
```python
"""Sacred core — immutable interfaces and domain."""

from . import (
    config,
    domain,
    io_utils,
    pipeline,
    ports,
    prompts,
    retry,
    utils,
)

__all__ = [
    "domain",
    "ports",
    "prompts",
    "config",
    "pipeline",
    "retry",
    "io_utils",
    "utils",
]

```

### `src/ai_assistant/core/config.py`
```python
"""Application configuration — Pydantic + env-prefix AI__."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "AppConfig",
    "ChatConfig",
    "ChunkerConfig",
    "CORSConfig",
    "EmbedderConfig",
    "LLMConfig",
    "load_config",
    "NamespaceConfig",
    "RAGConfig",
    "RerankerConfig",
    "SecurityConfig",
    "StorageConfig",
    "UIConfig",
    "VectorStoreConfig",
]


class CORSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CORS_", extra="forbid")
    allow_origins: list[str] = Field(default_factory=list)
    allow_credentials: bool = True
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])


class UIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_UI_", extra="forbid")
    static_path: str = "./ui"


class ChatConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CHAT_", extra="forbid")
    history_limit: int = 10
    max_history_messages: int = 10_000
    max_context_tokens: int | None = None
    tokenizer_model: str = "gpt-4o"
    tokenizer_local_dir: str = "./data/tokenizers"


class ChunkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CHUNKER_", extra="forbid")
    provider: str = "simple"
    chunk_size: int = 512
    chunk_overlap: int = 50


class EmbedderConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_EMBEDDER_", extra="forbid")
    provider: str = "mock"
    model: str = "text-embedding-3-small"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    dim: int = 384
    timeout: float = 60.0
    n_gpu_layers: int = 0
    n_batch: int = 512
    n_ubatch: int = 64
    mmap: bool = True
    mlock: bool = False


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_LLM_", extra="forbid")
    provider: str = "mock"
    model: str = "gpt-4o-mini"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    available_models: list[str] = Field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 300.0
    stop_sequences: list[str] = Field(default_factory=list)
    system_message: str | None = None
    # === Sampling ===
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=-1)
    min_p: float = Field(default=0.05, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=0.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    server_context_size: int | None = None
    # === llama.cpp / local backend runtime ===
    n_gpu_layers: int = 0
    n_batch: int = 512
    n_ubatch: int = 64
    mmap: bool = True
    mlock: bool = False


class VectorStoreConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_VECTOR_STORE_", extra="forbid")
    provider: str = "memory"
    index_path: str = "./data/indices/default"
    metric: str = "l2"
    dim: int = 384
    max_chunks: int = 100_000
    max_document_size: int = 10_485_760


class StorageConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_STORAGE_", extra="forbid")
    provider: str = "sqlite"
    db_path: str = "./data/storage.db"


class RerankerConfig(BaseSettings):
    """Reranker configuration — optional, backward compatible."""

    model_config = SettingsConfigDict(env_prefix="AI_RERANKER_", extra="forbid")
    provider: str | None = None  # "api" or None for no reranker
    model: str = "rerank-multilingual-v3.0"
    api_base: str = "https://api.cohere.com"
    api_key: str | None = None
    timeout: float = 30.0
    threshold: float = 0.3


class RAGStep(StrEnum):
    """RAG pipeline step identifiers — type-safe replacement for raw strings."""

    EMBED_QUERY = "embed_query"
    HYDE_QUERY = "hyde_query"
    MULTI_RETRIEVE = "multi_retrieve"
    RETRIEVE = "retrieve"
    RERANK = "rerank"
    BUILD_CONTEXT = "build_context"
    GENERATE = "generate"


class RAGConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_RAG_", extra="forbid")
    steps: list[RAGStep] = Field(
        default_factory=lambda: [
            RAGStep.EMBED_QUERY,
            RAGStep.RETRIEVE,
            RAGStep.RERANK,
            RAGStep.BUILD_CONTEXT,
            RAGStep.GENERATE,
        ]
    )
    prompt_version: str = "v1"
    prompt_name: str = "rag_strict"
    top_k: int = 5
    default_namespace: str = "default"
    relevance_threshold: float = 0.3
    max_tool_iterations: int = 5


class SecurityConfig(BaseSettings):
    """Security configuration — loaded once at startup."""

    model_config = SettingsConfigDict(env_prefix="AI_SECURITY_", extra="forbid")
    api_key: str | None = None
    rate_limit: str = "100/minute"
    max_body_size: int = 10_485_760
    allowed_hosts: list[str] = Field(default_factory=list)


class NamespaceConfig(BaseModel):
    """Per-namespace RAG overrides."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    relevance_threshold: float = Field(default=0.1, validation_alias="threshold")
    chunk_size: int = 512
    prompt: str = "rag_strict"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        extra="forbid",
    )
    app_name: str = "ai-assistant"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    config_version: str = "1.5.0"
    log_file: str | None = None
    cors: CORSConfig = Field(default_factory=CORSConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    chunker: ChunkerConfig = Field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    namespaces: dict[str, NamespaceConfig] = Field(
        default_factory=lambda: {
            "personal": NamespaceConfig(
                relevance_threshold=0.1, chunk_size=512, prompt="rag_strict"
            ),
            "work": NamespaceConfig(
                relevance_threshold=0.3, chunk_size=1024, prompt="rag_creative"
            ),
            "other": NamespaceConfig(),
            "code": NamespaceConfig(),
            "books": NamespaceConfig(),
        }
    )

    @field_validator("rag", mode="before")
    @classmethod
    def _load_rag_steps(cls, v: Any) -> Any:
        if isinstance(v, dict) and "steps" in v and isinstance(v["steps"], str):  # noqa: UP037
            return {**v, "steps": v["steps"].split(",")}
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_vector_store_relevance_threshold(cls, v: Any) -> Any:
        """Backward-compatible loader: migrate vector_store.relevance_threshold → rag."""
        if not isinstance(v, dict):
            return v
        vs = v.get("vector_store")
        if isinstance(vs, dict) and "relevance_threshold" in vs:
            rag = v.get("rag", {})
            if isinstance(rag, dict) and "relevance_threshold" not in rag:
                rag = {**rag, "relevance_threshold": vs["relevance_threshold"]}
                v = {**v, "rag": rag}
            # Strip the removed field so VectorStoreConfig(extra="forbid") doesn't choke
            vs = {k: val for k, val in vs.items() if k != "relevance_threshold"}
            v = {**v, "vector_store": vs}
        return v

    @model_validator(mode="after")
    def _check_dimensions(self) -> AppConfig:
        if self.embedder.dim != self.vector_store.dim:
            raise ValueError(
                f"embedder.dim ({self.embedder.dim}) must equal "
                f"vector_store.dim ({self.vector_store.dim})"
            )
        return self


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    """Load config from YAML, fallback to env defaults.

    Args:
        path: Path to the YAML config file.

    Returns:
        Populated AppConfig instance.

    Raises:
        ValueError: If the file contains invalid YAML.
        ValidationError: If unknown keys or env vars are present.
    """
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()
    try:
        with config_path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {config_path}: {exc}") from exc
    return AppConfig(**data)

```

### `src/ai_assistant/core/constants.py`
```python
"""Core constants — shared across features."""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["DOCUMENTS_ROOT", "FROZEN_NO_INFO_PHRASES", "RAG_NS_MAP", "RAG_PREFIX_RE"]

RAG_NS_MAP: dict[str, str] = {
    "p": "personal",
    "w": "work",
    "o": "other",
    "c": "code",
    "b": "books",
}
RAG_PREFIX_RE: re.Pattern[str] = re.compile(r"^\[(p|w|o|c|b)\]\s*(.*)", re.IGNORECASE)

DOCUMENTS_ROOT = Path("sources")

FROZEN_NO_INFO_PHRASES: frozenset[str] = frozenset(
    {
        "не достаточно",
        "недостаточно",
        "не имею",
        "не знаю",
        "not enough",
        "don't have",
        "no information",
        "не найдено",
        "not found",
        "i don't have",
        "i do not have",
        "don't know",
        "do not know",
        "у меня недостаточно",
        "у меня нет",
    }
)

```

### `src/ai_assistant/core/domain/__init__.py`
```python
"""Domain models — pure, no external dependencies."""

from .documents import Chunk, ChunkMetadata, Document
from .errors import AdapterError, ConfigurationError, VersionMismatchError
from .messages import (
    AssistantMessage,
    TextPayload,
    UserMessage,
)
from .pipeline import PipelineData

__all__ = [
    "UserMessage",
    "AssistantMessage",
    "TextPayload",
    "Document",
    "Chunk",
    "ChunkMetadata",
    "PipelineData",
    "ConfigurationError",
    "AdapterError",
    "VersionMismatchError",
]

```

### `src/ai_assistant/core/domain/documents.py`
```python
"""Document and chunk models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

__all__ = ["Chunk", "ChunkMetadata", "Document"]


@dataclass(frozen=True)
class ChunkMetadata:
    source: str
    index: int
    total_chunks: int
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    custom: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    id: str
    text: str
    embedding: list[float] | None = None
    metadata: ChunkMetadata | None = None


@dataclass
class Document:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)

```

### `src/ai_assistant/core/domain/errors.py`
```python
"""Domain exceptions."""

from __future__ import annotations

__all__ = [
    "AdapterError",
    "ConfigurationError",
    "EMBEDDER_NOT_PROVIDED",
    "INTERNAL_SERVER_ERROR",
    "LLM_NOT_PROVIDED",
    "QUERY_EMBEDDING_MISSING",
    "QUERY_MISSING",
    "QUERY_TEXT_MISSING",
    "VersionMismatchError",
    "VECTOR_STORE_NOT_PROVIDED",
]


class ConfigurationError(Exception):
    """Invalid configuration."""


class AdapterError(Exception):
    """Adapter operation failed."""


class VersionMismatchError(Exception):
    """Index/model version mismatch."""


# --- Pipeline step error messages ---
EMBEDDER_NOT_PROVIDED = "embed_query: embedder not provided"
QUERY_TEXT_MISSING = "embed_query: no query text"
VECTOR_STORE_NOT_PROVIDED = "retrieve: vector_store not provided"
QUERY_EMBEDDING_MISSING = "retrieve: no query embedding"
LLM_NOT_PROVIDED = "generate: llm not provided"
QUERY_MISSING = "generate: no query"
INTERNAL_SERVER_ERROR = "Internal server error"

```

### `src/ai_assistant/core/domain/messages.py`
```python
"""Message domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

__all__ = [
    "AssistantMessage",
    "MessageRole",
    "TextPayload",
    "UserMessage",
]


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True)
class TextPayload:
    content: str


@dataclass(frozen=True)
class UserMessage:
    role: MessageRole = field(default=MessageRole.USER, init=False)
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AssistantMessage:
    role: MessageRole = field(default=MessageRole.ASSISTANT, init=False)
    text: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

```

### `src/ai_assistant/core/domain/pipeline.py`
```python
"""Pipeline data carrier."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .documents import Chunk
    from .messages import AssistantMessage, UserMessage

__all__ = ["PipelineData"]


@dataclass(frozen=True, slots=True)
class PipelineData:
    query: UserMessage | None = None
    chunks: tuple[Chunk, ...] = field(default_factory=tuple)
    context: str = ""
    response: AssistantMessage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: tuple[str, ...] = field(default_factory=tuple)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def with_chunks(self, chunks: list[Chunk] | tuple[Chunk, ...]) -> PipelineData:
        """Return a new PipelineData with updated chunks."""
        return replace(self, chunks=tuple(chunks))

    def with_context(self, context: str) -> PipelineData:
        """Return a new PipelineData with updated context."""
        return replace(self, context=context)

    def with_response(self, response: AssistantMessage | None) -> PipelineData:
        """Return a new PipelineData with updated response."""
        return replace(self, response=response)

    def add_error(self, msg: str) -> PipelineData:
        """Return a new PipelineData with an additional error message."""
        return replace(self, errors=(*self.errors, msg))

    def with_metadata(self, metadata: dict[str, Any]) -> PipelineData:
        """Return a new PipelineData with merged metadata (shallow copy)."""
        return replace(self, metadata={**self.metadata, **metadata})

```

### `src/ai_assistant/core/io_utils.py`
```python
"""Atomic file operations."""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from pathlib import Path
from typing import cast

__all__ = ["atomic_write"]


async def atomic_write(
    path: str | Path,
    content: str | bytes,
    mode: str = "w",
) -> None:
    """Write *content* to *path* atomically via a temporary file.

    A sibling ``.tmp`` file is created in the same directory and moved
    into place with ``os.replace``.  On any failure the temporary file
    is removed.  The directory is fsync'd so the rename is durable.
    """
    target = Path(path)

    if mode not in {"w", "wb"}:
        raise ValueError(f"mode must be 'w' or 'wb', got {mode!r}")

    binary = "b" in mode
    if binary and not isinstance(content, bytes):
        raise TypeError(
            f"Expected bytes for mode={mode!r}, got {type(content).__name__}"
        )
    if not binary and not isinstance(content, str):
        raise TypeError(f"Expected str for mode={mode!r}, got {type(content).__name__}")

    def _sync() -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            if binary:
                with os.fdopen(fd, mode, closefd=True) as fh:
                    fh.write(cast("bytes", content))
                    fh.flush()
                    os.fsync(fh.fileno())
            else:
                with os.fdopen(fd, mode, closefd=True, encoding="utf-8") as fh:
                    fh.write(cast("str", content))
                    fh.flush()
                    os.fsync(fh.fileno())
            os.replace(tmp, target)
            # Persist directory metadata (POSIX)
            try:
                dir_fd = os.open(
                    target.parent,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
                )
            except OSError:
                pass  # Windows or filesystem without directory fsync support
            else:
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp)

    await asyncio.to_thread(_sync)

```

### `src/ai_assistant/core/logger.py`
```python
"""Simple structured logging."""

from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path
from typing import Final

__all__ = ["get_logger", "setup_logging"]

_LOCK: Final = threading.Lock()
_VALID_LEVELS: Final[frozenset[str]] = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)


class _TraceFormatter(logging.Formatter):
    """Formatter that includes trace_id when present in extra."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            record.trace_id_str = f" | trace_id={trace_id}"
        else:
            record.trace_id_str = ""
        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = "./data/app.log",
) -> logging.Logger:
    """Configure application logging.

    Idempotent: repeated calls reuse existing handlers but always
    refresh the logger level.
    """
    upper = level.upper()
    if upper not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log level {level!r}. Use one of: {sorted(_VALID_LEVELS)}"
        )

    logger = logging.getLogger("ai_assistant")
    logger.setLevel(getattr(logging, upper))

    with _LOCK:
        if logger.handlers:
            return logger

        fmt = "%(asctime)s | %(levelname)-8s | %(name)s%(trace_id_str)s | %(message)s"
        formatter = _TraceFormatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)

        if log_file:
            path = Path(log_file)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                fh = logging.FileHandler(path, encoding="utf-8")
                fh.setFormatter(formatter)
                logger.addHandler(fh)
            except OSError as exc:
                logger.error("Failed to create log file %s: %s", path, exc)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Get child logger."""
    return logging.getLogger(f"ai_assistant.{name}")

```

### `src/ai_assistant/core/metrics.py`
```python
"""In-memory metrics registry — stdlib only, Prometheus-compatible."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

__all__ = [
    "get_metrics",
    "get_metrics_json",
    "increment_counter",
    "observe_histogram",
]

_DEFAULT_BUCKETS = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
)

_counters: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)
_histograms: dict[
    tuple[str, tuple[tuple[str, str], ...]],
    dict[str, Any],
] = {}

_lock = threading.Lock()


def _labels_key(labels: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((labels or {}).items()))


def _key_str(name: str, labels: tuple[tuple[str, str], ...]) -> str:
    if not labels:
        return name
    label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels))
    return f"{name}{{{label_str}}}"


def _metric_line(
    name: str,
    labels: tuple[tuple[str, str], ...],
    value: str | int | float,
) -> str:
    return f"{_key_str(name, labels)} {value}"


def increment_counter(
    name: str,
    labels: dict[str, str] | None = None,
    value: int = 1,
) -> None:
    """Increment a counter metric."""
    key = (name, _labels_key(labels))
    with _lock:
        _counters[key] += value


def observe_histogram(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """Observe a value into a histogram."""
    key = (name, _labels_key(labels))
    with _lock:
        hist = _histograms.setdefault(
            key,
            {"buckets": defaultdict(int), "sum": 0.0, "count": 0},
        )
        for b in _DEFAULT_BUCKETS:
            if value <= b:
                hist["buckets"][b] += 1
        hist["sum"] += value
        hist["count"] += 1


def get_metrics() -> str:
    """Return metrics in Prometheus exposition format."""
    with _lock:
        lines: list[str] = []

        for (name, labels), value in _counters.items():
            lines.append(f"# HELP {name} Total")
            lines.append(f"# TYPE {name} counter")
            lines.append(_metric_line(name, labels, value))

        for (name, labels), hist in _histograms.items():
            lines.append(f"# HELP {name} Latency")
            lines.append(f"# TYPE {name} histogram")
            for b in _DEFAULT_BUCKETS:
                bucket_labels = labels + (("le", str(b)),)
                lines.append(
                    _metric_line(
                        f"{name}_bucket",
                        bucket_labels,
                        hist["buckets"].get(b, 0),
                    )
                )
            inf_labels = labels + (("le", "+Inf"),)
            lines.append(_metric_line(f"{name}_bucket", inf_labels, hist["count"]))
            lines.append(_metric_line(f"{name}_count", labels, hist["count"]))
            lines.append(_metric_line(f"{name}_sum", labels, f"{hist['sum']:.6f}"))

        return "\n".join(lines)


def get_metrics_json() -> dict[str, Any]:
    """Return metrics as a JSON-serializable dict."""
    with _lock:
        return {
            "counters": {
                _key_str(name, labels): value
                for (name, labels), value in _counters.items()
            },
            "histograms": {
                _key_str(name, labels): {
                    "buckets": {
                        str(b): hist["buckets"].get(b, 0) for b in _DEFAULT_BUCKETS
                    },
                    "count": hist["count"],
                    "sum": hist["sum"],
                }
                for (name, labels), hist in _histograms.items()
            },
        }

```

### `src/ai_assistant/core/pipeline.py`
```python
"""RAGPipeline executor — sacred, immutable."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_assistant.core.domain.pipeline import PipelineData

__all__ = ["RAGPipeline"]


class RAGPipeline:
    """Sequential step runner."""

    def __init__(
        self, steps: list[Callable[[PipelineData], Awaitable[PipelineData]]]
    ) -> None:
        self.steps = list(steps)

    async def run(
        self, data: PipelineData, metadata: dict[str, Any] | None = None
    ) -> PipelineData:
        """Execute steps sequentially, passing PipelineData through.

        Args:
            data: Initial pipeline data.
            metadata: Optional metadata dict merged into data.metadata.
                Used to inject dependencies (embedder, vector_store, etc.)
                without coupling steps to AppState.
        """
        if metadata:
            data = replace(data, metadata={**data.metadata, **metadata})
        for step in self.steps:
            data = await step(data)
        return data

```

### `src/ai_assistant/core/pipeline_steps.py`
```python
"""RAG pipeline steps with namespace and rerank support.

All steps return new PipelineData instances via dataclasses.replace().
No in-place mutation.
"""

from __future__ import annotations

import json
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ai_assistant.core.domain.errors import (
    EMBEDDER_NOT_PROVIDED,
    INTERNAL_SERVER_ERROR,
    LLM_NOT_PROVIDED,
    QUERY_EMBEDDING_MISSING,
    QUERY_MISSING,
    QUERY_TEXT_MISSING,
    VECTOR_STORE_NOT_PROVIDED,
    AdapterError,
)
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.logger import get_logger
from ai_assistant.core.metrics import increment_counter
from ai_assistant.core.ports.tools import ToolCall
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import count_tokens, get_context_limit

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_assistant.core.domain.documents import Chunk
    from ai_assistant.core.domain.pipeline import PipelineData

__all__: list[str] = [
    "build_context",
    "embed_query",
    "generate",
    "rerank",
    "retrieve",
    "STEP_REGISTRY",
    "step",
]

_logger = get_logger("pipeline.steps")

STEP_REGISTRY: dict[str, Callable[[PipelineData], Awaitable[PipelineData]]] = {}

# --- Token budget constants for generate() ---------------------------------
TOKEN_MARGIN_MIN = 256  # absolute minimum tokens reserved for response
TOKEN_MARGIN_PCT = 0.1  # fraction of context window reserved for response


def step(
    name: str,
) -> Callable[
    [Callable[[PipelineData], Awaitable[PipelineData]]],
    Callable[[PipelineData], Awaitable[PipelineData]],
]:
    """Register a pipeline step by its config name."""

    def decorator(
        func: Callable[[PipelineData], Awaitable[PipelineData]],
    ) -> Callable[[PipelineData], Awaitable[PipelineData]]:
        STEP_REGISTRY[name] = func
        return func

    return decorator


def _estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    return count_tokens(text, model)


def _get_llm_context_limit(llm: Any) -> int | None:
    return get_context_limit(llm)


# --- retry helpers for network calls ----------------------------------------


@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def _call_embed(embedder: Any, text: str) -> list[list[float]]:
    """Embed a single text with retry."""
    return await embedder.embed([text])


@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def _call_search(
    vector_store: Any, embedding: list[float], top_k: int, namespace: str
) -> list[Any]:
    """Search vector store with retry."""
    return await vector_store.search(embedding, top_k=top_k, namespace=namespace)


@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def _call_llm(llm: Any, messages: list[Any]) -> AssistantMessage:
    """Call LLM with retry."""
    return await llm.complete(messages)


@step("embed_query")
async def embed_query(data: PipelineData) -> PipelineData:
    """Embed the user query text.

    Metadata contract:
        IN:  embedder (IEmbedder) — required.
        OUT: query_embedding (list[float]) — produced on success.
        DATA: query.text (str) — must be non-empty.

    Errors added on failure:
        EMBEDDER_NOT_PROVIDED, QUERY_TEXT_MISSING, INTERNAL_SERVER_ERROR.
    """
    _logger.info("embed_query start", extra={"trace_id": data.trace_id})
    embedder = data.metadata.get("embedder")
    if embedder is None:
        _logger.warning("embed_query: no embedder", extra={"trace_id": data.trace_id})
        return data.add_error(EMBEDDER_NOT_PROVIDED)
    if data.query is None or not data.query.text:
        _logger.warning("embed_query: no query text", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_TEXT_MISSING)
    try:
        embeddings = await _call_embed(embedder, data.query.text)
        new_metadata = {**data.metadata, "query_embedding": embeddings[0]}
        _logger.info("embed_query done", extra={"trace_id": data.trace_id})
        return replace(data, metadata=new_metadata)
    except Exception:
        _logger.exception("embed_query failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("retrieve")
async def retrieve(data: PipelineData) -> PipelineData:
    """Retrieve relevant chunks from vector store (namespace-aware).

    Metadata contract:
        IN:  vector_store (IVectorStore) — required.
             query_embedding (list[float]) — produced by embed_query.
             top_k (int) — optional, default 5.
             namespace (str) — optional, default "default".
        OUT: chunks (list[Chunk]) — written to PipelineData.chunks.
             Metric "rag_chunks" recorded.

    Errors added on failure:
        VECTOR_STORE_NOT_PROVIDED, QUERY_EMBEDDING_MISSING, INTERNAL_SERVER_ERROR.
    """
    _logger.info("retrieve start", extra={"trace_id": data.trace_id})
    vector_store = data.metadata.get("vector_store")
    if vector_store is None:
        _logger.warning("retrieve: no vector_store", extra={"trace_id": data.trace_id})
        return data.add_error(VECTOR_STORE_NOT_PROVIDED)
    embedding = data.metadata.get("query_embedding")
    if embedding is None:
        _logger.warning("retrieve: no embedding", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_EMBEDDING_MISSING)
    try:
        top_k = data.metadata.get("top_k", 5)
        namespace = data.metadata.get("namespace") or "default"
        chunks = await _call_search(vector_store, embedding, top_k, namespace)
        increment_counter(
            "ai_assistant_rag_retrieve_total",
            labels={"namespace": namespace},
        )
        _logger.info(
            "retrieve done: %d chunks", len(chunks), extra={"trace_id": data.trace_id}
        )
        return data.with_chunks(chunks)
    except Exception:
        _logger.exception("retrieve failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("rerank")
async def rerank(data: PipelineData) -> PipelineData:
    """Rerank retrieved chunks by relevance and filter by threshold.

    If reranker is not configured (None), acts as transparent pass-through.

    Metadata contract:
        IN:  reranker (IReranker) — optional; if None, step is no-op.
             top_k (int) — optional, default 5.
             relevance_threshold (float) — optional, default 0.3.
        OUT: rerank_filtered_out (bool) — set True if all chunks filtered.
             rerank_scores (list[float]) — set if chunks survive filtering.
        DATA: chunks (list[Chunk]) — replaced with filtered subset.

    Errors added on failure:
        INTERNAL_SERVER_ERROR.
    """
    _logger.info(
        "rerank start: %d chunks", len(data.chunks), extra={"trace_id": data.trace_id}
    )
    if not data.chunks:
        return replace(data)

    reranker = data.metadata.get("reranker")

    if reranker is None:
        # Clean stale rerank metadata from previous pipeline runs
        new_metadata = {
            k: v
            for k, v in data.metadata.items()
            if k not in ("rerank_scores", "rerank_filtered_out")
        }
        return replace(data, metadata=new_metadata)

    try:
        _raw_query = data.query.text if data.query is not None else None
        query = _raw_query if _raw_query is not None else ""
        top_k = data.metadata.get("top_k", 5)
        threshold = data.metadata.get("relevance_threshold", 0.3)

        results = await reranker.rerank(query, data.chunks, top_k=top_k)

        filtered = [r for r in results if r.score >= threshold]

        if not filtered:
            new_metadata = {
                **data.metadata,
                "rerank_filtered_out": True,
            }
            _logger.info(
                "rerank: all chunks filtered out", extra={"trace_id": data.trace_id}
            )
            return replace(data, chunks=(), metadata=new_metadata)
        else:
            new_metadata = {
                **data.metadata,
                "rerank_scores": [r.score for r in filtered],
            }
            _logger.info(
                "rerank done: %d chunks",
                len(filtered),
                extra={"trace_id": data.trace_id},
            )
            return replace(
                data,
                chunks=tuple(r.chunk for r in filtered),
                metadata=new_metadata,
            )

    except Exception:
        _logger.exception("rerank failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("build_context")
async def build_context(data: PipelineData) -> PipelineData:
    """Build context string from retrieved (and reranked) chunks.

    Metadata contract:
        DATA: chunks (list[Chunk]) — read; context (str) — produced.
    """
    _logger.info(
        "build_context start: %d chunks",
        len(data.chunks),
        extra={"trace_id": data.trace_id},
    )
    if not data.chunks:
        return data.with_context("")
    lines = [chunk.text for chunk in data.chunks if chunk.text]
    context = "\n\n".join(lines)
    _logger.info(
        "build_context done: %d chars", len(context), extra={"trace_id": data.trace_id}
    )
    return data.with_context(context)


def _build_fallback_prompt(chunks: tuple[Chunk, ...], query_text: str) -> str:
    """Build a minimal RAG prompt from chunks when template lookup fails."""
    chunks_text = "\n".join(f"[{i + 1}] {c.text}" for i, c in enumerate(chunks))
    return f"Context:\n{chunks_text}\n\nQuestion: {query_text}\nAnswer:"


def _truncate_to_fit(
    data: PipelineData,
    prompt: str,
    prompt_name: str,
    prompt_version: str,
    query_text: str,
    limit: int,
) -> tuple[PipelineData, str]:
    """Remove chunks from the end until prompt fits in the token limit.

    Returns:
        (updated_data, updated_prompt). If all chunks are exhausted and
        the prompt still exceeds the limit, updated_data will have empty
        chunks and updated_prompt will reflect the last attempted context.
    """
    prompt_tokens = _estimate_tokens(prompt)
    current_data = data
    while current_data.chunks and prompt_tokens > limit:
        new_chunks = current_data.chunks[:-1]
        if not new_chunks:
            current_data = current_data.with_chunks(()).with_context("")
            break
        current_data = current_data.with_chunks(new_chunks)
        lines = [chunk.text for chunk in current_data.chunks if chunk.text]
        current_data = current_data.with_context("\n\n".join(lines))
        try:
            prompt = get_prompt(
                prompt_name,
                version=prompt_version,
                query=query_text,
                context=current_data.context,
            )
        except Exception:
            prompt = _build_fallback_prompt(current_data.chunks, query_text)
        prompt_tokens = _estimate_tokens(prompt)
    return current_data, prompt


@step("generate")
async def generate(data: PipelineData) -> PipelineData:
    _logger.info("generate start", extra={"trace_id": data.trace_id})
    llm = data.metadata.get("llm")
    if llm is None:
        _logger.warning("generate: no llm", extra={"trace_id": data.trace_id})
        return data.add_error(LLM_NOT_PROVIDED)
    if data.query is None:
        _logger.warning("generate: no query", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_MISSING)

    query_text = data.query.text or ""
    prompt_version = data.metadata["prompt_version"]
    prompt_name = data.metadata["prompt_name"]

    try:
        prompt = get_prompt(
            prompt_name,
            version=prompt_version,
            query=query_text,
            context=data.context,
        )
    except Exception:
        prompt = _build_fallback_prompt(data.chunks, query_text)

    max_ctx = _get_llm_context_limit(llm)
    if max_ctx is None or max_ctx <= 0:
        cfg_size = getattr(getattr(llm, "config", None), "server_context_size", None)
        max_ctx = cfg_size if type(cfg_size) is int else 4096

    prompt_tokens = _estimate_tokens(prompt)
    margin = max(TOKEN_MARGIN_MIN, int(max_ctx * TOKEN_MARGIN_PCT))
    limit = max_ctx - margin

    if prompt_tokens > limit:
        data, prompt = _truncate_to_fit(
            data, prompt, prompt_name, prompt_version, query_text, limit
        )
        prompt_tokens = _estimate_tokens(prompt)
        if prompt_tokens > limit:
            error_msg = (
                f"generate: prompt too long ({prompt_tokens} tokens) "
                f"exceeds limit ({limit})"
            )
            return data.add_error(error_msg).with_response(
                AssistantMessage(
                    text=(
                        "Sorry, the retrieved context is too large "
                        "to process. Please narrow your query."
                    )
                )
            )

    messages: list[Any] = [UserMessage(text=prompt)]
    response: AssistantMessage | None = None

    try:
        response = await _call_llm(llm, messages)
    except AdapterError:
        # Intentional bypass: LLM unavailability is a transient infrastructure
        # failure, not a pipeline logic error. The HTTP layer maps this to 503.
        _logger.exception("LLM unavailable", extra={"trace_id": data.trace_id})
        raise
    except Exception:
        _logger.exception(
            "generate failed after retries", extra={"trace_id": data.trace_id}
        )
        return data.add_error(INTERNAL_SERVER_ERROR).with_response(
            AssistantMessage(
                text="Sorry, I encountered an error generating the response."
            )
        )

    max_iterations = data.metadata.get("max_tool_iterations", 5)
    iteration = 0

    # Tool calling loop – each LLM call is also retried via _call_llm
    while response and response.tool_calls:
        if iteration >= max_iterations:
            error_msg = (
                f"generate: tool loop exceeded max iterations ({max_iterations})"
            )
            return data.add_error(error_msg).with_response(
                AssistantMessage(text="Tool limit reached")
            )
        iteration += 1
        messages.append(response)
        tool_registry = data.metadata.get("tool_registry")
        if tool_registry:
            for call in response.tool_calls:
                try:
                    func = call.get("function", {})
                    tool_name = func.get("name", "")
                    arguments = json.loads(func.get("arguments", "{}"))
                    tc = ToolCall(
                        tool_name=tool_name,
                        arguments=arguments,
                        call_id=call.get("id", ""),
                    )
                    result = await tool_registry.dispatch(tc)
                    content = (
                        result.output
                        if not result.is_error
                        else f"Error: {result.error}"
                    )
                except Exception as e:
                    content = f"Error: {e}"
                messages.append(
                    {
                        "role": "tool",
                        "content": str(content),
                        "tool_call_id": call.get("id", ""),
                    }
                )
            # Next LLM call (with tool results)
            try:
                response = await _call_llm(llm, messages)
            except AdapterError:
                # Intentional bypass — same reasoning as the main LLM call.
                _logger.exception(
                    "LLM unavailable during tool follow-up",
                    extra={"trace_id": data.trace_id},
                )
                raise
            except Exception:
                _logger.exception(
                    "tool follow-up call failed after retries",
                    extra={"trace_id": data.trace_id},
                )
                response = AssistantMessage(text="Sorry, a tool call failed.")
                break
        else:
            break

    final_response = (
        response
        if response
        else AssistantMessage(text="Sorry, tool call loop exhausted.")
    )
    _logger.info("generate done", extra={"trace_id": data.trace_id})
    return data.with_response(final_response)


@step("hyde_query")
async def hyde_query(data: PipelineData) -> PipelineData:
    """Hypothetical Document Embedding (HyDE).

    Generates a hypothetical answer to the query, embeds it,
    and stores the embedding in metadata for downstream retrieval.
    """
    _logger.info("hyde_query start", extra={"trace_id": data.trace_id})
    embedder = data.metadata.get("embedder")
    llm = data.metadata.get("llm")
    if embedder is None:
        _logger.warning("hyde_query: no embedder", extra={"trace_id": data.trace_id})
        return data.add_error(EMBEDDER_NOT_PROVIDED)
    if llm is None:
        _logger.warning("hyde_query: no llm", extra={"trace_id": data.trace_id})
        return data.add_error(LLM_NOT_PROVIDED)
    if data.query is None or not data.query.text:
        _logger.warning("hyde_query: no query text", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_TEXT_MISSING)

    # Generate hypothetical answer
    hyde_messages = [
        UserMessage(
            text=f"Write a short passage that answers this question: {data.query.text}"
        )
    ]
    try:
        hyde_resp: AssistantMessage = await _call_llm(llm, hyde_messages)
    except Exception:
        _logger.exception(
            "hyde_query: LLM call failed", extra={"trace_id": data.trace_id}
        )
        return data.add_error(INTERNAL_SERVER_ERROR)

    hyde_text = hyde_resp.text or ""
    if not hyde_text:
        return data.add_error("hyde_query: empty hypothetical answer")

    # Embed hypothetical answer
    try:
        embeddings = await _call_embed(embedder, hyde_text)
    except Exception:
        _logger.exception(
            "hyde_query: embedding failed", extra={"trace_id": data.trace_id}
        )
        return data.add_error(INTERNAL_SERVER_ERROR)

    new_metadata = {**data.metadata, "query_embedding": embeddings[0]}
    _logger.info("hyde_query done", extra={"trace_id": data.trace_id})
    return replace(data, metadata=new_metadata)

```

### `src/ai_assistant/core/ports/__init__.py`
```python
"""Core ports (interfaces). Immutable."""

from .chunker import IChunker
from .closable import IClosable
from .embedder import IEmbedder
from .initializable import IInitializable
from .llm import ILLM
from .reranker import IReranker, RerankResult
from .storage import IChatStorage, ISettingsStorage
from .vector_store import IVectorStore

__all__ = [
    "IChunker",
    "IClosable",
    "IEmbedder",
    "IInitializable",
    "ILLM",
    "IVectorStore",
    "IChatStorage",
    "ISettingsStorage",
    "IReranker",
    "RerankResult",
]

```

### `src/ai_assistant/core/ports/chunker.py`
```python
"""Chunker port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_assistant.core.domain.documents import Chunk, Document

__all__ = ["IChunker"]


class IChunker(ABC):
    """Split documents into chunks."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def chunk(self, document: Document) -> list[Chunk]:
        """Split document into chunks."""
        ...

```

### `src/ai_assistant/core/ports/closable.py`
```python
"""Closable port — for adapters requiring graceful shutdown."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["IClosable"]


class IClosable(ABC):
    """Mixin protocol for adapters that need explicit cleanup on shutdown."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Release resources and perform graceful shutdown."""
        ...

```

### `src/ai_assistant/core/ports/embedder.py`
```python
"""Embedder port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ai_assistant.core.ports.closable import IClosable

__all__ = ["IEmbedder"]


class IEmbedder(IClosable, ABC):
    """Text embedding interface."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding vector dimension."""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed list of texts."""
        ...

```

### `src/ai_assistant/core/ports/initializable.py`
```python
"""Initializable port — for adapters requiring explicit setup."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["IInitializable"]


class IInitializable(ABC):
    """Mixin protocol for adapters that need database or resource initialization."""

    @abstractmethod
    async def init_db(self) -> None:
        """Initialize persistent storage or other resources."""
        ...

```

### `src/ai_assistant/core/ports/llm.py`
```python
"""LLM port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.ports.closable import IClosable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

Message = UserMessage | AssistantMessage | dict[str, Any]

__all__ = ["ILLM", "Message"]


class ILLM(IClosable, ABC):
    """Language model interface."""

    system_message: str | None = None

    def __init__(self, config: Any) -> None:
        self.config = config

    async def shutdown(self) -> None:
        """Default no-op shutdown for LLMs without external resources."""
        pass

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AssistantMessage:
        """Non-streaming completion."""
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncIterator[str]: ...

```

### `src/ai_assistant/core/ports/reranker.py`
```python
"""Reranker port — post-retrieval relevance scoring."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ai_assistant.core.domain.documents import Chunk

__all__ = ["IReranker", "RerankResult"]


@dataclass
class RerankResult:
    """Single rerank result with relevance score."""

    chunk: Chunk
    score: float  # 0.0 to 1.0, higher = more relevant


class IReranker(ABC):
    """Re-rank retrieved chunks by relevance to query.

    Used after vector store retrieval to filter out false positives
    and improve context quality for generation.
    """

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: list[Chunk],
        top_k: int | None = None,
    ) -> list[RerankResult]:
        """Rerank chunks by relevance to query.

        Args:
            query: Original user query.
            chunks: Chunks from vector store retrieval.
            top_k: Max results to return. None = return all scored.

        Returns:
            List of RerankResult sorted by score descending.
        """
        ...

```

### `src/ai_assistant/core/ports/storage.py`
```python
"""Storage ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ai_assistant.core.ports.initializable import IInitializable

__all__ = ["IChatStorage", "ISettingsStorage"]


class IChatStorage(IInitializable, ABC):
    """Chat history persistence."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def save_message(self, conversation_id: str, message: dict[str, Any]) -> None:
        """Persist a single message for a conversation."""
        ...

    @abstractmethod
    async def get_history(
        self, conversation_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        """Return recent messages for a conversation, oldest first.

        Args:
            conversation_id: Conversation identifier.
            limit: Maximum number of messages to return.
            offset: Number of messages to skip (for pagination).
        """
        ...


class ISettingsStorage(ABC):
    """Settings persistence."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a setting value or *default* if absent."""
        ...

    @abstractmethod
    async def set(self, key: str, value: Any) -> None:
        """Persist a setting value."""
        ...

```

### `src/ai_assistant/core/ports/tools.py`
```python
"""Tool port — external capabilities (calculator, search, APIs, code execution.

This enables the LLM to call external tools, similar to OpenAI function calling
but framework-agnostic. ToolRegistry manages available tools; ITool is the
interface for individual tool implementations.

Future directions:
- MCP (Model Context Protocol) adapter
- Local code execution sandbox
- Hardware control (robotics, IoT)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "ITool",
    "IToolRegistry",
    "ToolCall",
    "ToolResult",
    "ToolSpec",
]


@dataclass(frozen=True)
class ToolSpec:
    """Schema describing a tool for LLM consumption.

    Mirrors OpenAI function schema but framework-agnostic.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    required: list[str] = field(default_factory=list)


@dataclass
class ToolCall:
    """A request from LLM to invoke a tool."""

    tool_name: str
    arguments: dict[str, Any]
    call_id: str = ""  # For matching response to request


@dataclass(frozen=True)
class ToolResult:
    """Result of a tool invocation."""

    call_id: str
    output: str | dict[str, Any]
    error: str | None = None
    is_error: bool = False


class ITool(ABC):
    """Single tool implementation."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @property
    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return the schema for this tool."""
        ...

    @abstractmethod
    async def execute(self, call_id: str, arguments: dict[str, Any]) -> ToolResult:
        """Execute the tool with given arguments.

        Args:
            call_id: Unique identifier for this tool call,
                must be propagated into the returned ToolResult.
            arguments: Tool arguments parsed from LLM response.
        """
        ...


class IToolRegistry(ABC):
    """Pure interface for tool registry — implementations provide storage strategy."""

    @abstractmethod
    def register(self, tool: ITool) -> None:
        """Add a tool to registry."""
        ...

    @abstractmethod
    def unregister(self, name: str) -> None:
        """Remove a tool from registry."""
        ...

    @abstractmethod
    def list_tools(self) -> list[ToolSpec]:
        """Return schemas of all registered tools."""
        ...

    @abstractmethod
    def get_tool(self, name: str) -> ITool | None:
        """Get tool by name."""
        ...

    @abstractmethod
    async def dispatch(self, call: ToolCall) -> ToolResult:
        """Execute a tool call by dispatching to the registered tool.

        Implementations must propagate *call.call_id* into the returned
        ToolResult by passing it to *tool.execute(call_id, ...)*.
        """
        ...

```

### `src/ai_assistant/core/ports/vector_store.py`
```python
"""Vector store port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

from ai_assistant.core.ports.closable import IClosable

if TYPE_CHECKING:
    from ai_assistant.core.domain.documents import Chunk

__all__ = ["IVectorStore"]


class IVectorStore(IClosable, ABC):
    """Vector storage with FAISS-like semantics."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        """Add chunks with embeddings to a namespace."""
        ...

    @abstractmethod
    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        namespace: str = "default",
    ) -> list[Chunk]:
        """Search by embedding in a namespace."""
        ...

    @abstractmethod
    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        """Delete chunks by ID from a namespace."""
        ...

    @abstractmethod
    async def save(self, path: str, namespace: str = "default") -> None:
        """Persist namespace index + metadata."""
        ...

    @abstractmethod
    async def load(self, path: str, namespace: str = "default") -> None:
        """Load namespace index + metadata. Validate version."""
        ...

    @abstractmethod
    async def list_by_filter(
        self,
        filters: dict[str, Any],
        namespace: str = "default",
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return (chunk_id, metadata) matching ALL filters key-values in namespace."""
        ...

    @abstractmethod
    async def list_namespaces(self, path: str) -> list[str]:
        """Return list of available namespace names."""
        ...

```

### `src/ai_assistant/core/prompts/__init__.py`
```python
"""Versioned prompt loader."""

from __future__ import annotations

import dataclasses
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

_env_cache: dict[str, Environment] = {}


def _make_hashable(value: Any) -> Any:
    """Convert a value into a hashable form for cache keys."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return tuple(_make_hashable(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, _make_hashable(v)) for k, v in value.items()))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = value.__dataclass_fields__
        return tuple(
            (k, _make_hashable(getattr(value, k, None))) for k in sorted(fields.keys())
        )
    return str(value)


def _kwargs_to_tuple(kwargs: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Convert kwargs dict into a hashable tuple."""
    return tuple(sorted((k, _make_hashable(v)) for k, v in kwargs.items()))


@lru_cache(maxsize=256)
def _render(name: str, version: str, kwargs_tuple: tuple[tuple[str, Any], ...]) -> str:
    """Render a Jinja2 template with LRU-cached result."""
    base = Path(__file__).parent / version
    if not base.exists():
        raise ValueError(f"Prompt version directory not found: {base}")

    env = _env_cache.get(version)
    if env is None:
        env = Environment(
            loader=FileSystemLoader(str(base)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        _env_cache[version] = env

    kwargs = dict(kwargs_tuple)
    return env.get_template(f"{name}.j2").render(**kwargs)


def get_prompt(name: str, version: str | None = None, **kwargs: Any) -> str:
    """Load and render a Jinja2 prompt template.

    Args:
        name: Template filename without .j2 extension.
        version: Prompt version directory (e.g., "v1", "v2").
        **kwargs: Template variables.

    Returns:
        Rendered prompt string.

    Raises:
        ValueError: If version is not provided.
    """
    if version is None:
        raise ValueError("prompt version is required")
    return _render(name, version, _kwargs_to_tuple(kwargs))

```

### `src/ai_assistant/core/prompts/v1/rag_creative.j2`
```text
You are a creative AI assistant. Use the retrieved context as inspiration.

Context:
{{ context }}

Question: {{ query }}

Provide an imaginative, engaging response. Feel free to expand beyond the context when appropriate.

```

### `src/ai_assistant/core/prompts/v1/rag_default.j2`
```text
You are a helpful AI assistant. Use the following retrieved context to answer the user's question.

Context:
{{ context }}

Question: {{ query }}

Answer concisely and accurately. If the context doesn't contain the answer, say "I don't have enough information."

```

### `src/ai_assistant/core/prompts/v1/rag_strict.j2`
```text
You are a precise AI assistant. Use the provided context to answer the question.

Rules:
1. Answer based on the context. If the context has relevant information (even partial), use it.
2. Only say "У меня недостаточно информации." if the context is completely empty or has zero connection to the question.
3. NEVER invent facts not present in the context.
4. Use citations [N] after each factual claim.
5. Be concise.

Context:
{{ context }}

Question: {{ query }}
Answer:

```

### `src/ai_assistant/core/prompts/v1/summarize.j2`
```text
Summarize the following text in {{ max_sentences }} sentences:

{{ text }}

Summary:

```

### `src/ai_assistant/core/retry.py`
```python
"""Retry decorator."""

from __future__ import annotations

import asyncio
import functools
import inspect
import random
import time
from collections.abc import Callable
from typing import Any, TypeVar, cast

__all__ = ["with_retry"]

F = TypeVar("F", bound=Callable[..., Any])

# Permanent errors that should NOT be retried
_PERMANENT_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
    ModuleNotFoundError,
)


def with_retry(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    max_delay: float | None = None,
    jitter: bool = False,
) -> Callable[[F], F]:
    """Decorator adding exponential backoff retry.

    Does NOT retry exceptions in _PERMANENT_ERRORS,
    SystemExit, or KeyboardInterrupt.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except (SystemExit, KeyboardInterrupt):
                    raise
                except _PERMANENT_ERRORS:
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        sleep_for = current_delay
                        if jitter:
                            sleep_for = random.uniform(0, sleep_for)
                        if max_delay is not None:
                            sleep_for = min(sleep_for, max_delay)
                        await asyncio.sleep(sleep_for)
                        current_delay *= backoff
            assert last_exception is not None
            raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except (SystemExit, KeyboardInterrupt):
                    raise
                except _PERMANENT_ERRORS:
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        sleep_for = current_delay
                        if jitter:
                            sleep_for = random.uniform(0, sleep_for)
                        if max_delay is not None:
                            sleep_for = min(sleep_for, max_delay)
                        time.sleep(sleep_for)
                        current_delay *= backoff
            assert last_exception is not None
            raise last_exception

        wrapper = async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
        return cast("F", wrapper)

    return decorator

```

### `src/ai_assistant/core/utils.py`
```python
"""Utility functions."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]

try:
    import tokenizers
except ImportError:
    tokenizers = None  # type: ignore[assignment]

__all__ = [
    "async_count_tokens",
    "async_get_tokenizer",
    "count_tokens",
    "get_context_limit",
    "get_tokenizer",
    "resolve_api_key",
]


def resolve_api_key(config_value: str | None, env_var: str = "OPENAI_API_KEY") -> str:
    """Resolve API key from config or environment."""
    if config_value is not None and config_value != "":
        return config_value
    key = os.getenv(env_var)
    if key:
        return key
    raise ValueError(f"API key not found in config or env var {env_var}")


def _resolve_tokenizer_dir(model: str, local_dir: str) -> Path | None:
    """Map model name to local tokenizer directory."""
    base = Path(local_dir)
    if not base.exists():
        return None

    normalized = model.lower().strip().replace("_", "-")

    try:
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            entry_norm = entry.name.lower().replace("_", "-")
            if entry_norm == normalized and (entry / "tokenizer.json").exists():
                return entry

        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            entry_norm = entry.name.lower().replace("_", "-")
            if (
                entry_norm in normalized or normalized.startswith(entry_norm + "-")
            ) and (entry / "tokenizer.json").exists():
                return entry
    except OSError:
        return None

    return None


def get_tokenizer(
    model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> Any | None:
    """Get tokenizer: tiktoken first (OpenAI), then local HF, then None."""
    if tiktoken is not None:
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            try:
                return tiktoken.get_encoding("cl100k_base")
            except Exception:
                pass
    if tokenizers is not None:
        tok_dir = _resolve_tokenizer_dir(model, local_dir)
        if tok_dir is not None:
            try:
                return tokenizers.Tokenizer.from_file(str(tok_dir / "tokenizer.json"))
            except Exception:
                pass
    return None


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk_count = sum(
        1
        for c in text
        if (
            "\u4e00" <= c <= "\u9fff"  # CJK Unified
            or "\u3400" <= c <= "\u4dbf"  # CJK Extension A
            or "\u3040" <= c <= "\u30ff"  # Hiragana + Katakana
            or "\uac00" <= c <= "\ud7af"  # Hangul Syllables
        )
    )
    return cjk_count / len(text)


def count_tokens(
    text: str, model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> int:
    """Count tokens. Fallback to char//4 if no tokenizer available.
    CJK-heavy text (>30%) falls back to len(text) instead of len(text)//4.
    """
    if not text:
        return 0
    enc = get_tokenizer(model, local_dir=local_dir)
    if enc is None:
        if _cjk_ratio(text) > 0.3:
            return len(text)
        return len(text) // 4
    try:
        # HF tokenizers: encode() returns Encoding with .tokens
        return len(enc.encode(text).tokens)
    except AttributeError:
        # tiktoken: encode() returns list[int]
        return len(enc.encode(text))
    except Exception:
        if _cjk_ratio(text) > 0.3:
            return len(text)
        return len(text) // 4


def get_context_limit(llm: Any) -> int | None:
    """Extract context window size from LLM adapter config."""
    cfg = getattr(llm, "config", None)
    if cfg is None:
        return None
    for attr in ("context_size", "server_context_size", "max_tokens"):
        limit = getattr(cfg, attr, None)
        if isinstance(limit, (int, float)) and limit > 0:
            return int(limit)
    return None


async def async_count_tokens(
    text: str, model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> int:
    """Async wrapper for count_tokens — offloads CPU-bound tiktoken/HF encoding to thread pool."""
    return await asyncio.to_thread(count_tokens, text, model, local_dir)


async def async_get_tokenizer(
    model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> Any | None:
    """Async wrapper for get_tokenizer — offloads CPU-bound tokenizer loading to thread pool."""
    return await asyncio.to_thread(get_tokenizer, model, local_dir)

```

### `src/ai_assistant/features/chat/handlers.py`
```python
"""Chat feature HTTP handlers."""

from __future__ import annotations

import json
import time
import uuid
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ai_assistant.api.deps import InitializedAppState, get_state
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.logger import get_logger
from ai_assistant.features.chat.schemas import (
    ChatRequest,
    ChatResponse,
    OAIChatCompletion,
    OAIChatCompletionRequest,
    OAIChatMessage,
    OAIChoice,
    OAIDeltaChunk,
    OAIModel,
    OAIModelList,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__ = ["router", "router_oai"]


def _raise_llm_unavailable(exc: AdapterError) -> None:
    """Map adapter-level failure to 503 Service Unavailable."""
    raise HTTPException(
        status_code=503,
        detail="LLM service temporarily unavailable. Please try again later.",
    ) from exc


_logger = get_logger("chat.handlers")


router = APIRouter(tags=["chat"])
router_oai = APIRouter(tags=["chat-oai"])

# --- Legacy endpoints (under /api/v1 via wrapper) ---


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> ChatResponse:
    conv_id = req.conversation_id or str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    _logger.info("Chat handler start: trace_id=%s", trace_id)
    try:
        response = await state.chat_manager.chat(
            message=req.message,
            conversation_id=conv_id,
            metadata={**req.metadata, "trace_id": trace_id},
        )
    except AdapterError as exc:
        _logger.warning("LLM unavailable: %s", exc, extra={"trace_id": trace_id})
        _raise_llm_unavailable(exc)
    except HTTPException:
        raise
    except Exception:
        _logger.exception("Chat failed", extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail="Internal server error") from None
    _logger.info("Chat handler done: trace_id=%s", trace_id)
    return ChatResponse(
        message=response.text or "",
        conversation_id=conv_id,
        metadata=response.metadata,
    )


@router.post("/chat/stream", response_model=None)
async def chat_stream(
    req: ChatRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> StreamingResponse:
    conv_id = req.conversation_id or str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    _logger.info("Chat stream handler start: trace_id=%s", trace_id)

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for chunk in state.chat_manager.stream_chat(
                message=req.message,
                conversation_id=conv_id,
                metadata={**req.metadata, "trace_id": trace_id},
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except AdapterError as exc:
            _logger.warning(
                "LLM unavailable in stream: %s", exc, extra={"trace_id": trace_id}
            )
            payload = json.dumps(
                {
                    "error": "LLM service temporarily unavailable. Please try again later."
                }
            )
            yield f"data: {payload}\n\n"
        except Exception:
            _logger.exception("Stream failed", extra={"trace_id": trace_id})
            payload = json.dumps({"error": "Internal server error"})
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- OpenAI-compatible endpoints (stay at root /v1/*) ---


# Cache model list per config object (config is immutable at runtime)
_model_list_cache: dict[int, OAIModelList] = {}


@router_oai.get("/v1/models", response_model=OAIModelList)
async def list_models(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> OAIModelList:
    cfg = state.config.llm
    cache_key = id(cfg)
    if cache_key not in _model_list_cache:
        models = cfg.available_models if cfg.available_models else []
        if not models:
            models = [cfg.model]
        _model_list_cache[cache_key] = OAIModelList(
            data=[OAIModel(id=m) for m in models]
        )
    return _model_list_cache[cache_key]


@router_oai.post("/v1/chat/completions", response_model=None)
async def openai_chat_completions(
    req: OAIChatCompletionRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> OAIChatCompletion | StreamingResponse:

    last_user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user" and m.content is not None:
            last_user_msg = m.content
            break

    conv_id = str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    _logger.info("OpenAI handler start: trace_id=%s", trace_id)
    model_id = req.model if req.model is not None else state.config.llm.model

    if req.stream:

        async def event_generator() -> AsyncIterator[str]:
            try:
                async for chunk in state.chat_manager.stream_chat(
                    message=last_user_msg,
                    conversation_id=conv_id,
                    metadata={"trace_id": trace_id},
                ):
                    delta = OAIDeltaChunk(
                        model=model_id,
                        choices=[
                            OAIChoice(
                                index=0,
                                delta=OAIChatMessage(role="assistant", content=chunk),
                                finish_reason=None,
                            )
                        ],
                    )
                    yield f"data: {delta.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            except AdapterError as exc:
                _logger.warning(
                    "LLM unavailable in stream: %s", exc, extra={"trace_id": trace_id}
                )
                payload = json.dumps(
                    {
                        "error": "LLM service temporarily unavailable. Please try again later."
                    }
                )
                yield f"data: {payload}\n\n"
            except Exception:
                _logger.exception("OpenAI stream failed", extra={"trace_id": trace_id})
                payload = json.dumps({"error": "Internal server error"})
                yield f"data: {payload}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    try:
        response = await state.chat_manager.chat(
            message=last_user_msg,
            conversation_id=conv_id,
            metadata={"trace_id": trace_id},
        )
    except AdapterError as exc:
        _logger.warning("LLM unavailable: %s", exc, extra={"trace_id": trace_id})
        _raise_llm_unavailable(exc)
    except HTTPException:
        raise
    except Exception:
        _logger.exception("OpenAI chat failed", extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail="Internal server error") from None

    _logger.info("OpenAI handler done: trace_id=%s", trace_id)
    return OAIChatCompletion(
        model=model_id,
        created=int(time.time()),
        choices=[
            OAIChoice(
                index=0,
                message=OAIChatMessage(role="assistant", content=response.text or ""),
                finish_reason="stop",
            )
        ],
    )

```

### `src/ai_assistant/features/chat/schemas.py`
```python
"""Chat feature Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Universal chat request."""

    message: str
    conversation_id: str | None = Field(
        default=None, description="Thread ID for continuity"
    )
    stream: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    """Chat response."""

    message: str
    conversation_id: str
    role: str = "assistant"
    metadata: dict[str, object] = Field(default_factory=dict)


class ChatStreamChunk(BaseModel):
    """SSE stream chunk."""

    delta: str
    conversation_id: str
    finished: bool = False


# --- OpenAI-compatible schemas ---


class OAIChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    content: str | None = None
    name: str | None = None


class OAIChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str | None = None
    messages: list[OAIChatMessage]
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: list[str] | str | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    user: str | None = None


class OAIChoice(BaseModel):
    index: int = 0
    message: OAIChatMessage | None = None
    delta: OAIChatMessage | None = None
    finish_reason: str | None = None


class OAIChatCompletion(BaseModel):
    id: str = "chatcmpl-local"
    object: str = "chat.completion"
    created: int = 0
    model: str = "local"
    choices: list[OAIChoice]


class OAIDeltaChunk(BaseModel):
    id: str = "chatcmpl-local"
    object: str = "chat.completion.chunk"
    created: int = 0
    model: str = "local"
    choices: list[OAIChoice]


class OAIModel(BaseModel):
    id: str
    object: str = "model"
    created: int = 1677610602
    owned_by: str = "local"


class OAIModelList(BaseModel):
    object: str = "list"
    data: list[OAIModel]


__all__ = [
    "ChatRequest",
    "ChatResponse",
    "ChatStreamChunk",
    "OAIChatMessage",
    "OAIChatCompletionRequest",
    "OAIChoice",
    "OAIChatCompletion",
    "OAIDeltaChunk",
    "OAIModel",
    "OAIModelList",
]

```

### `src/ai_assistant/features/rag/handlers.py`
```python
"""RAG feature HTTP handlers with namespace and reranker support."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.api.deps import InitializedAppState, get_state
from ai_assistant.core.constants import DOCUMENTS_ROOT
from ai_assistant.core.logger import get_logger
from ai_assistant.features.rag.indexing import index_folder
from ai_assistant.features.rag.manager import IndexingManager, RAGManager
from ai_assistant.features.rag.schemas import (
    DeleteRequest,
    DeleteResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    NamespaceListResponse,
    QueryRequest,
    QueryResponse,
    SaveChatRequest,
)

__all__ = ["router"]

_logger = get_logger("rag.handlers")

router = APIRouter(prefix="/rag", tags=["rag"])

# ── Background reindex coordination ─────────────────────────────────────────
_reindex_semaphore = asyncio.Semaphore(1)
_reindex_tasks: dict[str, asyncio.Task[dict[str, Any]]] = {}
_reindex_status: dict[str, dict[str, Any]] = {}
_reindex_lock = asyncio.Lock()

_REINDEX_STATUS_TTL_SECONDS = 3600
_REINDEX_STATUS_MAX_ENTRIES = 1000


async def _cleanup_reindex_status() -> None:
    """Remove expired entries and enforce max size cap on _reindex_status."""
    async with _reindex_lock:
        now = time.time()

        # TTL cleanup: remove entries whose last activity is older than TTL
        expired = [
            tid
            for tid, info in _reindex_status.items()
            if now - (info.get("finished_at") or info.get("started_at", 0))
            > _REINDEX_STATUS_TTL_SECONDS
        ]
        for tid in expired:
            _reindex_status.pop(tid, None)

        # Cap cleanup: if still over max, remove oldest by started_at
        if len(_reindex_status) > _REINDEX_STATUS_MAX_ENTRIES:
            sorted_by_age = sorted(
                _reindex_status.items(),
                key=lambda item: item[1].get("started_at", 0),
            )
            excess = len(_reindex_status) - _REINDEX_STATUS_MAX_ENTRIES
            for tid, _ in sorted_by_age[:excess]:
                _reindex_status.pop(tid, None)


def _get_rag_manager(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> RAGManager:
    return RAGManager(
        pipeline=state.pipeline,
        llm=state.llm,
        vector_store=state.vector_store,
        embedder=state.embedder,
        reranker=state.reranker,
    )


@router.post("/index", response_model=IndexResponse)
async def index_documents(
    req: IndexRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> IndexResponse:
    namespace = req.namespace or state.config.rag.default_namespace
    ns_cfg = state.config.namespaces.get(namespace)

    # ── Per-namespace chunker override (only if size differs from base) ──
    chunker = state.chunker
    if ns_cfg is not None and ns_cfg.chunk_size != state.config.chunker.chunk_size:
        base_cfg = state.config.chunker
        ns_chunker_cfg = base_cfg.model_copy(
            update={"chunk_size": ns_cfg.chunk_size}
        )
        chunker = create_adapter("chunker", ns_chunker_cfg)

    manager = IndexingManager(
        chunker=chunker,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )

    # ── Resource guard: document size ──
    max_doc_size = state.config.vector_store.max_document_size
    filtered_docs: list[dict[str, Any]] = []
    pre_errors: list[str] = []
    for doc in req.documents:
        content = doc.get("content", "")
        size = len(content.encode("utf-8"))
        if size > max_doc_size:
            doc_id = doc.get("id", "unknown")
            pre_errors.append(
                f"Document {doc_id} exceeds max size ({size} > {max_doc_size})"
            )
        else:
            filtered_docs.append(doc)

    if not filtered_docs:
        return IndexResponse(
            indexed_count=0,
            chunk_count=0,
            namespace=namespace,
            errors=pre_errors,
        )

    result = await manager.index_documents(filtered_docs, namespace=namespace)
    if pre_errors:
        result.setdefault("errors", []).extend(pre_errors)

    # Auto-save after indexing
    index_path = state.config.vector_store.index_path
    if index_path:
        try:
            await state.vector_store.save(index_path, namespace=namespace)
        except Exception:
            _logger.exception("Auto-save failed")
            result.setdefault("errors", []).append("Internal server error")
    return IndexResponse(**result, namespace=namespace)


@router.post("/query", response_model=QueryResponse)
async def query_rag(
    req: QueryRequest,
    manager: Annotated[RAGManager, Depends(_get_rag_manager)],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> QueryResponse:
    cfg = state.config.rag
    ns = req.namespace or cfg.default_namespace
    ns_cfg = state.config.namespaces.get(ns)

    # Per-namespace overrides with global fallback
    prompt_name = req.prompt_name
    if prompt_name is None and ns_cfg is not None:
        prompt_name = ns_cfg.prompt
    if prompt_name is None:
        prompt_name = cfg.prompt_name or "rag_strict"

    relevance_threshold = cfg.relevance_threshold
    if ns_cfg is not None:
        relevance_threshold = ns_cfg.relevance_threshold

    result = await manager.query(
        query_text=req.query,
        top_k=req.top_k or cfg.top_k,
        prompt_name=prompt_name,
        prompt_version=req.prompt_version or cfg.prompt_version,
        namespace=ns,
        relevance_threshold=relevance_threshold,
    )
    return QueryResponse(**result)


@router.post("/delete", response_model=DeleteResponse)
async def delete_chunks(
    req: DeleteRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> DeleteResponse:
    namespace = req.namespace or state.config.rag.default_namespace
    errors: list[str] = []
    deleted = 0
    try:
        if req.chunk_ids:
            await state.vector_store.delete(req.chunk_ids, namespace=namespace)
            deleted += len(req.chunk_ids)
        elif req.document_ids:
            all_chunks = await state.vector_store.list_by_filter(
                {}, namespace=namespace
            )
            to_delete = []
            for chunk_id, meta in all_chunks:
                if meta.get("source") in req.document_ids:
                    to_delete.append(chunk_id)
            if to_delete:
                await state.vector_store.delete(to_delete, namespace=namespace)
                deleted += len(to_delete)
    except Exception:
        _logger.exception("Delete chunks failed")
        errors.append("Internal server error")
    return DeleteResponse(deleted_chunks=deleted, errors=errors)


@router.get("/health", response_model=HealthResponse)
async def rag_health(
    manager: Annotated[RAGManager, Depends(_get_rag_manager)],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> HealthResponse:
    health = await manager.health()
    return HealthResponse(
        status=health["status"],
        index_loaded=health["index_loaded"],
        chunk_count=health["chunk_count"],
        embedder_dim=state.embedder.dimension,
    )


@router.get("/namespaces", response_model=NamespaceListResponse)
async def list_namespaces(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> NamespaceListResponse:
    index_path = state.config.vector_store.index_path
    namespaces: list[str] = []
    if index_path:
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
        except Exception:
            _logger.exception("List namespaces failed")
    if not namespaces:
        namespaces = ["default"]
    return NamespaceListResponse(namespaces=namespaces)


@router.post("/save-chat", response_model=None)
async def save_chat(
    req: SaveChatRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> dict[str, Any]:
    namespace = req.namespace
    filename = req.filename
    content = req.content

    # Save to documents folder
    folder = DOCUMENTS_ROOT / namespace
    folder_resolved = await asyncio.to_thread(folder.resolve)
    docs_resolved = await asyncio.to_thread(DOCUMENTS_ROOT.resolve)

    if not folder_resolved.is_relative_to(docs_resolved):
        raise HTTPException(status_code=400, detail="Invalid namespace")

    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
    file_path = (folder / filename).resolve()
    if not file_path.is_relative_to(folder_resolved):
        raise HTTPException(status_code=400, detail="Path traversal detected")

    try:
        await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")
    except Exception:
        _logger.exception("Failed to save file")
        raise HTTPException(status_code=500, detail="Internal server error") from None

    # Index the saved chat
    try:
        manager = IndexingManager(
            chunker=state.chunker,
            embedder=state.embedder,
            vector_store=state.vector_store,
        )
        result = await manager.index_documents(
            [
                {
                    "id": file_path.stem,
                    "content": content,
                    "metadata": {
                        "source": str(file_path),
                        "folder": namespace,
                        "type": "chat_export",
                    },
                }
            ],
            namespace=namespace,
        )

        # Auto-save index
        index_path = state.config.vector_store.index_path
        if index_path:
            await state.vector_store.save(index_path, namespace=namespace)

        return {
            "saved": True,
            "path": str(file_path),
            "namespace": namespace,
            "indexed_count": result.get("indexed_count", 0),
            "chunk_count": result.get("chunk_count", 0),
        }
    except Exception as e:
        # File saved but indexing failed
        return {
            "saved": True,
            "path": str(file_path),
            "namespace": namespace,
            "indexed": False,
            "error": str(e),
        }


@router.post("/reindex", response_model=None)
async def reindex_documents(
    req: dict[str, Any],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> dict[str, Any]:
    """Reindex documents from folders. Returns immediately, runs in background."""
    folder = req.get("folder")
    clear = req.get("clear", False)

    task_id = str(uuid.uuid4())

    async def _run() -> dict[str, Any]:
        async with _reindex_semaphore:
            await _cleanup_reindex_status()
            async with _reindex_lock:
                _reindex_status[task_id] = {
                    "status": "running",
                    "started_at": time.time(),
                }
            try:
                result = await index_folder(
                    folder=folder,
                    clear=clear,
                    chunker=state.chunker,
                    embedder=state.embedder,
                    vector_store=state.vector_store,
                    max_file_size=state.config.vector_store.max_document_size,
                )
                async with _reindex_lock:
                    _reindex_status[task_id] = {
                        "status": "completed",
                        "result": result,
                        "finished_at": time.time(),
                    }
                return result
            except Exception:
                _logger.exception("Background reindex failed")
                async with _reindex_lock:
                    _reindex_status[task_id] = {
                        "status": "failed",
                        "error": "Internal server error",
                        "finished_at": time.time(),
                    }
                raise
            finally:
                _reindex_tasks.pop(task_id, None)

    task = asyncio.create_task(_run())
    _reindex_tasks[task_id] = task
    return {"status": "started", "task_id": task_id}


@router.get("/reindex/status/{task_id}", response_model=None)
async def reindex_status(task_id: str) -> dict[str, Any]:
    """Get status of a background reindex task."""
    await _cleanup_reindex_status()
    async with _reindex_lock:
        if task_id in _reindex_status:
            info = _reindex_status[task_id]
            return {"task_id": task_id, **info}
    return {"task_id": task_id, "status": "unknown"}

```

### `src/ai_assistant/features/rag/schemas.py`
```python
"""RAG feature Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "DeleteRequest",
    "DeleteResponse",
    "HealthResponse",
    "IndexRequest",
    "IndexResponse",
    "NamespaceListResponse",
    "QueryRequest",
    "QueryResponse",
    "SaveChatRequest",
]


class IndexRequest(BaseModel):
    """Request to index documents."""

    documents: list[dict[str, Any]] = Field(
        ...,
        description="List of {id, content, metadata} objects",
    )
    namespace: str | None = Field(
        default=None,
        description="Index namespace (default, personal, work, etc.)",
    )


class IndexResponse(BaseModel):
    """Response after indexing."""

    indexed_count: int
    chunk_count: int
    namespace: str | None = None
    errors: list[str] = Field(default_factory=list)


class QueryRequest(BaseModel):
    """RAG query request."""

    query: str
    top_k: int | None = Field(default=None, ge=1, le=50)
    prompt_name: str | None = None
    prompt_version: str | None = None
    namespace: str | None = Field(default=None, description="Query namespace")


class QueryResponse(BaseModel):
    """RAG query response."""

    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    chunks_used: int
    errors: list[str] = Field(default_factory=list)


class DeleteRequest(BaseModel):
    """Delete documents/chunks request."""

    document_ids: list[str] | None = None
    chunk_ids: list[str] | None = None
    namespace: str | None = Field(default=None, description="Target namespace")


class DeleteResponse(BaseModel):
    """Delete response."""

    deleted_chunks: int
    errors: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """RAG health check."""

    status: str
    index_loaded: bool
    chunk_count: int
    embedder_dim: int | None = None


class NamespaceListResponse(BaseModel):
    """Available RAG namespaces."""

    namespaces: list[str]


class SaveChatRequest(BaseModel):
    """Request to save chat content to documents folder."""

    content: str = Field(..., min_length=1, description="Chat content to save")
    namespace: str = Field(
        default="personal",
        pattern=r"^[a-z]+$",
        description="Target namespace",
    )
    filename: str = Field(
        default="chat.md",
        pattern=r"^[^./\\][^/\\]*$",
        description="Filename without path traversal",
    )

```

## 🧩 API Signatures

### `launcher.py`
```python
# API: launcher.py

import argparse
import contextlib
import os
import subprocess
import sys
from pathlib import Path
def get_python(root: Path):

def collect(root: Path, subdir: str):

def sort_scripts(files: list[Path]):

def print_menu(scripts, tests, last):

def run(python, target, root, extra):

def find_target(num, scripts, tests):

def main():

```

### `src/ai_assistant/__init__.py`
```python
# API: src/ai_assistant/__init__.py

```

### `src/ai_assistant/adapters/__init__.py`
```python
# API: src/ai_assistant/adapters/__init__.py

```

### `src/ai_assistant/adapters/chunker_simple.py`
```python
# API: src/ai_assistant/adapters/chunker_simple.py

from __future__ import annotations
import uuid
from typing import Any
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
from ai_assistant.core.ports.chunker import IChunker
class SimpleChunker(IChunker):
    """Split text into fixed-size chunks with overlap."""

```

### `src/ai_assistant/adapters/embedder_mock.py`
```python
# API: src/ai_assistant/adapters/embedder_mock.py

from __future__ import annotations
import random
from typing import Any
from ai_assistant.core.ports.embedder import IEmbedder
class MockEmbedder(IEmbedder):
    """Deterministic fake embedder for testing."""

```

### `src/ai_assistant/adapters/embedder_openai_compatible.py`
```python
# API: src/ai_assistant/adapters/embedder_openai_compatible.py

from __future__ import annotations
import asyncio
import json
from typing import Any
import httpx
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.ports.embedder import IEmbedder
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key
def _extract_embeddings(resp_text: str, expected_dim: int, model: str):

class OpenAICompatibleEmbedder(IEmbedder):
    """Embedder using OpenAI-compatible REST API."""

```

### `src/ai_assistant/adapters/factory.py`
```python
# API: src/ai_assistant/adapters/factory.py

from __future__ import annotations
from typing import Any
def create_adapter(port: str, name: str, config: Any):
    """Create an adapter instance by port and name.

Args:
    port: Port category (e.g., "llm", "embedder").
    name: Adapter identifier (e.g., "mock", "openai_compatible").
    config: Configuration objec"""

```

### `src/ai_assistant/adapters/llm_mock.py`
```python
# API: src/ai_assistant/adapters/llm_mock.py

from __future__ import annotations
from typing import TYPE_CHECKING, Any
from ai_assistant.core.domain.messages import AssistantMessage
from ai_assistant.core.ports.llm import ILLM, Message
class MockLLM(ILLM):
    """Deterministic echo LLM for testing."""

```

### `src/ai_assistant/adapters/llm_openai_compatible.py`
```python
# API: src/ai_assistant/adapters/llm_openai_compatible.py

from __future__ import annotations
import json
from typing import TYPE_CHECKING, Any
import httpx
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import AssistantMessage, MessageRole
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.closable import IClosable
from ai_assistant.core.ports.llm import ILLM, Message
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key
class OpenAICompatibleLLM(ILLM, IClosable):
    """LLM using OpenAI-compatible REST API."""

```

### `src/ai_assistant/adapters/reranker_api.py`
```python
# API: src/ai_assistant/adapters/reranker_api.py

from __future__ import annotations
from typing import TYPE_CHECKING, Any
import httpx
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.ports.reranker import IReranker, RerankResult
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import resolve_api_key
class APIReranker(IReranker):
    """Cross-encoder reranker using external API (OpenAI-compatible /rerank).

Compatible with:
- Cohere /rerank
- Jina AI /rerank
- Any OpenAI-compatible rerank endpoint"""

```

### `src/ai_assistant/adapters/storage_sqlite.py`
```python
# API: src/ai_assistant/adapters/storage_sqlite.py

from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Any
import aiosqlite
from ai_assistant.core.ports.initializable import IInitializable
from ai_assistant.core.ports.storage import IChatStorage, ISettingsStorage
def _safe_json_loads(value: str | None, default: Any):

class SQLiteStorage(IChatStorage, ISettingsStorage, IInitializable):
    """Combined chat and settings storage."""

```

### `src/ai_assistant/adapters/vector_store_faiss.py`
```python
# API: src/ai_assistant/adapters/vector_store_faiss.py

from __future__ import annotations
import asyncio
import datetime
import json
from pathlib import Path
from typing import Any
import numpy as np
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.io_utils import atomic_write
from ai_assistant.core.ports.vector_store import IVectorStore
```

### `src/ai_assistant/adapters/vector_store_memory.py`
```python
# API: src/ai_assistant/adapters/vector_store_memory.py

from __future__ import annotations
import asyncio
import json
from pathlib import Path
from typing import Any
import numpy as np
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import VersionMismatchError
from ai_assistant.core.io_utils import atomic_write
from ai_assistant.core.ports.vector_store import IVectorStore
class MemoryVectorStore(IVectorStore):
    """Simple in-memory vector store with multi-namespace support and FIFO eviction.

Uses cosine similarity with strict threshold to prevent irrelevant results.
Enforces max_chunks per namespace to prevent """

class _NamespaceData:
    """Per-namespace state with FIFO eviction."""

```

### `src/ai_assistant/features/__init__.py`
```python
# API: src/ai_assistant/features/__init__.py

```

### `src/ai_assistant/features/chat/__init__.py`
```python
# API: src/ai_assistant/features/chat/__init__.py

```

### `src/ai_assistant/features/chat/manager.py`
```python
# API: src/ai_assistant/features/chat/manager.py

from __future__ import annotations
import re
from typing import TYPE_CHECKING, Any
from ai_assistant.core.constants import FROZEN_NO_INFO_PHRASES
from ai_assistant.core.constants import RAG_NS_MAP as _NS_MAP
from ai_assistant.core.constants import RAG_PREFIX_RE as _PREFIX_RE
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.utils import count_tokens, get_context_limit
class ChatManager:
    """Universal chat router."""

```

### `src/ai_assistant/features/rag/__init__.py`
```python
# API: src/ai_assistant/features/rag/__init__.py

```

### `src/ai_assistant/features/rag/indexing.py`
```python
# API: src/ai_assistant/features/rag/indexing.py

from __future__ import annotations
from pathlib import Path
from typing import Any
from ai_assistant.core.logger import get_logger
def _read_file(path: Path):
    """Read text file with encoding fallback."""

def _discover_documents(folder: str | None=None, max_file_size: int | None=None):
    """Discover documents in folders. Returns {namespace: [docs]}."""

async def index_folder(folder: str | None, clear: bool, chunker: Any, embedder: Any, vector_store: Any, max_file_size: int | None=None):
    """Index documents from disk folders directly into vector store.

Args:
    folder: Specific folder to index, or None for all.
    clear: If True, clear existing chunks in each namespace before indexing."""

```

### `src/ai_assistant/features/rag/manager.py`
```python
# API: src/ai_assistant/features/rag/manager.py

from __future__ import annotations
import re
import uuid
from typing import TYPE_CHECKING, Any
from ai_assistant.core.constants import FROZEN_NO_INFO_PHRASES
from ai_assistant.core.domain.documents import Chunk, Document
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
class IndexingManager:
    """Handles document ingestion: chunk + embed + store per namespace."""

class RAGManager:
    """Handles RAG queries using the pipeline per namespace."""

```

### `src/ai_assistant/main.py`
```python
# API: src/ai_assistant/main.py

from __future__ import annotations
from typing import Annotated, Any
from fastapi import Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ai_assistant.api.deps import InitializedAppState, get_state
from ai_assistant.api.lifespan import lifespan as _default_lifespan
from ai_assistant.api.middleware import MetricsMiddleware
from ai_assistant.api.router import assemble_routers
from ai_assistant.core.metrics import get_metrics, get_metrics_json
class _InfoResponse(BaseModel):

def create_app(state: InitializedAppState | None=None, lifespan: Any=None):
    """Application factory — creates a fresh FastAPI instance."""

```
