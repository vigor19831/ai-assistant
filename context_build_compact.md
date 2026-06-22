# AI Context
> **Generated:** 2026-06-22 11:41:18 UTC | **Mode:** `compact`
> **Metrics:** 113 files | 95 Python | 19,702 LOC
> **Full:** 48 | **Signatures:** 23 | **Listed:** 36

---

## 📋 Project Overview
```markdown
# AI Assistant

Chat with local LLMs using any OpenAI-compatible server. Fully offline. RAG with document namespaces.

## Quick Start

### 1. Install

```bash
pip install -e ".[faiss]"
```

### 2. Start LLM Server

**Option A — llama.cpp:**
```bash
llama-server -m model.gguf --port 8080
```

**Option B — Ollama:**
```bash
ollama serve
```

**Option C — vLLM:**
```bash
python -m vllm.entrypoints.openai.api_server --model your-model-name
```

### 3. Configure

Edit `config.yaml` to match your setup:

```
llm:
  api_base: http://127.0.0.1:8080/v1
  model: your-model-name

embedder:
  api_base: http://127.0.0.1:8081/v1
  model: your-embedder-model
  dim: 768

vector_store:
  dim: 768  # Must match embedder.dim
```

### 4. Run

```bash
python run_servers.py
python run_scripts.py
```

The API is available at `http://localhost:8000`.

### 5. Connect Client

Use any OpenAI-compatible client:

- **Page Assist** (browser extension) — recommended
- **Continue.dev** (VS Code)
- **OpenCode** (IDE)

Or call directly:
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "your-model", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Document Search (RAG)

### Index Documents

```bash
python scripts/index_documents.py
```

Or via API:
```bash
curl -X POST http://localhost:8000/api/v1/rag/index \
  -H "Authorization: Bearer sk-local-api-key" \
  -H "Content-Type: application/json" \
  -d '{"documents": [{"id": "doc1", "content": "..."}], "namespace": "work"}'
```

### Query with Namespaces

In chat, use prefixes to search specific document collections:

| Prefix | Namespace | Example |
|--------|-----------|---------|
| `[p]` | personal | `[p] What did I write about...` |
| `[w]` | work | `[w] Q3 revenue numbers` |
| `[c]` | code | `[c] How does auth work` |
| `[b]` | books | `[b] Summary of chapter 3` |
| `[o]` | other | `[o] Recipe for pasta` |

No prefix = search default namespace.

## Requirements

- Python 3
```

---

## 🚨 AI Development Guidelines
> Auto-extracted from: `ai_rules.md`
```markdown
# AI Rules
> Version: 2026-06-20
> Next review: 2026-09-20

## 0. Ground Truth

Only this document and `docs/context_build_*.md`. No previous conversations, no general best practices, no hallucinated APIs or config keys.

Hierarchy: code in `src/` > this file > README.

When code and rules conflict, code wins. If code violates a rule, that is known drift (see `docs/drift.md`). Propose fixing it, do not hallucinate stricter architecture.

## 0.1. Human-AI Division of Labor

AI may suggest improvements only when:
- They reduce code volume (fewer files, fewer lines)
- They fix a bug or security issue
- They are explicitly requested by user

AI must not suggest:
- New features, adapters, or dependencies
- Architectural changes
- "Best practices" that add complexity

## 1. Identity

You are an implementation assistant for a solo-maintained Python AI framework expected to survive decades.

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

## 2.1. Simplicity Constraints

- No new file for code <30 lines that fits in existing file
- No new class where a function suffices
- No new adapter until 2+ existing adapters have active users
- No configuration option for value used in only 1 place
- If a feature can be implemented in 1 file, it must be 1 file
- Prefer `if/else` over polymorphism when branches <3
- Prefer plain functions over classes when no state needed

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
- SIMPLICITY: No new files/classes/functions beyond what was explicitly requested

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

Do NOT use `request: Any` -- breaks FastAPI DI with 422.
Do NOT move `Request` under `TYPE_CHECKING` -- same result.

## 12. Rule Self-Check

Before outputting code, verify:
- [ ] All changed files listed in Output Protocol
- [ ] No rule from Section 2 (Absolute Constraints) violated
- [ ] No rule from Section 2.1 (Simplicity Constraints) violated
- [ ] If >3 files changed, split proposed or get confirmation
- [ ] Tests updated for new functionality
- [ ] No new features proposed without explicit user request

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
> Auto-generated from source code. Updated: 2026-06-22 11:41 UTC
> **Rule:** Check this table before adding try/except or changing error handling.
> **Note:** This is heuristic output — verify against source before acting.

## AI Usage Notes
> For AI assistants: apply these filters when using this table for analysis.

- **Skip `tests/` entries** for production analysis unless explicitly asked about test coverage.
- **Merge pairs**: `logger.exception("...")` + `raise AdapterError("...")` in same block = single error flow, count once.
- **Line numbers are approximate** ±10 lines due to code drift; always verify against current source.
- **Severity is heuristic** — trust `Critical`, verify `High`, question `Medium/Low` in context:
  - `Critical` = startup aborts (SystemExit, KeyboardInterrupt) — always real
  - `High` = request fails (ValueError, HTTPException, AdapterError) — usually real
  - `Medium` = degraded (OSError, JSONDecodeError) — check if recoverable
  - `Low` = client error / test artifact — often skip
- **When in doubt**: prefer reading source over trusting this table.

