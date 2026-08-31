# Known Architectural Drift

> Rule: Do not add new drift if old pattern can be fixed properly.
> AI reads this file before any architectural output (Document Meta §12).
> ACTIVE entries are constraints — do not "fix" them without explicit user request.
> FUTURE RISKS are deferred issues with concrete triggers — they are known, not forgotten.
> Git history is unreliable (commits often say "fix"). This file is the source of truth.

## ACTIVE (6)

| ID | Since | Location | Constraint | Exit Criteria |
|----|-------|----------|------------|---------------|
| 11 | 2026-06-09 | `core/prompts/__init__.py` | Jinja2 import in stdlib-only `core/` layer | Second template engine needed OR Jinja2 deprecated |
| 18 | 2026-06-14 | `api/security.py` | `_override_api_key` process-local; does not propagate across uvicorn/gunicorn workers | Multiprocess deployment becomes primary use case |
| 19 | 2026-06-14 | `core/config.py` | Pydantic + PyYAML import in stdlib-only `core/` layer. `config_version` + backward-compat loader in place | Pydantic 2y without release OR critical CVE unpatched >6mo |
| 29 | 2026-07-05 | `core/ports/tokenizer.py` | `ITokenizer` simplified; no multi-encoding support | Multi-encoding support needed |
| 34 | 2026-07-08 | `tests/test_stateful_ports.py` | `asyncio.run()` in `ThreadPoolExecutor` for Hypothesis (issue #4107 — no native async) | Hypothesis adds async state machine OR tests removed |
| 38 | 2026-08-12 | `tests/conftest.py` | `AsyncMock` cannot mock async generators → `MagicMock(side_effect=factory)` bypasses `spec=ILLM` | stdlib native async generator mock support OR `ILLM.stream` contract change |

## FIXED → Rule Extracted (see docs, no details needed)

| ID | Fixed | Rule / Location |
|----|-------|-----------------|
| 23 | 2026-06-29 | HTTP client ownership → `architecture.md` §4, §5 |
| 22 | 2026-06-28 | Port objects own config, PipelineData carries references → `architecture.md` §8, `ai_rules.md` §2.2 |
| 7 | 2026-06-28 | Shared CODE ok, shared RESOURCE banned → `architecture.md` §4.3, §8 |
| 14 | 2026-06-26 | Untyped `dict[str, dict]` bags banned → `architecture.md` §9 (antipatterns) |
| 8 | 2026-06-18 | `PipelineData.metadata: dict[str, Any]` replaced with typed fields → `architecture.md` §9 (antipatterns) |
| 31 | 2026-07-10 | Unconditional `shutdown()`, no `_closed` flag → `architecture.md` §6 |
| 30 | 2026-07-10 | `SystemMessage` in domain, removed from `ILLM` port → `architecture.md` §8 |
| 37 | 2026-07-28 | `min_relevance_score` stripped; strict rank-only → `architecture.md` §13 |
| 28 | 2026-08-19 | Removed `require_api_key` duplication from `admin.py` → `api/admin.py` |
| 39 | 2026-08-19 | Moved `_build_fallback_prompt` to `prompts/v1/fallback.j2` → `core/pipeline_steps.py` |
| 36 | 2026-07-19 | `threshold` removed; rank-only invariant. No deprecation cycle (pre-production, solo, no legacy configs) → `architecture.md` §13 |
| 35 | 2026-07-10 | `chat_history: tuple[tuple[str, str], ...]` eliminates runtime type introspection |
| 19+25 | 2026-06→07 | Config schema evolves via backward-compat loaders + `config_version` → `core/config.py` pattern |

## FIXED → History (one-liners, self-contained)

Recent window 2026-08-27 → now (working horizon). Pre-August archive
(#1–#39): one-liners in git history of this file; every lesson with a
surviving contract is extracted into the Rule Extracted table above,
the rest were plain bugfixes.

| ID | Fixed | Summary |
|----|-------|---------|
| 40 | 2026-08-27 | Delete-all left stale index files → deleted chunks resurrected on restart; empty namespace now removes its files (both vector store adapters) |
| 41 | 2026-08-27 | Memory store `save()` overwrote skipped namespaces with an empty store on shutdown; never-loaded namespaces no longer touch disk |
| 42 | 2026-08-27 | Watcher consumed the snapshot on failure → partial index frozen as complete; bounded retry (3 attempts), snapshot consumed on success only |
| 43 | 2026-08-28 | Retry lives in exactly one layer → `ai_rules.md` §7, `architecture.md` §9 (antipatterns) |
| 44 | 2026-08-27 | Mid-stream failure persisted a truncated assistant turn; save now runs only after the stream completes |
| 45 | 2026-08-27 | SSE frames carried multi-line chunks under one `data:` prefix — strict clients dropped the Sources block; every line carries its own prefix |
| 46 | 2026-08-27 | BOM files decoded with `utf-8` first → U+FEFF leaked into chunk text; `utf-8-sig` first, plain `utf-8` removed |
| 47 | 2026-08-27 | `/rag/reindex` without sources → `UnboundLocalError` masked as 500; explicit 400 before spawning the task |
| 48 | 2026-08-27 | Memory store silently FIFO-evicted on max_chunks overflow (eviction banned by ai_rules §2, RAM pressure never measured) and later persisted the loss; eviction removed, `add()` rejects like faiss, contract in port |
| 49 | 2026-08-28 | Sources block persisted into chat history — token waste, condense pollution, evidence feedback loop; history stores the clean answer, API keeps the block |
| 50 | 2026-08-28 | Refusal answers carried chunks as sources; strict-RAG refusal = empty sources/chunks_used=0; refusal strings in `core/constants.py` + prompt↔matcher sync test |
| 51 | 2026-08-28 | OAI chat history was write-only; handler now loads stored history on conversation_id without client messages (client-first) |
| 52 | 2026-08-31 | Query-path retry stacking removed (16 attempts worst case) — retry lives strictly in adapters; `PipelineConfig.retry`, `RetryConfig`, `retry_with_config` purged (CORE CHANGE) |
| 53 | 2026-08-31 | Dead LLM sampling fields purged (`top_k`, `min_p`, `repeat_penalty`, `presence_penalty`, `frequency_penalty`): never reached the adapter — config lied; no migration (#36 precedent) |
| 54 | 2026-08-31 | Defaults `temperature: 0.0`, `top_p: 1.0` — RAG determinism by default; killed 15/17-vs-17/17 sampling flakiness |
| 55 | 2026-08-31 | check_rag harness: run-unique conv-id, Sources stripped from client history, full answers logged on errors; §13.4-verified instrument fixes, chat e2e re-baselined |
| 56 | 2026-08-31 | check_rag: crash-blind error-* tests (500 passed "must not crash"); one-word negation guard; crash=FAIL, 3-word window |
| 57 | 2026-08-31 | Second dead-field batch purged (`n_batch`/`n_ubatch`/`mmap`/`mlock` × llm/embedder): read by neither adapters nor run_servers.py; knobs live in run_servers.yaml extra_args; `n_gpu_layers` kept (live). CORE CHANGE, no migration |
| 58 | 2026-08-31 | condense_question.j2 rewritten: zero-shot template let 7B drift into meta-questions; new contract (resolve pronouns; ask about the topic, never about documents; output-only-question) + cross-domain example; both models re-baselined ×2 |

## FUTURE RISKS (10)
| Risk | Trigger | When to fix |
|------|---------|-------------|
| Config migration bloat | >10 migrations in config.py | When loading old configs becomes slow |
| Test fatigue | Skipping tests due to mock boilerplate | When test coverage drops below 80% |
| LLM prompt coupling | Prompt instability on 14B+ models | When upgrading to 14B+ |
| Vector store RAM limit | Hitting 100K chunks | When max_chunks reached |
| Async lock complexity | Deadlocks in production | When deadlock rate > 1/month |
| Sibling-source deletion | Watcher reindexes one of 2+ sources sharing a namespace; orphan cleanup sees only that source's URIs and deletes the siblings' chunks | Before mapping a second source to a namespace |
| Phantom empty namespaces | `list_by_filter` on a never-populated namespace creates it in memory; the memory adapter later lists it and persists an empty store file | When namespace lifecycle code is touched |
| Silent fallback prompt | Invalid prompt_name (API request or config) renders `prompts/v1/fallback.j2` with degraded RAG instructions; only a log entry, no error to the caller | When prompt versioning/registry work begins |
| Hybrid search (BM25+vector, RRF) | Real corpus shows missed exact-term retrieval (BM25-zero vs vector hits on user queries) | CORE CHANGE: new index format + port extension + index sync design |
| RAM headroom shrink | Peak RAM (6.5/15 GB at ~140 bench docs) grows past ~10 GB with real corpus | Before adding any RAM-heavy component; measure first |
