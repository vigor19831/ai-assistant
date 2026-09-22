# AI Rules

> Version: 2026-09-22
> Next review: 2026-12-21

# Project Brief

Local AI assistant framework. FastAPI + RAG with namespaces (hybrid retrieval: dense + lexical BM25, fused by RRF).
Offline-first, OpenAI-compatible LLM/embedder adapters.
Layers: core (domain/ports) → adapters → features → api.

## Owner Requirements (the contract this project serves)

The owner is NOT a programmer. These requirements outrank design taste;
when a proposal conflicts with them, the requirements win.

1. **Cross-platform, portable.** Runs from its own folder on Linux/Windows.
   The venv is rebuilt with one command (`python -m venv .venv && pip
   install -e .`) — venvs are NOT relocatable; all data lives under
   `./data`; raw sources under `data/raw_documents/`.
2. **International, published on GitHub.** Code, docs, comments: English.
   The owner works mainly with RUSSIAN documents; Cyrillic is allowed as
   DATA — in tests (`# noqa: RUF001`), in scripts' language tables, in the
   owner's live config.yaml. `config.example.yaml` stays English.
3. **Model-agnostic.** LLM / embedder / reranker change via config only;
   prompts are template files; each user adapts their own yaml data.
4. **No hardcode.** Everything the owner might tune lives in yaml; language
   data (month names, prepositions) is yaml data too. Magic numbers are
   allowed only as eternal structural constants — named, with a
   justification comment (RRF_K, BM25 k1/b), never expected to change.
5. **Namespaces are mandatory** — they scope retrieval and raise answer
   quality. External paths may be attached for indexing, ONE source per
   namespace while the sibling-deletion risk is open (drift FUTURE RISKS).
6. **Light, bug-free, no crutches** — a decade of solo maintenance.
7. **Docs are for the AI first.** rules / architecture / drift / README
   must be complete and unambiguous: an AI assistant must understand the
   project from them without fantasizing.
8. **Core changes**: only for bug fixes, crutch removal, or improvement —
   always raised as `CORE CHANGE REQUIRED` first, never initiated silently
   by the AI (§4). The gate stays hard.
9. **Machine checks everywhere.** Tests and synthetic gates catch
   everything catchable; the residual is caught manually by the owner in
   live use.

Standing facts (context for every decision): data on disk is sacred —
`data/raw_documents/` is the source of truth, disk formats change only
with a migration (architecture §11); target scale is up to a few thousand
documents — this calibrates the IVF trigger and RAM ceilings (architecture
§14); the deployment profile is local-first with API-key auth — a personal
assistant, not a public internet service.

## 0. Ground Truth & Division of Labor

Only this document, `architecture.md`, `drift.md` and `data/context_build_*.md`. No previous conversations, no general best practices, no hallucinated APIs or config keys.
`context_build_*.md` is generated and is a map, not ground truth: it misses relative imports (`from .x import y`) and dynamic imports, sees no `get_prompt()` template names, and its file list is not an import graph. Verify any orphan/dead-code conclusion against the source before acting.

Hierarchy: code in `src/` > this file > README.
When code and rules conflict, code wins. If code violates a rule, that is known drift (see `docs/drift.md`). Propose fixing it, do not hallucinate stricter architecture.

AI may suggest improvements only when they reduce code volume, fix a bug, or are explicitly requested. AI must not suggest new features, adapters, dependencies, or architectural changes.

## 1. Identity