| Component | Exception | Trigger | Severity |
|-----------|-----------|---------|----------|
| `core.retry` | `SystemExit/KeyboardInterrupt` | raise | Critical |
| `tests.test_retry` | `KeyboardInterrupt` | Raised KeyboardInterrupt | Critical |
| `adapters.chunker_simple` | `ValueError` | chunk_size must be > 0, got {...} | High |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap must be >= 0, got {...} | High |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap ({...}) must be < chunk_size ({...}) | High |
| `adapters.embedder_openai_compatible` | `AdapterError` | Unexpected response shape from {...}: {...} | High |
| `adapters.embedder_openai_compatible` | `AdapterError` | Dimension mismatch: expected {...}, got {...} for text[{...}... | High |
| `adapters.factory` | `ValueError` | faiss-cpu is not installed but vector_store.provider='faiss' | High |
| `adapters.factory` | `ValueError` | sqlite3 not available but storage.provider='sqlite' | High |
| `adapters.factory` | `ValueError` | Unknown adapter port '{...}' | High |
| `adapters.factory` | `ValueError` | No {...} adapter registered for '{...}' | High |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS search: expected {...}, got {...... | High |
| `adapters.vector_store_faiss` | `AdapterError` | Index metadata missing for namespace '{...}': {...} not foun... | High |
| `adapters.vector_store_faiss` | `AdapterError` | Index file missing for namespace '{...}': {...} not found. P... | High |
| `adapters.vector_store_faiss` | `AdapterError` | Invalid store.json for namespace '{...}': {...} | High |
| `adapters.vector_store_faiss` | `AdapterError` | Index integrity check failed for namespace '{...}': FAISS ha... | High |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored metric '{...}' != config metric '{.... | High |
| `adapters.vector_store_memory` | `AdapterError` | Index load failed for namespace '{...}': chunk '{...}' has e... | High |
| `adapters.vector_store_memory` | `AdapterError` | Index integrity check failed for namespace '{...}': embeddin... | High |
| `adapters.vector_store_memory` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High |
| `api.admin` | `HTTPException` | Unknown error | High |
| `api.deps` | `RuntimeError` | LLM adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Embedder adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Vector store adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Pipeline failed to initialize | High |
| `api.deps` | `RuntimeError` | Storage adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Chunker adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Chat manager failed to initialize | High |
| `api.deps` | `RuntimeError` | State not initialized | High |
| `api.deps` | `ValueError` | Unknown step: {...} | High |
| `api.security` | `HTTPException` | Unknown error | High |
| `core.config` | `ValueError` | path must be non-empty | High |
| `core.config` | `ValueError` | path must be relative, got: {...} | High |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High |
| `core.config` | `ValueError` | Invalid YAML in {...}: {...} | High |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High |
| `core.logger` | `ValueError` | Invalid log format {...}. Use 'text' or 'json'. | High |
| `core.pipeline` | `ConfigurationError` | Missing required PipelineData fields: {...} | High |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High |
| `core.prompts.__init__` | `ValueError` | prompt version is required | High |
| `core.retry` | `RuntimeError` | last_exception is None after retry loop | High |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High |
| `features.chat.handlers` | `HTTPException` | Unknown error | High |
| `features.chat.manager` | `AdapterError` | LLM call failed: {...} | High |
| `features.chat.manager` | `AdapterError` | LLM stream failed: {...} | High |
| `features.rag.handlers` | `HTTPException` | Unknown error | High |
| `tests.test_api` | `HTTPException` | Unknown error | High |
| `tests.test_api` | `RuntimeError` | boom | High |
| `tests.test_api` | `ValueError` | No storage adapter registered | High |
| `tests.test_e2e` | `ValueError` | Error with "quotes" and 
 newlines | High |
| `tests.test_pipeline` | `AdapterError` | LLM down | High |
| `tests.test_pipeline` | `RuntimeError` | transient | High |
| `tests.test_pipeline` | `RuntimeError` | fail | High |
| `tests.test_pipeline` | `RuntimeError` | attempt {...} | High |
| `tests.test_pipeline` | `ValueError` | permanent | High |
| `tests.test_properties` | `ValueError` | Unknown embedder: {...} | High |
| `tests.test_properties` | `ValueError` | Unknown llm: {...} | High |
| `tests.test_properties` | `ValueError` | Unknown reranker: {...} | High |
| `tests.test_properties` | `ValueError` | Unknown chunker: {...} | High |
| `tests.test_rag` | `HTTPException` | Unknown error | High |
| `tests.test_retry` | `exc` | fail #{...} | High |
| `tests.test_stateful_ports` | `RuntimeError` | TMP_DIR not set. Call _set_tmp_dir() first. | High |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | _logger.exception( | Medium |
| `adapters.factory` | `ImportError` | raise ValueError( | Medium |
| `adapters.llm_openai_compatible` | `AttributeError` | _logger.warning( | Medium |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | raise AdapterError(f"Unexpected response shape: {exc}") from | Medium |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | continue | Medium |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | _logger.warning( | Medium |
| `adapters.llm_openai_compatible` | `TypeError` | return [] | Medium |
| `adapters.reranker_api` | `KeyError/TypeError` | _logger.exception( | Medium |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | continue | Medium |
| `adapters.storage_sqlite` | `JSONDecodeError` | _logger.warning("JSON decode failed in storage", extra={"err | Medium |
| `adapters.vector_store_faiss` | `Exception` | with contextlib.suppress(OSError): | Medium |
| `adapters.vector_store_faiss` | `ImportError` | faiss = None  # type: ignore[assignment, no-redef] | Medium |
| `adapters.vector_store_faiss` | `ImportError` | faiss-cpu is not installed but vector_store.provider='faiss' | Medium |
| `adapters.vector_store_faiss` | `JSONDecodeError` | _logger.error( | Medium |
| `adapters.vector_store_faiss` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium |
| `api.deps` | `ValueError/ImportError` | _logger.exception( | Medium |
| `api.lifespan` | `AttributeError` | logger.warning("No app state found during shutdown") | Medium |
| `api.lifespan` | `Exception` | logger.exception("Index load failed on startup") | Medium |
| `api.lifespan` | `Exception` | logger.exception( | Medium |
| `api.lifespan` | `Exception` | logger.exception("Index save failed") | Medium |
| `api.lifespan` | `Exception` | logger.exception("Adapter shutdown failed", extra={"adapter" | Medium |
| `api.lifespan` | `TimeoutError` | logger.warning( | Medium |
| `api.lifespan` | `TimeoutError` | logger.warning("Adapter shutdown timed out", extra={"adapter | Medium |
| `api.security` | `ValueError` | raise HTTPException( | Medium |
| `core.config` | `YAMLError` | raise ValueError(f"Invalid YAML in {config_path}: {exc}") fr | Medium |
| `core.io_utils` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium |
| `core.io_utils` | `TypeError` | Expected str for mode={...}, got {...} | Medium |
| `core.logger` | `OSError` | sys.stderr.write(f"Failed to create log file {path}: {exc}\n | Medium |
| `core.pipeline_steps` | `AdapterError` | _logger.exception("LLM unavailable", extra={"trace_id": data | Medium |
| `core.pipeline_steps` | `Exception` | _logger.exception("embed_query failed", extra={"trace_id": d | Medium |
| `core.pipeline_steps` | `Exception` | _logger.exception("retrieve failed", extra={"trace_id": data | Medium |
| `core.pipeline_steps` | `Exception` | _logger.exception("rerank failed", extra={"trace_id": data.t | Medium |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(current_data.chunks, query_t | Medium |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(data.chunks, query_text) | Medium |
| `core.pipeline_steps` | `Exception` | _logger.exception( | Medium |
| `core.retry` | `Exception` | last_exception = e | Medium |
| `core.retry` | `_PERMANENT_ERRORS` | raise | Medium |
| `core.retry` | `last_exception` | Raised last_exception | Medium |
| `core.utils` | `AttributeError` | return len(enc.encode(text)) | Medium |
| `core.utils` | `Exception` | pass | Medium |
| `core.utils` | `Exception` | if _cjk_ratio(text) > _CJK_RATIO_THRESHOLD: | Medium |
| `core.utils` | `ImportError` | tiktoken = None  # type: ignore[assignment] | Medium |
| `core.utils` | `ImportError` | tokenizers = None  # type: ignore[assignment] | Medium |
| `core.utils` | `KeyError` | try: | Medium |
| `core.utils` | `OSError` | return None | Medium |
| `features.chat.handlers` | `AdapterError` | _logger.warning( | Medium |
| `features.chat.handlers` | `AdapterError` | payload = json.dumps( | Medium |
| `features.chat.handlers` | `Exception` | await queue.put(exc) | Medium |
| `features.chat.handlers` | `Exception` | _logger.exception("Chat failed", extra={"trace_id": trace_id | Medium |
| `features.chat.handlers` | `Exception` | _logger.exception("Stream failed", extra={"trace_id": trace_ | Medium |
| `features.chat.handlers` | `Exception` | payload = json.dumps({"error": "Internal server error"}) | Medium |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI stream failed", extra={"trace_id": | Medium |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI chat failed", extra={"trace_id": t | Medium |
| `features.chat.handlers` | `HTTPException` | raise | Medium |
| `features.chat.handlers` | `TimeoutError` | yield ": ping\n\n" | Medium |
| `features.chat.handlers` | `item` | Raised item | Medium |
| `features.chat.manager` | `AdapterError` | raise | Medium |
| `features.chat.manager` | `Exception` | logger.warning( | Medium |
| `features.chat.manager` | `Exception` | logger.warning("History load failed", extra={"error": str(ex | Medium |
| `features.chat.manager` | `Exception` | duration_ms = int((time.perf_counter() - start) * 1000) | Medium |
| `features.chat.manager` | `Exception` | logger.warning("History save failed", extra={"error": str(ex | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("Auto-save failed") | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("Delete chunks failed") | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("List namespaces failed") | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("Failed to save file") | Medium |
| `features.rag.handlers` | `Exception` | return { | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("Background reindex failed") | Medium |
| `features.rag.manager` | `Exception` | _logger.exception("Health check failed") | Medium |
| `tests.test_api` | `Exception` | errors.append(e) | Medium |
| `tests.test_api` | `ImportError` | sqlite3 not available | Medium |
| `tests.test_chat` | `StopAsyncIteration` | Raised StopAsyncIteration | Medium |
| `tests.test_retry` | `exc_cls` | permanent | Medium |
| `tests.test_smoke` | `Exception` | return req, None, None | Medium |
| `tests.test_stateful_ports` | `RuntimeError` | loop = asyncio.new_event_loop() | Medium |
| `tests.test_adapters` | `OSError` | simulated write failure | Low |
| `tests.test_domain` | `OSError` | no dir fsync | Low |
| `tests.test_logger` | `OSError` | disk full | Low |

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
| 16 | `src/ai_assistant/core/config.py` | Admin endpoints unprotected by default | Any client with api_key could mutate runtime security policy | Added `admin_enabled: bool = False` to `SecurityConfig`; admin endpoints return 404 unless explicitly enabled | Low |

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
    LICENSE
    NOTICE
    README.md
    config.example.yaml
    config.yaml
    pyproject.toml
    run_scripts.py
    run_servers.py
docs/
    ai_rules.md
    drift.md
    error_taxonomy.md
    future.md
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
ui/
    index.html
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
  - → `ai_assistant.core.domain.errors: AdapterError, VersionMismatchError`
  - → `ai_assistant.core.io_utils: atomic_write`
  - → `ai_assistant.core.logger: get_logger`
  - → `ai_assistant.core.ports.vector_store: IVectorStore`
- `src/ai_assistant/api/admin.py`
  - → `ai_assistant.api.deps: AppState, get_state`
  - → `ai_assistant.api.security: require_api_key, set_api_key`
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
  - → `ai_assistant.core.retry: with_retry`
- `src/ai_assistant/api/middleware.py`
  - → `ai_assistant.core: metrics`
- `src/ai_assistant/api/router.py`
  - → `ai_assistant.api.security: require_api_key`
  - → `ai_assistant.api: admin`
  - → `ai_assistant.core.config: SecurityConfig`
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
  - → `ai_assistant.core.utils: async_count_tokens`
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
  - → `ai_assistant.core.config: CORSConfig, SecurityConfig, load_config`
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
  - → `ai_assistant.core.config: AppConfig, RAGStep, SecurityConfig, load_config`
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
  - → `ai_assistant.core.io_utils: atomic_write`
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
  - → `ai_assistant.features.rag.handlers: reindex_documents`
  - → `ai_assistant.features.rag.handlers: router`
  - → `ai_assistant.features.rag.indexing: index_folder`
  - → `ai_assistant.features.rag.manager: IndexingManager, RAGManager`
  - → `ai_assistant.features.rag.manager: RAGManager`
  - → `ai_assistant.features.rag.schemas: ReindexRequest`
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
  - → `ai_assistant.core.utils: resolve_api_key`
  - → `ai_assistant.core: utils`

---

## 📦 Files

### Full Content
- `.gitignore`
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
- `src/ai_assistant/features/chat/handlers.py`
- `src/ai_assistant/features/chat/schemas.py`
- `src/ai_assistant/features/rag/handlers.py`
- `src/ai_assistant/features/rag/schemas.py`

### Signatures Only
- `run_scripts.py`
- `run_servers.py`
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
- `src/ai_assistant/features/__init__.py`
- `src/ai_assistant/features/chat/__init__.py`
- `src/ai_assistant/features/chat/manager.py`
- `src/ai_assistant/features/rag/__init__.py`
- `src/ai_assistant/features/rag/indexing.py`
- `src/ai_assistant/features/rag/manager.py`
- `src/ai_assistant/main.py`

### Listed Only (no content)
- `LICENSE`
- `NOTICE`
- `config.example.yaml`
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
- `ui/index.html`

---

## 🔑 Full Code

### `.gitignore`
```text
# =============================================================================
# PYTHON
# =============================================================================

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
*.dist-info/
pip-wheel-metadata/

# Testing
.coverage
htmlcov/
.pytest_cache/
tests/.pytest_cache/
.test_tmp/
.pytest_tmp/
.hypothesis/

# Type checking / linting
.mypy_cache/
.ruff_cache/

# =============================================================================
# VIRTUAL ENVIRONMENTS
# =============================================================================

venv/
env/
ENV/
.venv

# =============================================================================
# IDE
# =============================================================================

.idea/
.vscode/
*.swp
*.swo
*.sublime-project
*.sublime-workspace
*.sublime-settings
Package Control.last-run
Package Control.cache/

# =============================================================================
# OS
# =============================================================================

.DS_Store
Thumbs.db
*~
.nfs*
.directory
.Trash-*

# =============================================================================
# PROJECT: AI Assistant
# =============================================================================

# Data & indices
data/
*.faiss
*.db
*.db-journal
*.db-shm
*.db-wal
*.store.json

# Secrets & environment
.env
.env.local

# Logs
*.log
/*.log
tests_run_*.log

# Runtime
scripts/*.pid
scripts/*.log
/*.pid

# User content (never commit)
sources/
vendor/

# src-layout build artifacts
src/*.egg-info/
src/**/*.egg-info/

# Generated docs
docs/context_build_*.md

# Test artifacts
MagicMock/

# Local config with secrets (config.example.yaml is tracked)
config.yaml

```

### `README.md`
```text
# AI Assistant

Chat with local LLMs using any OpenAI-compatible server. Fully offline. RAG with document namespaces.

## Quick Start

### 1. Install

```bash
pip install -e ".[faiss]"
```

### 2. Start LLM Server

**Option A — llama.cpp:**
```bash
llama-server -m model.gguf --port 8080
```

**Option B — Ollama:**
```bash
ollama serve
```

**Option C — vLLM:**
```bash
python -m vllm.entrypoints.openai.api_server --model your-model-name
```

### 3. Configure

Edit `config.yaml` to match your setup:

```
llm:
  api_base: http://127.0.0.1:8080/v1
  model: your-model-name

embedder:
  api_base: http://127.0.0.1:8081/v1
  model: your-embedder-model
  dim: 768

vector_store:
  dim: 768  # Must match embedder.dim
```

### 4. Run

```bash
python run_servers.py
python run_scripts.py
```

The API is available at `http://localhost:8000`.

### 5. Connect Client

Use any OpenAI-compatible client:

- **Page Assist** (browser extension) — recommended
- **Continue.dev** (VS Code)
- **OpenCode** (IDE)

Or call directly:
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "your-model", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Document Search (RAG)

### Index Documents

```bash
python scripts/index_documents.py
```

Or via API:
```bash
curl -X POST http://localhost:8000/api/v1/rag/index \
  -H "Authorization: Bearer sk-local-api-key" \
  -H "Content-Type: application/json" \
  -d '{"documents": [{"id": "doc1", "content": "..."}], "namespace": "work"}'
```

### Query with Namespaces

In chat, use prefixes to search specific document collections:

| Prefix | Namespace | Example |
|--------|-----------|---------|
| `[p]` | personal | `[p] What did I write about...` |
| `[w]` | work | `[w] Q3 revenue numbers` |
| `[c]` | code | `[c] How does auth work` |
| `[b]` | books | `[b] Summary of chapter 3` |
| `[o]` | other | `[o] Recipe for pasta` |

No prefix = search default namespace.

## Requirements

- Python 3.13+
- 8+ GB RAM (CPU mode)
- GPU optional

## Development

This project is developed by a solo creator with extensive use of AI-assisted programming tools.

The author defines the product vision, architecture, requirements, testing strategy, and development roadmap, while AI tools are used to accelerate implementation, refactoring, documentation, and experimentation.

All design decisions, feature prioritization, and project direction remain under human supervision.

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for details.

```

### `config.yaml`
```text
# AI Assistant — Universal Configuration
# Works with any OpenAI-compatible API: llama-server, Ollama, vLLM, OpenAI
# Environment variables with AI_ prefix override values below

# ── Application ──
app_name: ai-assistant
debug: true
host: 0.0.0.0
port: 8000
config_version: "1.5.0"

# ── CORS ──
cors:
  allow_origins:
    - "http://localhost"
    - "http://127.0.0.1"
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
  api_key: sk-local-api-key
  model: embeddinggemma-300m-q8_0
  dim: 768
  timeout: 60.0
  connect_timeout: 5.0  # TCP connection timeout (None = use timeout)
  n_gpu_layers: 0        # -1 = all layers on GPU, 0 = CPU only, N = N layers on GPU
  n_batch: 512            # Batch size for processing
  n_ubatch: 64            # Micro-batch size
  mmap: true              # Memory-mapped files (saves RAM)
  mlock: false            # Lock pages in RAM (prevent swap)

# ── LLM ──
llm:
  provider: openai_compatible
  api_base: http://127.0.0.1:8080/v1
  api_key: sk-local-api-key
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
  connect_timeout: 5.0  # TCP connection timeout (None = use timeout)
  server_context_size: 4096
  # === GPU / Performance ===
  n_gpu_layers: 99        # -1 = all layers on GPU, 0 = CPU only
  n_batch: 512            # Batch size
  n_ubatch: 64            # Micro-batch size
  mmap: true              # Memory-mapped files
  mlock: false            # Lock pages in RAM

# ── Vector Store ──
vector_store:
  provider: faiss
  index_path: ./data/indices
  metric: l2
  dim: 768                # MUST equal embedder.dim
  max_chunks: 100000
  max_document_size: 10485760

# ── Storage ──
storage:
  provider: sqlite
  db_path: ./data/storage.db

# ── Reranker ──
reranker:
  provider: null
  model: rerank-multilingual-v3.0
  api_base: https://api.cohere.com
  api_key: sk-local-api-key
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
  token_margin_min: 256
  token_margin_pct: 0.1

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

# ── Security ──
security:
  api_key: sk-local-api-key
  max_body_size: 10485760
  allowed_hosts: ["localhost", "127.0.0.1"]

# ── Logging ──
logging:
  level: "INFO"       # DEBUG, INFO, WARNING, ERROR
  file: "./data/app.log"
  format: "text"      # "text" or "json"
  max_bytes: 10485760 # 10 MB per log file before rotation
  backup_count: 2     # Keep 2 backup files (app.log.1, app.log.2)

# ── UI ──
ui:
  static_path: "../../ui"

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
    "aiosqlite>=0.20.0,<1.0.0",
    "anyio>=4.0.0,<5.0.0",
    "starlette>=0.36.0,<1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0,<9.0.0",
    "pytest-asyncio>=0.23.0,<1.0.0",
    "pytest-timeout>=2.3.0,<3.0.0",
    "respx>=0.21.0,<1.0.0",
    "hypothesis>=6.100.0,<7.0.0",
    "ruff>=0.4.0,<1.0.0",
    "mypy>=1.10.0,<2.0.0",
    "types-PyYAML>=6.0.12,<7.0.0",
    "types-aiofiles>=23.2.0,<24.0.0",
    "packaging>=20.0,<30.0",
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
ignore = ["E501", "TC003", "TC001"]

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
minversion = "8.2"
addopts = "-ra -q --strict-markers --tb=short"
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
python_files = "test_*.py"
python_classes = "Test*"
python_functions = "test_*"
markers = [
    "online: requires running server",
    "slow: takes >1s",
    "smoke: smoke tests",
    "contract: contract tests",
    "e2e: end-to-end tests",
    "integration: integration tests",
    "regression: regression tests",
]

[tool.mutmut]
paths_to_mutate = ["src/ai_assistant/core/", "src/ai_assistant/adapters/", "src/ai_assistant/features/", "src/ai_assistant/api/", "src/ai_assistant/pipeline/"]
pytest_add_cli_args_test_selection = ["tests/"]
backup = false

[tool.coverage.run]
branch = true
source = ["src/ai_assistant"]

[tool.coverage.report]
skip_covered = false
show_missing = true

[tool.coverage.html]
directory = "htmlcov"

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
from ai_assistant.api.security import require_api_key, set_api_key

__all__ = ["router"]

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(require_api_key)],
)


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
    if not state.config.security.admin_enabled:
        raise HTTPException(status_code=404, detail="Not found")
    cfg = state.config.llm
    return _CurrentModelResponse(
        model=cfg.model,
        provider=cfg.provider,
    )


@router.post("/api-key", response_model=_UpdateApiKeyResponse)
async def update_api_key(
    req: _UpdateApiKeyRequest,
    state: Annotated[AppState, Depends(get_state)],
) -> _UpdateApiKeyResponse:
    if not state.config.security.admin_enabled:
        raise HTTPException(status_code=404, detail="Not found")
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

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from starlette.requests import Request  # noqa: TC002  # FastAPI DI requires runtime

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.core.config import AppConfig, RAGStep
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    LLMConfigData,
    RerankerConfigData,
    StorageConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.pipeline import RAGPipeline
from ai_assistant.core.pipeline_steps import STEP_REGISTRY
from ai_assistant.features.chat.manager import ChatManager

if TYPE_CHECKING:
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
    "RAGState",
    "get_state",
    "init_adapters",
]

_logger = get_logger("deps")


def _to_float(value: object, default: float = 0.0) -> float:
    """Safely convert a value to float with explicit narrowing."""
    if isinstance(value, (int, float)):
        return float(value)
    return default


@dataclass
class RAGState:
    """Explicit per-instance RAG background task state.

    Replaces module-level globals to eliminate shared mutable state
    across tests and application instances.
    """

    semaphore: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(1))
    tasks: dict[str, asyncio.Task[dict[str, object]]] = field(default_factory=dict)
    status: dict[str, dict[str, object]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    STATUS_TTL_SECONDS: int = field(default=3600, repr=False)
    STATUS_MAX_ENTRIES: int = field(default=1000, repr=False)

    async def cleanup_status(self) -> None:
        """Remove expired entries and enforce max size cap on status."""
        import time

        async with self.lock:
            now = time.time()

            expired: list[str] = []
            for tid, info in self.status.items():
                finished_at = info.get("finished_at")
                started_at = info.get("started_at", 0)
                last_activity = finished_at if isinstance(finished_at, (int, float)) else started_at
                last_activity_float = _to_float(last_activity)
                if now - last_activity_float > self.STATUS_TTL_SECONDS:
                    expired.append(tid)

            for tid in expired:
                self.status.pop(tid, None)

            if len(self.status) > self.STATUS_MAX_ENTRIES:
                sorted_by_age = sorted(
                    self.status.items(),
                    key=lambda item: _to_float(item[1].get("started_at", 0)),
                )
                excess = len(self.status) - self.STATUS_MAX_ENTRIES
                for tid, _ in sorted_by_age[:excess]:
                    self.status.pop(tid, None)

            # Clean up finished tasks that may have leaked past done-callback/finally
            finished_tasks = [
                tid for tid, task in self.tasks.items() if task.done()
            ]
            for tid in finished_tasks:
                self.tasks.pop(tid, None)


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
    rag_state: RAGState | None = None


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
    reranker: IReranker
    rag_state: RAGState


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
# Config conversion — Pydantic -> dataclass for port contracts
# ---------------------------------------------------------------------------


def _chunker_data(cfg: AppConfig) -> ChunkerConfigData:
    c = cfg.chunker
    return ChunkerConfigData(
        chunk_size=c.chunk_size,
        chunk_overlap=c.chunk_overlap,
    )


def _embedder_data(cfg: AppConfig) -> EmbedderConfigData:
    c = cfg.embedder
    return EmbedderConfigData(
        model=c.model,
        api_base=c.api_base,
        api_key=c.api_key,
        dim=c.dim,
        timeout=c.timeout,
        connect_timeout=c.connect_timeout,
        n_gpu_layers=c.n_gpu_layers,
        n_batch=c.n_batch,
        n_ubatch=c.n_ubatch,
        mmap=c.mmap,
        mlock=c.mlock,
    )


def _llm_data(cfg: AppConfig) -> LLMConfigData:
    c = cfg.llm
    return LLMConfigData(
        model=c.model,
        api_base=c.api_base,
        api_key=c.api_key,
        max_tokens=c.max_tokens,
        temperature=c.temperature,
        timeout=c.timeout,
        connect_timeout=c.connect_timeout,
        server_context_size=c.server_context_size,
        top_p=c.top_p,
        top_k=c.top_k,
        min_p=c.min_p,
        repeat_penalty=c.repeat_penalty,
        presence_penalty=c.presence_penalty,
        frequency_penalty=c.frequency_penalty,
        stop_sequences=tuple(c.stop_sequences),
        system_message=c.system_message,
        available_models=tuple(c.available_models),
        n_gpu_layers=c.n_gpu_layers,
        n_batch=c.n_batch,
        n_ubatch=c.n_ubatch,
        mmap=c.mmap,
        mlock=c.mlock,
    )


def _vector_store_data(cfg: AppConfig) -> VectorStoreConfigData:
    c = cfg.vector_store
    return VectorStoreConfigData(
        dim=c.dim,
        index_path=c.index_path,
        metric=c.metric,
        max_chunks=c.max_chunks,
        max_document_size=c.max_document_size,
    )


def _storage_data(cfg: AppConfig) -> StorageConfigData:
    c = cfg.storage
    return StorageConfigData(db_path=c.db_path)


def _reranker_data(cfg: AppConfig) -> RerankerConfigData | None:
    if cfg.reranker is None or cfg.reranker.provider is None:
        return None
    c = cfg.reranker
    return RerankerConfigData(
        model=c.model,
        api_base=c.api_base,
        api_key=c.api_key,
        timeout=c.timeout,
        threshold=c.threshold,
    )


# ---------------------------------------------------------------------------
# Adapter initialization
# ---------------------------------------------------------------------------


async def init_adapters(config: AppConfig) -> InitializedAppState:
    """Initialize all adapters via factory and return populated InitializedAppState."""
    state = AppState(config=config)
    cfg = config

    state.chunker = create_adapter("chunker", cfg.chunker.provider, _chunker_data(cfg))
    state.embedder = create_adapter(
        "embedder", cfg.embedder.provider, _embedder_data(cfg)
    )
    state.llm = create_adapter("llm", cfg.llm.provider, _llm_data(cfg))
    state.vector_store = create_adapter(
        "vector_store",
        cfg.vector_store.provider,
        _vector_store_data(cfg),
    )

    reranker_cfg = _reranker_data(cfg)
    if reranker_cfg is not None and cfg.reranker.provider is not None:
        state.reranker = create_adapter("reranker", cfg.reranker.provider, reranker_cfg)
    else:
        state.reranker = create_adapter("reranker", "null", RerankerConfigData())

    try:
        state.storage = create_adapter(
            "storage", cfg.storage.provider, _storage_data(cfg)
        )
    except (ValueError, ImportError):
        _logger.exception(
            "Storage adapter not available",
            extra={"provider": cfg.storage.provider},
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
        token_margin_min=cfg.rag.token_margin_min,
        token_margin_pct=cfg.rag.token_margin_pct,
    )

    state.rag_state = RAGState()

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
        rag_state=state.rag_state,
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
from typing import TYPE_CHECKING, Any

from ai_assistant.api.deps import init_adapters
from ai_assistant.api.security import get_expected_api_key, set_api_key
from ai_assistant.core.config import AppConfig, load_config
from ai_assistant.core.logger import get_logger, setup_logging
from ai_assistant.core.retry import with_retry

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

    from ai_assistant.api.static import mount_static

    mount_static(app, config)

    log_cfg = config.logging
    log_level = log_cfg.level if log_cfg else ("DEBUG" if config.debug else "INFO")
    log_file = log_cfg.file if log_cfg else None
    log_fmt = log_cfg.format if log_cfg else "text"
    max_bytes = log_cfg.max_bytes if log_cfg else 10_485_760
    backup_count = log_cfg.backup_count if log_cfg else 2
    setup_logging(
        level=log_level,
        log_file=log_file,
        fmt=log_fmt,
        max_bytes=max_bytes,
        backup_count=backup_count,
    )

    if config.security.api_key and get_expected_api_key() is None:
        set_api_key(config.security.api_key)

    state = await init_adapters(config)
    app.state.app_state = state

    # Load persisted indices from disk via port contract
    if state.vector_store is not None:
        index_path = state.vector_store.index_path
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
            for ns in namespaces:
                await state.vector_store.load(index_path, namespace=ns)
            logger.info(
                "Loaded indices",
                extra={"count": len(namespaces), "path": index_path},
            )
        except Exception:
            logger.exception("Index load failed on startup")
            raise

    try:
        yield
    finally:
        await _async_cleanup(app, config)


async def _async_cleanup(app: FastAPI, config: AppConfig) -> None:
    """Async cleanup actions.

    Sets app.state.shutdown_degraded = True if index persistence fails
    so that the lifespan caller can react (e.g., non-zero exit).
    """
    try:
        state = app.state.app_state
    except AttributeError:
        logger.warning("No app state found during shutdown")
        return

    degraded = False

    # 1. Persist indices FIRST — metrics/adapter shutdown may block/hang
    if state.vector_store is not None:
        index_path = state.vector_store.index_path
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
            saved = 0
            for ns in namespaces:
                try:
                    await _save_index_with_timeout(
                        state.vector_store, index_path, ns
                    )
                    logger.info(
                        "Index saved", extra={"path": index_path, "namespace": ns}
                    )
                    saved += 1
                except TimeoutError:
                    logger.warning(
                        "Index save timed out",
                        extra={"path": index_path, "namespace": ns},
                    )
                    degraded = True
                except Exception:
                    logger.exception(
                        "Index save failed after retries",
                        extra={"path": index_path, "namespace": ns},
                    )
                    degraded = True
            logger.info(
                "Indices persisted",
                extra={"saved": saved, "total": len(namespaces)},
            )
            if degraded:
                logger.critical(
                    "Shutdown degraded: one or more indices failed to persist"
                )
                app.state.shutdown_degraded = True
        except Exception:
            logger.exception("Index save failed")
            app.state.shutdown_degraded = True

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
                await asyncio.wait_for(adapter.shutdown(), timeout=5.0)
                logger.info("Adapter shutdown complete", extra={"adapter": name})
            except TimeoutError:
                logger.warning("Adapter shutdown timed out", extra={"adapter": name})
            except Exception:
                logger.exception("Adapter shutdown failed", extra={"adapter": name})


@with_retry(max_retries=3, delay=0.5, backoff=2.0)
async def _save_index_with_retry(
    vector_store: Any, index_path: str, namespace: str
) -> None:
    """Save index with retry.

    Raises:
        Exception: If save fails after all retries.
    """
    await vector_store.save(index_path, namespace=namespace)


async def _save_index_with_timeout(
    vector_store: Any, index_path: str, namespace: str
) -> None:
    """Save index with timeout (no retry on timeout).

    Raises:
        TimeoutError: If save exceeds 10 seconds.
        Exception: If save fails after retries.
    """
    await asyncio.wait_for(
        _save_index_with_retry(vector_store, index_path, namespace),
        timeout=10.0,
    )

```

### `src/ai_assistant/api/middleware.py`
```python
"""FastAPI middleware for request metrics."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from fastapi import Response  # noqa: TC002  # BaseHTTPMiddleware dispatch uses runtime
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import (
    Request,  # noqa: TC002  # BaseHTTPMiddleware dispatch uses runtime
)

from ai_assistant.core import metrics

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
            metrics.increment_counter(
                "ai_assistant_requests_total",
                labels={"method": method, "path": path, "status": status},
            )
            metrics.observe_histogram(
                "ai_assistant_request_duration_seconds",
                value=duration,
                labels={"path": path},
            )

```

### `src/ai_assistant/api/router.py`
```python
"""Auto-discovery router assembly."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Response

from ai_assistant.api import admin
from ai_assistant.api.security import require_api_key
from ai_assistant.core.config import SecurityConfig
from ai_assistant.core.metrics import get_metrics, get_metrics_json

# Explicit feature handler imports — import errors surface at compile time
# instead of being deferred to the first HTTP request.
from ai_assistant.features.chat import handlers as chat_handlers
from ai_assistant.features.rag import handlers as rag_handlers

__all__ = ["assemble_routers"]

# Tags for routers that stay at root (no /api/v1 prefix).
# Admin has its own auth and admin_enabled gate.
_ROOT_TAGS: frozenset[str] = frozenset({"chat-oai", "metrics", "admin"})

# Metrics router — no API key, Prometheus-compatible exposition format
_metrics_router = APIRouter(tags=["metrics"])


@_metrics_router.get("/metrics", response_class=Response)
async def _metrics_endpoint() -> Response:
    return Response(content=get_metrics(), media_type="text/plain; version=0.0.4")


@_metrics_router.get("/metrics/json")
async def _metrics_json_endpoint() -> dict[str, Any]:
    return get_metrics_json()


# Explicit router registry — missing handlers fail immediately at import time.
# Add new routers here when adding feature handlers.
_ROUTERS: list[APIRouter] = [
    _metrics_router,
    admin.router,
    chat_handlers.router,
    chat_handlers.router_oai,
    rag_handlers.router,
]


def assemble_routers(security: SecurityConfig | None = None) -> list[APIRouter]:
    """Collect routers from explicitly imported feature handlers + admin.

    Args:
        security: Security configuration. If *openai_routes_require_auth* is True,
            OpenAI-compatible routes (chat-oai) will require API key auth.
    """
    routers = list(_ROUTERS)

    # Determine which root-tagged routers require protection
    protected_root_tags: set[str] = set()
    if security is not None and security.openai_routes_require_auth:
        protected_root_tags.add("chat-oai")
    # Metrics always stays unprotected
    always_unprotected: frozenset[str] = frozenset({"metrics"})

    wrapped: list[APIRouter] = []
    for router in routers:
        is_root = any(tag in _ROOT_TAGS for tag in router.tags)
        is_always_unprotected = any(
            tag in always_unprotected for tag in router.tags
        )
        is_protected_root = any(
            tag in protected_root_tags for tag in router.tags
        )

        if is_always_unprotected:
            # Metrics always stays unprotected
            wrapped.append(router)
        elif not is_root:
            # Legacy routers get /api/v1 prefix + API key dependency
            wrapper = APIRouter(dependencies=[Depends(require_api_key)])
            wrapper.include_router(router, prefix="/api/v1")
            wrapped.append(wrapper)
        elif is_protected_root:
            # Root router that needs auth: wrap with dependency, no prefix
            wrapper = APIRouter(dependencies=[Depends(require_api_key)])
            wrapper.include_router(router)
            wrapped.append(wrapper)
        else:
            # Root routers keep their original paths, no prefix, no extra wrapper
            wrapped.append(router)

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
    env_key = os.getenv("AI_SECURITY_API_KEY")
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
    if cl:
        try:
            if int(cl) > int(max_sz):
                raise HTTPException(status_code=413, detail="Payload too large")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid Content-Length"
            ) from None


_bearer_dependency = Depends(bearer_scheme)


async def require_api_key(
    credentials: HTTPAuthorizationCredentials = _bearer_dependency,
) -> None:
    expected = get_expected_api_key()
    if not expected:
        raise HTTPException(status_code=401, detail="API key not configured")
    if not credentials or not hasattr(credentials, "credentials"):
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

__all__ = ["mount_static"]


def mount_static(app: FastAPI, config: Any) -> None:
    """Mount /ui once, only if directory exists."""
    if getattr(app.state, "static_mounted", False):
        return
    ui_cfg = config.ui
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
    logger,
    pipeline,
    ports,
    prompts,
    retry,
    utils,
)

__all__ = [
    "config",
    "domain",
    "io_utils",
    "logger",
    "pipeline",
    "ports",
    "prompts",
    "retry",
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
    connect_timeout: float | None = None
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
    connect_timeout: float | None = None
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
    n_gpu_layers: int = 99
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
    token_margin_min: int = 256
    token_margin_pct: float = 0.1
    documents_root: str = "sources"
    chat_exports_root: str = "sources"

    @field_validator("documents_root", "chat_exports_root")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        """Normalize path: strip trailing slashes, reject absolute paths."""
        v = v.strip()
        if not v:
            raise ValueError("path must be non-empty")
        if v.startswith("/") or v.startswith("\\") or v.startswith("~"):
            raise ValueError(f"path must be relative, got: {v}")
        return v.rstrip("/").rstrip("\\")


class SecurityConfig(BaseSettings):
    """Security configuration — loaded once at startup."""

    model_config = SettingsConfigDict(env_prefix="AI_SECURITY_", extra="forbid")
    api_key: str | None = None
    admin_enabled: bool = False
    max_body_size: int = 10_485_760
    allowed_hosts: list[str] = Field(default_factory=list)
    openai_routes_require_auth: bool = False


class NamespaceConfig(BaseModel):
    """Per-namespace RAG overrides."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    relevance_threshold: float = Field(default=0.1, validation_alias="threshold")
    chunk_size: int = 512
    prompt: str = "rag_strict"


class LoggingConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_LOGGING_", extra="forbid")
    level: str = "INFO"
    file: str | None = "./data/app.log"
    format: str = "text"  # "text" or "json"
    max_bytes: int = 10_485_760  # 10 MB
    backup_count: int = 2


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        extra="forbid",
        env_file=".env",
    )
    app_name: str = "ai-assistant"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    config_version: str = "1.6.0"
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
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
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
        if type(v) is dict and "steps" in v and type(v["steps"]) is str:  # noqa: UP037
            return {**v, "steps": [s.strip() for s in v["steps"].split(",")]}
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_vector_store_relevance_threshold(cls, v: Any) -> Any:
        """Backward-compatible loader: migrate vector_store.relevance_threshold → rag."""
        if type(v) is not dict:
            return v
        vs = v.get("vector_store")
        if type(vs) is dict and "relevance_threshold" in vs:
            rag = v.get("rag", {})
            if type(rag) is dict and "relevance_threshold" not in rag:
                rag = {**rag, "relevance_threshold": vs["relevance_threshold"]}
                v = {**v, "rag": rag}
            # Strip the removed field so VectorStoreConfig(extra="forbid") doesn't choke
            vs = {k: val for k, val in vs.items() if k != "relevance_threshold"}
            v = {**v, "vector_store": vs}
        return v

    @model_validator(mode="before")
    @classmethod
    def _migrate_security_rate_limit(cls, v: Any) -> Any:
        """Backward-compatible loader: strip removed security.rate_limit field."""
        if type(v) is not dict:
            return v
        sec = v.get("security")
        if type(sec) is dict and "rate_limit" in sec:
            # rate_limit was removed — strip it so SecurityConfig(extra="forbid") doesn't choke
            sec = {k: val for k, val in sec.items() if k != "rate_limit"}
            v = {**v, "security": sec}
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
    ToolMessage,
    UserMessage,
)
from .pipeline import PipelineData

__all__ = [
    "UserMessage",
    "AssistantMessage",
    "ToolMessage",
    "Document",
    "Chunk",
    "ChunkMetadata",
    "PipelineData",
    "ConfigurationError",
    "AdapterError",
    "VersionMismatchError",
]

```

### `src/ai_assistant/core/domain/configs.py`
```python
"""Immutable dataclass configurations for adapter port contracts.

Each dataclass mirrors a subset of the Pydantic AppConfig models
(core/config.py) as stdlib-only frozen dataclasses. This keeps
core/ports/ free of any Pydantic dependency and guarantees immutability.

All fields have sensible defaults matching the production config defaults.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkerConfigData:
    """Configuration for document chunking adapters.

    Attributes:
        chunk_size: Target size of each chunk in characters.
        chunk_overlap: Number of overlapping characters between chunks.
    """

    chunk_size: int = 512
    chunk_overlap: int = 50


@dataclass(frozen=True, slots=True)
class EmbedderConfigData:
    """Configuration for text embedding adapters.

    Attributes:
        model: Model identifier on the embedding server.
        api_base: Base URL of the OpenAI-compatible embedding API.
        api_key: Optional API key for authentication.
        dim: Embedding vector dimension (must match vector_store.dim).
        timeout: Total request timeout in seconds.
        connect_timeout: TCP connection timeout in seconds.
        n_gpu_layers: Number of layers to offload to GPU (-1 = all, 0 = CPU).
        n_batch: Batch size for embedding processing.
        n_ubatch: Micro-batch size.
        mmap: Use memory-mapped files to reduce RAM usage.
        mlock: Lock pages in RAM to prevent swapping.
    """

    model: str = "text-embedding-3-small"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    dim: int = 384
    timeout: float = 60.0
    connect_timeout: float | None = None
    n_gpu_layers: int = 0
    n_batch: int = 512
    n_ubatch: int = 64
    mmap: bool = True
    mlock: bool = False


@dataclass(frozen=True, slots=True)
class LLMConfigData:
    """Configuration for language model adapters.

    Attributes:
        model: Model identifier on the LLM server.
        api_base: Base URL of the OpenAI-compatible LLM API.
        api_key: Optional API key for authentication.
        max_tokens: Maximum tokens to generate per completion.
        temperature: Sampling temperature (0.0 = deterministic, 1.0 = random).
        timeout: Total request timeout in seconds.
        connect_timeout: TCP connection timeout in seconds.
        server_context_size: Context window size advertised by the server.
        top_p: Nucleus sampling probability threshold.
        top_k: Top-k sampling limit (-1 = disabled).
        min_p: Minimum token probability threshold.
        repeat_penalty: Penalty for repeated tokens (1.0 = no penalty).
        presence_penalty: Penalty for token presence (-2.0 to 2.0).
        frequency_penalty: Penalty for token frequency (-2.0 to 2.0).
        stop_sequences: Sequences that stop generation.
        system_message: Optional system prompt override.
        available_models: List of models available on this server.
        n_gpu_layers: Number of layers to offload to GPU (-1 = all, 0 = CPU).
        n_batch: Batch size for inference.
        n_ubatch: Micro-batch size.
        mmap: Use memory-mapped files to reduce RAM usage.
        mlock: Lock pages in RAM to prevent swapping.
    """

    model: str = "gpt-4o-mini"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 300.0
    connect_timeout: float | None = None
    server_context_size: int | None = None
    top_p: float = 0.95
    top_k: int = 40
    min_p: float = 0.05
    repeat_penalty: float = 1.1
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    stop_sequences: tuple[str, ...] = ()
    system_message: str | None = None
    available_models: tuple[str, ...] = ()
    n_gpu_layers: int = 99
    n_batch: int = 512
    n_ubatch: int = 64
    mmap: bool = True
    mlock: bool = False


@dataclass(frozen=True, slots=True)
class VectorStoreConfigData:
    """Configuration for vector store adapters.

    Attributes:
        dim: Embedding vector dimension (must match embedder.dim).
        index_path: Directory path for persistent index storage.
        metric: Distance metric ("l2", "cosine", "ip").
        max_chunks: Maximum number of chunks per namespace.
        max_document_size: Maximum document size in bytes.
    """

    dim: int = 384
    index_path: str = "./data/indices/default"
    metric: str = "l2"
    max_chunks: int = 100_000
    max_document_size: int = 10_485_760


@dataclass(frozen=True, slots=True)
class StorageConfigData:
    """Configuration for persistent storage adapters.

    Attributes:
        db_path: Path to the SQLite database file.
    """

    db_path: str = "./data/storage.db"


@dataclass(frozen=True, slots=True)
class RerankerConfigData:
    """Configuration for reranker adapters.

    Attributes:
        model: Model identifier for the reranker endpoint.
        api_base: Base URL of the reranker API.
        api_key: Optional API key for authentication.
        timeout: Total request timeout in seconds.
        threshold: Minimum relevance score to keep a chunk (0.0 to 1.0).
    """

    model: str = "rerank-multilingual-v3.0"
    api_base: str = "https://api.cohere.com"
    api_key: str | None = None
    timeout: float = 30.0
    threshold: float = 0.3

```

### `src/ai_assistant/core/domain/documents.py`
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ChunkMetadata:
    """Immutable metadata for a chunk."""

    source: str
    index: int
    total_chunks: int
    custom: dict[str, Any] = field(default_factory=dict)
    original_path: str | None = None
    source_uri: str | None = None  # Relative path from root (documents_root / chat_exports_root), e.g. "personal/notes.md"


@dataclass(frozen=True, slots=True)
class Chunk:
    """Immutable text chunk with optional embedding and metadata."""

    id: str
    text: str
    embedding: list[float] | None = None
    metadata: ChunkMetadata | None = None


@dataclass(frozen=True, slots=True)
class Document:
    """Immutable source document."""

    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)

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
    "LLM_UNAVAILABLE",
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
LLM_UNAVAILABLE = "generate: LLM unavailable"

```

### `src/ai_assistant/core/domain/messages.py`
```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class UserMessage:
    """User message."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    """Assistant message."""

    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ToolMessage:
    """Tool result message."""

    text: str
    call_id: str
    metadata: dict[str, Any] = field(default_factory=dict)

```

### `src/ai_assistant/core/domain/pipeline.py`
```python
"""Pipeline data carrier."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .documents import Chunk
    from .messages import AssistantMessage, UserMessage
    from .ports.embedder import IEmbedder
    from .ports.llm import ILLM
    from .ports.reranker import IReranker
    from .ports.vector_store import IVectorStore

__all__ = ["PipelineData", "PipelineConfig"]

@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Typed configuration for RAG pipeline steps.

    Mirrors a subset of RAGConfig as a stdlib dataclass
    so that pipeline steps have a typed contract without
    depending on Pydantic.
    """

    top_k: int = 5
    namespace: str = "default"
    relevance_threshold: float = 0.3
    prompt_name: str = "rag_strict"
    prompt_version: str = "v1"
    token_margin_min: int = 256
    token_margin_pct: float = 0.1

@dataclass(frozen=True, slots=True)
class PipelineData:
    query: UserMessage | None = None
    chunks: tuple[Chunk, ...] = field(default_factory=tuple)
    context: str = ""
    response: AssistantMessage | None = None
    errors: tuple[str, ...] = field(default_factory=tuple)
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    # Typed dependency fields — replace metadata bag
    embedder: IEmbedder | None = None
    vector_store: IVectorStore | None = None
    reranker: IReranker | None = None
    llm: ILLM | None = None
    pipeline_config: PipelineConfig | None = None
    query_embedding: list[float] | None = None
    tokenizer_model: str | None = None
    rerank_filtered_out: bool | None = None
    rerank_scores: list[float] | None = None

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

    def with_query_embedding(self, query_embedding: list[float] | None) -> PipelineData:
        """Return a new PipelineData with updated query_embedding."""
        return replace(self, query_embedding=query_embedding)

    def with_rerank_filtered_out(self, rerank_filtered_out: bool | None) -> PipelineData:
        """Return a new PipelineData with updated rerank_filtered_out."""
        return replace(self, rerank_filtered_out=rerank_filtered_out)

    def with_rerank_scores(self, rerank_scores: list[float] | None) -> PipelineData:
        """Return a new PipelineData with updated rerank_scores."""
        return replace(self, rerank_scores=rerank_scores)

```

### `src/ai_assistant/core/io_utils.py`
```python
"""Atomic file operations."""

from __future__ import annotations

import asyncio
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
    if binary and type(content) is not bytes:
        raise TypeError(
            f"Expected bytes for mode={mode!r}, got {type(content).__name__}"
        )
    if not binary and type(content) is not str:
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
            # os.replace() already atomically removes tmp on success.
            # On failure (before replace), tmp may remain; mkstemp creates
            # files in a temp dir that the OS cleans up. No unlink needed.
            pass

    await asyncio.to_thread(_sync)

```

### `src/ai_assistant/core/logger.py`
```python
"""Structured logging with text/json format support and trace_id propagation."""

from __future__ import annotations

import json
import logging
import logging.handlers
import sys
import threading
from pathlib import Path
from typing import Final

__all__ = ["get_logger", "setup_logging"]

_LOCK: Final = threading.Lock()
_VALID_LEVELS: Final[frozenset[str]] = frozenset(
    {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}
)


class _TextFormatter(logging.Formatter):
    """Text formatter with trace_id support — thread-safe, no record mutation."""

    def format(self, record: logging.LogRecord) -> str:
        trace_id = getattr(record, "trace_id", None)
        trace_prefix = f"trace_id={trace_id} | " if trace_id else ""
        record.message = record.getMessage()
        record.asctime = self.formatTime(record, self.datefmt)
        return (
            f"{record.asctime} | {record.levelname:8} | {record.name} | "
            f"{trace_prefix}{record.message}"
        )


class _JsonFormatter(logging.Formatter):
    """JSON formatter with structured fields including trace_id.

    Extra fields are detected dynamically by comparing against a baseline
    LogRecord, so this does not hardcode Python version-specific attributes.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        trace_id = getattr(record, "trace_id", None)
        if trace_id:
            log_entry["trace_id"] = trace_id

        # Detect extra fields by diffing against a default LogRecord.
        # This set is computed once per format call — cheap and future-proof.
        baseline = vars(logging.makeLogRecord({}))
        for key, value in record.__dict__.items():
            if key not in baseline and not key.startswith("_"):
                log_entry[key] = value

        return json.dumps(log_entry, ensure_ascii=False, default=str)


def setup_logging(
    level: str = "INFO",
    log_file: str | Path | None = "./data/app.log",
    fmt: str = "text",
    max_bytes: int = 10_485_760,
    backup_count: int = 2,
) -> logging.Logger:
    """Configure application logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Path to log file, or None for console-only.
        fmt: Log format — "text" or "json".
        max_bytes: Maximum size in bytes before rotating the log file.
        backup_count: Number of backup files to keep.

    Repeated calls clear existing handlers and recreate them,
    allowing format changes at runtime (e.g., on config reload).
    """
    upper = level.upper()
    if upper not in _VALID_LEVELS:
        raise ValueError(
            f"Invalid log level {level!r}. Use one of: {sorted(_VALID_LEVELS)}"
        )

    if fmt not in {"text", "json"}:
        raise ValueError(f"Invalid log format {fmt!r}. Use 'text' or 'json'.")

    logger = logging.getLogger("ai_assistant")
    logger.setLevel(getattr(logging, upper))

    with _LOCK:
        # Clear existing handlers to allow format reconfiguration
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)

        formatter: logging.Formatter = (
            _TextFormatter() if fmt == "text" else _JsonFormatter()
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(formatter)
        logger.addHandler(console)

        if log_file:
            path = Path(log_file)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                fh = logging.handlers.RotatingFileHandler(
                    path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
                fh.setFormatter(formatter)
                logger.addHandler(fh)
            except OSError as exc:
                sys.stderr.write(f"Failed to create log file {path}: {exc}\n")

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

from typing import TYPE_CHECKING

from ai_assistant.core.domain.errors import ConfigurationError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_assistant.core.domain.pipeline import PipelineData


__all__ = ["RAGPipeline", "ConfigurationError"]


class RAGPipeline:
    """Sequential step runner."""

    def __init__(
        self, steps: list[Callable[[PipelineData], Awaitable[PipelineData]]]
    ) -> None:
        self.steps = list(steps)

    async def run(self, data: PipelineData) -> PipelineData:
        """Execute steps sequentially, passing PipelineData through.

        Args:
            data: Initial pipeline data with dependencies pre-populated
                via explicit typed fields (embedder, vector_store, etc.).

        Raises:
            ConfigurationError: If required fields are missing for
                the configured steps.
        """
        required_fields = self._required_fields_for_steps()
        missing = [f for f in required_fields if getattr(data, f) is None]
        if missing:
            raise ConfigurationError(
                f"Missing required PipelineData fields: {missing}"
            )
        for step in self.steps:
            data = await step(data)
        return data

    def _required_fields_for_steps(self) -> set[str]:
        """Return required PipelineData field names based on configured steps."""
        from ai_assistant.core.pipeline_steps import STEP_REGISTRY

        field_map: dict[str, set[str]] = {
            "embed_query": {"embedder"},
            "retrieve": {"vector_store"},
            "rerank": {"reranker"},
            "build_context": set(),
            "generate": {"llm", "pipeline_config", "tokenizer_model"},
            "hyde_query": {"embedder", "llm"},
        }
        required: set[str] = set()
        for step_name, step_func in STEP_REGISTRY.items():
            if any(s is step_func for s in self.steps):
                required |= field_map.get(step_name, set())
        return required

```

### `src/ai_assistant/core/pipeline_steps.py`
```python
"""RAG pipeline steps with namespace and rerank support.
All steps return new PipelineData instances via dataclasses.replace().
No in-place mutation.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from ai_assistant.core.domain.errors import (
    EMBEDDER_NOT_PROVIDED,
    INTERNAL_SERVER_ERROR,
    LLM_NOT_PROVIDED,
    LLM_UNAVAILABLE,
    QUERY_EMBEDDING_MISSING,
    QUERY_MISSING,
    QUERY_TEXT_MISSING,
    VECTOR_STORE_NOT_PROVIDED,
    AdapterError,
)
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineConfig
from ai_assistant.core.logger import get_logger
from ai_assistant.core.metrics import increment_counter
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.retry import with_retry
from ai_assistant.core.utils import async_count_tokens

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from ai_assistant.core.domain.documents import Chunk
    from ai_assistant.core.domain.pipeline import PipelineData
    from ai_assistant.core.ports.embedder import IEmbedder
    from ai_assistant.core.ports.llm import ILLM, Message
    from ai_assistant.core.ports.vector_store import IVectorStore

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


async def _estimate_tokens(text: str, model: str) -> int:
    return await async_count_tokens(text, model)


# --- retry helpers for network calls ----------------------------------------


@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def _call_embed(embedder: IEmbedder, text: str) -> list[list[float]]:
    """Embed a single text with retry."""
    return await embedder.embed([text])


@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def _call_search(
    vector_store: IVectorStore, embedding: list[float], top_k: int, namespace: str
) -> list[Chunk]:
    """Search vector store with retry."""
    return await vector_store.search(embedding, top_k=top_k, namespace=namespace)


@with_retry(max_retries=3, delay=1.0, backoff=2.0)
async def _call_llm(llm: ILLM, messages: list[Message]) -> AssistantMessage:
    """Call LLM with retry."""
    return await llm.complete(messages)


@step("embed_query")
async def embed_query(data: PipelineData) -> PipelineData:
    """Embed the user query text.

    Field contract:
        IN:  embedder (IEmbedder) — required.
        OUT: query_embedding (list[float]) — produced on success.
        DATA: query.text (str) — must be non-empty.

    Errors added on failure:
        EMBEDDER_NOT_PROVIDED, QUERY_TEXT_MISSING, INTERNAL_SERVER_ERROR.
    """
    _logger.debug("embed_query start", extra={"trace_id": data.trace_id})
    embedder = data.embedder
    if embedder is None:
        _logger.warning("embed_query: no embedder", extra={"trace_id": data.trace_id})
        return data.add_error(EMBEDDER_NOT_PROVIDED)
    if data.query is None or not data.query.text:
        _logger.warning("embed_query: no query text", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_TEXT_MISSING)
    try:
        embeddings = await _call_embed(embedder, data.query.text)
        if not embeddings:
            _logger.warning(
                "embed_query: empty embedding response",
                extra={"trace_id": data.trace_id},
            )
            return data.add_error(INTERNAL_SERVER_ERROR)
        _logger.debug("embed_query done", extra={"trace_id": data.trace_id})
        return data.with_query_embedding(embeddings[0])
    except Exception:
        _logger.exception("embed_query failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("retrieve")
async def retrieve(data: PipelineData) -> PipelineData:
    """Retrieve relevant chunks from vector store (namespace-aware).

    Field contract:
        IN:  vector_store (IVectorStore) — required.
             query_embedding (list[float]) — produced by embed_query.
             pipeline_config (PipelineConfig) — provides top_k, namespace.
        OUT: chunks (tuple[Chunk, ...]) — written to PipelineData.chunks.
             Metric "rag_chunks" recorded.

    Errors added on failure:
        VECTOR_STORE_NOT_PROVIDED, QUERY_EMBEDDING_MISSING, INTERNAL_SERVER_ERROR.
    """
    _logger.debug("retrieve start", extra={"trace_id": data.trace_id})
    vector_store = data.vector_store
    if vector_store is None:
        _logger.warning("retrieve: no vector_store", extra={"trace_id": data.trace_id})
        return data.add_error(VECTOR_STORE_NOT_PROVIDED)
    embedding = data.query_embedding
    if embedding is None:
        _logger.warning("retrieve: no embedding", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_EMBEDDING_MISSING)
    try:
        cfg = data.pipeline_config
        if cfg is None:
            cfg = PipelineConfig()
        top_k = cfg.top_k
        namespace = cfg.namespace
        chunks = await _call_search(vector_store, embedding, top_k, namespace)
        increment_counter(
            "ai_assistant_rag_retrieve_total",
            labels={"namespace": namespace},
        )
        _logger.debug(
            "retrieve done", extra={"trace_id": data.trace_id, "chunks": len(chunks)}
        )
        return data.with_chunks(chunks)
    except Exception:
        _logger.exception("retrieve failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("rerank")
async def rerank(data: PipelineData) -> PipelineData:
    """Rerank retrieved chunks by relevance and filter by threshold.

    Field contract:
        IN:  reranker (IReranker) — required, never None (NullReranker if disabled).
             pipeline_config (PipelineConfig) — provides top_k, relevance_threshold.
        OUT: rerank_filtered_out (bool) — set True if all chunks filtered.
             rerank_scores (list[float]) — set if chunks survive filtering.
        DATA: chunks (tuple[Chunk, ...]) — replaced with filtered subset.

    Errors added on failure:
        INTERNAL_SERVER_ERROR.
    """
    _logger.debug(
        "rerank start", extra={"trace_id": data.trace_id, "chunks": len(data.chunks)}
    )
    if not data.chunks:
        return replace(data)

    reranker = data.reranker
    if reranker is None:
        _logger.warning("rerank: no reranker", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)

    try:
        _raw_query = data.query.text if data.query is not None else None
        query = _raw_query if _raw_query is not None else " "
        cfg = data.pipeline_config
        if cfg is None:
            cfg = PipelineConfig()
        top_k = cfg.top_k
        threshold = cfg.relevance_threshold

        results = await reranker.rerank(query, data.chunks, top_k=top_k)

        filtered = [r for r in results if r.score >= threshold]

        if not filtered:
            _logger.debug(
                "rerank: all chunks filtered out", extra={"trace_id": data.trace_id}
            )
            return data.with_chunks(()).with_rerank_filtered_out(True)
        else:
            _logger.debug(
                "rerank done",
                extra={"trace_id": data.trace_id, "chunks": len(filtered)},
            )
            return (
                data.with_chunks(tuple(r.chunk for r in filtered))
                .with_rerank_scores([r.score for r in filtered])
            )

    except Exception:
        _logger.exception("rerank failed", extra={"trace_id": data.trace_id})
        return data.add_error(INTERNAL_SERVER_ERROR)


@step("build_context")
async def build_context(data: PipelineData) -> PipelineData:
    """Build context string from retrieved (and reranked) chunks.

    Field contract:
        DATA: chunks (tuple[Chunk, ...]) — read; context (str) — produced.
    """
    _logger.debug(
        "build_context start",
        extra={"trace_id": data.trace_id, "chunks": len(data.chunks)},
    )
    if not data.chunks:
        return data.with_context("")
    lines = [chunk.text for chunk in data.chunks if chunk.text]
    context = "\n\n".join(lines)
    _logger.debug(
        "build_context done",
        extra={"trace_id": data.trace_id, "chars": len(context)},
    )
    return data.with_context(context)


def _build_fallback_prompt(chunks: tuple[Chunk, ...], query_text: str) -> str:
    """Build a minimal RAG prompt from chunks when template lookup fails."""
    chunks_text = "\n".join(f"[{i + 1}] {c.text}" for i, c in enumerate(chunks))
    return f"Context:\n{chunks_text}\n\nQuestion: {query_text}\nAnswer:"


async def _truncate_to_fit(
    data: PipelineData,
    prompt: str,
    prompt_name: str,
    prompt_version: str,
    query_text: str,
    limit: int,
    model: str,
) -> tuple[PipelineData, str]:
    """Remove chunks from the end until prompt fits in the token limit.

    Returns:
        (updated_data, updated_prompt). If all chunks are exhausted and
        the prompt still exceeds the limit, updated_data will have empty
        chunks and updated_prompt will reflect the last attempted context.
    """
    prompt_tokens = await _estimate_tokens(prompt, model=model)
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
        prompt_tokens = await _estimate_tokens(prompt, model=model)
    return current_data, prompt


@step("generate")
async def generate(data: PipelineData) -> PipelineData:
    """Generate response from context using LLM.

    Field contract:
        IN:  llm (ILLM) — required.
             pipeline_config (PipelineConfig) — provides prompt_name,
                 prompt_version, token_margin_min, token_margin_pct.
             tokenizer_model (str) — required for token estimation.
        DATA: query (UserMessage), context (str), chunks (tuple[Chunk, ...]).
        OUT: response (AssistantMessage).
    """
    _logger.debug("generate start", extra={"trace_id": data.trace_id})
    llm = data.llm
    if llm is None:
        _logger.warning("generate: no llm", extra={"trace_id": data.trace_id})
        return data.add_error(LLM_NOT_PROVIDED)
    if data.query is None:
        _logger.warning("generate: no query", extra={"trace_id": data.trace_id})
        return data.add_error(QUERY_MISSING)

    query_text = data.query.text or "  "
    cfg = data.pipeline_config
    if cfg is None:
        cfg = PipelineConfig()
    prompt_version = cfg.prompt_version
    prompt_name = cfg.prompt_name

    try:
        prompt = get_prompt(
            prompt_name,
            version=prompt_version,
            query=query_text,
            context=data.context,
        )
    except Exception:
        prompt = _build_fallback_prompt(data.chunks, query_text)

    max_ctx = llm.get_context_limit()

    tokenizer_model = data.tokenizer_model
    if tokenizer_model is None:
        _logger.error(
            "tokenizer_model missing in PipelineData",
            extra={"trace_id": data.trace_id},
        )
        return data.add_error("tokenizer_model missing in PipelineData")
    prompt_tokens = await _estimate_tokens(prompt, model=tokenizer_model)
    margin = max(cfg.token_margin_min, int(max_ctx * cfg.token_margin_pct))
    limit = max_ctx - margin

    if prompt_tokens > limit:
        data, prompt = await _truncate_to_fit(
            data, prompt, prompt_name, prompt_version, query_text, limit,
            model=tokenizer_model,
        )
        prompt_tokens = await _estimate_tokens(prompt, model=tokenizer_model)
        if prompt_tokens > limit:
            error_msg = (
                f"generate: prompt too long ({prompt_tokens} tokens)  "
                f"exceeds limit ({limit}) "
            )
            return data.add_error(error_msg).with_response(
                AssistantMessage(
                    text=(
                        "Sorry, the retrieved context is too large  "
                        "to process. Please narrow your query. "
                    )
                )
            )

    messages: list[Message] = [UserMessage(text=prompt)]
    response: AssistantMessage | None = None

    try:
        response = await _call_llm(llm, messages)
    except AdapterError as exc:
        _logger.exception("LLM unavailable", extra={"trace_id": data.trace_id})
        return data.add_error(f"{LLM_UNAVAILABLE} ({exc})").with_response(
            AssistantMessage(
                text="LLM service temporarily unavailable. Please try again later."
            )
        )
    except Exception:
        _logger.exception(
            "generate failed after retries", extra={"trace_id": data.trace_id}
        )
        return data.add_error(INTERNAL_SERVER_ERROR).with_response(
            AssistantMessage(
                text="Sorry, I encountered an error generating the response. "
            )
        )

    _logger.debug("generate done", extra={"trace_id": data.trace_id})
    return data.with_response(response)


@step("hyde_query")
async def hyde_query(data: PipelineData) -> PipelineData:
    """Hypothetical Document Embedding (HyDE).

    Generates a hypothetical answer to the query, embeds it,
    and stores the embedding in PipelineData for downstream retrieval.
    """
    _logger.debug("hyde_query start", extra={"trace_id": data.trace_id})
    embedder = data.embedder
    llm = data.llm
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
    hyde_messages: list[Message] = [
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
        if not embeddings:
            _logger.warning(
                "hyde_query: empty embedding response",
                extra={"trace_id": data.trace_id},
            )
            return data.add_error(INTERNAL_SERVER_ERROR)
    except Exception:
        _logger.exception(
            "hyde_query: embedding failed", extra={"trace_id": data.trace_id}
        )
        return data.add_error(INTERNAL_SERVER_ERROR)

    _logger.debug("hyde_query done", extra={"trace_id": data.trace_id})
    return data.with_query_embedding(embeddings[0])

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
"""core/ports/chunker.py"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_assistant.core.domain.configs import ChunkerConfigData
    from ai_assistant.core.domain.documents import Chunk, Document

__all__ = ["IChunker"]


class IChunker(ABC):
    """Split documents into chunks."""

    def __init__(self, config: ChunkerConfigData) -> None:
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
"""core/ports/embedder.py"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_assistant.core.domain.configs import EmbedderConfigData
from ai_assistant.core.ports.closable import IClosable

__all__ = ["IEmbedder"]


class IEmbedder(IClosable, ABC):
    """Text embedding interface."""

    def __init__(self, config: EmbedderConfigData) -> None:
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
"""core/ports/llm.py"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from ai_assistant.core.domain.configs import LLMConfigData
from ai_assistant.core.domain.messages import AssistantMessage, ToolMessage, UserMessage
from ai_assistant.core.ports.closable import IClosable

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

Message = UserMessage | AssistantMessage | ToolMessage

__all__ = ["ILLM", "Message"]


class ILLM(IClosable, ABC):
    """Language model interface."""

    system_message: str | None = None

    def __init__(self, config: LLMConfigData) -> None:
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

    @abstractmethod
    def get_context_limit(self) -> int | None:
        """Return the context window size in tokens, or None if unknown."""
        ...

```

### `src/ai_assistant/core/ports/reranker.py`
```python
"""core/ports/reranker.py"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_assistant.core.domain.configs import RerankerConfigData
    from ai_assistant.core.domain.documents import Chunk

from ai_assistant.core.ports.closable import IClosable

__all__ = ["IReranker", "RerankResult"]


@dataclass(frozen=True)
class RerankResult:
    """Single rerank result with relevance score."""

    chunk: Chunk
    score: float  # 0.0 to 1.0, higher = more relevant


class IReranker(IClosable, ABC):
    """Re-rank retrieved chunks by relevance to query.

    Used after vector store retrieval to filter out false positives
    and improve context quality for generation.
    """

    def __init__(self, config: RerankerConfigData) -> None:
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
"""core/ports/storage.py"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ai_assistant.core.domain.configs import StorageConfigData
from ai_assistant.core.ports.initializable import IInitializable

__all__ = ["IChatStorage", "ISettingsStorage"]


class IChatStorage(IInitializable, ABC):
    """Chat history persistence."""

    def __init__(self, config: StorageConfigData) -> None:
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

    def __init__(self, config: StorageConfigData) -> None:
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
    parameters: dict[str, object]  # JSON Schema object
    required: list[str] = field(default_factory=list)


@dataclass(frozen=True)
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

    def __init__(self, config: object) -> None:
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
"""core/ports/vector_store.py"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_assistant.core.domain.configs import VectorStoreConfigData
    from ai_assistant.core.domain.documents import Chunk

from ai_assistant.core.ports.closable import IClosable

__all__ = ["IVectorStore"]


class IVectorStore(IClosable, ABC):
    """Vector storage with FAISS-like semantics."""

    def __init__(self, config: VectorStoreConfigData) -> None:
        self.config = config

    @property
    @abstractmethod
    def index_path(self) -> str:
        """Return the base path for index persistence.

        Adapters must expose this so that lifespan and health checks
        can locate indices without reaching into config internals.
        """
        ...

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
        filters: dict[str, str | int | float | bool | None],
        namespace: str = "default",
    ) -> list[tuple[str, dict[str, str | int | float | bool | None]]]:
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

### `src/ai_assistant/core/query_parser.py`
```python
"""Single source of truth for RAG query prefix parsing."""

from __future__ import annotations

from ai_assistant.core.constants import RAG_NS_MAP, RAG_PREFIX_RE

__all__ = ["parse_rag_query"]


def parse_rag_query(text: str) -> tuple[str, str]:
    """Extract RAG prefix and return (clean_text, namespace).

    Examples:
        "[p] hello" -> ("hello", "personal")
        "[w] test"  -> ("test", "work")
        "hello"     -> ("hello", "default")
    """
    if not text:
        return ("", "default")

    match = RAG_PREFIX_RE.match(text)
    if not match:
        return (text, "default")

    prefix = match.group(1).lower()
    clean = match.group(2).strip()
    namespace = RAG_NS_MAP.get(prefix, "default")
    return (clean, namespace)

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
            if last_exception is None:
                raise RuntimeError("last_exception is None after retry loop")
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
            if last_exception is None:
                raise RuntimeError("last_exception is None after retry loop")
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
    "get_tokenizer",
    "resolve_api_key",
]

# Named constant for CJK ratio threshold to avoid magic numbers
# CJK-heavy text above this threshold uses len(text) instead of len(text)//4
_CJK_RATIO_THRESHOLD: float = 0.3


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
    model: str, local_dir: str = "./data/tokenizers"
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
    text: str, model: str, local_dir: str = "./data/tokenizers"
) -> int:
    """Count tokens. Fallback to char//4 if no tokenizer available.
    CJK-heavy text (>threshold) falls back to len(text) instead of len(text)//4.
    """
    if not text:
        return 0
    enc = get_tokenizer(model, local_dir=local_dir)
    if enc is None:
        if _cjk_ratio(text) > _CJK_RATIO_THRESHOLD:
            return len(text)
        return len(text) // 4
    try:
        # HF tokenizers: encode() returns Encoding with .tokens
        return len(enc.encode(text).tokens)
    except AttributeError:
        # tiktoken: encode() returns list[int]
        return len(enc.encode(text))
    except Exception:
        if _cjk_ratio(text) > _CJK_RATIO_THRESHOLD:
            return len(text)
        return len(text) // 4


async def async_count_tokens(
    text: str, model: str, local_dir: str = "./data/tokenizers"
) -> int:
    """Async wrapper for count_tokens — offloads CPU-bound tiktoken/HF encoding to thread pool."""
    return await asyncio.to_thread(count_tokens, text, model, local_dir)


async def async_get_tokenizer(
    model: str, local_dir: str = "./data/tokenizers"
) -> Any | None:
    """Async wrapper for get_tokenizer — offloads CPU-bound tokenizer loading to thread pool."""
    return await asyncio.to_thread(get_tokenizer, model, local_dir)

```

### `src/ai_assistant/features/chat/handlers.py`
```python
"""Chat feature HTTP handlers."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import suppress
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

# --- Heartbeat helper -------------------------------------------------------

SSE_HEARTBEAT_INTERVAL: float = 15.0  # seconds


async def _stream_with_heartbeat(
    stream: AsyncIterator[str],
    interval: float = SSE_HEARTBEAT_INTERVAL,
) -> AsyncIterator[str]:
    """Wrap async iterator with SSE heartbeat comments to prevent proxy timeout."""
    queue: asyncio.Queue[str | None | Exception] = asyncio.Queue()

    async def _producer() -> None:
        try:
            async for chunk in stream:
                await queue.put(chunk)
            await queue.put(None)  # EOF sentinel
        except Exception as exc:
            await queue.put(exc)

    task = asyncio.create_task(_producer())
    last_activity = asyncio.get_event_loop().time()

    try:
        while True:
            elapsed = asyncio.get_event_loop().time() - last_activity
            timeout = max(0.1, interval - elapsed)

            try:
                item = await asyncio.wait_for(queue.get(), timeout=timeout)
            except TimeoutError:
                yield ": ping\n\n"
                last_activity = asyncio.get_event_loop().time()
                continue

            if item is None:
                yield "data: [DONE]\n\n"
                return

            # noqa: no-isinstance-in-production  # queue sentinel: str | None | Exception
            if isinstance(item, Exception):
                raise item

            yield f"data: {item}\n\n"
            last_activity = asyncio.get_event_loop().time()

    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


# --- Legacy endpoints (under /api/v1 via wrapper) ---------------------------


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> ChatResponse:
    conv_id = req.conversation_id or str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    _logger.info(
        "Chat handler start",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )
    try:
        response = await state.chat_manager.chat(
            message=req.message,
            conversation_id=conv_id,
            metadata={**req.metadata, "trace_id": trace_id},
        )
    except AdapterError as exc:
        _logger.warning(
            "LLM unavailable",
            extra={"trace_id": trace_id, "error": str(exc)},
        )
        _raise_llm_unavailable(exc)
    except HTTPException:
        raise
    except Exception:
        _logger.exception("Chat failed", extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail="Internal server error") from None
    _logger.info(
        "Chat handler done",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )
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
    _logger.info(
        "Chat stream handler start",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )

    async def _llm_stream() -> AsyncIterator[str]:
        try:
            async for chunk in state.chat_manager.stream_chat(
                message=req.message,
                conversation_id=conv_id,
                metadata={**req.metadata, "trace_id": trace_id},
            ):
                yield chunk
        except AdapterError as exc:
            _logger.warning(
                "LLM unavailable in stream",
                extra={"trace_id": trace_id, "error": str(exc)},
            )
            raise
        except Exception:
            _logger.exception("Stream failed", extra={"trace_id": trace_id})
            raise

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for item in _stream_with_heartbeat(_llm_stream()):
                yield item
        except AdapterError:
            payload = json.dumps(
                {
                    "error": "LLM service temporarily unavailable. Please try again later."
                }
            )
            yield f"data: {payload}\n\n"
        except Exception:
            payload = json.dumps({"error": "Internal server error"})
            yield f"data: {payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# --- OpenAI-compatible endpoints (stay at root /v1/*) ---------------------


@router_oai.get("/v1/models", response_model=OAIModelList)
async def list_models(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> OAIModelList:
    cfg = state.config.llm
    models = cfg.available_models if cfg.available_models else []
    if not models:
        models = [cfg.model]
    return OAIModelList(data=[OAIModel(id=m) for m in models])


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

    if not last_user_msg.strip():
        raise HTTPException(
            status_code=400,
            detail="At least one user message with non-empty content is required.",
        )

    conv_id = str(uuid.uuid4())
    trace_id = uuid.uuid4().hex
    _logger.info(
        "OpenAI handler start",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )
    model_id = req.model if req.model is not None else state.config.llm.model

    if req.stream:

        async def _llm_stream() -> AsyncIterator[str]:
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
                    yield delta.model_dump_json()
            except AdapterError as exc:
                _logger.warning(
                    "LLM unavailable in stream",
                    extra={"trace_id": trace_id, "error": str(exc)},
                )
                raise
            except Exception:
                _logger.exception("OpenAI stream failed", extra={"trace_id": trace_id})
                raise

        async def event_generator() -> AsyncIterator[str]:
            try:
                async for item in _stream_with_heartbeat(_llm_stream()):
                    yield item
            except AdapterError:
                payload = json.dumps(
                    {
                        "error": "LLM service temporarily unavailable. Please try again later."
                    }
                )
                yield f"data: {payload}\n\n"
            except Exception:
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
        _logger.warning(
            "LLM unavailable",
            extra={"trace_id": trace_id, "error": str(exc)},
        )
        _raise_llm_unavailable(exc)
    except HTTPException:
        raise
    except Exception:
        _logger.exception("OpenAI chat failed", extra={"trace_id": trace_id})
        raise HTTPException(status_code=500, detail="Internal server error") from None

    _logger.info(
        "OpenAI handler done",
        extra={"trace_id": trace_id, "conversation_id": conv_id},
    )
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
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.api.deps import InitializedAppState, get_state
from ai_assistant.core.domain.errors import LLM_UNAVAILABLE
from ai_assistant.core.logger import get_logger
from ai_assistant.core.query_parser import parse_rag_query
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
    ReindexRequest,
    SaveChatRequest,
)

__all__ = ["router"]

_logger = get_logger("rag.handlers")

router = APIRouter(prefix="/rag", tags=["rag"])


def _get_rag_manager(
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> RAGManager:
    return RAGManager(
        pipeline=state.pipeline,
        llm=state.llm,
        vector_store=state.vector_store,
        embedder=state.embedder,
        reranker=state.reranker,
        token_margin_min=state.config.rag.token_margin_min,
        token_margin_pct=state.config.rag.token_margin_pct,
        tokenizer_model=state.config.chat.tokenizer_model,
    )


@router.post("/index", response_model=IndexResponse)
async def index_documents(
    req: IndexRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> IndexResponse:
    start = time.perf_counter()
    namespace = req.namespace or state.config.rag.default_namespace
    ns_cfg = state.config.namespaces.get(namespace)

    # -- Per-namespace chunker override (only if size differs from base) --
    chunker = state.chunker
    if ns_cfg is not None and ns_cfg.chunk_size != state.config.chunker.chunk_size:
        base_cfg = state.config.chunker
        ns_chunker_cfg = base_cfg.model_copy(update={"chunk_size": ns_cfg.chunk_size})
        chunker = create_adapter("chunker", base_cfg.provider, ns_chunker_cfg)

    manager = IndexingManager(
        chunker=chunker,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )

    # -- Resource guard: document size --
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

    duration_ms = int((time.perf_counter() - start) * 1000)
    _logger.info(
        "Index documents completed",
        extra={
            "namespace": namespace,
            "indexed_count": result.get("indexed_count", 0),
            "chunk_count": result.get("chunk_count", 0),
            "duration_ms": duration_ms,
            "errors": len(result.get("errors", [])),
        },
    )
    return IndexResponse(**result, namespace=namespace)


@router.post("/query", response_model=QueryResponse)
async def query_rag(
    req: QueryRequest,
    manager: Annotated[RAGManager, Depends(_get_rag_manager)],
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> QueryResponse:
    start = time.perf_counter()
    cfg = state.config.rag
    ns = req.namespace or cfg.default_namespace
    query_text = req.query

    # Fallback: if namespace not explicitly set, try parsing from query text
    if ns == cfg.default_namespace:
        parsed_text, parsed_ns = parse_rag_query(req.query)
        if parsed_ns != "default":
            query_text = parsed_text
            ns = parsed_ns

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
        query_text=query_text,
        top_k=req.top_k or cfg.top_k,
        prompt_name=prompt_name,
        prompt_version=req.prompt_version or cfg.prompt_version,
        namespace=ns,
        relevance_threshold=relevance_threshold,
    )
    duration_ms = int((time.perf_counter() - start) * 1000)
    _logger.info(
        "RAG query completed",
        extra={
            "namespace": ns,
            "query_len": len(query_text),
            "chunks_used": result.get("chunks_used", 0),
            "duration_ms": duration_ms,
            "errors": len(result.get("errors", [])),
        },
    )
    for err in result.get("errors", []):
        if err.startswith(LLM_UNAVAILABLE):
            raise HTTPException(
                status_code=503,
                detail="LLM service temporarily unavailable. Please try again later.",
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

    # Save to chat exports folder
    exports_root = Path(state.config.rag.chat_exports_root)
    folder = exports_root / namespace
    folder_resolved = await asyncio.to_thread(folder.resolve)
    docs_resolved = await asyncio.to_thread(exports_root.resolve)

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
                        "source": str(Path(namespace) / filename),
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
    req: ReindexRequest,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> dict[str, Any]:
    """Reindex documents from folders. Returns immediately, runs in background."""
    folder = req.folder
    clear = req.clear
    task_id = str(uuid.uuid4())
    rag_state = state.rag_state

    async def _run() -> dict[str, Any]:
        async with rag_state.semaphore:
            await rag_state.cleanup_status()
            async with rag_state.lock:
                rag_state.status[task_id] = {
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
                    documents_root=Path(state.config.rag.documents_root),
                )
                async with rag_state.lock:
                    rag_state.status[task_id] = {
                        "status": "completed",
                        "result": result,
                        "finished_at": time.time(),
                    }
                return result
            except Exception:
                _logger.exception("Background reindex failed")
                async with rag_state.lock:
                    rag_state.status[task_id] = {
                        "status": "failed",
                        "error": "Internal server error",
                        "finished_at": time.time(),
                    }
                raise
            finally:
                rag_state.tasks.pop(task_id, None)

    task = asyncio.create_task(_run())
    task.add_done_callback(lambda _: rag_state.tasks.pop(task_id, None))
    rag_state.tasks[task_id] = task
    return {"status": "started", "task_id": task_id}


@router.get("/reindex/status/{task_id}", response_model=None)
async def reindex_status(
    task_id: str,
    state: Annotated[InitializedAppState, Depends(get_state)],
) -> dict[str, Any]:
    """Get status of a background reindex task."""
    rag_state = state.rag_state
    await rag_state.cleanup_status()
    async with rag_state.lock:
        if task_id in rag_state.status:
            info = rag_state.status[task_id]
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
    "ReindexRequest",
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


class ReindexRequest(BaseModel):
    """Request to reindex documents from folders."""

    folder: str | None = Field(
        default=None, description="Specific folder to index, or None for all."
    )
    clear: bool = Field(
        default=False, description="If True, clear existing chunks before indexing."
    )

```

## 🧩 API Signatures

### `run_scripts.py`
```python
# API: run_scripts.py

import json
import os
import subprocess
import sys
import time
from pathlib import Path
def get_python(root: Path):

def collect(root: Path, subdir: str):

def _sort(files: list[Path]):

def _fmt_duration(seconds: float):

def _fmt_ago(timestamp: float):

def _get_docstring(path: str):

def _load_history(root: Path):

def _save_history(root: Path, history: dict[str, dict[str, object]]):

def print_menu(scripts, history, last, last_time):

def run(py, target, root, extra, history):

def main():

```

### `run_servers.py`
```python
# API: run_servers.py

from __future__ import annotations
import contextlib
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
def _ensure_venv():

def _reexec_if_needed():

import yaml
def _run(cmd: list[str], log: Path | None=None, **kwargs):

def port_free(port: int):

def wait_port(port: int, timeout: float=30.0):

def _find_exe(name: str):

def _find_model(name: str):

def _load_config():

def _wait_for_stop():

def start():

def stop():

def kill_main():

def _pause_on_error():

def main():

```

### `src/ai_assistant/__init__.py`
```python
# API: src/ai_assistant/__init__.py

```

### `src/ai_assistant/adapters/__init__.py`
```python
# API: src/ai_assistant/adapters/__init__.py

from __future__ import annotations
from ai_assistant.adapters._registry import register
from ai_assistant.adapters.factory import create_adapter
```

### `src/ai_assistant/adapters/_registry.py`
```python
# API: src/ai_assistant/adapters/_registry.py

from __future__ import annotations
from collections.abc import Callable
def register(port: str, name: str):
    """Register an adapter class under a port and name.

Usage:
    @register("llm", "mock")
    class MockLLM(ILLM): ..."""

def get_registry():
    """Return a shallow copy of the registry for inspection."""

```

### `src/ai_assistant/adapters/chunker_simple.py`
```python
# API: src/ai_assistant/adapters/chunker_simple.py

from __future__ import annotations
import uuid
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import ChunkerConfigData
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
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import EmbedderConfigData
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
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import EmbedderConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.logger import get_logger
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
from ai_assistant.adapters._registry import get_registry, register
from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.embedder_openai_compatible import OpenAICompatibleEmbedder
from ai_assistant.adapters.llm_mock import MockLLM
from ai_assistant.adapters.llm_openai_compatible import OpenAICompatibleLLM
from ai_assistant.adapters.reranker_api import APIReranker
from ai_assistant.adapters.reranker_null import NullReranker
from ai_assistant.adapters.storage_sqlite import SQLiteStorage
from ai_assistant.adapters.vector_store_faiss import FaissVectorStore
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
def create_adapter(port: str, name: str, config: Any):
    """Create an adapter instance by port and name via registry lookup.

Args:
    port: Port category (e.g., "llm", "embedder").
    name: Adapter identifier (e.g., "mock", "openai_compatible").
    config:"""

```

### `src/ai_assistant/adapters/llm_mock.py`
```python
# API: src/ai_assistant/adapters/llm_mock.py

from __future__ import annotations
from typing import TYPE_CHECKING
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import LLMConfigData
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
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import LLMConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import AssistantMessage, ToolMessage, UserMessage
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
from typing import TYPE_CHECKING
import httpx
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import RerankerConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.logger import get_logger
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

### `src/ai_assistant/adapters/reranker_null.py`
```python
# API: src/ai_assistant/adapters/reranker_null.py

from __future__ import annotations
from typing import TYPE_CHECKING
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import RerankerConfigData
from ai_assistant.core.ports.reranker import IReranker, RerankResult
class NullReranker(IReranker):
    """No-op reranker that returns chunks unchanged."""

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
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import StorageConfigData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.storage import IChatStorage, ISettingsStorage
def _safe_json_loads(value: str | None, default: Any):

class SQLiteStorage(IChatStorage, ISettingsStorage):
    """Combined chat and settings storage."""

```

### `src/ai_assistant/adapters/vector_store_faiss.py`
```python
# API: src/ai_assistant/adapters/vector_store_faiss.py

from __future__ import annotations
import asyncio
import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any
import anyio
import numpy as np
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import VectorStoreConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.io_utils import atomic_write
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.vector_store import IVectorStore
class _NamespaceData:
    """Per-namespace runtime state."""

def _chunk_to_dict(chunk: Chunk):
    """Serialize Chunk to dict (strict, no extra fields)."""

def _chunk_from_dict(data: dict[str, Any]):
    """Deserialize dict to Chunk (strict, matches domain model)."""

class FaissVectorStore(IVectorStore):
    """FAISS-backed vector store with namespace support."""

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
from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import VectorStoreConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import AdapterError, VersionMismatchError
from ai_assistant.core.io_utils import atomic_write
from ai_assistant.core.logger import get_logger
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
import os
import re
import time
from typing import TYPE_CHECKING, Any
from ai_assistant.core.constants import FROZEN_NO_INFO_PHRASES
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.domain.messages import AssistantMessage, UserMessage
from ai_assistant.core.domain.pipeline import PipelineData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.prompts import get_prompt
from ai_assistant.core.query_parser import parse_rag_query
from ai_assistant.core.utils import async_count_tokens
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

def _discover_documents(folder: str | None=None, max_file_size: int | None=None, documents_root: Path | None=None):
    """Discover documents in folders. Returns {namespace: [docs]}."""

async def index_folder(folder: str | None, clear: bool, chunker: Any, embedder: Any, vector_store: Any, max_file_size: int | None=None, documents_root: Path | None=None):
    """Index documents from disk folders directly into vector store.

Args:
    folder: Specific folder to index, or None for all.
    clear: If True, clear existing chunks in each namespace before indexing."""

```

### `src/ai_assistant/features/rag/manager.py`
```python
# API: src/ai_assistant/features/rag/manager.py

from __future__ import annotations
import time
import uuid
from dataclasses import replace
from typing import TYPE_CHECKING, Any
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata, Document
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
import os
from typing import Annotated, Any
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ai_assistant.api.deps import InitializedAppState, get_state
from ai_assistant.api.lifespan import lifespan as _default_lifespan
from ai_assistant.api.middleware import MetricsMiddleware
from ai_assistant.api.router import assemble_routers
from ai_assistant.core.config import CORSConfig, SecurityConfig, load_config
class _InfoResponse(BaseModel):

def _load_cors_config(state: InitializedAppState | None):
    """Return CORS config from state or fallback to safe defaults."""

def create_app(state: InitializedAppState | None=None, lifespan: Any=None):
    """Application factory — creates a fresh FastAPI instance."""

```
