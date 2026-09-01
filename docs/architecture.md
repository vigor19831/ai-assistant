# Architecture

> Version: 2026-08-31
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
- Order: persist indices → background tasks → adapter shutdown.

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

**#43** (2026-08-27): Retry wrapper stacked on a retried adapter — 16 attempts, minutes-long opaque failures. **Rule:** §7 ai_rules — retry lives in exactly one layer.

**#50** (2026-08-28): Refusal answers carried retrieved chunks as sources. **Rule:** refusal = complete answer without evidence; refusal strings are shared constants with a prompt-sync test.

**Benchmark discipline** (2026-08-28): a spec edit was recommended from failure logs alone, before reading the evaluator code — turned out to be both wrong and benchmark-fitting. **Rule:** §13.4 edit discipline; read the instrument before judging it.

## 9. Antipatterns (AI Must Never Use)

| Pattern | Why Banned | Where It Appeared |
|---|---|---|
| `_own_*` flag | Conditional cleanup | DRIFT #23 |
| Shared stateful resource in `AppState` | Unclear lifecycle | DRIFT #23 |
| `getattr(obj, "config", None)` | Bypasses port contract | DRIFT #3, #4 |
| `dict[str, Any]` metadata bags | Untyped, grows forever | DRIFT #8, #14 |
| Lazy init (`dict[str, Callable]`) | Hidden state | ai_rules.md §2 |
| `**kwargs` in ports | Breaks contract | ai_rules.md §2 |
| Stacked retry layers | Multiplied attempts (up to 16), opaque failure time | DRIFT #43 |
| Hardcoded prompt strings in code | Prompt knowledge rots in two places, matcher drifts silently | DRIFT #50 (fixed via constants + sync test) |
| Proposing changes when asked to find bugs | Scope creep | This document §3.1 |

## 10. For the Non-Programmer Maintainer

If AI proposes a change, ask it:

1. "What breaks if we do nothing?" — If answer is "nothing", reject.
2. "How many files change?" — If >3, reject or split.
3. "Does this add a flag or condition?" — If yes, reject.
4. "Who creates and who closes?" — If answer has "if" or "depends", reject.
5. "Show me the rollback" — If AI can't show one-line rollback, reject.
6. "Are we changing the code or the measuring stick?" — If the change
   touches the benchmark or its expectations, demand the justification
   before applying: is it a proven instrument defect, or a failure we
   want to disappear?

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
- `RAGState.chat_semaphore` — caps concurrent chat/LLM requests (chat.max_concurrent_chat)
- `MemoryVectorStore._lock` — concurrent add/search/delete on shared in-memory index
- `FaissVectorStore._lock` — same contract as MemoryVectorStore

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
- `drift.md` = "what we fixed and why" + FUTURE RISKS (deferred issues with concrete triggers) + benchmark known limitations
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
   No manual spot-checking, no "looks correct". The benchmark itself
   is edited under discipline: instrument defects may be fixed only
   when provable independently of current results; test expectations
   change only when self-contradictory (e.g. requiring a format the
   query itself demands, then failing it as unfaithful) — never to
   accommodate an observed failure. Code moves toward the benchmark,
   not the benchmark toward the code.

5. **Context budget derives from `ILLM.get_context_limit()`.**
   No hardcoded top_k without comment linking it to chunk size.

