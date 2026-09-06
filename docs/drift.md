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
| 59 | 2026-09-01 | index_documents.py removed: third executor over the same index (script + watcher + API) caused CPU contention, timeout cycles, and disk/memory divergence; no unique function — watcher (60 s poll, 300 s window) + POST /rag/reindex cover all cases, large files split via prepare_docs.py |
| 60 | 2026-09-01 | Dual -ngl launch flags: run_servers.py built -ngl from config.yaml while run_servers.yaml extra_args appended it again — llama.cpp keeps the last flag, so the embedder ran "-ngl 0 ... -ngl 99" and died at startup ("HTTP request failed" at 47 ms); all 08-31 "GPU indexing" attempts were conflicted-flag runs. Rule: n_gpu_layers lives in config.yaml only, extra_args never carries -ngl |
| 61 | 2026-09-01 | Reranker env-block removed (double CPU-gating) + reranker.n_gpu_layers added to schema (RerankerConfig/Data/mapper, pattern #57 — extra="forbid" caught the missing field at startup, as designed). First live GPU indexing: 3400 chunks — CPU never completed (300 s window, ~4 chunks/s); GPU embedder ~2 min working time at LLM=10 layers, VRAM 2.3/4GB |
| 62 | 2026-09-01 | Concurrent reindex executors (manual task + watcher poll) over one embedder: the watcher's own 3-attempt cycle ran parallel to the task, timed out independently ("failed 3 times, giving up") while the task completed — file mtime was clean (find -newermt empty). Rule: trigger one reindex path at a time |
| 63 | 2026-09-01 | Vector store migrated memory→faiss at live-corpus growth (user-declared 1–2K files/month; ~40–60K chunks projected vs the 100K trigger). Reason: RAM scaling + disk (faiss binary vectors ~×5 smaller than JSON-float stores; the 202 MB JSON mystery = old crash-era layers, clean start = 59 KB/doc). Provider switch in config; full reindex = the migration (faiss reads no JSON stores) |
| 64 | 2026-09-01 | SOURCE_INDEX_TIMEOUT (300 s) killed every indexing pass at ~85% (2900/3397 chunks, ~10 chunks/s GPU at LLM=10) — retries restarted from zero because progress was RAM-only until the final store write. embed.progress/done logging (added the same day) exposed it on first use. Fixes: (1) window 300→600 s (measured × 1.7); (2) document-level checkpointing in index_folder — each doc is embed→upsert→atomic-save, a kill loses at most one doc, the next pass resumes via filter_unchanged_docs. The watcher window is now a pause between checkpoints, never a full reset. Honest GPU rate: ~10 chunks/s → 5.5 min/MB. VERIFIED 2026-09-02: kill-midway test invariants green (the initial red was a wrong test expectation — chunks-per-doc > 1; a replica proved the pipeline correct); full benchmark 17/17 + 25/30 on faiss with live reindex of the 3397-chunk corpus |
| 65 | 2026-09-02 | atoms pipeline: 142 KB → 12 parts × 12 KB → 21m16s, zero HTTP errors. Archivist profile in config.yaml (part_bytes 12000 = ctx 8192 − 800 instr − 1500 answer; llm_model null → field omitted, None-guard against str(None)="None"). Four 400-errors root-caused en route: model-name mismatch → omit field; 30 KB parts → 11963 tokens → exceed_context_size → token-budget split; None-string → guard. mtime idempotency (per-layer SKIP). Default: split only — atoms are explicit just-in-time on mature chats. Verification: 3/3 control questions answered as synthesis, atoms layer in Sources; rerank top_score on consolidation queries 0.007-0.12 (an atom answers one question; "list all decisions" matches no single chunk by construction) — synthesis quality judged by answer shape and layer coverage, not rerank score |
| 66 | 2026-09-03 | prepare_docs: freshness marker checked part01 only → small as-is files reprocessed every run (menu [2]: ~5 min LLM → 127 ms SKIP after fix); grown-past-threshold source kept its stale as-is copy beside new parts → both indexed (`_reconcile_outputs` in `split_file` + main); atom seam //2 → //4 (17041 B on 12000 B budget measured). Rule: idempotency marker = the exact artifact the producer writes; freshness tests drive the real producer, not hand-crafted outputs. Tests 17→20 |
| 67 | 2026-09-03 | Archivist A/B (watch corpus, same split): 7B keeps the crown — RU atoms 2.5/3; 4B rejected for RU (0.5/3 — EN atoms, EN answers on RU queries), ×3 speed + clean facts (no caliber≈watch merge) recorded as reserve. THE DECISION TEST (prompt): no user quote → not a decision; 4/4 blocks "No user decisions", Q5-class answers stopped asserting a user choice. Cross-model proof: raw corpus reproduces the false "you chose X" on BOTH models — atoms = status guard, a corpus property. Residual 7B ceilings: section duplication, year hallucination, EN on URL-heavy parts. 4B archivist viable only with per-part language header — see FUTURE RISKS |
| 68 | 2026-09-03 | Config window math as method (values local, config.yaml never committed): window = context budget + generation + margin; max_context_tokens ~60% of window or long dialogs silently truncate. Rebalance 5000/10/0.15 → 4800/6/0.10, check_rag verified: 7B 17/17+8/9, 4B 17/17+9/9; cost: format-strict-1 → known limitation (0.10 margin trims a chunk on open synthesis). Rule: every config rebalance = check_rag pass + a named cost |
| 69 | 2026-09-03 | check_all AST audit false positives: registry keys prefixed "src." vs real "ai_assistant.*" imports (false never-imported, grep-disproved); stem fallback marked same-named modules imported (removed); function-scoped imports counted as load edges — flagged deps↔manager cycle that is its standard cure (layer-legal both ways); cycles now load-edges-only; tests+scripts count as callers. Recorded cause wrong: collector always visited function bodies |
| 70 | 2026-09-04 | scripts/ + launchers under ruff+mypy strict (84+66 first enable; RUFF_TARGETS/MYPY_TARGETS in check_all; check_rag per-file exempt per §13.4). FINDING: check_llm broken 4 days since #53/#57 purge — dead fields still passed to ConfigData, caught by first full [5]. Also: dead chat_query headers removed (auth on AsyncClient), decorative api_key stripped, stream errors printed (#55), TypedDict audit registry. Lessons: isolated mypy on scripts = false zero (src in target list always); anchors need exact file content |
| 71 | 2026-09-04 | tests/ under ruff (§15 per §14): debt 372→0 — dead imports/vars, 12 import-redefs (arithmetic: 971+9=1000, no shadowed tests), misplaced mock binding, fixture return-bug, NameError masked as AdapterError (import restored), SLEEP marker renamed "sleep: intentional" (noqa collision, 11 mo invisible), ruff format adopted; RU/CJK = test data (noqa). Lessons: anchors from fresh extraction, never memory/render; region-extractor loop for k-line files |
| 72 | 2026-09-05 | tests/ under mypy (owner decision): ~310 fixed — 9 fakes promoted to port ABCs (duck-typed contract defect), AppConfig(**dict)→model_validate, CHAT_NS_PREFIX into __all__, MYPY_TEST_FLAGS (see check_all.py; pyproject overrides dead on mypy 1.20.2); ~80 annotation cosmetics frozen by disabled codes — deliberate, revisit: tests become a package. Lessons: structural edits via sed banned (4 accidents, all gate-caught); ast.parse per patch; full commands only; fakes need explicit __init__ (port config); tests-mypy target must include src/ (#70 mirror) |
| 73 | 2026-09-05 | Tokenizer UX (3 owner field findings): model switch in config bricked startup on missing tokenizer.json. Now: huggingface adapter degrades to CharFallback (loud warning + recovery instruction; #48 pattern). Fatal stay: package missing, empty path, corrupt file. Warning says "restart" (config read once). check_llm: tokenizer block + compact redesign (verdict lines only, logger clamp — adapter tracebacks on down servers buried output; detail in app log). Choice: char over cl100k — universal, conservative overcount. Stale raise-test rewritten to fallback contract (gate-caught, expected) |
| 74 | 2026-09-05 | clean_cache + live logs (owner memory caught it): `*.log` deletion on Linux unlinked open files silently — process wrote into deleted inode, log never reappeared; the remembered "skipped (locked)" was Windows FS behavior, absent on Linux. Fix: `_stack_running()` guard (pgrep llama-server/uvicorn), live `.log` = SKIP with hint; cleanup after stop. Rule: OS-dependent protection is no protection — behavioral guards live in the script |
| 75 | 2026-09-05 | check_rag 7B ×8-run attribution: canon `17/17+8/9+24/30` byte-identical ×3 (score arrays equal — pipeline deterministic). 12:14 outlier `9/9+26/30` = char-fallback tokenizer (deleted-files window before download+restart; CtxTok ratios match char counts: RU ×1.5, EN +8%); not reproducible ×5 with exact tokenizer — margin/ctx-window/chat-budget all leave CtxTok untouched (frictionless at bench-scale). Rule: fix tokenizer mode before judging runs; single-run deviation = find the config delta first |
| 76 | 2026-09-05 | config-liveness audit (owner: "do yaml fields control anything?"): CLEAN — 0 dead knobs; 7 mapper builders pass every field (post-#53/#57 wiring sound); external consumers OK (run_servers `n_gpu_layers`/`server_context_size`, prepare_docs `archivist.*`); `debug` alive (main.py:90). Method: reader-pattern grep (`cfg.field`), not word-count — `logger.debug` noise gives false readers. Budget knobs frictionless at bench contexts (72-263 tok vs 4800) — await real-corpus loads |
| 77 | 2026-09-05 | First live A/B eval (5 own chat docs, 12 questions): atoms pipeline PROVEN — retrieval completeness up (categories→models, final recommendations surface, URL-noise gone, ~24 min/135 KB). DECISION TEST FAILED on live RU chats: 7 assistant opinions labeled `Status: decision` (subject inversion — "я бы выбрал" → "user decided"); atoms turned weak hallucination into evidenced lie: Q9 regressed from honest "I don't know" to "Вы выбрали Sprinter" with atom as proof. Root cause isolated by probe (manual status demotion → honest answers restored): the atom Status label, not retrieval/generation. Fix task: `ARCHIVIST_PROMPT` decision-test hardening (7B inverts speaker in RU dialogues; test-guard from task 1 in place). Manual atom edits = measurement probe only, never a process |
| 78 | 2026-09-06 | decision-guard campaign, live-verified across two atom regenerations: atom validator in prepare_docs (grep-verified quotes; 2 live demotions in final run; form-drift risk — "User stated" escapes regex, expand in next iter) + ARCHIVIST_PROMPT hardening (slot-enforcement, speaker-check, body-phrasing: bodies now attribute "ChatGPT предложил", zero "Вы выбрали") + rag_strict rule 12 + few-shot examples (RU examples caused refusal-generalization on sparse-signal queries — CONTRACT 17→14; EN examples restored 17/17; second confirmation: 7B follows example FORM over rule TEXT). Result: trap questions 2.5/3 — autodom/watches hold "I don't know" across regenerations; residual: cream=raw-chank advice-echo ("Если найдешь: Tarrago") when rerank picks source over atoms — known limitation, next lever is a few-shot case "advice-phrased-as-answer → still I don't know" (tomorrow). Also: first make_atoms ReadTimeout (post-benchmark VRAM contention, retry passed) |

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
