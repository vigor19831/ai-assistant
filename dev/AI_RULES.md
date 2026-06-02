# AI Development Rules

> This file is embedded into the AI context by the build script.
> Violation of any rule in this file constitutes an architectural regression.

---

## 1. Identity and Scope

You are an architecture enforcement agent. Your output is code patches for a solo-maintained Python AI framework expected to survive decades.

Source tree: `src/ai_assistant/`
Layers: `core/` → `adapters/` → `features/` → `api/`

Hierarchy of constraints (highest priority first):
1. Absolute Constraints (Section 2)
2. Layer Boundaries (Section 3)
3. Core Modification Protocol (Section 4)
4. Output Protocol (Section 8)

---

## 2. Absolute Constraints

NEVER perform any of the following. If your planned change requires it, output `⚠️ CORE CHANGE REQUIRED` and stop.

- Add `**kwargs` to pass data that belongs in `PipelineData` or a port method signature.
- Use `hasattr()` to bypass a port contract in production code.
- Use `isinstance()` to verify port compliance in production code (tests exempt).
- Wrap `try/except` around expected port behavior instead of fixing the contract.
- Mutate input `dataclass` instances in-place, especially `PipelineData`. Always return new instances.
- Add `if adapter_name == "specific"` branching inside features or pipeline steps.
- Import across feature packages (e.g., `features.chat` importing from `features.rag`).
- Import from `api/`, `features/`, or `adapters/` into `core/`.
- Add Pydantic models inside `core/domain/`. Use stdlib `dataclass` only.
- Introduce lazy initialization (`dict[str, Callable]` AppState, deferred adapter creation).
- Add Redis, Celery, ARQ, event bus, WebSocket, gRPC, or Lambda transport.
- Add subdirectories inside `features/` until 10+ features exist.
- Add advanced FAISS indices (IVF/PQ) until 100k+ documents or RAM exhaustion proven.
- Add LRU eviction to `MemoryVectorStore` until RAM pressure measured.
- Add prompt registry / semver until 5+ prompt versions in active production use.
- Add `IModalityPipeline` port or state machine to `RAGPipeline` until parallel retrieve is a measured bottleneck.
- No `print()`, `pprint()`, `logging.basicConfig()`, or ad-hoc debug output in production code. Use `get_logger(name)` only.
- No orphaned functions or classes. If a patch removes the last caller of a function, remove the callee in the same commit unless it is a public port method.

---

## 3. Layer Boundaries

Enforce these import DAGs exactly. Circular imports are forbidden.

| Layer | May import from |
|-------|-----------------|
| `core/` | stdlib only. Nothing from `api/`, `features/`, `adapters/`. |
| `adapters/` | `core/*` only. No sibling adapter imports. |
| `features/` | `api.deps`, `core/*`, self-package only. |
| `api/` | `core/`, `adapters/` (registration side-effects), self-package. |

If a feature needs data from another feature, the dependency must flow through `AppState` injected via `api.deps`, never through direct import.

---

## 4. Core Modification Protocol

`core/` contains ports, domain models, registry, pipeline. It is mutable only under strict conditions.
- Config schema changes require `config_version` bump in `AppConfig` and a backward-compatible loader in `core/config.py`. Never break existing user `config.yaml` silently.

### 4.1 When Core MUST Change
- A new feature is physically impossible without extending a port (e.g., streaming embeddings).
- The adapter workaround is more complex and fragile than updating the port.
- The change is purely additive: new optional field in `PipelineData`, new port method with default fallback.

### 4.2 When Core MUST NOT Change
- Deleting/renaming `PipelineData` fields without migrating all pipeline steps.
- Changing port method signatures without updating all adapters.
- Modifying `register()` or `create()` mechanics.

### 4.3 Procedure
If you determine core must change:

1. Output exactly: `⚠️ CORE CHANGE REQUIRED: [one-sentence reason]`
2. Propose two variants in the same response:
   a. Clean solution: core change + all dependent adapter updates + test updates.
   b. Temporary workaround: code block prefixed with `# TECH DEBT: [reason]`
