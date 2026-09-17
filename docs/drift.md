# Known Architectural Drift

> Rule: Do not add new drift if old pattern can be fixed properly.
> AI reads this file before any architectural output (Document Meta §12).
> ACTIVE entries are constraints — do not "fix" them without explicit user request.
> FUTURE RISKS are deferred issues with concrete triggers — they are known, not forgotten.
> Git history is unreliable (commits often say "fix"). This file is the source of truth.
> Compaction rule: when History exceeds ~40 entries — extract surviving
> rules, commit the full text, then compress to one-liners
> (2026-09-11: #40–#99; 2026-09-12 round 3: #100–#111; 2026-09-14
> round 4: rule-extracted History rows deduped — lessons live in
> the Rule Extracted table and architecture.md; 2026-09-15 round 5:
> attribution campaign #124–#131, model-era titles retired to §14
> compaction; 2026-09-17 round 6: #129–#141 (model era + hybrid
> campaign) compacted to one-liners — surviving contracts in the
> Rule Extracted table, full text in git history).
>
> Risk hygiene (2026-09-14): bug-fix campaign closed items #112–#120.
> FUTURE RISKS entries touched by that campaign are annotated with
> the closing drift ID — when an annotated risk no longer matches
> the code, the entry is stale: fix or delete it, do not trust it.

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
| 22 | 2026-06-28 | Port objects own config, PipelineData carries references → `ai_rules.md` §2.2 |
| 7 | 2026-06-28 | Shared CODE ok, shared RESOURCE banned → `architecture.md` §4.3 |
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
| 49+89 | 2026-08→09 | History sanitized at one choke point (ChatManager); every door history enters gets the same cleaning — the API response keeps the sources block, stored history does not → `features/chat/manager.py` |
| 50 | 2026-08-28 | Refusal = empty sources; refusal strings are constants + prompt sync test → `architecture.md` §13.6 |
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
| 124 | 2026-09-14 | Chat exports indexed with speaker/date markers: every chunk carries who spoke and when (`_clean_chat_export`, markers every 12 lines); unknown export formats cleaned but never labeled ([HINT]); plain documents pass byte-identical → `scripts/prepare_docs.py` |
| 127 | 2026-09-14 | Context citations numbered per source file over the Sources-block key (source_uri > original_path > source): in-text [Document N] resolves 1:1 against Sources → `core/pipeline_steps.py` |
| 132 | 2026-09-16 | `prepare_docs.llm_model`: null/empty = omit the model field — a single-model local server routes without it; the permanent local value |
| 134 | 2026-09-16 | A prompt completeness rule must ship with homonym disambiguation; one variable per run with byte-identical retrieval = clean attribution |
| 135 | 2026-09-16 | Model-bound checks degrade to a visible xfail with explanation; mechanical contracts stay hard red — a known model limitation must not fail every full run → `tests/test_prepare_docs.py` |
| 136+140 | 2026-09-16 | A new port is TWO lines: the file AND the `__init__.py` board; ASYNC240 flags pathlib only on direct `Path()` bindings — fix the defect class, not the flag reading |
| 137 | 2026-09-16 | Hybrid fusion is rank-only RRF over per-leg candidate budgets; the lexical leg queries the ORIGINAL wording exactly once → `architecture.md` §13.7 |
| 138 | 2026-09-16 | Pure addition of an optional config section needs no `config_version` bump; breaking changes do → `ai_rules.md` §4 |
| 139 | 2026-09-16 | Dual-store discipline: write vector-first (capacity gate), delete lexical-first; a lexical failure is recorded, not raised; the skip guard requires BOTH stores' evidence (#93 class) |
| 140+141 | 2026-09-17 | Every mock touching lifespan must name BOTH state AND config fields — MagicMock fabricates unknowns as non-None → `ai_rules.md` §15; drift rows wrap underscored identifiers in backticks |


## FIXED → History (one-liners, self-contained)

