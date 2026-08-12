# Architecture

> Version: 2026-08-12
> Companion to: ai_rules.md
> Purpose: Prevents AI from proposing architectural changes that create hidden problems; defines RAG philosophy and core principles.

---

## 1. Project Identity (Non-Negotiable)

- **offline-first**: Core works without cloud
- **solo-maintained**: One human, 10+ years. Every change must be explainable in one sentence to a non-programmer
- **immutable core**: `core/` changes only when physically impossible otherwise
- **AI is implementation assistant, not architect**: AI proposes code only. Architecture decisions belong to the human

---

## 2. RAG Philosophy

> Every answer must be traceable to evidence. Every engineering decision must be traceable to a principle.

### 2.1. Purpose

Build a production-grade RAG system that is simple, maintainable, and explainable, while achieving state-of-the-art answer quality. Every architectural decision must improve quality, maintainability, observability, or extensibility.

### 2.2. Core Principles

**Retrieval is Recall**
The retriever finds potentially useful information. It does not reason, filter answers, or make decisions.

**Ranking is Ordering**
The reranker only orders retrieved candidates. It never decides whether the model should answer.

**Context is Evidence**
Context is evidence, not an answer. The pipeline provides evidence; the LLM performs reasoning.

**LLM Owns Reasoning**
The pipeline should never simulate reasoning with heuristics. If the context is insufficient, the LLM should conclude that no supported answer exists.

### 2.3. Separation of Responsibilities

Each pipeline stage has exactly one responsibility.

```text
Retrieve → Rerank → Build Context → Generate
```

Business logic must not leak across stage boundaries.

### 2.4. Evidence First

Answers must be grounded in retrieved evidence, not model confidence. Unsupported claims are considered failures.

### 2.5. Stable Contracts

Components communicate only through explicit, stable contracts. Implementations may change; contracts should remain stable.

### 2.6. Simplicity Over Complexity

Prefer small, understandable improvements over clever architectures. Complexity must always have measurable value.

### 2.7. Observability

Every answer should be traceable. The system should always make it possible to understand: what was retrieved; what was sent to the model; why the answer was produced. Good diagnostics are part of the architecture.

### 2.8. Quality, Evolution, Measurement

Optimize for quality, not features. Improve incrementally — one area per iteration (retrieval, ranking, chunking, context, evaluation). Every improvement must be measurable. The architecture should outlive individual components: embedding models, rerankers, LLMs, or vector databases may change without changing the core philosophy.

## 3. The AI Cannot Override These

### 3.1. Workflow Lock

| User Asked For | AI Must Do | AI Must NOT Do |
|---|---|---|
| Find bugs | List bugs with file:line | Propose refactoring |
| Fix a bug | Minimal fix, one file preferred | "While I'm here, let's also..." |
| Add feature | Implement exactly what was asked | Add "helper" infrastructure |
| Review code | Report issues only | Suggest architectural changes |
| Explain code | Explain what IS there | Suggest what SHOULD be there |
| Refactor (explicit) | Execute the agreed plan | Expand scope mid-execution |

Rule: If the user's request does not contain the words "refactor", "restructure", "redesign", or "architectural change", AI MUST NOT propose them.

### 3.2. Conversation Lock

- If AI proposed X and user accepted, AI cannot propose not-X in the same conversation
- If AI previously agreed to a pattern, contradicting it requires marking as `CORE CHANGE REQUIRED`
- AI must not "improve" its own previous accepted output without explicit user request

### 3.3. Output Lock

Every AI response that includes code changes MUST start with:

```
CHECKLIST:
- [ ] Reduces code volume or fixes bug? ___
- [ ] Explicitly requested? ___
- [ ] Adds hidden state? ___ (if YES → STOP)
- [ ] Shares stateful resource? ___ (if YES → STOP)
- [ ] Touches >3 files? ___ (if YES → discuss first)
- [ ] Changes core/? ___ (if YES → CORE CHANGE REQUIRED)
```