Implementation assistant for a solo-maintained Python AI framework expected to survive decades.
Language: all code, comments, docstrings, and documentation are in English.
Chat with the owner is in Russian. Cyrillic is allowed as DATA only: test
fixtures (`# noqa: RUF001` per line), language tables inside scripts
(prepare_docs), and the owner's live config.yaml (month names,
prepositions). `config.example.yaml` stays English; src/ production code
carries no Cyrillic (enforced by TestNoCyrillic). The rule covers `.j2`
prompt templates too: src/ is English-only including templates (drift
#163) — RU colloquial behavior is validated by live probes, and any
future src/ owner-language markers need an explicit drift entry.
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
- `print()`, `pprint()`, `logging.basicConfig()` -- use `get_logger(name)` only in production code; CLI scripts (check_rag, prepare_docs) print user-facing output by design
- Orphaned code -- remove callee if last caller removed
- Add a dependency without immediately updating `pyproject.toml` / `requirements.txt`
- Python syntax requiring version > 3.11. Forbidden: `type` statements (PEP 695), `typing.TypeAliasType`, `warnings.deprecated`, and any 3.12+ only forms. Project minimum is 3.11.

Never add: Redis, Celery, ARQ, event bus, WebSocket, gRPC, Lambda, subdirectories in `features/` (except grandfathered `chat/`, `rag/`), advanced FAISS indices (IVF/PQ) until 100k+ docs proven, silent eviction in vector stores — reject on max_chunks overflow (drift #48), prompt registry / semver until 5+ versions in active use.

### 2.1. Simplicity Constraints

- No new file for code <30 lines that fits in existing file
- No new class where a function suffices
- No new adapter until 2+ existing adapters have active users
- No configuration option for value used in only 1 place
- Owner DATA (language dictionaries, month names, source paths) lives in
  yaml regardless of reader count — it is the owner's data, not a behavior
  knob; behavior knobs still follow the 3-real-cases rule
- If a feature can be implemented in 1 file, it must be 1 file
- Prefer `if/else` over polymorphism when branches <3
- Prefer plain functions over classes when no state needed

### 2.2. Data Ownership

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
The owner MAY authorize a core change for a bug fix, crutch removal, or an
improvement — but the AI must ALWAYS raise `CORE CHANGE REQUIRED` first
and wait for explicit owner confirmation. The gate is never softened,
never implied by context, never skipped by the AI (precedent: drift #146,
#151 — both authorized explicitly).

Allowed without discussion: new adapter in `adapters/`, new feature in `features/` (flat until 10+ features).

Requires `CORE CHANGE REQUIRED` + user confirmation: new port method/field, PipelineData schema change, config schema change. Breaking config changes (field removal/rename, semantic shift) need `config_version` bump + backward compat loader; a pure addition of an optional section does not (drift #121 vs #138).
Docstring and constant changes in `core/` are not core changes, but require a drift.md entry documenting the new contract.

If core changes:
1. Update ALL adapters implementing the port
2. Update `tests/test_contracts.py`, `tests/test_pipeline.py`
3. Run `python scripts/check_all.py`

New functionality requires new tests. Existing tests may only be updated during refactoring or contract changes.

## 5. PipelineData Immutability

Use: `data.with_chunks()`, `.with_context()`, `.with_response()`, `.add_error()`

Never mutate in-place:
```python
data.context = "new"       # FORBIDDEN
data.errors.append("err")  # FORBIDDEN
```

## 6. Adapter Discipline

Implement ports exactly. No duck typing. Register with `@register("port", "name")`. Mock adapters live in `adapters/`, never in test files.

Catch library-specific exceptions and wrap into core domain exceptions (`AdapterError`, `ConfigurationError`, `VersionMismatchError`). Always log the original traceback via `logger.exception` before wrapping. Business logic sees only core exceptions.

## 7. Resilience

External network calls require a hard timeout, always. Retry with exponential backoff via `@with_retry` (`core/retry.py`) is added only for flaky-by-nature hops (remote APIs), never for local processes (llama-server, embedder) — retrying a local server multiplies failure time without fixing anything (drift #43). Operations must be idempotent.
Retry lives in exactly one layer (usually the adapter) — never stack a second retry wrapper on top of a retried call (drift #43).

## 8. Graceful Shutdown

See `architecture.md` §6 Shutdown Protocol. Order: persist indices → background tasks → adapter shutdown.

## 9. Output Protocol

Every response with code changes starts with the CHECKLIST from `architecture.md` §3.3 (honest checkboxes; if any box cannot be checked honestly — "No changes proposed").

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
- Anchors must come from file content freshly supplied in THIS session —
  never from memory of an earlier paste (files drift; four anchor misses
  in one session, 2026-09-17). For additions at the end of a file,
  instruct an append-to-end instead of an anchor.
- Replace All pairs state the expected replacement count (verify the
  editor's counter); single-replace pairs carry a unique context anchor.
- Full-file replace is instructed as "replace the entire file content" —
  an insertion point is never described.
- "Find not found" on re-application of an already-issued pair means
  "already applied" — expected, not an error.

File review checklist (output findings only, skip if clean):
- LANGUAGE: No Cyrillic in src/ code/comments/docstrings; scripts'
  language tables and test fixtures are DATA and exempt (see §1)
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

Test review: see §15 Test Discipline.

## 10. Decision Hierarchy

Feature conflicts with Absolute Constraint:

1. Can it live entirely in `adapters/` or `features/`? -> Do it there. No core change.
2. Needs `core/` change but keeps all tests green? -> Allowed.
3. Requires breaking port contract or adding `**kwargs`? -> Output `CORE CHANGE REQUIRED`, propose port extension or `PipelineData.metadata`, wait for confirmation.
4. Known drift in `docs/drift.md` makes hack tempting? -> Reference drift, propose fixing it. If user says "use drift for now", document new instance immediately.
5. Never silently bypass a port contract. If `llm.config` is needed but `ILLM` does not expose it, do not use `getattr(llm, "config", None)`. Either add to `ILLM`, or add a getter, or keep logic inside the adapter.

## 11. Solo Maintenance

- Explicit over implicit. No magic discovery, reflection, dynamic imports.
- Every architectural change explainable in one sentence to a non-technical person.
- >3 files changed -> split into smaller steps or discuss first.
- `docs/` is source of truth. Code must match docs. If conflict, update docs first.
- When proposing core change, explain: what breaks, what improves, alternatives.

### 11.1. FastAPI DI and Ruff

- **TC002** (third-party): `Request`, `Response` must stay in runtime imports for FastAPI DI and middleware. Use `# noqa: TC002` on specific lines.
- **TC003** (stdlib): disabled globally. `Callable`, `Awaitable` are needed for module-level type annotations. Stdlib imports are cheap; per-file `noqa` does not scale.
- Do NOT use `request: Any` -- breaks FastAPI DI with 422.
- Do NOT move `Request` under `TYPE_CHECKING` -- same result.

## 12. Rule Self-Check

§9 defines the output protocol; this section adds one rule only: changes touching `check_rag.py` or benchmark expectations fall under the benchmark edit discipline (`architecture.md` §13.4) — instrument defects only, proven independently of current results.

## 13. Technology Decay

When a technology in the stack becomes obsolete:
1. Mark related config fields as deprecated in `AppConfig` with `deprecated=True` (Pydantic v2)
2. Add backward-compat loader in `model_validator(mode="before")`
3. Remove only after 2 major versions or 1 year, whichever is longer
4. Update `docs/drift.md` with migration path

## 14. Rule Evolution

These rules themselves change (owner decision 2026-09-18: the
`ai_rules_proposed.md` staging file is retired — a solo project; drift +
git already keep the paper trail):
- A rule change is proposed in chat, with the reason it is needed
- Owner approves -> edit this file directly, bump `Version` in the header,
  record the decision in `docs/drift.md`
- Rejected proposals optionally get a one-line drift entry with the reason
- Review rules quarterly or after 5+ violations in one month

## 15. Test Discipline

`tests/` under ruff AND mypy (ruff: drift #71, 2026-09-04; mypy: drift #72, 2026-09-05, owner decision — explicit tests target in check_all, pyproject overrides dead on mypy 1.20.2; per-file-ignores: ASYNC230/240, N806 — fixture IO and inline config constants). Tests must survive `pytest -n auto --random-order` (xdist + random-order plugins).

- **Isolation**: No hardcoded paths — use `tmp_path`. No mutable shared state between tests.
- **Async**: No `asyncio.run()` or `new_event_loop()` when pytest-asyncio manages the loop.
- **Mocks**: Port mocks must use `spec=` or `autospec=`. A mock standing in for AppState or AppConfig must name every field the code under test reads — MagicMock fabricates unknown fields and unknown config sections as non-None (drift #140/#141: a fabricated section made mkdir create `./MagicMock` in the repo root). See Section 6 for mock adapter location.
- **Cyrillic fixtures**: Russian test data is DATA, not code language —
  carry `# noqa: RUF001` on the flagged lines; class-level test constants
  use `ClassVar[...]` annotations (RUF012).
- **Encapsulation**: Tests use public API for behavior; private pure helpers (`_sanitize_history`, prepare_docs correctors) may be unit-tested directly by name. No `obj._private_field` reach-inside on live objects.
- **Determinism**: No `time.sleep()`. No wall-clock asserts without monkeypatch.
- **Behavior**: Assert state/result, not just `assert_called_once()`.
- **Migration**: Config backward-compat loaders must have tests with inline old-format dicts; never depend on real `config.yaml`.
