# AI Rules
> Version: 2026-06-24
> Next review: 2026-09-20

# Project Brief
Local AI assistant framework. FastAPI + RAG with namespaces.
Offline-first, OpenAI-compatible LLM/embedder adapters.
Layers: core (domain/ports) → adapters → features → api.

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

## 2.2. Data Ownership
Port objects own their configuration. Callers pass port objects, not port config fields.
PipelineData contains only runtime state. Config values live in PipelineConfig or port objects.

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

### Test review checklist (output findings only, skip if clean):
- ISOLATION: No hardcoded paths, no mutable shared state, no mutable module-level globals
- ASYNC: No `asyncio.run()` or `new_event_loop()` when pytest-asyncio manages the loop
- MOCKS: Port mocks use `spec=` or `autospec=`
- ENCAPSULATION: No access to `_private` fields in assertions
- DETERMINISM: No `time.sleep()`, no wall-clock asserts without monkeypatch
- BEHAVIOR: Asserts state/result, not just mock call counts

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
- [ ] No rule from Section 15 (Test Discipline) violated, if tests are changed
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

## 15. Test Discipline

`tests/` excluded from ruff/mypy, but not from architecture. Tests must survive `pytest -n auto`, `--reverse`, `--random-order`.

- **Isolation**: No hardcoded paths — use `tmp_path`. No mutable shared state between tests.
- **Async**: No `asyncio.run()` or `new_event_loop()` when pytest-asyncio manages the loop.
- **Mocks**: Port mocks must use `spec=` or `autospec=`. See Section 6 for mock adapter location.
- **Encapsulation**: Tests use public API only. No `obj._private_field` in assertions.
- **Determinism**: No `time.sleep()`. No wall-clock asserts without monkeypatch.
- **Behavior**: Assert state/result, not just `assert_called_once()`.