If AI cannot check all boxes honestly, it MUST output: "No changes proposed. Current implementation is acceptable."

## 4. Resource Ownership (The Rule That Would Have Prevented DRIFT #23)

### 4.1. The One Law

**Who creates a resource — closes it. Unconditionally. No flags. No exceptions.**

### 4.2. What This Means

```python
# FORBIDDEN — conditional cleanup
class BadAdapter:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client or httpx.AsyncClient()
        self._own_client = client is None  # ← HIDDEN STATE

    async def shutdown(self) -> None:
        if self._own_client:  # ← CONDITIONAL CLEANUP
            await self._client.aclose()

# REQUIRED — unconditional cleanup
class GoodAdapter:
    def __init__(self, config: ConfigData) -> None:
        self._client = httpx.AsyncClient()  # ← I CREATE IT

    async def shutdown(self) -> None:
        await self._client.aclose()  # ← I CLOSE IT. ALWAYS.
```

### 4.3. The Distinction That Matters

| | Shared CODE | Shared RESOURCE |
|---|---|---|
| What | Function, constant, pure logic | Object with mutable state |
| Cleanup | None needed | Someone must close/release |
| Example | `async_post_json()` in `_http.py` | `httpx.AsyncClient` |
| Rule | OK to share across adapters | NEVER share across adapters |
| Test | "Does it have a `close()` or `__del__`?" | If yes → NOT shareable |

## 5. HTTP Client Strategy (Post-DRIFT #23)

### 5.1. Decision Tree (AI Must Follow)

```text
Need HTTP POST in adapter?
├── Is it one-off? → Use httpx.post() directly, no client
├── Is it recurring? → Create self._client in __init__
│   └── shutdown() MUST call aclose() unconditionally
└── Is it shared across adapters? → REJECTED. Not allowed.
```

### 5.2. Why Shared Client Is Banned

- **Lifecycle mismatch**: LLM adapter may outlive embedder
- **Config divergence**: Different timeouts, limits, mounts
- **Shutdown complexity**: Requires reference counting or ownership flags
- **Test isolation**: Leaks state between tests
- **Solo maintenance**: "Who closes this?" must have one-sentence answer

## 6. Shutdown Protocol

### 6.1. Invariants

- `shutdown()` is unconditional. No `if`. No flags.
- Lifespan calls `shutdown()` on every `IClosable`. It does NOT inspect internals.
- No-op adapters implement `shutdown()` as `pass`.
- Order: persist indices → adapter shutdown → metrics last.

### 6.2. Lifespan Cleanup (Current)

```python
# REQUIRED: lifespan does not know what adapters hold
for adapter, name in adapters:
    if adapter is not None:
        try:
            await asyncio.wait_for(adapter.shutdown(), timeout=5.0)
        except TimeoutError:
            logger.warning("Adapter shutdown timed out", extra={"adapter": name})
        except Exception:
            logger.exception("Adapter shutdown failed", extra={"adapter": name})

# FORBIDDEN: lifespan reaching inside adapters
await state.http_client.aclose()  # ← lifespan knows too much
```

## 7. Refactoring: When Yes, When No

### 7.1. YES (Do It)

| Trigger | Condition |
|---|---|
| Duplication | Same pattern in ≥3 places |
| Bug | Code is provably wrong |
| Drift | Violates documented rule (see drift.md) |
| Explicit request | User asked for it |
| Volume reduction | Reduces files AND lines |

### 7.2. NO (Reject)

| Trigger | Why Rejected |
|---|---|
| "Cleaner" | Subjective |
| "Pythonic" | Idiomatic preference |
| "On future" | Speculative |
| "Best practice" | External pattern, adds complexity |
| "More flexible" | Adds abstraction for 1 use case |
| Shared resource | See Section 4 |

### 7.3. Scale Rule