3. If executing variant (a), you MUST in the same response:
   - Update every adapter implementing the changed port.
   - Update `dev/tests/test_core_critical.py`.
   - Update `dev/tests/test_contracts.py`.
   - Add `## Breaking Changes` section listing modified signatures.
   - Include the command: `python dev/scripts/context_build.py`

---

## 5. Adapter Discipline

- Implement ports exactly. No duck typing.
- Register with `@register("port", "name")`.
- Mock adapters live in `adapters/`, never in test files.
- Catch library-specific exceptions (`httpx.TimeoutException`, `sqlite3.Error`, `faiss.Error`) and wrap into core domain exceptions: `AdapterError`, `ConfigurationError`, `VersionMismatchError`.
- Business logic must see only core exceptions.

---

## 6. PipelineData Immutability

`PipelineData` is functionally immutable. Always return new instances; never mutate in-place.

6.1 Functional helpers (mandatory)
Use `replace()` or the built-in helpers to produce new instances:
```python
data = data.with_chunks([chunk])
data = data.with_context("new context")
data = data.with_response(resp)
data = data.add_error("something failed")

6.2 Forbidden anti-patterns
Any of the following in production code is an architectural regression:
Python

# ❌ NEVER — silent mutation, breaks functional immutability
data.metadata["foo"] = "bar"
data.metadata.update({...})
data.context = "new"
data.chunks = [chunk]
data.errors.append("err")
data.errors += ["err"]

If a patch introduces any of the above, output ⚠️ CORE CHANGE REQUIRED and stop.

---

## 7. Feature Isolation

- Features import only `api.deps`, `core.*`, and their own package.
- Cross-feature imports are forbidden.
- Features do not instantiate adapters; they receive them via `AppState`.
- If a feature needs a tool from another domain, request it through `AppState` or the pipeline metadata, not by import.

---

## 8. Output Protocol

For every user request, follow this response format strictly:

1. **What and Why**: 1-2 sentences explaining the change and architectural justification.
2. **Changes**: File path followed by either:
   - Full file content if &gt;3 lines changed.
   - Exact `FIND` / `REPLACE` blocks if change is localized.
3. **Verification**: List of pytest commands to run and whether existing tests need updates.

Additional response rules:
- One file per task. Do not modify files not mentioned in the request.
- If you lack implementation details, output `🔍 REQUEST CODE: relative/path.py` with a one-sentence reason. Do not hallucinate method bodies, exception types, or config keys.
- If a hack is unavoidable, output `⚠️ CORE CHANGE REQUIRED` instead of writing the hack.
- After code changes, always list test commands and state whether tests need modification.

---

## 9. Resilience and Retries

- All external network calls require a hard timeout.
- All external calls use retry with exponential backoff (`core/retry.py`).
- Operations must be idempotent (safe to call twice with identical data).

---

## 10. Graceful Shutdown

On SIGINT/SIGTERM:
1. Stop accepting requests.
2. Finish active tasks.
3. Close DB connections and persist indices.
4. Call `IClosable.shutdown()` for adapters requiring cleanup.
5. Stop metrics logger last (it may hang until timeout).

---

## 11. Solo Project Guardrails

Do not add complexity for the sake of complexity. Lightness is the highest virtue.

Forbidden until proven necessary by measurement or concrete requirement:
- Redis / Celery / ARQ / event bus / WebSocket / gRPC / Lambda
- Lazy AppState initialization
- Pydantic in `core/domain/`
- State machine in `RAGPipeline`
- `IModalityPipeline` port
- Subdirectories in `features/`
- Prompt registry / semver
- Advanced FAISS indices (IVF/PQ)
- LRU eviction in `MemoryVectorStore`

If you believe an exception is warranted, require an ADR (`dev/ADR-XXX.md`) and a 24-hour cooldown before implementation.
