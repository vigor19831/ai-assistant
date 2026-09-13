# Known Architectural Drift

> Rule: Do not add new drift if old pattern can be fixed properly.
> AI reads this file before any architectural output (Document Meta §12).
> ACTIVE entries are constraints — do not "fix" them without explicit user request.
> FUTURE RISKS are deferred issues with concrete triggers — they are known, not forgotten.
> Git history is unreliable (commits often say "fix"). This file is the source of truth.
> Compaction rule: when History exceeds ~40 entries — extract surviving
> rules, commit the full text, then compress to one-liners
> (2026-09-11: #40–#99; 2026-09-12 round 3: #100–#111).

## ACTIVE

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
| 46 | 2026-08-27 | File reads: utf-8-sig first, cp1251 fallbacks after — BOM must not leak → `features/rag/indexing.py` |
| 49+89 | 2026-08→09 | History sanitized at one choke point (ChatManager); every door history enters gets the same cleaning → `features/chat/manager.py` |
| 50 | 2026-08-28 | Refusal = empty sources; refusal strings are constants + prompt sync test → `architecture.md` §8 |
| 60 | 2026-09-01 | n_gpu_layers lives in config.yaml only; extra_args never carries -ngl → `run_servers.yaml` |
| 66 | 2026-09-03 | Idempotency marker = the exact artifact the producer writes → `scripts/prepare_docs.py` |
| 69+76 | 2026-09-03→05 | Audit hygiene: grep-verify imports before orphan conclusions; config liveness by reader-pattern, not word count |
| 70+72 | 2026-09-04→05 | Lint/type targets must include src+scripts+tests; structural test edits: sed banned, ast.parse per patch → `scripts/check_all.py` |
| 73 | 2026-09-05 | Missing asset degrades loudly (warning + recovery); corrupt/empty stays fatal → `adapters/huggingface_tokenizer.py` |
| 74 | 2026-09-05 | OS-dependent protection is no protection — behavioral guards live in the script |
| 77 | 2026-09-05 | Manual corpus/atom edits = measurement probe only, never a process |
| 78+85 | 2026-09-06→08 | Prompt stop-rule: no Nth iteration for a leaking pattern; benchmark-green ≠ live-green → `architecture.md` §14 lessons |
| 82 | 2026-09-07 | Bench never clears watcher-mapped namespaces (bench_000, [000]) → `scripts/check_rag.py` |
| 83 | 2026-09-07 | Test premises verified against the corpus, not intent |
| 91 | 2026-09-10 | A language check needs an external reference — self-comparison cannot see a uniform flip → V5 in `scripts/prepare_docs.py` |
| 92 | 2026-09-10 | POLICY: atoms OFF until a 14B-class model fits VRAM; a distillation layer must measurably beat its source |
| 93 | 2026-09-10 | A skip condition must verify the artifact it vouches for, not just the key it remembers |
| 97+98 | 2026-09-11 | Never lock a known defect as a required test outcome; flake rule: single red → re-run + find the config delta, two consecutive reds → investigate |
| 107 | 2026-09-12 | Pre-flight max_chunks: refuse before embedding; the store stays the guard (#48) → `features/rag/indexing.py` |
| 108-110 | 2026-09-12 | Ingestion tree: root=default, subfolders=namespaces, _atomize/=intent; documents/ is a mirror, never edited by hand → `architecture.md` §2.9, `scripts/prepare_docs.py` |
| 111 | 2026-09-12 | Reconcile: leftovers of vanished sources removed only on an explicit y/N; the index is the watcher's → `scripts/prepare_docs.py` |

## FIXED → History (one-liners, self-contained)

Working horizon: 2026-08-27 → now. Entries are one-liners; the full
text of every entry lives in this file's git history. Every lesson
with a surviving contract is extracted into the Rule Extracted table
above or already lives in architecture.md. Compacted 2026-09-11
(round 2, after the #1–#39 archive); 2026-09-12 (round 3: #100–#111).

| ID | Fixed | Summary |
|----|-------|---------|
| 40 | 2026-08-27 | Empty namespace now removes its index files — deleted chunks no longer resurrect on restart (both stores) |
| 41 | 2026-08-27 | Shutdown save no longer overwrites never-loaded namespaces with an empty store |
| 42 | 2026-08-27 | Watcher consumes the snapshot on success only; bounded retry (3) |
| 43 | 2026-08-28 | Retry stacking removed (16 attempts worst case) — one layer only |
| 44 | 2026-08-27 | Assistant turn persisted only after the stream completes |
| 45 | 2026-08-27 | Every SSE line carries its own `data:` prefix |
| 46 | 2026-08-27 | utf-8-sig first — U+FEFF no longer leaks into chunks (rule extracted) |
| 47 | 2026-08-27 | `/rag/reindex` without sources: explicit 400 (was 500 via UnboundLocalError) |
| 48 | 2026-08-27 | max_chunks overflow rejects; silent eviction removed — contract in the port |
| 49 | 2026-08-28 | Sources block stripped from stored history; API keeps the block (rule extracted) |
| 50 | 2026-08-28 | Refusal = empty sources, chunks_used=0; constants + sync test (rule extracted) |
| 51 | 2026-08-28 | OAI history is client-first: stored history loads on conversation_id |
| 52 | 2026-08-31 | Query-path retry stacking purged (CORE CHANGE, no migration) |
| 53+57 | 2026-08-31 | Dead config fields purged in two batches — config must not lie |
| 54 | 2026-08-31 | Defaults `temperature: 0.0` / `top_p: 1.0` — determinism by default |
| 55+56 | 2026-08-31 | check_rag harness hardening: run-unique conv-id, Sources strip, crash=FAIL |
| 58 | 2026-08-31 | condense_question.j2 contract rewrite; both models re-baselined ×2 |
| 59 | 2026-09-01 | index_documents.py removed — one executor over one index |
| 60 | 2026-09-01 | Dual -ngl flags killed the embedder at startup (rule extracted) |
| 61 | 2026-09-01 | reranker.n_gpu_layers added to schema; first live GPU indexing (~10 chunks/s) |
| 62 | 2026-09-01 | Manual task + watcher raced over one embedder; one reindex path at a time |
| 63 | 2026-09-01 | memory→faiss at corpus growth; full reindex = the migration |
| 64 | 2026-09-01 | 600 s window + document checkpoints: a kill loses ≤1 doc (verified live) |
| 65 | 2026-09-02 | Atoms pipeline born: part budget 12000 B, four 400s root-caused; default split-only |
| 66 | 2026-09-03 | Freshness marker checked part01 only → 5 min → 127 ms SKIP (rule extracted) |
| 67 | 2026-09-03 | Archivist A/B: 7B crown (RU 2.5/3), 4B rejected for RU; THE DECISION TEST born |
| 68 | 2026-09-03 | Window-math method; every rebalance = check_rag pass + a named cost |
| 69 | 2026-09-03 | AST-audit false positives fixed; grep-verify rule extracted |
| 70 | 2026-09-04 | scripts/ + launchers under ruff+mypy strict; first full run caught check_llm broken 4 days |
| 71+72 | 2026-09-04→05 | tests/ under ruff then mypy; debt 372 + ~310 → 0 |
| 73 | 2026-09-05 | Missing tokenizer.json → CharFallback (loud warning); corrupt file stays fatal |
| 74 | 2026-09-05 | Linux unlink on open *.log → deleted inode; `_stack_running` guard (rule extracted) |
| 75 | 2026-09-05 | Canon outlier = char-fallback tokenizer; fix tokenizer mode before judging runs |
| 76 | 2026-09-05 | Config-liveness audit CLEAN: 0 dead knobs |
| 77 | 2026-09-05 | Live A/B: atoms proven for retrieval; DECISION TEST FAILED — subject inversion root-caused to the Status label |
| 78 | 2026-09-06 | Decision-guard campaign closed at benchmark maxima; live see-saw documented; validator ChatGPT-format-bound |
| 79 | 2026-09-07 | 4B = daily driver (best atoms, ×2.4 faster); EN-on-RU persists |
| 80 | 2026-09-07 | DeepSeek probe: invented-dates class born; format-agnostic layers hold |
| 81 | 2026-09-07 | Validator coverage is load-bearing: on ####-less corpus the decision-trap failed |
| 82 | 2026-09-07 | Bench wiped the live namespace; bench_000 + [000] isolation (rule extracted) |
| 83 | 2026-09-07 | 4 FUTURE tests contradicted their own corpus; FUTURE 30→29 (rule extracted) |
| 84 | 2026-09-07 | Atoms bench tier: FUTURE 29→34; atoms-undated-1 red on both (4B evades, 7B confabulates) |
| 85 | 2026-09-08 | Date-fix stop-rule: 'not-specified' is contagious on 4B; fully reverted |
| 86 | 2026-09-08 | Validator merged into prepare_docs (--validate); V5 content-stripping + V6 file-stem defects fixed |
| 87 | 2026-09-09 | Validation campaign closed; language header refuted (14B-class ×2); component B e2e gate born |
| 88 | 2026-09-09 | Atomic upsert in both stores — the duplicate window is closed |
| 89 | 2026-09-09 | Sources blocks reached the LLM via client-provided history; choke-point strip (rule extracted) |
| 90 | 2026-09-09 | Producer hardened: three birth-time correctors (dedup, decision demotion, date guard) |
| 91 | 2026-09-10 | V5 reference = the source chat's script; markdown image-noise stripped in split_file |
| 92 | 2026-09-10 | POLICY: atoms OFF until 14B fits VRAM — raw beats 4B atoms; basket exception (rule extracted) |
| 93 | 2026-09-10 | Watcher skip verifies chunk count vs total_chunks — a partial store self-repairs |
| 94 | 2026-09-10 | #81 closed as not-reproducible: new engine, raw-only corpus, zero false refusals |
| 95 | 2026-09-11 | `clean_cache` live-log guard: pgrep → port check (works on all OSes) |
| 96 | 2026-09-11 | `run_scripts.py` venv relaunch made Windows-safe (`run_servers` pattern) |
| 97 | 2026-09-11 | Required-V5 assert dropped: the 09-10 engine cured the EN flip (rule extracted) |
| 98 | 2026-09-11 | Quote-survival flake on 7B (3G/1R session): single red → re-run (rule extracted) |
| 99 | 2026-09-11 | `download_tokenizers`: atomic write — a network cut can no longer brick startup |
| 100 | 2026-09-11 | `clean_cache` rmtree onerror (B028): replacement needs 3.12+ — runtime version pick; legacy branch + noqa die together when the min passes 3.11 |
| 101 | 2026-09-11 | Windows kill fix: `_pid_alive` gate, CTRL_BREAK graceful, ≤10 s poll then force (safe: atomic writes); CREATE_NO_WINDOW dropped; Windows untested live — verify when back |
| 102 | 2026-09-11 | `run_servers` HOST default 0.0.0.0 → 127.0.0.1: a missing host fails safe (loopback) |
| 103 | 2026-09-11 | `llama.log` rotation port-guarded — Linux unlink under a running server is silent (#74 class) |
| 105 | 2026-09-12 | FlashAttention A/B (7B, new engine): verdicts byte-identical (17/17 + 9/9 + 31/34, new canon); speed tie (PCIe-bound); RAM 5.57 vs 6.04 GB (single run) — kept ON for headroom; run_servers.yaml: fa pairs toggle together |
| 106 | 2026-09-12 | Pre-read skip: stored uri stats fetched before the disk read — unchanged+complete files not re-read; orphan cleanup keyed on the disk inventory; clear re-reads all; watcher filters by include |
| 107 | 2026-09-12 | Scale stage 1: pre-flight max_chunks — human-readable refusal before embedding (rule extracted) |
| 108 | 2026-09-12 | Atomization intent folder, basket retired — the stale-copy trap dies by construction (rule extracted) |
| 109 | 2026-09-12 | Namespace mirroring — documents/ mirrors the raw tree (rule extracted) |
| 110 | 2026-09-12 | `_atomize` rename (sorts first); INFO line freshness-aware (rule extracted) |
| 111 | 2026-09-12 | Reconcile vanished sources: list → y/N → cleanup; the index is the watcher's (rule extracted) |
| 112 | 2026-09-12 | Unreadable is not deleted: read/stat OSError keeps the file's uri in the disk inventory — orphan cleanup preserves the chunks; WARNING per unreadable file; empty-but-readable keeps old semantics |
| 113 | 2026-09-12 | Watcher visibility: `_index_source` (module-level in lifespan.py) ERROR-logs runs with success=False; success ⇔ errors empty — the "failed"-substring check is gone (capital-F "Failed to chunk" errors were silent successes); empty corpus ("No documents found") is a failed run, not a silent success |
| 114 | 2026-09-12 | `index_folder` main loop iterates `sorted(expected_namespaces)` — per-namespace processing order no longer varies across processes (string-hash randomization); FUTURE RISK closed as executed |
| 115 | 2026-09-13 | Index saves bounded by `INDEX_IO_TIMEOUT` (`wait_for`): checkpoint save in `index_folder` and chat-export save in save-chat — a hung store can no longer stall the indexing loop or the HTTP request; checkpoint timeout lands in errors (fails the run per #113), chat-export timeout answers saved=True + indexed=False + reason |
| 116 | 2026-09-13 | save-chat checks content against `vector_store.max_document_size` before indexing — oversized export: file saved, indexed=False, reason (same contract as POST /rag/index); `_index_chat_export` uses `shutdown_chunker_if_temporary` — the 6th manual copy is gone |
| 117 | 2026-09-13 | POST /rag/delete with no selector is HTTP 400, same contract as reindex-without-sources (drift #47 family) — was 200 with the error in the body; the check moved before the try block (an in-try raise would surface as 500); the dead else-branch removed |
| 118 | 2026-09-13 | Targeted reindex reads only mapped sources: `index_folder` filters sources to the namespaces it processes (#8 — the full-reindex loop was N x reads); a nonexistent target fails fast before any disk read (late check + `processed_any` removed as dead); an emptied target namespace now returns "No documents found" (failed run) — watcher-path parity per #113, was a silent `{indexed: 0}` success |

## FUTURE RISKS

| Risk | Trigger | When to fix |
|------|---------|-------------|
| Split date-grounding criteria: producer (_ground_dates) accepts verbatim-or-covered, V2 checks covered-only — a date present verbatim in the source but yielding no parsed covering token gives a false V2 error | First observed false V2 flag | Unify into one _is_grounded shared by producer and validator |
| make_atoms is all-or-nothing: no retry, no per-part checkpoint — a transient HTTP failure mid-run discards the accumulated answers (zero errors measured, #65) | First network failure or lost long run | Bounded retry (3 attempts, single layer); per-part checkpoint only if losses repeat |
| Atom self-sufficiency is a prompt declaration, not a checked property: atoms with unresolved references ("he/it", "see above") or degenerate length pass V1-V6 | Unresolved-reference atoms observed in the live corpus | Add V7 as warn-only heuristics after the owner confirms real cases |
| _split_for_atoms cuts hard seams: a fact spanning two parts is extracted per-part (no proven loss to date; overlap would feed the duplication the #90 dedup guards) | A documented fact lost or misattributed specifically at a part seam | Overlap, dedup-aware; no change without a proven seam defect |
| The archivist prompt FINAL instruction still promises cross-part merge / Chronology completeness that independent per-part requests cannot deliver (#90 closed only the mechanical dedup half) | Next planned archivist prompt revision | Drop the unfulfillable sentence or feed prior-parts digests into FINAL (token-budget aware) |
| Atoms output is free-form markdown: a recurring malformed-format class would require regex surgery over the corpus | Malformed atoms become a documented recurring failure class | JSON-mode output — rewrites prompt, validators and corpus; only for a proven syntactic (not semantic) defect class |
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
| 7B bench multi-turn-1 ('Why?' followup): FLAKY, nondeterministic — 4 red / 2 green incl. one green on cold (2026-09-08 08:33; cold-warm correlation disproven); §14 greedy jitter amplified by chat condensation flips the verdict — first counterexample to 'all verdict-neutral'; [000]-correlated ([d] stable historically), live [d]+'Почему?' green; step unattributed (no condensed-query logging); 4B unaffected | flake rate grows, or numeric prefix used live | log condensed query (§2.7); rule: re-run before classifying a surprising 7B red |
| atoms-undated-1 red on both models (4B evades 'when'-answers 'what'; 7B confabulates by merging facts); prompt-level cure leaks into anti-echo rules (drift #85) | 14B-class model adopted, or a generation-side date-phrase guard designed | re-attempt date honesty at that layer |
| Advanced FAISS indices (IVF/PQ) — flat search cost grows linearly past ~100K chunks per namespace | single namespace exceeds 100K chunks (trigger already in ai_rules §2) | train IVF index, re-verify atomic upsert (#88) on it, config_version bump for the index format (stage 4 — CORE CHANGE, discuss first) |
| No date/source filters before retrieval — "what did I decide about X in March"-class queries rely on ranking alone | 3 documented live cases of "definitely there, not found" | metadata filter in QueryRequest -> vector store port extension (stage 5 — CORE CHANGE, discuss first) |
| prepare_docs: a document moved out of _atomize/ back to the root keeps its atoms file — atoms stop refreshing but are never removed; a stale atoms file keeps serving retrieval | first observed stale answer from a demoted document | extend the planned deletion-cascade reconcile to demotions — owner decision |
| 7B atomizer echoes archivist-prompt template fragments as atoms: deterministic (temp 0.0), same 34/141 Latin-letter atoms on re-extraction; V5 flags them (Latin-in-RU) — a known residual, caught by the validator; atoms stay experimental (#92) | template echo pollutes retrieval answers, or a 14B-class model is adopted | producer-side template-fragment filter (birth-time corrector, #90 family) or manual atom deletion |
| Inventory "unseen vs absent": orphan cleanup deletes chunks for any uri missing from the disk inventory; #112 closed the read/stat-failure path, but files dropped before the inventory is built (Path.is_file() swallows stat errors, an unreadable subdirectory truncates rglob, oversize skip) still count as deleted | Orphan chunks removed for a file that provably exists on disk | Positive-absence design: cleanup deletes only uris whose parent directory was successfully listed; oversize policy is a separate owner decision |
| Unreadable file at index time: chunks preserved (#112) and the failure is loud (#113), but the new content is not retried until the next file change or a manual reindex — retrying only transient failures needs a typed error taxonomy to tell them from deterministic refusals | A changed file serves stale content past the next watcher pass (watch the log for "Watcher reindex failed" + unreadable-file warnings) | Typed error taxonomy in the result channel, then a bounded retry for transient-only failures (one layer — drift #43) |