>3 files changed → discussion, not action.
If refactoring touches >3 files, split into steps or get explicit confirmation.

## 8. Decision Log (Why These Rules Exist)

**#23** (2026-06-29): Shared `httpx.AsyncClient` + `_own_client` flag → hidden state, conditional shutdown, factory special-casing. **Rule:** §4.1 unconditional ownership, §5 per-adapter client only.

**#22** (2026-06-28): `tokenizer_model` duplicated `ITokenizer.model_name`. **Rule:** Port objects own config; PipelineData carries references, not config duplicates.

**#7** (2026-06-28): Shared CODE extracted correctly; then tried to share CLIENT too. **Rule:** Shared CODE ok, shared RESOURCE forbidden. AI cannot bundle them.

## 9. Antipatterns (AI Must Never Use)

| Pattern | Why Banned | Where It Appeared |
|---|---|---|
| `_own_*` flag | Conditional cleanup | DRIFT #23 |
| Shared stateful resource in `AppState` | Unclear lifecycle | DRIFT #23 |
| `getattr(obj, "config", None)` | Bypasses port contract | DRIFT #3, #4 |
| `dict[str, Any]` metadata bags | Untyped, grows forever | DRIFT #8, #14 |
| Lazy init (`dict[str, Callable]`) | Hidden state | ai_rules.md §2 |
| `**kwargs` in ports | Breaks contract | ai_rules.md §2 |
| Proposing changes when asked to find bugs | Scope creep | This document §3.1 |

## 10. For the Non-Programmer Maintainer

If AI proposes a change, ask it:

1. "What breaks if we do nothing?" — If answer is "nothing", reject.
2. "How many files change?" — If >3, reject or split.
3. "Does this add a flag or condition?" — If yes, reject.
4. "Who creates and who closes?" — If answer has "if" or "depends", reject.
5. "Show me the rollback" — If AI can't show one-line rollback, reject.

## 11. The "Sacred Disk & Config" Doctrine

Disk formats are sacred. User data outlives code. Code must serve data, not the reverse.

### 11.1. Persistence Lock

Disk formats (SQLite schemas, JSON structures, FAISS metadata, YAML configs) are immutable without migration.

| What | Rule |
|---|---|
| `ChunkMetadata`, `ReindexStatusEntry`, stored JSON | NEVER change fields without backward-compat loader |
| New field in stored dataclass | MUST provide migration code (see `core/config.py` `config_version` pattern) |
| No migration provided | NO CHANGE ALLOWED |
| Config schema change | MUST bump `config_version` + backward-compat loader |

Why: Solo maintainer cannot manually recover corrupted indices or lost chat history. Data loss is permanent.

Decision Log #5: `ChunkMetadata` schema drift (`created_at` serialized but not in domain model) required local `_chunk_to_dict` / `_chunk_from_dict` helpers for strict deserialization. Lesson: disk format must match domain model exactly.

### 11.2. Dependency & Config Freeze

| What | Rule |
|---|---|
| New pip dependency | FORBIDDEN if stdlib/`httpx`/`pydantic`/`numpy` can solve it |
| New config field | FORBIDDEN unless parameter used in ≥3 places |
| "Make it configurable" | REJECT. Hardcode until 3 real cases demand change |
| Config dump prevention | Every field must justify its existence. No "maybe useful" |

Why: Dependencies rot. Config becomes unmaintainable. Solo maintainer cannot track 50 options.

Existing ai_rules.md: Section 2 bans Redis/Celery/etc. Section 2.1 bans config for 1-use values. This section adds the threshold (≥3) and the framing (freeze, not just caution).

### 11.3. Concurrency & Async Lock

| What | Rule |
|---|---|
| New `asyncio.Lock` / `Semaphore` | FORBIDDEN without documented race condition that breaks production |
| Sync → async rewrite | FORBIDDEN for "purity" or "performance" without measured bottleneck |
| Async → sync rewrite | FORBIDDEN for "simplicity" if it breaks existing async contracts |
| Default | Boring synchronous code wins unless proven otherwise |

