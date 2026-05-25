# AI Development Rules

&gt; **AI Context:** This file is auto-extracted by `context_build.py` into `context_build.md` as the `## AI Development Guidelines` block.

## Sacred Core Policy
`src/ai_assistant/core/` contains contracts: ports, domain models, registry, pipeline.  
**Core changes are allowed** when they produce a cleaner solution than an adapter workaround.  
**Mandatory:** Any core change must include updates to all dependent adapters in the same solution.

## Red Flags — Stop and Propose Core Change
If you catch yourself doing any of the following in an adapter or feature:
- Using `**kwargs` to pass data that should be typed in `PipelineData`
- `hasattr()` checks to bypass a port contract
- `try/except` around expected port behavior
- Ignoring a port's return type or mutating input dataclasses in-place
- Adding `if adapter_name == "specific"` branching inside a feature

→ **Stop.** This means the core contract is insufficient.  
**Propose a core change** instead of hacking around it. Output: `⚠️ CORE CHANGE REQUIRED: [reason]`

## Adapter Discipline
- Implement ports exactly. No duck typing.
- Register with `@register("port", "name")`.
- Mock implementations live in `adapters/`, not in test files.
- Adapters must not depend on other adapters' internals.
- Adapters may depend only on `core.*` and third-party libraries.

## Feature Isolation
- Features (`chat`, `rag`, `image_analysis`) import only from `api.deps`, `core.*`, and their own package.
- Cross-feature imports are forbidden.
- Features do not instantiate adapters directly; they receive them via `AppState`.

## When Core Must Change
- A new feature is physically impossible without extending a port (e.g., streaming embeddings).
- The workaround in an adapter is more complex and fragile than updating the port.
- The change is additive (new optional field in `PipelineData`, new method in a port with default fallback).

## When Core Must NOT Change
- Deleting or renaming fields in `PipelineData` without migrating all pipeline steps.
- Changing method signatures in ports without updating all adapters.
- Modifying `register()` / `create()` mechanics.

## Procedure: Changing Core
1. Output: `⚠️ CORE CHANGE REQUIRED: [reason]`
2. Propose 2 variants:
   a. Clean solution via Core + dependency updates in the same response
   b. Temporary workaround with `# TECH DEBT: [reason]`
3. If changing Core, mandatory:
   - Update all adapters using the changed port
   - Update `test_core_critical.py`, `test_contracts.py`
   - Add `## Breaking Changes` section in response
   - Run `python dev/scripts/context_build.py`

## Solo Project Guardrails — What Not To Do
&gt; These constraints exist to keep the project maintainable by a single developer for decades.  
&gt; Do not violate them without an ADR (`dev/ADR-XXX.md`) and a 24-hour cooldown.

### Infrastructure & Concurrency
- **No lazy AppState (`dict[str, Callable]`)** — eager init gives fail-fast at startup. Critical for solo operation.
- **No Redis / Celery / ARQ** — `asyncio.Queue` or `asyncio.create_task()` are sufficient for a local framework. Add a broker only when `Queue` is proven insufficient under real load.
- **No event bus / state manager / WebSocket / gRPC / Lambda transport** — until a concrete multi-instance or transport requirement exists.

### Core & Domain
- **No Pydantic in `core/domain/`** — sacred core must have zero external dependencies. Use `dataclass` from stdlib.
- **No state machine in `RAGPipeline`** — sequential runner covers 95 % of cases. Upgrade only when parallel retrieve is a real, measured bottleneck.
- **No `IModalityPipeline` port in `core/ports/`** — premature abstraction. Features are already isolated by the "no cross-feature imports" rule. Add a coordination port only when 2+ features genuinely duplicate the same orchestration logic.

### Features & Adapters
- **No hierarchy in `features/` (subdirectories)** — keep flat structure until 10+ features force grouping.
- **No prompt registry / semver** — until 5+ prompt versions are actively used in production.
- **No advanced FAISS indices (IVF/PQ)** — until index exceeds 100k documents or RAM is demonstrably exhausted.
- **No LRU eviction in MemoryVectorStore** — until RAM pressure is measured and confirmed.

### Meta
- **Never add complexity for the sake of complexity** — lightness is the highest virtue in a solo project.