6. **"Don't know" is LLM's decision, not pipeline guardrail.**
   Prompt teaches the phrase; pipeline does not hardcode refusal.
   Refusal answers are complete strict-RAG answers and carry no
   evidence: sources are empty, chunks_used is 0 (drift #50).
   Retrieval diagnostics still reach the caller via metrics and logs.

## 14. Hardware Ceiling Log

| Date | Hardware | LLM | Result | Verdict |
|---|---|---|---|---|
| 2026-07-13 | GTX 1650 4GB / 16GB RAM | gemma-4-e2b-it | 6/13 | First baseline. Multihop/noise rejection/open synthesis need ≥8B params. |
| 2026-08-12 | GTX 1650 4GB / 16GB RAM | Qwen3-4B (Q5_K_M) + multi-query retrieval + optimized prompts | 13/17 + 1/2 e2e | Small-class entry. bge-m3 RU-synonym limit noted. |
| 2026-08-12→28 | GTX 1650 4GB / 16GB RAM | Qwen2.5-7B-Instruct (IQ4_XS) | 17/17 ×4 + 7-8/9 CHAT | **KING (RAG).** Only 17/17 holder; 4× pass under temp-0.7 noise proves margin. 14B+ needs 12GB+ VRAM (08-25 verdict). |
| 2026-08-24→28 | GTX 1650 4GB / 16GB RAM | 9B class: Qwen3.5-9B, Ornith-9B ×2 | 13-14/17 | **REJECTED ×3.** PCIe bottleneck on 4GB; latency ×2-3; identical failures CPU vs GPU (temp-0 determinism cross-check). |
| 2026-08-29 | GTX 1650 4GB / 16GB RAM | Phi-4-mini (Q5_K_M) | 14/17 + 9/9 CHAT | Chat champion (2-3× speed), kept as chat-fallback. Trap inhibition + multihop still parameter-bound. |
| 2026-08-29→30 | GTX 1650 4GB / 16GB RAM | Qwen3.5-4B (IQ4_XS) | 16/17 → 17/17 + 9/9 CHAT | Strongest small candidate; passes trap-1/2, multihop-1. "VRAM-starved" 08-30 attribution corrected 08-31 (sampling noise). |
| 2026-09-01 | GTX 1650 4GB / 16GB RAM | **First live corpus indexing** (drift #60–62): 1.3 MB / 41 docs / 3400 chunks | CPU embedder: ~4 chunks/s — never completes within the 300 s watcher window (infinite retry loop). GPU embedder (bge-m3, LLM at 10 layers, 2.3/4 GB VRAM): **~2 min working time, completed**. ×7 vs CPU, and the only path that finishes at all. Indexing profile: LLM 10 + embedder GPU; serving: LLM 20 + embedder CPU | Indexing is a profile switch, not a permanent state; GPU embedder requires single-flag config (drift #60) |
| 2026-08-31 | GTX 1650 4GB / 16GB RAM | **FINAL CAMPAIGN** — deterministic (temp 0.0, drift #54), fixed harness (D1/D2/D5), post-#58 re-baseline (both ×2): Qwen3.5-4B (IQ4_XS, 40 layers) vs Qwen2.5-7B (IQ4_XS, 20 layers) | 4B: 17/17 + 9/9 CHAT + 22/30 ×2. 7B: 17/17 + **8/9 CHAT** + **24/30** ×2. | **THRONE DECISION: 7B stays king (RAG discipline, anti-noise at weak signals, top FUTURE); 4B = RAG-heir (sole 9/9 CHAT).** Chat-path postmortem: condensation-1 fixed by condense prompt contract (#58); multi-turn-1 is a 7B parametric ceiling (proven via ideal-question control — generation refuses at 1-chunk context). Two-tier: 7B primary / 4B RAG-heir / Phi chat-fallback. |

**Standing conclusions** (replaces per-run prose):
- King: Qwen2.5-7B IQ4_XS (20 layers). Heirs: Qwen3.5-4B IQ4_XS (RAG, 40 layers), Phi-4-mini (chat).
- Small-class re-test each generation; first probes: trap-1, trap-2, multihop-1.
- Benchmark determinism: temperature 0.0 mandatory (drift #54). Verdicts (Result lines) reproduce byte-identically; rerank scores jitter at the 4th decimal on strong signals and ~0.02 on weak (GGML batching), and greedy generation may vary one phrasing per run (llama.cpp GPU nondeterminism) — all verdict-neutral.
- Chat e2e numbers valid only from 2026-08-31 onward (D1 conv-id fix; re-baselined again post-#58).
- Corpus ingestion: files >150 KB are split via `scripts/prepare_docs.py` (source: `data/raw_documents/`); CPU embedder rate ~4 chunks/s, GPU ~×7 — indexing runs in the indexing profile (LLM 10 layers + GPU embedder), serving in the normal profile (LLM 20 + CPU embedder).
- Chat-path follow-ups: condensation-1 fixed by the condense prompt contract (drift #58); multi-turn-1 remains a 7B parametric ceiling — the sole residual chat fail.
- Raw run archives: `data/check_rag_*.log` (per-run details live there, not here).