Documented exceptions (do not add more without Decision Log entry):

- `RAGState.semaphore` — background reindex vs API requests race
- `RAGState._lock` — atomic task status updates
- `MemoryVectorStore._lock` — concurrent add/search/delete on shared in-memory index

Why: Concurrency bugs are the hardest to debug solo. Locks add complexity that compounds over 10 years.

### 11.4. The "Boring Code" Mandate

Code must be readable by someone who knows only `if/else`, `for`, and `def`.

**FORBIDDEN** (never use, never propose):

- Metaclasses
- Custom descriptors
- `__slots__` outside `core/domain/` dataclasses
- Dynamic imports (`importlib` in production code)
- `sys._getframe`, `inspect` stack walking
- Magic `__getattr__` / `__getattribute__`
- `eval()`, `exec()`, `compile()`
- Property factories, class decorators
- Context managers for trivial `try/finally`

**ACCEPTABLE** (the entire project uses only these):

- Plain functions and classes
- `if/else`, `for`, `while`
- `try/except` for expected errors only
- `with` for resources (files, connections)
- `dataclass(frozen=True, slots=True)` in `core/domain/`
- `@register` decorator (explicit, not magic)

Why: "Pythonic magic" is unmaintainable solo. In 5 years, you will not remember why a metaclass was needed. In 10 years, Python may deprecate it.

## 12. Document Meta

- `ai_rules.md` = "what is forbidden" (constraints)
- This document = "how AI must behave" + "RAG philosophy" (behavioral lock)
- `drift.md` = "what we fixed and why"
- AI reads ALL THREE before any architectural output
- This document takes precedence over ai_rules.md on architectural decisions
- Changes to this document require explicit human approval

## 13. RAG Invariants (Event-Proof)

Rules that survive model changes, hardware changes, and adapter swaps.

1. **Reranker is rank-only.** Never filter by absolute score threshold.
   Ordinal rank (top_n) is the only valid interface. Pipeline decides
   sufficiency, not the reranker.

2. **Pipeline never inspects adapter internals.** No hasattr, isinstance,
   or getattr on port objects. Capability dataclass is the only bridge.

3. **Prompts live in `prompts/` as Jinja2 files.** Never in Python strings
   or f-strings in pipeline logic.

4. **`check_rag.py` is the only source of truth for RAG quality.**
   No manual spot-checking, no "looks correct".

5. **Context budget derives from `LLMCapability.context_window`.**
   No hardcoded top_k without comment linking it to chunk size.

6. **"Don't know" is LLM's decision, not pipeline guardrail.**
   Prompt teaches the phrase; pipeline does not hardcode refusal.

## 14. Hardware Ceiling Log

| Date | Hardware | LLM | Result | Limitation |
|---|---|---|---|---|
| 2026-07-13 | GTX 1650 4GB | gemma-4-e2b-it | 6/13 PASS | multihop, noise rejection, open synthesis require >=8B params |
| 2026-08-12 | GTX 1650 4GB / 16GB RAM | Qwen3-4B-Instruct-2507 (Q5_K_M) | 13/17 PASS + 1/2 e2e chat | trap-1, trap-2, multihop-1 FAIL; 9 known limitations; 4B weaker than 7B on RAG tasks |
| 2026-08-12 | GTX 1650 4GB / 16GB RAM | Qwen2.5-7B-Instruct (IQ4_XS) + multi-query retrieval + optimized universal prompt | 16/17 PASS + 2/2 e2e chat | trap-2 PASS; semantic-ru-1 FAIL (bge-m3 embedding limitation on Russian synonyms). Prompt optimized for 7B-70B models |

Expected fix: LLM upgrade (Qwen2.5-14B-Instruct, DeepSeek-R1-Distill-Qwen-7B). No pipeline changes required.
