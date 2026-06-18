# AI Context
> **Generated:** 2026-06-18 14:19:25 UTC | **Mode:** `rules`
> **Metrics:** 108 files | 93 Python | 18,339 LOC
> **Full:** 0 | **Signatures:** 0 | **Listed:** 101

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

```
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

# 4. Запуск (из корня проекта, .venv активируется автоматически или будут подсказки по установке)
Кликаем дважды на run.py


# Или вручную:
python scripts/run.py
python main.py
uvicorn ai_assistant.main:app --host 0.0.0.0 --port 8000

# 5. UI
# Подключи любой OpenAI-compatible клиент к http://localhost:8000
# Рекомендуется: Page Assist (браузерное расширение)
```

## RAG — поиск по документам

```bash
# Индексация документов (ПЕРЕСМОТРЕТЬ РАСПОЛОЖЕНИЕ ФАЙЛА)
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
> Version: 2026-06-17
> Next review: 2026-09-17

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
- Add a dependency without immediately updating `pyproject.toml` / `requirements.txt`

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

New functionality requires new tests. Existing tests may only be updated during refactoring or contract changes.

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

## 6. Adapter Discipline

Implement ports exactly. No duck typing. Register with `@register("port", "name")`. Mock adapters live in `adapters/`, never in test files.

Catch library-specific exceptions and wrap into core domain exceptions (`AdapterError`, `ConfigurationError`, `VersionMismatchError`). Always log the original traceback via `logger.exception` before wrapping. Business logic sees only core exceptions.

## 7. Resilience

All external network calls require hard timeout. All external calls use retry with exponential backoff (`core/retry.py`). Operations must be idempotent.

## 8. Graceful Shutdown

On SIGINT/SIGTERM: stop accepting requests, finish active tasks, close DB connections and persist indices, call `IClosable.shutdown()`, stop metrics logger last.

## 9. Output Protocol

Response format:
1. What and Why -- 1-2 sentences
2. Changes -- file path + full content or FIND/REPLACE
3. Verification -- pytest commands, test update needed?

**FIND/REPLACE format:** Two separate fenced blocks per change. The user copies each block directly into editor find/replace.

```find:src/path/to/file.py
# 2 lines of unchanged context ABOVE
OLD code exactly as in file
# 2 lines of unchanged context BELOW
```

```replace:src/path/to/file.py
# 2 lines of unchanged context ABOVE
NEW replacement code
# 2 lines of unchanged context BELOW
```

Rules:
- Labels `find:` and `replace:` are mandatory and must include the file path.
- Content inside blocks must match the original file EXACTLY.
- No other text between the two blocks.
- If change exceeds 10 lines, output the full file as `replace:` block only.

File review checklist (output findings only, skip if clean):
- LANGUAGE: No Cyrillic in code/comments/docstrings (domain constants exempt)
- EMOJI: No U+1F600+ in `.py` files
- DUPLICATES: No copy-paste artifacts, orphaned code, commented dead code
- MAGIC: No bare literals used >1 place without named constant
- TYPES: No `Any` where concrete type is visible. Enforced by `mypy --strict` (or equivalent) in `scripts/check_all.py`
- LAYERS: Imports comply with Section 3
- IMMUTABILITY: No PipelineData mutation
- PORTS: No `hasattr`, `isinstance` on port objects
- DOCS: Docstrings in English, triple quotes, describe intent
- LOGGING: `get_logger(name)` used
- SECRETS: No hardcoded keys/tokens
- STYLE: Line length <=88, double quotes, f-strings

## 10. Decision Hierarchy

Feature conflicts with Absolute Constraint:

1. Can it live entirely in `adapters/` or `features/`? -> Do it there. No core change.
2. Needs `core/` change but keeps all tests green? -> Allowed. Update `error_taxonomy.md`.
3. Requires breaking port contract or adding `**kwargs`? -> Output `CORE CHANGE REQUIRED`, propose port extension or `PipelineData.metadata`, wait for confirmation.
4. Known drift in `docs/drift.md` makes hack tempting? -> Reference drift, propose fixing it. If user says "use drift for now", document new instance immediately.
5. Never silently bypass a port contract. If `llm.config` is needed but `ILLM` does not expose it, do not use `getattr(llm, "config", None)`. Either add to `ILLM`, or add a getter, or keep logic inside the adapter.

## 11. Solo Maintenance

- Explicit over implicit. No magic discovery, reflection, dynamic imports.
- Every architectural change explainable in one sentence to a non-technical person.
- >3 files changed -> split into smaller steps or discuss first.
- `docs/` is source of truth. Code must match docs. If conflict, update docs first.
- When proposing core change, explain: what breaks, what improves, alternatives.

### 11.1. FastAPI DI and Ruff type-checking rules

With `from __future__ import annotations`, all annotations are strings
at runtime. Ruff cannot distinguish typing-only usage from runtime usage.

- **TC002** (third-party): `Request`, `Response` must stay in runtime imports
  for FastAPI DI and middleware. Use `# noqa: TC002` on specific lines.
  `runtime-evaluated-decorators` does not cover all cases (e.g. methods
  in BaseHTTPMiddleware, functions used via Annotated[...]).
- **TC003** (stdlib): disabled globally. `Callable`, `Awaitable` are
  needed for module-level type annotations. Stdlib imports are cheap;
  per-file `noqa` does not scale.

Do NOT use `request: Any` — breaks FastAPI DI with 422.
Do NOT move `Request` under `TYPE_CHECKING` — same result.

## 12. Rule Self-Check

Before outputting code, verify:
- [ ] All changed files listed in Output Protocol
- [ ] No rule from Section 2 (Absolute Constraints) violated
- [ ] If >3 files changed, split proposed or get confirmation
- [ ] Tests updated for new functionality

## 13. Technology Decay

When a technology in the stack becomes obsolete:
1. Mark related config fields as deprecated in `AppConfig` with `deprecated=True` (Pydantic v2)
2. Add backward-compat loader in `model_validator(mode="before")`
3. Remove only after 2 major versions or 1 year, whichever is longer
4. Update `docs/drift.md` with migration path

## 14. Rule Evolution

These rules themselves change:
- Proposed changes go to `docs/ai_rules_proposed.md`
- User approves -> move to this file, bump `rules_version` in header
- Rejected ideas stay in `proposed.md` with reason for rejection
- Review rules quarterly or after 5+ violations in one month

