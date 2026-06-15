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

**FIND/REPLACE format:** Always include 2-3 lines of unchanged context before and after. Use strict markers:
```python
<<<<<<< FIND
def old_function():
    pass
===
def new_function():
    # new logic
    pass
>>>>>>> REPLACE
```
If the change exceeds 15 lines, output the full file content or split into multiple small blocks.

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

## FastAPI DI and Ruff type-checking rules

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