Working horizon: 2026-08-27 → now. Entries are one-liners; the full
text of every entry lives in this file's git history. Every lesson
with a surviving contract is extracted into the Rule Extracted table
above or already lives in architecture.md. Compacted 2026-09-11
(round 2, after the #1–#39 archive); 2026-09-12 (round 3: #100–#111);
2026-09-14 (round 4: rows whose lesson lives in the Rule Extracted
table deduped); 2026-09-15 (round 5); 2026-09-17 (round 6: #129–#141).

| ID | Fixed | Summary |
|----|-------|---------|
| 40 | 2026-08-27 | Empty namespace now removes its index files — deleted chunks no longer resurrect on restart (both stores) |
| 41 | 2026-08-27 | Shutdown save no longer overwrites never-loaded namespaces with an empty store |
| 42 | 2026-08-27 | Watcher consumes the snapshot on success only; bounded retry (3) |
| 43 | 2026-08-28 | Retry stacking removed (16 attempts worst case) — one layer only |
| 44 | 2026-08-27 | Assistant turn persisted only after the stream completes |
| 45 | 2026-08-27 | Every SSE line carries its own `data:` prefix |
| 47 | 2026-08-27 | `/rag/reindex` without sources: explicit 400 (was 500 via UnboundLocalError) |
| 48 | 2026-08-27 | max_chunks overflow rejects; silent eviction removed — contract in the port |
| 51 | 2026-08-28 | OAI history is client-first: stored history loads on conversation_id |
| 52 | 2026-08-31 | Query-path retry stacking purged (CORE CHANGE, no migration) |
| 53+57 | 2026-08-31 | Dead config fields purged in two batches — config must not lie |
| 54 | 2026-08-31 | Defaults `temperature: 0.0` / `top_p: 1.0` — determinism by default |
| 55+56 | 2026-08-31 | check_rag harness hardening: run-unique conv-id, Sources strip, crash=FAIL |
| 58 | 2026-08-31 | condense_question.j2 contract rewrite; both models re-baselined ×2 |
| 59 | 2026-09-01 | index_documents.py removed — one executor over one index |
| 61 | 2026-09-01 | reranker.n_gpu_layers added to schema; first live GPU indexing (~10 chunks/s) |
| 62 | 2026-09-01 | Manual task + watcher raced over one embedder; one reindex path at a time |
| 63 | 2026-09-01 | memory→faiss at corpus growth; full reindex = the migration |
| 64 | 2026-09-01 | 600 s window + document checkpoints: a kill loses ≤1 doc (verified live) |
| 65 | 2026-09-02 | Atoms pipeline born: part budget 12000 B, four 400s root-caused; default split-only |
| 66 | 2026-09-03 | Freshness marker checked part01 only → 5 min → 127 ms SKIP (rule extracted) |
| 67 | 2026-09-03 | Archivist A/B: 7B crown (RU 2.5/3), 4B rejected for RU; THE DECISION TEST born |
| 68 | 2026-09-03 | Window-math method; every rebalance = check_rag pass + a named cost |
| 70 | 2026-09-04 | scripts/ + launchers under ruff+mypy strict; first full run caught check_llm broken 4 days |
| 71+72 | 2026-09-04→05 | tests/ under ruff then mypy; debt 372 + ~310 → 0 |
| 74 | 2026-09-05 | Linux unlink on open *.log → deleted inode; `_stack_running` guard (rule extracted) |
| 75 | 2026-09-05 | Canon outlier = char-fallback tokenizer; fix tokenizer mode before judging runs |
| 76 | 2026-09-05 | Config-liveness audit CLEAN: 0 dead knobs |
| 77 | 2026-09-05 | Live A/B: atoms proven for retrieval; DECISION TEST FAILED — subject inversion root-caused to the Status label |
| 78 | 2026-09-06 | Decision-guard campaign closed at benchmark maxima; live see-saw documented; validator ChatGPT-format-bound |
| 79 | 2026-09-07 | 4B = daily driver (best atoms, ×2.4 faster); EN-on-RU persists |
| 80 | 2026-09-07 | DeepSeek probe: invented-dates class born; format-agnostic layers hold |
| 81 | 2026-09-07 | Validator coverage is load-bearing: on ####-less corpus the decision-trap failed |
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
| 111 | 2026-09-12 | Reconcile vanished sources: list → y/N → cleanup; the index is the watcher's (rule extracted) |
| 112 | 2026-09-12 | Unreadable is not deleted: read/stat OSError keeps the file's uri in the disk inventory — orphan cleanup preserves the chunks; WARNING per unreadable file; empty-but-readable keeps old semantics |
| 113 | 2026-09-12 | Watcher visibility: module-level `_index_source` (lifespan.py) ERROR-logs success=False runs; success ⇔ errors empty — the "failed"-substring check is gone (capital-F chunk errors were silent successes); empty corpus is a failed run |
| 114 | 2026-09-12 | `index_folder` main loop iterates `sorted(expected_namespaces)` — processing order no longer varies across processes; FUTURE RISK closed as executed |
| 115 | 2026-09-13 | Index saves bounded by `INDEX_IO_TIMEOUT`: checkpoint (`index_folder`) and chat-export (save-chat) — a hung store can no longer stall the indexing loop or the HTTP request; checkpoint timeout lands in errors (fails the run per #113), export timeout answers saved=True + indexed=False |
| 116 | 2026-09-13 | save-chat checks `vector_store.max_document_size` before indexing — oversized export: saved, indexed=False + reason (same contract as POST /rag/index); `_index_chat_export` uses `shutdown_chunker_if_temporary` — 6th manual copy gone |
| 117 | 2026-09-13 | /rag/delete with no selector is HTTP 400, same contract as reindex-without-sources (drift #47 family) — was 200 + error in the body; the check sits before the try block (in-try raise would surface as 500); dead else-branch removed |
| 118 | 2026-09-13 | Targeted reindex reads only mapped sources (full loop was N x reads); a nonexistent target fails fast before any disk read (late check + `processed_any` removed as dead); an emptied target returns "No documents found" — #113 parity, was a silent `{indexed: 0}` success |
| 119 | 2026-09-13 | Interruption symmetry: the 4h timeout branch restores namespaces from disk exactly like cancellation — module-level `_restore_reindex_namespaces` is the single restore path; memory must not stay ahead of the last durable state |
| 120 | 2026-09-14 | `list_by_filter` typed-wins parity: faiss merges custom keys first, typed overwrite (as memory does) — a custom key can no longer shadow `source`/`source_uri` in one store but not the other; no-op `except Exception: raise` in faiss `_save_unlocked` removed |
| 121 | 2026-09-14 | Dead config field `ChatConfig.max_history_messages` removed (audit M2: no reader in src/scripts/tests/run_servers — grep-verified); config_version 3→4, old configs absorbed silently in the version validator |
| 122 | 2026-09-14 | Refusal contract unified (audit M1): one matcher — `is_refusal_answer` in core.constants — for both entry paths; preamble refusals no longer carry sources via /rag/query (parity with chat, live-caught 2026-09-10 edge). An LLM-unavailable answer keeps the no-evidence shape (error answer, not a refusal) and /rag/query raises 503 for it — chat-path parity; degraded-but-answered runs (errors + real answer) stay 200 |
| 123 | 2026-09-14 | `NamespaceConfig.prefix` docstring corrected: "Single-character" → "Short" — the live config uses "000" (3 chars) and query_parser handles it (audit L1); schema and behavior unchanged |
| 125 | 2026-09-14 | Live probe "overhaul vs new car": a 7B atom with an inverted fact (cheaper→more expensive) outranked its truthful raw source while both were retrieved; atoms demoted, corpus raw-only — POLICY #92 confirmed by measurement |
| 126 | 2026-09-14 | Live-caught attribution failures on raw chunks (bench green, live red): "which errors did I make" / "which decision did I take" attributed assistant advice as user actions — closed by #124 speaker markers; residual class (advice → inferred non-action) is 7B-bound, prompt word-lists rejected |
| 128 | 2026-09-14 | Archivist e2e gate green-rate ~75%→~25% after the llama.cpp engine update: acceptance quotes paraphrased, not verbatim; atom code unchanged, bench canon intact — engine-side. Recovered to 6/7 green on release 0.4.1 (2026-09-15); residual flake stays under the #97 re-run rule |
| 129 | 2026-09-15 | 0.4.1 live regression root-caused: Qwen2.5-7B × new-engine interaction; retrieval byte-identical across the flip (rerank 8/3, top 0.0143 both) — engine kept; model-engine pairs are re-validated together, an older model aging on a newer engine is expected, not a defect (method → architecture §14) |
| 130 | 2026-09-15 | Post-update gate extended: bench ×2 + canary still misses live-style regressions (bench covers the high-confidence edge, live fails at the low one) — protocol: bench ×2 + canary ×N + a fixed live mini-session (5-6 attribution probes, fresh chat) (→ architecture §14) |
| 131 | 2026-09-15 | Qwen3.5-4B × llama.cpp 0.4.1 adopted as serving baseline: 12 live probes, attribution clean (best of the campaign); documented 4B residuals: EN-on-RU ~2/12, bench 16/17 + 7/9 + 28/34 |
| 132 | 2026-09-16 | Gemma-4-E4B × 0.4.1 replaces Qwen as serving baseline: 16/17 + 9/9 + 29/34 — first 9/9 chat tier, ×2 identical, live attribution 4/4; Qwen retained as atomizer only (completeness prompt pulls noise and leaks facts live); Gemma-archivist rejected (quote ×3, 12 fabricated dates, translit); atom-batch swap: kill stack → Qwen on 8080 → prepare_docs [2] → restart; `llm_model` contract → rule extracted |
| 133 | 2026-09-16 | rag_strict.j2: Python example emits the 1991 fact + neutral Zenit-E completeness example (validated cross-model and live); top_k 3→5 — condensation-1 recovered, big-1 partial, format-strict-1 red (accepted price); ngl 99 ≡ 999, any partial layout deterministically red on condensation-1 — the layout must be deterministic; llama.log empty via launcher -lv 1 |
| 134 | 2026-09-16 | Iteration B (completeness rule in rag_strict #6) reverted after one measured run: homonym doc leaked into answers (priority-1), condensation-1 flipped to refusal, retrieval byte-identical — every delta prompt-attributable; corrected diagnosis: retrieval-2 'guido' is ranking-side (the creator chunk never reaches context on definitional queries), top_k lever measured shut (6 ≡ 5, 7 = −1 test); rule → extracted |
| 135 | 2026-09-16 | Archivist e2e gate two-tier: mechanical contract (atoms file, clean non-V5) stays hard red on every model; the verbatim-quote check is model-bound and degrades to a visible xfail — verified: Gemma xfail, Qwen full-suite green; rule → extracted |
| 136 | 2026-09-16 | Hybrid stage 1: `ILexicalIndex` port + stdlib BM25 adapter (`LexicalBm25Index`); JSON per-namespace disk format v1 — indices are derived data, rebuild by reindex (owner decision); inert until stage 4; stage lessons → extracted |
| 137 | 2026-09-16 | Hybrid stage 2: `PipelineData.lexical_index` (None = pre-hybrid byte-identical) + RRF fusion in `retrieve`/`multi_query_retrieve` — the lexical leg queries the ORIGINAL wording once, tie-break by chunk id, `RRF_K=60` constant; still inert until wiring |
| 138 | 2026-09-16 | Hybrid stage 3: `lexical_index` config section (provider, index_path) — absent section = dense-only, the `RerankerConfig` pattern with a required provider; no config_version bump: a pure optional addition migrates nothing (#121 vs #138) |
| 139 | 2026-09-16 | Hybrid stage 4a (write path): dual-store writes — vector first (capacity gate), lexical failure recorded not raised; dual-store skip guard = the missing-evidence detector (#93 class); lexical-first clear/orphan ordering (no resurrection window); per-store self-listing clears; inert until 4b |
| 140 | 2026-09-16 | Hybrid stage 4b (wiring): adapter created iff the section is present; startup load / shutdown save; both query paths; all delete selectors mirrored (each store lists its OWN contents, lexical first); activation owner-owned — enable = section + restart + reindex + check_rag ×2; lessons → extracted |
| 141 | 2026-09-17 | Hybrid activated: check_rag 16/17 + 9/9 + 29/34 — level-identical, set shifted (format-strict-1 green via the lexical leg, big-1 jazz/cat deeper, 'guido' unchanged); peak RAM 5.86 vs 5.39 GB (+0.5 GB, the measured price); MagicMock invents unknown CONFIG sections too — the `./MagicMock` repo-root litter caught and closed; rules → extracted |
| 142 | 2026-09-17 | Comment audit (all 884 lines, src+scripts): 2 filename-dup first lines removed, duplicated mypy-flags comment block deduped, download_tokenizers design-musing block replaced with one intent line, reranker_null "old tests" wording corrected (the None-config call is a live test, not legacy). Verdict: 876/884 load-bearing "why" comments — density healthy, no further action; comment classes confirmed: drift links, decisions-with-cost, spec blocks (prepare_docs/check_rag/check_all) |
| 143 | 2026-09-17 | Attribution diagnostics raised to INFO (FUTURE RISK closed): rag.condense log line (original/condensed query) was DEBUG-only — two live condensation regressions (2026-09-14/15) were diagnosed by manual rerank-score comparison instead; stream path logged chunks_used=N on refusals where non-stream logged 0 (#50 contract broken in the log, not in responses) — both fixed, log-only, no behavior change. Gate catch: UP032 — the new INFO line used .format; §9 STYLE mandates f-strings (cited in this very session before violating it — the rules are for the AI too).|
| 145 | 2026-09-17 | rag_strict synthesis (owner-merged): base+rule-3 same-subject exception (third-person examples preserved) + Python/Spanish examples + rule 13 (date-not-specified) = 17/17 + 9/9 + 29/34 — first full contract+chat on Gemma. Attribution measured: the EXAMPLE is the only 'guido' catalyst (rules alone fail, attempt #6), third-person style keeps condensation alive (first-person examples break it, #133 class), rule 13 brings atoms-undated-1 with no observed contagion this run (#85 watch continues). Prices: edge-2 + format-strict-1 join known-limits (weaker listing pressure); priority-1 stays red by design tension — same query as retrieval-2, one requires guido, the other forbids snake, no single answer passes both. Caveat: Python/Spanish examples are verbatim bench cases (#133 discipline says neutral domains) — generalization unproven, neutralization deferred as optional future iteration. Rule 2 pronoun exception likely inert (generate never sees history) — kept, harmless. ×2 re-run + live mini-session pending before canon |

## FUTURE RISKS

| Risk | Trigger | When to fix |
|------|---------|-------------|
| Split date-grounding criteria: producer (`_ground_dates`) accepts verbatim-or-covered, V2 checks covered-only — a date present verbatim in the source but yielding no parsed covering token gives a false V2 error | First observed false V2 flag | Unify into one `_is_grounded` shared by producer and validator |
| make_atoms is all-or-nothing: no retry, no per-part checkpoint — a transient HTTP failure mid-run discards the accumulated answers (zero errors measured, #65) | First network failure or lost long run | Bounded retry (3 attempts, single layer); per-part checkpoint only if losses repeat |
| Atom self-sufficiency is a prompt declaration, not a checked property: atoms with unresolved references ("he/it", "see above") or degenerate length pass V1-V6 | Unresolved-reference atoms observed in the live corpus | Add V7 as warn-only heuristics after the owner confirms real cases |
| `_split_for_atoms` cuts hard seams: a fact spanning two parts is extracted per-part (no proven loss to date; overlap would feed the duplication the #90 dedup guards) | A documented fact lost or misattributed specifically at a part seam | Overlap, dedup-aware; no change without a proven seam defect |
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
| RAM headroom shrink | Peak RAM (6.5/15 GB at ~140 bench docs) grows past ~10 GB with real corpus | Before adding any RAM-heavy component; measure first |
| condensation-1 fragility: flips with GPU offload layout (full green 3/3, partial red 5/5, #133) and with rag_strict answer-style shifts (first-person examples broke it, #145) — the log line is INFO now (#143) | a surprising condensation red, or any rag_strict edit / serving layout change | verify layout first, read rag.condense in app.log, re-run the full chat tier after any prompt edit |
| atoms-undated-1 red on both models (4B evades 'when'-answers 'what'; 7B confabulates by merging facts); prompt-level cure leaks into anti-echo rules (drift #85) | 14B-class model adopted, or a generation-side date-phrase guard designed | re-attempt date honesty at that layer |
| Advanced FAISS indices (IVF/PQ) — flat search cost grows linearly past ~100K chunks per namespace | single namespace exceeds 100K chunks (trigger already in ai_rules §2) | train IVF index, re-verify atomic upsert (#88) on it, config_version bump for the index format (stage 4 — CORE CHANGE, discuss first) |
| No date/source filters before retrieval — "what did I decide about X in March"-class queries rely on ranking alone | 3 documented live cases of "definitely there, not found" | metadata filter in QueryRequest -> vector store port extension (stage 5 — CORE CHANGE, discuss first) |
| prepare_docs: a document moved out of _atomize/ back to the root keeps its atoms file — atoms stop refreshing but are never removed; a stale atoms file keeps serving retrieval. Triggered live 2026-09-14 (demoted atom outranked its truthful raw source); closed by owner action + #111 reconcile — the demotion path itself still has no deletion cascade | next demotion of an _atomize document | extend reconcile to demotions — owner decision |
| 7B atomizer echoes archivist-prompt template fragments as atoms: deterministic (temp 0.0), same 34/141 Latin-letter atoms on re-extraction; V5 flags them (Latin-in-RU). Triggered live 2026-09-14 (THE DECISION TEST served as an answer from the atoms); corpus raw-only since (#92/#125) — echo sleeping | atoms re-enabled on a 14B-class model, or re-observed on any corpus | producer-side template-fragment filter (birth-time corrector, #90 family) or manual atom deletion |
| Same-stem collisions (#2, review 2026-09-13): two files with the same stem in one namespace (chat.md + chat.txt) share `metadata.source = stem` — the per-file indexing loop makes the last writer erase the first file's chunks (batch /rag/index keeps both; chat path protected by the synthetic `__chat__` id). Fix = key change on disk + full reindex — disk format is sacred, no migration warranted while the live tree has no such pair | first observed real collision in the live tree (one file's chunks vanish after another indexes) | owner decision: new key format (e.g. source_uri) + backward-compat loader + reindex, or reject duplicate stems at collect time (cheap warning, no migration) |
| Probe atoms (zawita-obuvi) live in the default namespace from the 2026-09-16 Gemma-archivist probe; _atomize exit has no deletion cascade — #92 says raw-only | owner decision / next reconcile | remove atoms file from documents/, restore source to root, reconcile y/N; or accept as a time-boxed experiment |
| e2e archivist gate is red on the serving model by design — a full-green suite requires the atomizer swapped onto 8080 for the run | release checkpoint / full green suite needed | swap procedure per #132 during check_all |
| Priority-pair tension (#145): retrieval-2 and priority-1 ask the SAME question in the same namespace; one requires 'guido' in the answer, the other forbids 'snake' — with both docs in context no single answer passes both (the 145-prompt answers guido+snake: retrieval-2 green, priority-1 red) | any attempt to "fix" priority-1 or retrieval-2 | accept the documented tradeoff; a real fix needs answer-side entity disambiguation the 4B class lacks — re-evaluate on a model change |
| Second-resolution mtime (#9, review 2026-09-13): `last_modified` is a "%Y-%m-%d %H:%M:%S" string — two saves within one second compare equal; the watcher sees the change (float mtime) but the pre-read skip and unchanged-filter both match on the truncated string, so the update is deliberately skipped. The watcher then consumes the snapshot — the change never indexes until the next touch | first documented case of a sub-second save missed (stale answer traced to it) | store float mtime in metadata (stored-format change — needs a migration decision), or compare disk float mtime against stored string with a sub-second tolerance |
| Emptied source folder (#10, review 2026-09-13): "0 docs, chunks exist" guard keeps the chunks forever — by design (data-loss protection, #112 tightened it). Since #113 every watcher pass ERROR-logs "No documents found", so the state is loud; cleanup is manual (`/rag/delete` with clear). Half-open: folders whose files are all unreadable also hold chunks silently (WARNING per file) | sustained noise from the ERROR log on an intentionally emptied folder, or a stale answer served long-term | owner decision: a reconcile mode with explicit y/N (like #111 prepare_docs), or a documented acceptance with a periodic reminder in the log |
| Double checkpoint write per document (#16, review 2026-09-13): `upsert` persists inside (#88 atomicity) and the per-document checkpoint saves again (#64 crash window) — two full namespace writes per document. At ~3.5K chunks both writes are milliseconds; at 80K chunks ≈ 120 MB x 2 per document. The checkpoint is also the safety net for the port-default upsert contract, so removing it is not a one-liner | namespace approaches max_chunks / indexing pass duration grows visibly (measure first) | measure save duration per checkpoint; if dominant, checkpoint every N documents instead of each (crash window grows to N docs — needs an explicit tradeoff decision) |
| Inventory "unseen vs absent": orphan cleanup deletes chunks for any uri missing from the disk inventory; #112 closed the read/stat-failure path, but files dropped before the inventory is built (Path.is_file() swallows stat errors, an unreadable subdirectory truncates rglob, oversize skip) still count as deleted | Orphan chunks removed for a file that provably exists on disk | Positive-absence design: cleanup deletes only uris whose parent directory was successfully listed; oversize policy is a separate owner decision |
| Unreadable file at index time: chunks preserved (#112) and the failure is loud (#113), but the new content is not retried until the next file change or a manual reindex — retrying only transient failures needs a typed error taxonomy to tell them from deterministic refusals | A changed file serves stale content past the next watcher pass (watch the log for "Watcher reindex failed" + unreadable-file warnings) | Typed error taxonomy in the result channel, then a bounded retry for transient-only failures (one layer — drift #43) |
| Watcher keys snapshots by `str(path)`: two SourceConfigs sharing one path overwrite each other's snapshots every poll — change detection for one of them becomes unreliable | before mapping a second source to the same path | key by (namespace, path) |
| Chunker-shared `custom` dict aliases across frozen chunks — latent until a chunker returns chunks sharing one dict | a chunker that shares one custom dict between chunks | copy on chunk rebuild in IndexingManager |