```

---

## ⚠️ Error Taxonomy
> Auto-extracted from: `error_taxonomy.md`
```markdown
## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-18 14:19 UTC
> **Rule:** Check this table before adding try/except or changing error handling.

| Component | Exception | Trigger | Severity | Line |
|-----------|-----------|---------|----------|------|
| `core.retry` | `SystemExit/KeyboardInterrupt` | raise | Critical | 49 |
| `tests.test_retry` | `KeyboardInterrupt` | Raised KeyboardInterrupt | Critical | 132 |
| `adapters.chunker_simple` | `ValueError` | chunk_size must be > 0, got {...} | High | 24 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap must be >= 0, got {...} | High | 26 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap ({...}) must be < chunk_size ({...}) | High | 28 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Unexpected response shape from {...}: {...} | High | 35 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Dimension mismatch: expected {...}, got {...} for text[{...}... | High | 39 |
| `adapters.factory` | `ValueError` | faiss-cpu is not installed but vector_store.provider='faiss' | High | 54 |
| `adapters.factory` | `ValueError` | sqlite3 not available but storage.provider='sqlite' | High | 63 |
| `adapters.factory` | `ValueError` | Unknown adapter port '{...}' | High | 69 |
| `adapters.factory` | `ValueError` | No {...} adapter registered for '{...}' | High | 73 |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High | 174 |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High | 84 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High | 137 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS search: expected {...}, got {...... | High | 186 |
| `adapters.vector_store_faiss` | `AdapterError` | Index metadata missing for namespace '{...}': {...} not foun... | High | 276 |
| `adapters.vector_store_faiss` | `AdapterError` | Index file missing for namespace '{...}': {...} not found. P... | High | 294 |
| `adapters.vector_store_faiss` | `AdapterError` | Invalid store.json for namespace '{...}': {...} | High | 315 |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 328 |
| `adapters.vector_store_memory` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 162 |
| `api.admin` | `HTTPException` | Unknown error | High | 49 |
| `api.deps` | `RuntimeError` | LLM adapter failed to initialize | High | 311 |
| `api.deps` | `RuntimeError` | Embedder adapter failed to initialize | High | 313 |
| `api.deps` | `RuntimeError` | Vector store adapter failed to initialize | High | 315 |
| `api.deps` | `RuntimeError` | Pipeline failed to initialize | High | 317 |
| `api.deps` | `RuntimeError` | Storage adapter failed to initialize | High | 319 |
| `api.deps` | `RuntimeError` | Chunker adapter failed to initialize | High | 321 |
| `api.deps` | `RuntimeError` | Chat manager failed to initialize | High | 323 |
| `api.deps` | `RuntimeError` | State not initialized | High | 342 |
| `api.deps` | `ValueError` | Unknown step: {...} | High | 153 |
| `api.security` | `HTTPException` | Unknown error | High | 63 |
| `core.config` | `ValueError` | path must be non-empty | High | 179 |
| `core.config` | `ValueError` | path must be relative, got: {...} | High | 181 |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High | 290 |
| `core.config` | `ValueError` | Invalid YAML in {...}: {...} | High | 317 |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High | 28 |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High | 84 |
| `core.logger` | `ValueError` | Invalid log format {...}. Use 'text' or 'json'. | High | 89 |
| `core.pipeline` | `ConfigurationError` | Missing required PipelineData fields: {...} | High | 40 |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High | 41 |
| `core.prompts.__init__` | `ValueError` | prompt version is required | High | 71 |
| `core.retry` | `RuntimeError` | last_exception is None after retry loop | High | 64 |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High | 40 |
| `features.chat.handlers` | `HTTPException` | Unknown error | High | 38 |
| `features.chat.manager` | `AdapterError` | LLM call failed: {...} | High | 293 |
| `features.chat.manager` | `AdapterError` | LLM stream failed: {...} | High | 390 |
| `features.rag.handlers` | `HTTPException` | Unknown error | High | 179 |
| `tests.test_api` | `HTTPException` | Unknown error | High | 1430 |
| `tests.test_api` | `RuntimeError` | boom | High | 1495 |
| `tests.test_api` | `ValueError` | No storage adapter registered | High | 671 |
| `tests.test_e2e` | `ValueError` | Error with "quotes" and 
 newlines | High | 218 |
| `tests.test_pipeline` | `AdapterError` | LLM down | High | 519 |
| `tests.test_pipeline` | `RuntimeError` | transient | High | 621 |
| `tests.test_pipeline` | `RuntimeError` | fail | High | 651 |
| `tests.test_pipeline` | `RuntimeError` | attempt {...} | High | 673 |
| `tests.test_pipeline` | `ValueError` | permanent | High | 628 |
| `tests.test_properties` | `ValueError` | Unknown embedder: {...} | High | 41 |
| `tests.test_properties` | `ValueError` | Unknown llm: {...} | High | 60 |
| `tests.test_properties` | `ValueError` | Unknown reranker: {...} | High | 73 |
| `tests.test_properties` | `ValueError` | Unknown chunker: {...} | High | 86 |
| `tests.test_rag` | `HTTPException` | Unknown error | High | 183 |
| `tests.test_retry` | `exc` | fail #{...} | High | 38 |
| `tests.test_stateful_ports` | `RuntimeError` | TMP_DIR not set. Call _set_tmp_dir() first. | High | 43 |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | _logger.exception( | Medium | 30 |
| `adapters.factory` | `ImportError` | raise ValueError( | Medium | 53 |
| `adapters.llm_openai_compatible` | `AttributeError` | _logger.warning( | Medium | 96 |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | raise AdapterError(f"Unexpected response shape: {exc}") from | Medium | 173 |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | continue | Medium | 246 |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | _logger.warning( | Medium | 264 |
| `adapters.llm_openai_compatible` | `TypeError` | return [] | Medium | 87 |
| `adapters.reranker_api` | `KeyError/TypeError` | _logger.exception( | Medium | 79 |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | continue | Medium | 91 |
| `adapters.storage_sqlite` | `JSONDecodeError` | _logger.warning("JSON decode failed in storage", extra={"err | Medium | 27 |
| `adapters.vector_store_faiss` | `ImportError` | faiss = None  # type: ignore[assignment, no-redef] | Medium | 30 |
| `adapters.vector_store_faiss` | `ImportError` | faiss-cpu is not installed but vector_store.provider='faiss' | Medium | 93 |
| `adapters.vector_store_faiss` | `JSONDecodeError` | _logger.error( | Medium | 307 |
| `api.deps` | `ValueError/ImportError` | _logger.exception( | Medium | 276 |
| `api.lifespan` | `AttributeError` | logger.warning("No app state found during shutdown") | Medium | 85 |
| `api.lifespan` | `Exception` | logger.exception("Index load failed on startup") | Medium | 72 |
| `api.lifespan` | `Exception` | logger.exception("Index save failed") | Medium | 114 |
| `api.lifespan` | `Exception` | logger.exception("Adapter shutdown failed", extra={"adapter" | Medium | 134 |
| `api.lifespan` | `TimeoutError` | logger.warning( | Medium | 105 |
| `api.lifespan` | `TimeoutError` | logger.warning("Adapter shutdown timed out", extra={"adapter | Medium | 132 |
| `api.security` | `ValueError` | raise HTTPException( | Medium | 64 |
| `core.config` | `YAMLError` | raise ValueError(f"Invalid YAML in {config_path}: {exc}") fr | Medium | 316 |
| `core.io_utils` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium | 59 |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium | 32 |
| `core.io_utils` | `TypeError` | Expected str for mode={...}, got {...} | Medium | 36 |
| `core.logger` | `OSError` | sys.stderr.write(f"Failed to create log file {path}: {exc}\n | Medium | 120 |
| `core.pipeline_steps` | `AdapterError` | _logger.exception("LLM unavailable", extra={"trace_id": data | Medium | 377 |
| `core.pipeline_steps` | `Exception` | _logger.exception("embed_query failed", extra={"trace_id": d | Medium | 128 |
| `core.pipeline_steps` | `Exception` | _logger.exception("retrieve failed", extra={"trace_id": data | Medium | 171 |
| `core.pipeline_steps` | `Exception` | _logger.exception("rerank failed", extra={"trace_id": data.t | Medium | 229 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(current_data.chunks, query_t | Medium | 295 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(data.chunks, query_text) | Medium | 336 |
| `core.pipeline_steps` | `Exception` | _logger.exception( | Medium | 384 |
| `core.retry` | `Exception` | last_exception = e | Medium | 53 |
| `core.retry` | `_PERMANENT_ERRORS` | raise | Medium | 51 |
| `core.retry` | `last_exception` | Raised last_exception | Medium | 65 |
| `core.utils` | `AttributeError` | return len(enc.encode(text)) | Medium | 130 |
| `core.utils` | `Exception` | pass | Medium | 83 |
| `core.utils` | `Exception` | if _cjk_ratio(text) > _CJK_RATIO_THRESHOLD: | Medium | 133 |
| `core.utils` | `ImportError` | tiktoken = None  # type: ignore[assignment] | Medium | 12 |
| `core.utils` | `ImportError` | tokenizers = None  # type: ignore[assignment] | Medium | 17 |
| `core.utils` | `KeyError` | try: | Medium | 80 |
| `core.utils` | `OSError` | return None | Medium | 67 |
| `features.chat.handlers` | `AdapterError` | _logger.warning( | Medium | 121 |
| `features.chat.handlers` | `AdapterError` | payload = json.dumps( | Medium | 177 |
| `features.chat.handlers` | `Exception` | await queue.put(exc) | Medium | 66 |
| `features.chat.handlers` | `Exception` | _logger.exception("Chat failed", extra={"trace_id": trace_id | Medium | 129 |
| `features.chat.handlers` | `Exception` | _logger.exception("Stream failed", extra={"trace_id": trace_ | Medium | 169 |
| `features.chat.handlers` | `Exception` | payload = json.dumps({"error": "Internal server error"}) | Medium | 184 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI stream failed", extra={"trace_id": | Medium | 256 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI chat failed", extra={"trace_id": t | Medium | 291 |
| `features.chat.handlers` | `HTTPException` | raise | Medium | 127 |
| `features.chat.handlers` | `TimeoutError` | yield ": ping\n\n" | Medium | 79 |
| `features.chat.handlers` | `item` | Raised item | Medium | 90 |
| `features.chat.manager` | `AdapterError` | raise | Medium | 280 |
| `features.chat.manager` | `Exception` | logger.warning( | Medium | 219 |
| `features.chat.manager` | `Exception` | logger.warning("History load failed", extra={"error": str(ex | Medium | 236 |
| `features.chat.manager` | `Exception` | duration_ms = int((time.perf_counter() - start) * 1000) | Medium | 282 |
| `features.chat.manager` | `Exception` | logger.warning("History save failed", extra={"error": str(ex | Medium | 331 |
| `features.rag.handlers` | `Exception` | _logger.exception("Auto-save failed") | Medium | 109 |
| `features.rag.handlers` | `Exception` | _logger.exception("Delete chunks failed") | Medium | 209 |
| `features.rag.handlers` | `Exception` | _logger.exception("List namespaces failed") | Medium | 238 |
| `features.rag.handlers` | `Exception` | _logger.exception("Failed to save file") | Medium | 270 |
| `features.rag.handlers` | `Exception` | return { | Medium | 308 |
| `features.rag.handlers` | `Exception` | _logger.exception("Background reindex failed") | Medium | 355 |
| `features.rag.manager` | `Exception` | _logger.exception("Health check failed") | Medium | 188 |
| `tests.test_api` | `Exception` | errors.append(e) | Medium | 369 |
| `tests.test_api` | `ImportError` | sqlite3 not available | Medium | 694 |
| `tests.test_chat` | `StopAsyncIteration` | Raised StopAsyncIteration | Medium | 44 |
| `tests.test_retry` | `exc_cls` | permanent | Medium | 264 |
| `tests.test_smoke` | `Exception` | return req, None, None | Medium | 538 |
| `tests.test_stateful_ports` | `RuntimeError` | loop = asyncio.new_event_loop() | Medium | 66 |
| `tests.test_logger` | `OSError` | disk full | Low | 214 |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.

```

---

## ⚠️ Error Taxonomy
> Auto-extracted from: `DRIFT.md`
```markdown
# Known Architectural Drift

| ID | File | Broken Rule | Why | Fix | Priority |
|----|------|-------------|-----|-----|----------|
| 1 | Fixed 2026-06-09: get_context_limit() added to ILLM port. All adapters updated. |
| 2 | Fixed 2026-06-09: NullReranker introduced. `rerank()` no longer branches on `None`. `InitializedAppState.reranker` is `IReranker` (non-optional). |
| 3 | Fixed 2026-06-09: getattr(config, "vector_store") removed. Pydantic validation guarantees field presence. |
| 4 | Fixed 2026-06-13: Replaced all `getattr(config, "x", default)` with direct `config.x` access in all adapters. All defaults verified in `AppConfig` Pydantic models. |
| 5 | Fixed 2026-06-14: `ChunkMetadata` schema drift. `vector_store_faiss.py` and `vector_store_memory.py` serialized `created_at` (not in domain model) and missed `total_chunks` in FAISS `add()`. Introduced `dataclass_from_dict` in `core/utils.py` for strict deserialization. |
| 6 | Fixed 2026-06-14: Added `get_logger` to `embedder_openai_compatible.py` and `reranker_api.py`. All `AdapterError` wraps now preceded by `logger.exception`. |
| 7 | `adapters/embedder_openai_compatible.py`, `adapters/llm_openai_compatible.py` | Duplicate HTTP client setup (httpx.AsyncClient, POST, raise_for_status, json parse) | Layer boundaries prevent shared httpx code: core/ is stdlib-only, adapters/ may only import core/*. Extracting to core/ violates stdlib-only rule. Extracting to adapters/_shared violates layer boundaries. | Accept duplication as architectural constraint. Revisit if >3 adapters share pattern. | Low |
| 8 | Fixed 2026-06-18: Replaced `metadata: dict[str, Any]` with explicit typed fields in `PipelineData` (embedder, vector_store, reranker, llm, pipeline_config, query_embedding, tokenizer_model, rerank_filtered_out, rerank_scores). All casts and string-key access removed from pipeline steps and tests. |
| 9 | ~~`src/ai_assistant/core/pipeline_steps.py`~~ (fixed 2026-06-17) | ~~`model: str = "gpt-4o"` default~~ | ~~Default был fallback для тестов/CLI~~ | **Fixed:** убраны все дефолты `"gpt-4o"` из `_estimate_tokens()` и `_truncate_to_fit()`. `tokenizer_model` теперь обязательный ключ в metadata. `ChatManager` всегда передаёт его. Все тесты обновлены. | — |
| 10 | `src/ai_assistant/core/retry.py` | `max_retries=3, delay=1.0, backoff=2.0` хардкод в `@with_retry` на адаптерах | Resilience policy — не бизнес-логика. Меняется раз в 10 лет. Вынесение в config требует CORE CHANGE (новые поля в `EmbedderConfigData`, `LLMConfigData`, `RerankerConfigData`) + inline-фабрики декораторов (костыль). | Accept as architectural constraint. Пересмотреть при добавлении `IRetryPolicy` порта или embedded-режима с 0 retries. | Low |
| 11 | `src/ai_assistant/core/prompts/__init__.py` | Jinja2 import в core/ | Prompt rendering — domain logic, Jinja2 — implementation detail. Для 30-летнего горизонта абстракция `IPromptRenderer` предпочтительна, но требует нового порта + адаптера + обновления factory + всех вызовов. | Accept as grandfathered exception. Документировать при добавлении второго движка шаблонов (Mustache, etc.). | Low |
| 12 | `src/ai_assistant/core/prompts/__init__.py` | `_make_hashable()` без защиты от циклических ссылок | Текущие prompts не содержат self-referencing dataclasses. Защита — YAGNI. | Accept. Добавить при первом `RecursionError` в продакшене. | Low |
| 13 | `core/domain/documents.py` | `original_path` smuggled through pipeline without contract | No first-class field for source URI propagation | Added `source_uri` to `ChunkMetadata` (CORE CHANGE) | Low |
| 14 | `src/ai_assistant/api/deps.py` (`RAGState.status: dict[str, object]`) | No `Any`/`object` where concrete type is visible (AI Rules Section 9, TYPES). | `RAGState` stores background reindex task status as heterogenous dict to avoid CORE CHANGE in current scope. Values are timestamps (float), strings, and nested dicts. | Introduce `ReindexStatusEntry` dataclass in `core/domain/` and type `RAGState.status` as `dict[str, ReindexStatusEntry]`. Requires updating `handlers.py`, `test_rag.py`, `test_contracts.py`. | Low |
| 15 | `src/ai_assistant/core/pipeline.py` (`_required_fields_for_steps`) | Upfront validation should cover all inputs; `query_embedding` is produced by previous step, not input. | `retrieve` requires `query_embedding`, but it is produced by `embed_query`/`hyde_query`. Upfront validation fails valid pipelines. Removing it loses early error for `[retrieve]` without embedding step. | Introduce step dependency graph in `_required_fields_for_steps` to distinguish inputs from produced fields. Or split `retrieve` into `retrieve` (requires embedding) and `retrieve_raw` (requires pre-computed). | Low |


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
| **GraphRAG** | research | Needs graph DB, entity extraction logic | adapters/graph_store_*.py, core/ports/graph.py (CORE CHANGE) |
| **Computer Use** | research | OS permissions, safety sandbox for actions | adapters/computer_use_*.py, core/ports/tools.py |
| **LLM-as-a-Judge** | planned | Needs secondary local model, eval datasets | features/eval/judge.py, adapters/llm_judge_*.py |
| **Continuous Local Learning** | research | Needs LoRA training loop, VRAM management | scripts/fine_tune.py, adapters/llm_lora_*.py |
| **PII Redaction & Encryption** | planned | Needs local NER model, crypto library | adapters/pii_redactor.py, core/io_utils.py (AES) |
| **OpenTelemetry Tracing** | planned | Needs opentelemetry-api/sdk dependencies | core/tracing.py, api/middleware.py |
| **Desktop UX / Wake-word** | research | Needs native bindings, audio stream access | adapters/wake_word_*.py, desktop/ (new top-level dir) |

Rule: If feature needs core/ change, discuss first. If solvable in adapters/, do it.

```

---

## 🗂️ Structure
```
    .gitignore
    README.md
    config.yaml
    pyproject.toml
docs/
    ai_rules.md
    drift.md
    error_taxonomy.md
    future.md
    readme_dev.md
    todo.md
    todo_done.md
scripts/
    check_all.py
    check_llm.py
    check_rag.py
    clean_cache.py
    context_build.py
    download_tokenizers.py
    error_taxonomy_build.py
    index_documents.py
    kill.py
    open_shell.py
    structure.py
src/
    ai_assistant/
        __init__.py
        main.py
        adapters/
            __init__.py
            _registry.py
            chunker_simple.py
            embedder_mock.py
            embedder_openai_compatible.py
            factory.py
            llm_mock.py
            llm_openai_compatible.py
            reranker_api.py
            reranker_null.py
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
            query_parser.py
            retry.py
            utils.py
            domain/
                __init__.py
                configs.py
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
    conftest.py
    test_adapters.py
    test_api.py
    test_chat.py
    test_config.py
    test_contracts.py
    test_domain.py
    test_e2e.py
    test_integration.py
    test_logger.py
    test_metrics.py
    test_pipeline.py
    test_prompts.py
    test_properties.py
    test_rag.py
    test_resilience.py
    test_retry.py
    test_smoke.py
    test_stateful_ports.py
    test_static.py
    test_tokenizer.py
```

---

## 🔗 Dependencies

- `scripts/check_llm.py`
  - → `ai_assistant.core.config: load_config`
- `scripts/check_rag.py`
  - → `ai_assistant.adapters.factory: create_adapter`
  - → `ai_assistant.core.config: load_config`
  - → `ai_assistant.core.constants: RAG_NS_MAP`
  - → `ai_assistant.core.domain.configs: EmbedderConfigData`
  - → `ai_assistant.core.domain.messages: UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline_steps: embed_query, retrieve, build_context, rerank`
  - → `ai_assistant.core.query_parser: parse_rag_query`
- `scripts/index_documents.py`
  - → `ai_assistant.api.deps: init_adapters`
  - → `ai_assistant.core.config: load_config`
  - → `ai_assistant.features.rag.indexing: index_folder`
- `src/ai_assistant/adapters/__init__.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.adapters.factory: create_adapter`
- `src/ai_assistant/adapters/chunker_simple.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: ChunkerConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata, Document`
  - → `ai_assistant.core.ports.chunker: IChunker`
- `src/ai_assistant/adapters/embedder_mock.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: EmbedderConfigData`
  - → `ai_assistant.core.ports.embedder: IEmbedder`
- `src/ai_assistant/adapters/embedder_openai_compatible.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: EmbedderConfigData`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.ports.embedder: IEmbedder`
  - → `ai_assistant.core.retry: with_retry`
  - → `ai_assistant.core.utils: resolve_api_key`
- `src/ai_assistant/adapters/factory.py`
  - → `ai_assistant.adapters._registry: get_registry, register`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.embedder_openai_compatible: OpenAICompatibleEmbedder`
  - → `ai_assistant.adapters.llm_mock: MockLLM`
  - → `ai_assistant.adapters.llm_openai_compatible: OpenAICompatibleLLM`
  - → `ai_assistant.adapters.reranker_api: APIReranker`
  - → `ai_assistant.adapters.reranker_null: NullReranker`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
- `src/ai_assistant/adapters/llm_mock.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: LLMConfigData`
  - → `ai_assistant.core.domain.messages: AssistantMessage`
  - → `ai_assistant.core.ports.llm: ILLM, Message`
- `src/ai_assistant/adapters/llm_openai_compatible.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: LLMConfigData`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.domain.messages: AssistantMessage, ToolMessage, UserMessage`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.ports.closable: IClosable`
  - → `ai_assistant.core.ports.llm: ILLM, Message`
  - → `ai_assistant.core.retry: with_retry`
  - → `ai_assistant.core.utils: resolve_api_key`
- `src/ai_assistant/adapters/reranker_api.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: RerankerConfigData`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.ports.reranker: IReranker, RerankResult`
  - → `ai_assistant.core.retry: with_retry`
  - → `ai_assistant.core.utils: resolve_api_key`
- `src/ai_assistant/adapters/reranker_null.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: RerankerConfigData`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.ports.reranker: IReranker, RerankResult`
- `src/ai_assistant/adapters/storage_sqlite.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: StorageConfigData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.ports.storage: IChatStorage, ISettingsStorage`
- `src/ai_assistant/adapters/vector_store_faiss.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: VectorStoreConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.errors: AdapterError, VersionMismatchError`
  - → `ai_assistant.core.io_utils: atomic_write`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.ports.vector_store: IVectorStore`
- `src/ai_assistant/adapters/vector_store_memory.py`
  - → `ai_assistant.adapters._registry: register`
  - → `ai_assistant.core.domain.configs: VectorStoreConfigData`
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
  - → `ai_assistant.core.domain.configs: ChunkerConfigData, EmbedderConfigData, LLMConfigData, RerankerConfigData, StorageConfigData, VectorStoreConfigData`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.pipeline_steps: STEP_REGISTRY`
  - → `ai_assistant.core.ports: ILLM, IChatStorage, IChunker, IEmbedder, IReranker, IVectorStore`
  - → `ai_assistant.features.chat.manager: ChatManager`
- `src/ai_assistant/api/lifespan.py`
  - → `ai_assistant.api.deps: init_adapters`
  - → `ai_assistant.api.security: get_expected_api_key, set_api_key`
  - → `ai_assistant.api.static: mount_static`
  - → `ai_assistant.core.config: AppConfig, load_config`
  - → `ai_assistant.core.logger: get_logger, setup_logging`
- `src/ai_assistant/api/middleware.py`
  - → `ai_assistant.core: metrics`
- `src/ai_assistant/api/router.py`
  - → `ai_assistant.api.security: require_api_key`
  - → `ai_assistant.api: admin`
  - → `ai_assistant.core.metrics: get_metrics, get_metrics_json`
  - → `ai_assistant.features.chat: handlers`
  - → `ai_assistant.features.rag: handlers`
- `src/ai_assistant/api/security.py`
  - → `ai_assistant.core.logger: get_logger`
- `src/ai_assistant/core/pipeline.py`
  - → `ai_assistant.core.domain.errors: ConfigurationError`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.pipeline_steps: STEP_REGISTRY`
- `src/ai_assistant/core/pipeline_steps.py`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.domain.errors: EMBEDDER_NOT_PROVIDED, INTERNAL_SERVER_ERROR, LLM_NOT_PROVIDED, LLM_UNAVAILABLE, QUERY_EMBEDDING_MISSING, QUERY_MISSING, QUERY_TEXT_MISSING, VECTOR_STORE_NOT_PROVIDED, AdapterError`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineConfig`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.metrics: increment_counter`
  - → `ai_assistant.core.ports.embedder: IEmbedder`
  - → `ai_assistant.core.ports.llm: ILLM, Message`
  - → `ai_assistant.core.ports.vector_store: IVectorStore`
  - → `ai_assistant.core.prompts: get_prompt`
  - → `ai_assistant.core.retry: with_retry`
  - → `ai_assistant.core.utils: async_count_tokens`
- `src/ai_assistant/core/ports/chunker.py`
  - → `ai_assistant.core.domain.configs: ChunkerConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, Document`
- `src/ai_assistant/core/ports/embedder.py`
  - → `ai_assistant.core.domain.configs: EmbedderConfigData`
  - → `ai_assistant.core.ports.closable: IClosable`
- `src/ai_assistant/core/ports/llm.py`
  - → `ai_assistant.core.domain.configs: LLMConfigData`
  - → `ai_assistant.core.domain.messages: AssistantMessage, ToolMessage, UserMessage`
  - → `ai_assistant.core.ports.closable: IClosable`
- `src/ai_assistant/core/ports/reranker.py`
  - → `ai_assistant.core.domain.configs: RerankerConfigData`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.ports.closable: IClosable`
- `src/ai_assistant/core/ports/storage.py`
  - → `ai_assistant.core.domain.configs: StorageConfigData`
  - → `ai_assistant.core.ports.initializable: IInitializable`
- `src/ai_assistant/core/ports/vector_store.py`
  - → `ai_assistant.core.domain.configs: VectorStoreConfigData`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.ports.closable: IClosable`
- `src/ai_assistant/core/query_parser.py`
  - → `ai_assistant.core.constants: RAG_NS_MAP, RAG_PREFIX_RE`
- `src/ai_assistant/features/chat/handlers.py`
  - → `ai_assistant.api.deps: InitializedAppState, get_state`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.features.chat.schemas: ChatRequest, ChatResponse, OAIChatCompletion, OAIChatCompletionRequest, OAIChatMessage, OAIChoice, OAIDeltaChunk, OAIModel, OAIModelList`
- `src/ai_assistant/features/chat/manager.py`
  - → `ai_assistant.core.constants: FROZEN_NO_INFO_PHRASES`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineConfig`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.ports.llm: Message`
  - → `ai_assistant.core.ports: ILLM, IChatStorage, IEmbedder, IReranker, IVectorStore`
  - → `ai_assistant.core.prompts: get_prompt`
  - → `ai_assistant.core.query_parser: parse_rag_query`
  - → `ai_assistant.core.utils: count_tokens`
- `src/ai_assistant/features/rag/handlers.py`
  - → `ai_assistant.adapters.factory: create_adapter`
  - → `ai_assistant.api.deps: InitializedAppState, get_state`
  - → `ai_assistant.core.domain.errors: LLM_UNAVAILABLE`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.query_parser: parse_rag_query`
  - → `ai_assistant.features.rag.indexing: index_folder`
  - → `ai_assistant.features.rag.manager: IndexingManager, RAGManager`
  - → `ai_assistant.features.rag.schemas: DeleteRequest, DeleteResponse, HealthResponse, IndexRequest, IndexResponse, NamespaceListResponse, QueryRequest, QueryResponse, ReindexRequest, SaveChatRequest`
- `src/ai_assistant/features/rag/indexing.py`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.features.rag.manager: IndexingManager`
- `src/ai_assistant/features/rag/manager.py`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata, Document`
  - → `ai_assistant.core.domain.messages: UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineConfig`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.ports: ILLM, IEmbedder, IReranker, IVectorStore`
- `src/ai_assistant/main.py`
  - → `ai_assistant.api.deps: InitializedAppState, get_state`
  - → `ai_assistant.api.lifespan: lifespan`
  - → `ai_assistant.api.middleware: MetricsMiddleware`
  - → `ai_assistant.api.router: assemble_routers`
  - → `ai_assistant.core.config: CORSConfig, load_config`
- `tests/conftest.py`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.embedder_openai_compatible: OpenAICompatibleEmbedder`
  - → `ai_assistant.adapters.llm_mock: MockLLM`
  - → `ai_assistant.adapters.llm_openai_compatible: OpenAICompatibleLLM`
  - → `ai_assistant.adapters.reranker_api: APIReranker`
  - → `ai_assistant.adapters.reranker_null: NullReranker`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.api.deps: InitializedAppState, RAGState`
  - → `ai_assistant.core.config: AppConfig`
  - → `ai_assistant.core.domain.configs: ChunkerConfigData`
  - → `ai_assistant.core.domain.configs: EmbedderConfigData`
  - → `ai_assistant.core.domain.configs: LLMConfigData`
  - → `ai_assistant.core.domain.configs: RerankerConfigData`
  - → `ai_assistant.core.domain.configs: StorageConfigData`
  - → `ai_assistant.core.domain.configs: VectorStoreConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.ports.reranker: RerankResult`
  - → `ai_assistant.core: prompts`
- `tests/test_adapters.py`
  - → `ai_assistant.adapters._registry: get_registry`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.factory: create_adapter`
  - → `ai_assistant.adapters.llm_mock: MockLLM`
  - → `ai_assistant.adapters.llm_openai_compatible: OpenAICompatibleLLM`
  - → `ai_assistant.adapters.reranker_null: NullReranker`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.core.domain.configs: ChunkerConfigData, EmbedderConfigData, LLMConfigData, RerankerConfigData, StorageConfigData, VectorStoreConfigData`
  - → `ai_assistant.core.domain.configs: VectorStoreConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata, Document`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.domain.errors: VersionMismatchError`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.messages: ToolMessage`
  - → `ai_assistant.core.ports.initializable: IInitializable`
  - → `ai_assistant.core.ports.reranker: RerankResult`
  - → `ai_assistant.core.ports.storage: IChatStorage`
- `tests/test_api.py`
  - → `ai_assistant`
  - → `ai_assistant.adapters.reranker_null: NullReranker`
  - → `ai_assistant.api.admin: _UpdateApiKeyRequest, _UpdateApiKeyResponse, update_api_key`
  - → `ai_assistant.api.deps: AppState, InitializedAppState, _STEP_MAP, _build_step_funcs, get_state, init_adapters`
  - → `ai_assistant.api.deps: RAGState`
  - → `ai_assistant.api.lifespan: _async_cleanup, _load_config, lifespan`
  - → `ai_assistant.api.middleware: MetricsMiddleware`
  - → `ai_assistant.api.router: _ROOT_TAGS`
  - → `ai_assistant.api.router: _ROUTERS, assemble_routers`
  - → `ai_assistant.api.security: SECURITY_MAX_BODY, bearer_scheme, check_request_size, get_expected_api_key, require_api_key, set_api_key`
  - → `ai_assistant.api.security: set_api_key`
  - → `ai_assistant.api: admin`
  - → `ai_assistant.core.config: AppConfig, RAGStep, load_config`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.pipeline_steps: STEP_REGISTRY`
  - → `ai_assistant.core: metrics`
  - → `ai_assistant.main: create_app`
- `tests/test_chat.py`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.reranker_null: NullReranker`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.core.config: NamespaceConfig`
  - → `ai_assistant.core.domain.configs: EmbedderConfigData, RerankerConfigData, VectorStoreConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.pipeline_steps: build_context, embed_query, retrieve`
  - → `ai_assistant.features.chat.manager: ChatManager`
- `tests/test_config.py`
  - → `ai_assistant.core.config: AppConfig, ChatConfig, ChunkerConfig, CORSConfig, LLMConfig, NamespaceConfig, RAGConfig, RAGStep, SecurityConfig, UIConfig, VectorStoreConfig, load_config`
- `tests/test_contracts.py`
  - → `ai_assistant.adapters._registry: get_registry`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.embedder_openai_compatible: OpenAICompatibleEmbedder`
  - → `ai_assistant.adapters.llm_mock: MockLLM`
  - → `ai_assistant.adapters.llm_openai_compatible: OpenAICompatibleLLM`
  - → `ai_assistant.adapters.reranker_api: APIReranker`
  - → `ai_assistant.adapters.reranker_null: NullReranker`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.api: deps`
  - → `ai_assistant.api: lifespan`
  - → `ai_assistant.core.domain.messages: AssistantMessage, ToolMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.ports.chunker: IChunker`
  - → `ai_assistant.core.ports.closable: IClosable`
  - → `ai_assistant.core.ports.embedder: IEmbedder`
  - → `ai_assistant.core.ports.initializable: IInitializable`
  - → `ai_assistant.core.ports.llm: ILLM`
  - → `ai_assistant.core.ports.llm: Message`
  - → `ai_assistant.core.ports.reranker: IReranker`
  - → `ai_assistant.core.ports.storage: IChatStorage`
  - → `ai_assistant.core.ports.vector_store: IVectorStore`
  - → `ai_assistant.core.ports: IChatStorage, IChunker, IClosable, IEmbedder, ILLM, IReranker, IVectorStore`
  - → `ai_assistant.core.ports: IChatStorage, IChunker, IEmbedder, ILLM, IReranker, IVectorStore`
- `tests/test_domain.py`
  - → `ai_assistant.core.constants: FROZEN_NO_INFO_PHRASES`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.messages: AssistantMessage, ToolMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.ports.tools: ToolResult`
  - → `ai_assistant.core: prompts`
- `tests/test_e2e.py`
  - → `ai_assistant.adapters.reranker_null: NullReranker`
  - → `ai_assistant.api.deps: RAGState`
  - → `ai_assistant.api.security: set_api_key`
  - → `ai_assistant.core.config: NamespaceConfig`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.messages: AssistantMessage`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.features.chat.manager: ChatManager`
  - → `ai_assistant.main: create_app`
- `tests/test_integration.py`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.embedder_openai_compatible: OpenAICompatibleEmbedder`
  - → `ai_assistant.adapters.llm_mock: MockLLM`
  - → `ai_assistant.adapters.llm_openai_compatible: OpenAICompatibleLLM`
  - → `ai_assistant.adapters.reranker_api: APIReranker`
  - → `ai_assistant.adapters.reranker_null: NullReranker`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.api.deps: InitializedAppState, init_adapters`
  - → `ai_assistant.core.config: AppConfig, EmbedderConfig, LLMConfig`
  - → `ai_assistant.core.domain.configs: ChunkerConfigData, EmbedderConfigData, LLMConfigData, RerankerConfigData, StorageConfigData, VectorStoreConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata, Document`
  - → `ai_assistant.core.domain.documents: ChunkMetadata`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineConfig`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.pipeline_steps: build_context, embed_query, generate, hyde_query, rerank, retrieve`
- `tests/test_logger.py`
  - → `ai_assistant.core.logger: _JsonFormatter, _TextFormatter, _VALID_LEVELS, get_logger, setup_logging`
- `tests/test_metrics.py`
  - → `ai_assistant.core.metrics: _DEFAULT_BUCKETS, _key_str, _labels_key, _metric_line, get_metrics, get_metrics_json, increment_counter, observe_histogram`
- `tests/test_pipeline.py`
  - → `ai_assistant.core.domain.documents: Chunk`
  - → `ai_assistant.core.domain.errors: AdapterError, LLM_UNAVAILABLE`
  - → `ai_assistant.core.domain.errors: EMBEDDER_NOT_PROVIDED, INTERNAL_SERVER_ERROR, LLM_NOT_PROVIDED, QUERY_EMBEDDING_MISSING, QUERY_MISSING, QUERY_TEXT_MISSING, VECTOR_STORE_NOT_PROVIDED`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineConfig, PipelineData`
  - → `ai_assistant.core.pipeline_steps: build_context, embed_query, generate, hyde_query, rerank, retrieve`
  - → `ai_assistant.core.ports.reranker: RerankResult`
  - → `ai_assistant.core.retry: with_retry`
- `tests/test_prompts.py`
  - → `ai_assistant.core.prompts: _env_cache, _make_hashable, _render, get_prompt`
  - → `ai_assistant.core.prompts: _kwargs_to_tuple`
- `tests/test_properties.py`
  - → `ai_assistant.adapters.chunker_simple: SimpleChunker`
  - → `ai_assistant.adapters.embedder_mock: MockEmbedder`
  - → `ai_assistant.adapters.llm_mock: MockLLM`
  - → `ai_assistant.adapters.reranker_null: NullReranker`
  - → `ai_assistant.core.domain.configs: ChunkerConfigData`
  - → `ai_assistant.core.domain.configs: EmbedderConfigData`
  - → `ai_assistant.core.domain.configs: LLMConfigData`
  - → `ai_assistant.core.domain.configs: RerankerConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata, Document`
  - → `ai_assistant.core.domain.messages: AssistantMessage, UserMessage`
  - → `ai_assistant.core.ports.chunker: IChunker`
  - → `ai_assistant.core.ports.embedder: IEmbedder`
  - → `ai_assistant.core.ports.llm: ILLM`
  - → `ai_assistant.core.ports.reranker: IReranker`
- `tests/test_rag.py`
  - → `ai_assistant.adapters.vector_store_faiss: FaissVectorStore`
  - → `ai_assistant.api.deps: RAGState`
  - → `ai_assistant.core.domain.configs: VectorStoreConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.domain.errors: INTERNAL_SERVER_ERROR`
  - → `ai_assistant.core.domain.errors: LLM_UNAVAILABLE`
  - → `ai_assistant.core.domain.messages: UserMessage`
  - → `ai_assistant.core.domain.pipeline: PipelineData`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.pipeline: RAGPipeline`
  - → `ai_assistant.core.pipeline_steps: rerank`
  - → `ai_assistant.features.chat.manager: ChatManager`
  - → `ai_assistant.features.rag.handlers: router`
  - → `ai_assistant.features.rag.indexing: index_folder`
  - → `ai_assistant.features.rag.manager: IndexingManager, RAGManager`
  - → `ai_assistant.features.rag.manager: RAGManager`
- `tests/test_resilience.py`
  - → `ai_assistant.adapters.embedder_openai_compatible: OpenAICompatibleEmbedder`
  - → `ai_assistant.adapters.llm_openai_compatible: OpenAICompatibleLLM`
  - → `ai_assistant.core.domain.configs: EmbedderConfigData, LLMConfigData`
  - → `ai_assistant.core.domain.errors: AdapterError`
  - → `ai_assistant.core.domain.messages: UserMessage`
- `tests/test_retry.py`
  - → `ai_assistant.core.retry: with_retry, _PERMANENT_ERRORS`
- `tests/test_smoke.py`
  - → `ai_assistant`
  - → `ai_assistant.adapters.factory: __all__`
  - → `ai_assistant.api.router: _ROUTERS, assemble_routers`
  - → `ai_assistant.api.security: get_expected_api_key`
  - → `ai_assistant.api.static: mount_static`
  - → `ai_assistant.api: deps`
  - → `ai_assistant.api: lifespan`
  - → `ai_assistant.core.config: load_config, AppConfig`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.logger: setup_logging`
  - → `ai_assistant.core.ports.tools: ITool, ToolSpec, ToolResult`
- `tests/test_stateful_ports.py`
  - → `ai_assistant.adapters.storage_sqlite: SQLiteStorage`
  - → `ai_assistant.adapters.vector_store_memory: MemoryVectorStore`
  - → `ai_assistant.core.domain.configs: VectorStoreConfigData, StorageConfigData`
  - → `ai_assistant.core.domain.documents: Chunk, ChunkMetadata`
  - → `ai_assistant.core.ports.storage: IChatStorage`
  - → `ai_assistant.core.ports.vector_store: IVectorStore`
- `tests/test_static.py`
  - → `ai_assistant.api.static: mount_static`
- `tests/test_tokenizer.py`
  - → `ai_assistant.core.utils: _CJK_RATIO_THRESHOLD`
  - → `ai_assistant.core.utils: _resolve_tokenizer_dir, async_count_tokens, async_get_tokenizer, count_tokens, get_tokenizer`

---

## 📦 Files

### Listed Only (no content)
- `.gitignore`
- `README.md`
- `config.yaml`
- `pyproject.toml`
- `scripts/check_all.py`
- `scripts/check_llm.py`
- `scripts/check_rag.py`
- `scripts/clean_cache.py`
- `scripts/context_build.py`
- `scripts/download_tokenizers.py`
- `scripts/error_taxonomy_build.py`
- `scripts/index_documents.py`
- `scripts/kill.py`
- `scripts/open_shell.py`
- `scripts/structure.py`
- `src/ai_assistant/__init__.py`
- `src/ai_assistant/adapters/__init__.py`
- `src/ai_assistant/adapters/_registry.py`
- `src/ai_assistant/adapters/chunker_simple.py`
- `src/ai_assistant/adapters/embedder_mock.py`
- `src/ai_assistant/adapters/embedder_openai_compatible.py`
- `src/ai_assistant/adapters/factory.py`
- `src/ai_assistant/adapters/llm_mock.py`
- `src/ai_assistant/adapters/llm_openai_compatible.py`
- `src/ai_assistant/adapters/reranker_api.py`
- `src/ai_assistant/adapters/reranker_null.py`
- `src/ai_assistant/adapters/storage_sqlite.py`
- `src/ai_assistant/adapters/vector_store_faiss.py`
- `src/ai_assistant/adapters/vector_store_memory.py`
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
- `src/ai_assistant/core/domain/configs.py`
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
- `src/ai_assistant/core/query_parser.py`
- `src/ai_assistant/core/retry.py`
- `src/ai_assistant/core/utils.py`
- `src/ai_assistant/features/__init__.py`
- `src/ai_assistant/features/chat/__init__.py`
- `src/ai_assistant/features/chat/handlers.py`
- `src/ai_assistant/features/chat/manager.py`
- `src/ai_assistant/features/chat/schemas.py`
- `src/ai_assistant/features/rag/__init__.py`
- `src/ai_assistant/features/rag/handlers.py`
- `src/ai_assistant/features/rag/indexing.py`
- `src/ai_assistant/features/rag/manager.py`
- `src/ai_assistant/features/rag/schemas.py`
- `src/ai_assistant/main.py`
- `tests/conftest.py`
- `tests/test_adapters.py`
- `tests/test_api.py`
- `tests/test_chat.py`
- `tests/test_config.py`
- `tests/test_contracts.py`
- `tests/test_domain.py`
- `tests/test_e2e.py`
- `tests/test_integration.py`
- `tests/test_logger.py`
- `tests/test_metrics.py`
- `tests/test_pipeline.py`
- `tests/test_prompts.py`
- `tests/test_properties.py`
- `tests/test_rag.py`
- `tests/test_resilience.py`
- `tests/test_retry.py`
- `tests/test_smoke.py`
- `tests/test_stateful_ports.py`
- `tests/test_static.py`
- `tests/test_tokenizer.py`

---
