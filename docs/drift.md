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
> Rule Extracted table, full text in git history; 2026-09-18
> round 7: #142–#152 (observability, coverage, lexical backfill,
> date campaign, docs sync) compacted the same way; 2026-09-30
> round 8: #112–#223 compacted — surviving contracts in the Rule
> Extracted table, full text in git history).
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
| 60 | 2026-09-01 | `n_gpu_layers` lives in config.yaml only; `extra_args` never carries -ngl → `run_servers.yaml` |
| 66 | 2026-09-03 | Idempotency marker = the exact artifact the producer writes → `scripts/prepare_docs.py` |
| 69+76 | 2026-09-03→05 | Audit hygiene: grep-verify imports before orphan conclusions; config liveness by reader-pattern, not word count |
| 70+72 | 2026-09-04→05 | Lint/type targets must include src+scripts+tests; structural test edits: sed banned, ast.parse per patch → `scripts/check_all.py` |
| 73 | 2026-09-05 | Missing asset degrades loudly (warning + recovery); corrupt/empty stays fatal → `adapters/huggingface_tokenizer.py` |
| 74 | 2026-09-05 | OS-dependent protection is no protection — behavioral guards live in the script |
| 77 | 2026-09-05 | Manual corpus/atom edits = measurement probe only, never a process |
| 78+85 | 2026-09-06→08 | Prompt stop-rule: no Nth iteration for a leaking pattern; benchmark-green ≠ live-green → `architecture.md` §14 lessons |
| 82 | 2026-09-07 | Bench never clears watcher-mapped namespaces (`bench_000`, `[000]`) → `scripts/check_rag.py` |
| 83 | 2026-09-07 | Test premises verified against the corpus, not intent |
| 91 | 2026-09-10 | A language check needs an external reference — self-comparison cannot see a uniform flip → V5 in `scripts/prepare_docs.py` |
| 92 | 2026-09-10 | POLICY: atoms OFF until a 14B-class model fits VRAM; a distillation layer must measurably beat its source |
| 93 | 2026-09-10 | A skip condition must verify the artifact it vouches for, not just the key it remembers |
| 97+98 | 2026-09-11 | Never lock a known defect as a required test outcome; flake rule: single red → re-run + find the config delta, two consecutive reds → investigate |
| 107 | 2026-09-12 | Pre-flight `max_chunks`: refuse before embedding; the store stays the guard (#48) → `features/rag/indexing.py` |
| 108-110 | 2026-09-12 | Ingestion tree: root=default, subfolders=namespaces, `_atomize/`=intent; documents/ is a mirror, never edited by hand → `architecture.md` §2.9, `scripts/prepare_docs.py` |
| 111 | 2026-09-12 | Reconcile: leftovers of vanished sources removed only on an explicit y/N; the index is the watcher's → `scripts/prepare_docs.py` |
| 124 | 2026-09-14 | Chat exports indexed with speaker/date markers: every chunk carries who spoke and when (`_clean_chat_export`, markers every 12 lines); unknown export formats cleaned but never labeled ([HINT]); plain documents pass byte-identical → `scripts/prepare_docs.py` |
| 127 | 2026-09-14 | Context citations numbered per source file over the Sources-block key (`source_uri` > `original_path` > source): in-text [Document N] resolves 1:1 against Sources → `core/pipeline_steps.py` |
| 132 | 2026-09-16 | `prepare_docs.llm_model`: null/empty = omit the model field — a single-model local server routes without it; the permanent local value |
| 134 | 2026-09-16 | A prompt completeness rule must ship with homonym disambiguation; one variable per run with byte-identical retrieval = clean attribution |
| 135 | 2026-09-16 | Model-bound checks degrade to a visible xfail with explanation; mechanical contracts stay hard red — a known model limitation must not fail every full run → `tests/test_prepare_docs.py` |
| 136+140 | 2026-09-16 | A new port is TWO lines: the file AND the `__init__.py` board; ASYNC240 flags pathlib only on direct `Path()` bindings — fix the defect class, not the flag reading |
| 137 | 2026-09-16 | Hybrid fusion is rank-only RRF over per-leg candidate budgets; the lexical leg queries the ORIGINAL wording exactly once → `architecture.md` §13.7 |
| 138 | 2026-09-16 | Pure addition of an optional config section needs no `config_version` bump; breaking changes do → `ai_rules.md` §4 |
| 139 | 2026-09-16 | Dual-store discipline: write vector-first (capacity gate), delete lexical-first; a lexical failure is recorded, not raised; the skip guard requires BOTH stores' evidence (#93 class) |
| 140+141 | 2026-09-17 | Every mock touching lifespan must name BOTH state AND config fields — MagicMock fabricates unknowns as non-None → `ai_rules.md` §15; drift rows wrap underscored identifiers in backticks |
| 146 | 2026-09-18 | The lexical mirror is repaired from the vector inventory at startup — the embedder is never a repair tool → `architecture.md` §2.9 |
| 149 | 2026-09-18 | A chunk's date is what the document itself states: markers at split time, no honest date → empty value, never a guess → `architecture.md` §2.9 |
| 151 | 2026-09-18 | A date frame is a query scope like a namespace: narrows search BEFORE ranking, both legs or neither, undated honestly excluded → `architecture.md` §13.8 |
| 113 | 2026-09-12 | Watcher runs are loud: success ⇔ errors empty; failures ERROR-log; an empty corpus is a failed run → `features/rag/manager.py` |
| 119 | 2026-09-13 | Interrupted reindex restores namespaces from disk — memory never stays ahead of the durable state → `features/rag/handlers.py` |
| 122 | 2026-09-14 | One refusal matcher for both entry paths; LLM-unavailable is a 503 error, not a refusal → `core/constants.py` |
| 164 | 2026-09-21 | Off-RAG turns pollute condensation — the condense context filters both roles (user prefix + assistant Sources marker) → `features/chat/manager.py` |


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
| 48 | 2026-08-27 | `max_chunks` overflow rejects; silent eviction removed — contract in the port |
| 51 | 2026-08-28 | OAI history is client-first: stored history loads on `conversation_id` |
| 52 | 2026-08-31 | Query-path retry stacking purged (CORE CHANGE, no migration) |
| 53+57 | 2026-08-31 | Dead config fields purged in two batches — config must not lie |
| 54 | 2026-08-31 | Defaults `temperature: 0.0` / `top_p: 1.0` — determinism by default |
| 55+56 | 2026-08-31 | `check_rag` harness hardening: run-unique conv-id, Sources strip, crash=FAIL |
| 58 | 2026-08-31 | `condense_question.j2` contract rewrite; both models re-baselined ×2 |
| 59 | 2026-09-01 | `index_documents.py` removed — one executor over one index |
| 61 | 2026-09-01 | `reranker.n_gpu_layers` added to schema; first live GPU indexing (~10 chunks/s) |
| 62 | 2026-09-01 | Manual task + watcher raced over one embedder; one reindex path at a time |
| 63 | 2026-09-01 | memory→faiss at corpus growth; full reindex = the migration |
| 64 | 2026-09-01 | 600 s window + document checkpoints: a kill loses ≤1 doc (verified live) |
| 65 | 2026-09-02 | Atoms pipeline born: part budget 12000 B, four 400s root-caused; default split-only |
| 66 | 2026-09-03 | Freshness marker checked part01 only → 5 min → 127 ms SKIP (rule extracted) |
| 67 | 2026-09-03 | Archivist A/B: 7B crown (RU 2.5/3), 4B rejected for RU; THE DECISION TEST born |
| 68 | 2026-09-03 | Window-math method; every rebalance = `check_rag` pass + a named cost |
| 70 | 2026-09-04 | scripts/ + launchers under ruff+mypy strict; first full run caught `check_llm` broken 4 days |
| 71+72 | 2026-09-04→05 | tests/ under ruff then mypy; debt 372 + ~310 → 0 |
| 74 | 2026-09-05 | Linux unlink on open *.log → deleted inode; `_stack_running` guard (rule extracted) |
| 75 | 2026-09-05 | Canon outlier = char-fallback tokenizer; fix tokenizer mode before judging runs |
| 76 | 2026-09-05 | Config-liveness audit CLEAN: 0 dead knobs |
| 77 | 2026-09-05 | Live A/B: atoms proven for retrieval; DECISION TEST FAILED — subject inversion root-caused to the Status label |
| 78 | 2026-09-06 | Decision-guard campaign closed at benchmark maxima; live see-saw documented; validator ChatGPT-format-bound |
| 79 | 2026-09-07 | 4B = daily driver (best atoms, ×2.4 faster); EN-on-RU persists |
| 80 | 2026-09-07 | DeepSeek probe: invented-dates class born; format-agnostic layers hold |
| 81 | 2026-09-07 | Validator coverage is load-bearing: on ####-less corpus the decision-trap failed |
| 84 | 2026-09-07 | Atoms bench tier: FUTURE 29→34; `atoms-undated-1` red on both (4B evades, 7B confabulates) |
| 85 | 2026-09-08 | Date-fix stop-rule: 'not-specified' is contagious on 4B; fully reverted |
| 86 | 2026-09-08 | Validator merged into `prepare_docs` (--validate); V5 content-stripping + V6 file-stem defects fixed |
| 87 | 2026-09-09 | Validation campaign closed; language header refuted (14B-class ×2); component B e2e gate born |
| 88 | 2026-09-09 | Atomic upsert in both stores — the duplicate window is closed |
| 89 | 2026-09-09 | Sources blocks reached the LLM via client-provided history; choke-point strip (rule extracted) |
| 90 | 2026-09-09 | Producer hardened: three birth-time correctors (dedup, decision demotion, date guard) |
| 91 | 2026-09-10 | V5 reference = the source chat's script; markdown image-noise stripped in `split_file` |
| 92 | 2026-09-10 | POLICY: atoms OFF until 14B fits VRAM — raw beats 4B atoms; basket exception (rule extracted) |
| 93 | 2026-09-10 | Watcher skip verifies chunk count vs `total_chunks` — a partial store self-repairs |
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
| 105 | 2026-09-12 | FlashAttention A/B (7B, new engine): verdicts byte-identical (17/17 + 9/9 + 31/34, new canon); speed tie (PCIe-bound); RAM 5.57 vs 6.04 GB (single run) — kept ON for headroom; `run_servers.yaml`: fa pairs toggle together |
| 106 | 2026-09-12 | Pre-read skip: stored uri stats fetched before the disk read — unchanged+complete files not re-read; orphan cleanup keyed on the disk inventory; clear re-reads all; watcher filters by include |
| 111 | 2026-09-12 | Reconcile vanished sources: list → y/N → cleanup; the index is the watcher's (rule extracted) |
| 112 | 2026-09-12 | Unreadable ≠ deleted: OSError keeps the uri in the disk inventory — orphan cleanup preserves the chunks; WARNING per file |
| 113 | 2026-09-12 | Watcher loudness — see Rule Extracted |
| 114 | 2026-09-12 | `index_folder` iterates `sorted(expected_namespaces)` — deterministic order; FUTURE RISK closed |
| 115 | 2026-09-13 | Index saves bounded by `INDEX_IO_TIMEOUT` (checkpoint + save-chat); a hung store can no longer stall the loop or the request |
| 116 | 2026-09-13 | save-chat pre-checks `max_document_size` (saved, indexed=False + reason — the /rag/index contract); `shutdown_chunker_if_temporary` reused |
| 117 | 2026-09-13 | /rag/delete without a selector → 400 (the #47 family); the check sits before the try block |
| 118 | 2026-09-13 | Targeted reindex reads only mapped sources; nonexistent target fails fast; emptied target = "No documents found" (#113 parity) |
| 119 | 2026-09-13 | Reindex interruption restores from disk — see Rule Extracted |
| 120 | 2026-09-14 | `list_by_filter` typed-wins parity in both stores — a custom key cannot shadow `source`/`source_uri` in one only |
| 121 | 2026-09-14 | Dead config field `max_history_messages` removed; `config_version` 3→4, old configs absorbed |
| 122 | 2026-09-14 | Refusal contract unified — see Rule Extracted |
| 123 | 2026-09-14 | `NamespaceConfig.prefix` docstring: "Single-character" → "Short" (the live config uses "000"); schema unchanged |
| 125 | 2026-09-14 | Live probe: an inverted-fact atom outranked its truthful source — atoms demoted, corpus raw-only; #92 confirmed by measurement |
| 126 | 2026-09-14 | Live attribution failures on raw chunks — closed by speaker markers; the residual class is 7B-bound |
| 128 | 2026-09-14 | Archivist e2e broke on the engine update (paraphrased quotes), recovered on 0.4.1; residual flake → the #97 re-run rule |
| 129 | 2026-09-15 | 0.4.1 regression root-caused to the model×engine pair; retrieval byte-identical; pairs re-validated together (method → §14) |
| 130 | 2026-09-15 | Post-update gate: bench ×2 + canary + a fixed live mini-session — bench misses the low-confidence edge (→ §14) |
| 131 | 2026-09-15 | Qwen3.5-4B × 0.4.1 = serving baseline; residuals documented (EN-on-RU ~2/12) |
| 132 | 2026-09-16 | Gemma-4-E4B replaces Qwen as serving (first 9/9 chat tier); Qwen = atomizer; atom-batch swap runbook (kill → 8080 → [2] → restart) |
| 133 | 2026-09-16 | `rag_strict.j2`: 1991-fact example + neutral Zenit-E case; `top_k` 3→5 (one accepted red); the layout must be deterministic (ngl 99 ≡ 999) |
| 134 | 2026-09-16 | Iteration B reverted after one measured run: homonym leak + condensation flip, retrieval byte-identical — every delta prompt-attributable; 'guido' is ranking-side |
| 135 | 2026-09-16 | Archivist gate two-tier — see Rule Extracted (#135) |
| 136 | 2026-09-16 | Hybrid stage 1: `ILexicalIndex` port + stdlib BM25; JSON disk format v1; derived data — reindex rebuilds |
| 137 | 2026-09-16 | Hybrid stage 2: `PipelineData.lexical_index` + RRF fusion in both retrieve steps; ORIGINAL wording once; `RRF_K=60` constant |
| 138 | 2026-09-16 | Hybrid stage 3: `lexical_index` config section — absent = dense-only; optional addition, no bump (#121 vs #138) |
| 139 | 2026-09-16 | Hybrid stage 4a: dual-store writes — vector first (capacity gate), lexical failure recorded; dual-store skip guard (#93 class) |
| 140 | 2026-09-16 | Hybrid stage 4b: wiring — adapter iff section present; delete selectors mirrored; activation owner-owned (section + restart + reindex + bench ×2) |
| 141 | 2026-09-17 | Hybrid activated: level-identical, set shifted; +0.5 GB RAM (the lexical text copy); MagicMock invents CONFIG sections too — the `./MagicMock` litter |
| 142 | 2026-09-17 | Comment audit: 4 defects in 884 lines — density healthy |
| 143 | 2026-09-17 | `rag.condense` → INFO, stream refusal logs `chunks_used=0`; UP032 — the rules bind the AI too |
| 145 | 2026-09-17 | `rag_strict` synthesis (owner-merged): first full contract+chat on Gemma; the EXAMPLE is the only 'guido' catalyst; priority-1 red by design tension |
| 146 | 2026-09-17 | Lexical mirror backfill at startup (CORE CHANGE: `list_chunks`): re-fed from stored texts, embedder never called; `ADJUDICATED_DUPLICATES` registry |
| 147 | 2026-09-17 | CPU embed rate ~8.7 on 0.4.1 — the GPU switch buys little; docs-only |
| 148 | 2026-09-17 | +21 tests: FAISS guards, rollbacks, overflow, backfill branches; suite 1183→1204 |
| 149 | 2026-09-17 | Date stage 1: machine-form markers at split, `doc_date` into `ChunkMetadata.custom`; re-baselined |
| 151 | 2026-09-18 | Date stage 2 (CORE CHANGE: `date_filter` on both ports): pre-retrieval frame in BOTH legs, phrase STAYS in text; live-verified |
| 152 | 2026-09-18 | Docs sync: owner requirements codified (`ai_rules` top block); architecture §1/§2.9/§13.8/§14; anchor-freshness rule (§9) |
| 154 | 2026-09-18 | Hardcode audit CLEAN; follow-ups: cloud defaults → empty + `_check_explicit_models` guard in BOTH config layers — a forgotten `api_base` spent real money silently |
| 155 | 2026-09-18 | Config-freeze UPHELD against 8 extraction proposals; seven literals named; `file_encodings` → yaml (owner language data) |
| 156 | 2026-09-18 | Test mannequin factories (conftest + local helpers); the #151 wiring-drift class closed; protocol lessons → extracted |
| 157 | 2026-09-18 | Test hygiene: five dead fixtures removed (grep is the tool — fixtures are invisible to AST); lexical shutdown covered honestly |
| 158 | 2026-09-19 | Backup feature (CORE CHANGE): three non-rebuildable assets, self-verified copies; lesson → extracted: a new script touches three lists |
| 159 | 2026-09-21 | Live session (40+ probes): F1/F5-v2 closed (JSON migration + #161); F2 is model-independent — retest on every upgrade; rule: a re-exported chat is a new corpus |
| 160 | 2026-09-20 | Corpus → chat-JSON (SaveAI): `_chat_json_to_markdown` (role/`created_at`/`displayModel` → [Speaker, date] markers); freshness/orphan changes ship with their stale-marker test; multi-part test edits go by-name scripts, not FIND/REPLACE |
| 161 | 2026-09-21 | `condense_question.j2` rewrite (4 iterations): pronoun resolution + topic-is-final + NEVER different-topic; CLOSED live; PRICE: condensation-1 → known limitation, canon 28/34 |
| 162 | 2026-09-21 | .md chat-export cleaner retired (~250 lines); chats = JSON only, .md/.txt plain, byte-identical; atoms reactivation requires a JSON decision-validator rewrite |
| 163 | 2026-09-21 | LANGUAGE RULE: src/ English-only INCLUDING .j2 templates; Cyrillic = DATA only; future src/ owner-language markers need an explicit drift entry |
| 164 | 2026-09-21 | Off-RAG turns pollute condensation — see Rule Extracted |
| 165 | 2026-09-21 | OWNER BACKLOG → implemented as #176 (`chat.max_tokens_plain`): superseded |
| 166 | 2026-09-21 | `context_build` truncation removed — ground-truth docs ship IN FULL, 80k tripwire; History tail + FUTURE RISKS were silently lost before |
| 167 | 2026-09-21 | `run_servers` hardening: venv check, default-key guard, -ngl single-source, honest readiness/exit codes |
| 168 | 2026-09-21 | `check_rag` hardening: tier counters, 65 s timeout, negation window, stream parity, monitor into the log; re-baseline expected |
| 169 | 2026-09-21 | `prepare_docs` batch 4: grown-json cured both sides; `--full` layer separation; flags validated before the destructive reconcile |
| 170 | 2026-09-22 | Bench re-baseline: `atoms-undated-1` GREEN; canon 16/16 + 8/9 + 29/35, 6 known limitations |
| 171 | 2026-09-22 | `kill.py`: guarded probes, honest exit code (held ports = 1); aligned with `run_servers.kill_main` |
| 172 | 2026-09-22 | Small fixes, 8 scripts: honest counters/exit codes, dead code — full list in git |
| 173 | 2026-09-22 | `mutmut_check`: flag leak fixed; "all killed" retracted — mutmut 2.x exit codes don't encode survivors |
| 174 | 2026-09-22 | Docs batch: Apache-2.0 LICENSE, NOTICE, pyproject package-data; docs synced to #160/#162/#163 |
| 175 | 2026-09-22 | Final pass: comment audit clean, `_REASON_MAX`/`_DOC_SIZE_WARNING` named |
| 176 | 2026-09-22 | CORE CHANGE: `chat.max_tokens_plain` — optional plain-chat budget; cured mid-sentence off-RAG truncation |
| 177 | 2026-09-22 | Chat UI attach WORKS client-side (10 files / 5 MB / 50K chars); the 8K window is the limitation (FUTURE RISKS) |
| 178 | 2026-09-22 | `admin.py` state typed; `main.py` version from package metadata |
| 179 | 2026-09-22 | Final gate, bench half: ×2 identical 16/16 + 9/9 + 29/35; condensation-1 green (fragile) |
| 180 | 2026-09-22 | Final gate, live half: core green; NEW class premise-compliance red; genitive dates unparsed (yaml data) |
| 181 | 2026-09-22 | Prompt sync guard caught a bulk-pass defect; a bulk template pass commits only after a green `check_all` |
| 182 | 2026-09-23 | `rag_strict.j2` RU markers (#163-required authorization): rule 12 verb list, rule 13 «Дата не указана», RU examples |
| 183 | 2026-09-23 | Live audit: `lexical_index` missing from the qwen profile — a profile diff contains ONLY model sections |
| 184 | 2026-09-23 | Qwen-heir serving gate FAIL both configs: over-synthesis, over-refusal — non-serving |
| 185 | 2026-09-23 | Gemma-4-E4B QAT adopted: ×2 identical 16/16 + 9/9 + 30/35, strictly better; VRAM 3030 MB; rollback profiles retained |
| 186 | 2026-09-23 | CORE CHANGE: bilingual refusal — `rag.refusal_phrase_local` (owner yaml, src ASCII), matched on both entry paths; injection refusal stays EN |
| 187 | 2026-09-23 | Bilingual re-baseline: deps wiring gap caught by missing-ru-2 (its designed job); canon 16/16 + 9/9 + 31/36 |
| 188 | 2026-09-24 | Bare-day frame (CORE CHANGE): day digits anchor the match, a bare month never activates; precedence digital > prepositional > bare day |
| 190 | 2026-09-24 | Date stage 3 (CORE CHANGE): `DateFilter.day` — exact-day filter; `doc_date` full YYYY-MM-DD (legacy matches month frames only); sliding inheritance; one reindex closed the campaign |
| 191 | 2026-09-24 | FAISS adaptive fetch: x4 → x100 → full scan until `top_k` filtered results; dedup via `seen_ids`; BM25 unaffected; a day requires an explicit year |
| 192 | 2026-09-24 | `multi_query` abstraction bridge: canon held, the probe not met — chunk dilution, not the prompt → #193 |
| 193 | 2026-09-24 | Speaker-aware chunking REVERTED: mechanically sound, the 4B declined to bind — slicing cannot fix a comprehension ceiling; revisit via atoms/14B |
| 196 | 2026-09-24 | Atoms live pilot: Gemma-4 passed clean, Qwen3.5 hallucinated — CAUGHT by V5; the my-voice class IS reachable |
| 198 | 2026-09-24 | Qwen3.5-4B fails the refusal contract + bloats chat — Gemma serving, Qwen atomizer (#132 pattern) |
| 199 | 2026-09-24 | Hardware ceiling reaffirmed: 8B degrades latency AND quality; ceiling is 7B, practically the current Gemma |
| 200 | 2026-09-24 | `prepare_docs` stays CLI, NOT src/: split trigger >300 lines, move trigger an API/UI entry — neither met |
| 201 | 2026-09-24 | Wrong-home reconcile: atoms outside `_atomize/` = stale-move leftovers — same y/N as #111 |
| 202 | 2026-09-25 | `prepare_docs` full review: healthy; one seam — correctors read RAW json vs CONVERTED text, deferred until observed |
| 203 | 2026-09-25 | Output legend: a 10-code preface prints once before argparse — codes match the emitters exactly; zero behavior change |
| 204 | 2026-09-25 | `make_atoms` ConnectError humanized: one-line diagnosis + exit 1 — the 40-line traceback read as a code defect |
| 205 | 2026-09-25 | `ARCHIVIST_PROMPT` first-person rule: preferences in the DIRECT form («Пользователь предпочитает X»); assistant advice keeps attribution |
| 206 | 2026-09-25 | Pickup probe CLOSED as model-bound, FINAL: every data-side layer proven fixed across 5 attempts; reopen ONLY on (a) serving model upgrade, (b) atoms on 14B — no data-side work can move this |
| 207 | 2026-09-25 | Conditional `multi_query`: a non-empty lexical leg SKIPS the LLM variations (~4-7 s saved); counter honest 1+len(variations) |
| 208 | 2026-09-25 | Bounded retry in `make_atoms` (3 attempts, single layer); ConnectError-after-retries keeps the humanized exit |
| 209 | 2026-09-25 | Correctors compare against the CONVERTED source — typographic quotes no longer falsely demoted |
| 210 | 2026-09-25 | Empty-export SKIP split: "recognized but EMPTY — re-export" ≠ "not a recognized export" |
| 211 | 2026-09-25 | Yardstick tests in `check_rag`: premise-1, preference-1 (CONTRACT-tier), preference-2 (the #206 binding inch); future tier 36→40 — leading indicators for a model swap |
| 212 | 2026-09-25 | Condense NO-TOPIC rule: an unnamed-topic follow-up with MULTI-topic history inherits nothing — output as-is; the live case as a template example |
| 213 | 2026-09-25 | Web extraction: trafilatura (live 3-way benchmark); .html is NOT a raw input — pages arrive as clean .md from external tools |
| 214 | 2026-09-26 | `web_grab` wrapper: URL at the runner prompt (or --batch); clipboard mode cut before shipping dead (one case = one path, §11.2); Pop-OS guard, collision-safe slugs, trafilatura via venv CLI |
| 215 | 2026-09-26 | Docs sync wave 1: `ai_rules.md` 2026-09-26 — Standing Facts name the three source channels; CLI-print exemption covers `web_grab` |
| 216 | 2026-09-26 | Docs sync wave 2: architecture §1 three channels; §2.9 Split/Dates/Atoms synced to #188-#191, #194, #196-#210; §13.7-13.8 conditional `multi_query` + day/month frames; version → 2026-09-26 |
| 217 | 2026-09-28 | Chat capture userscripts: recorder (E) captures fetch/XHR/WS/SSE, cache-busts deltas, decodes batchexecute/IndexedDB/hidden apiv2 (Kimi recipe via grep of SaveAI); scout (S) = diagnostics; both in scripts/; SaveAI stays the second independent source |
| 218 | 2026-09-28 | `web_grab` writes to Downloads: the owner reviews the .md; `raw_documents` receives web pages only by an explicit move — the recorder's barrier |
| 219 | 2026-09-28 | Backup scope: explicit owner list + storage db via backup-API; userscripts live in scripts/ (git is their backup); missing items WARN |
| 220 | 2026-09-28 | `run_scripts` empty-Enter crash fixed (IndexError on `shlex.split("")[0]`); Enter redraws the menu |
| 221 | 2026-09-28 | Coverage lessons: one key-line per new site format; sub-second pair ordering needs second-granularity sorting; alert() text is uncopyable — diagnostics download files |
| 222 | 2026-09-29 | `check_rag` chat-no-prefix matcher accepts full-form refusals; the #97 re-run confirmed the flake class first; instrument defect proven per §13.4 |
| 223 | 2026-09-29 | Test-isolation litter: two writers closed (`test_api` hardcoded live path; the stateful machine's default `index_path`, `delete()` auto-persists). Method: `sys.addaudithook` tracer. Rules: single-file bisects miss order-dependent writers — census runs the full suite; the empty `test/` dir was NOT a phantom-namespace manifestation (no store file) — an untraced mkdir leftover |
| 224 | 2026-09-29 | All-namespaces fan-out (CORE CHANGE, owner-authorized): `NAMESPACE_ALL` makes both retrieve steps search every namespace (sorted) and RRF-fuse into ONE untruncated pool (no single-ns `fetch_k` pre-cut); the sentinel resolves IN the steps — API and chat share it, zero feature changes; regular namespaces byte-identical (`test_fanout.py`); the reserved name is documented (never a real `all/` folder); two patch defects caught pre-production; fan-out includes every listed namespace (bench artifacts join `[all]`) |
| 225 | 2026-09-29 | Chat namespace dropdown: `GET /rag/prefixes` from the yaml (sources x prefixes + the `all` sentinel); the UI fetches on every open — zero hardcoded namespaces; latent `nsBadge` ReferenceError fixed; lesson: the conftest `client` builds from `mock_state` — mutate `isolated_app_state` → build your own TestClient |
| 226 | 2026-09-29 | Prefix convention → full names (`[default]`, `[work]`, `[all]`) in example+README (self-documenting, uniqueness free); UI input area restructured: full-width textarea, controls row below, hint line retired |
| 227 | 2026-09-30 | Live indexing indicator: `index_folder` publishes progress+result into a handlers slot (function-scoped imports — the cycle cure); `GET /rag/index-status` serves it; the pipeline is the ONE source — watcher/reindex/modal report identically (design 1 saw one of three doors, rolled back whole). UI: bar + outcome line ABOVE the panel (it never moves), clear-button inside the textarea, uniform 10 s poll (the cheapest endpoint in the project). Lessons: anchors from live files, whole-list import anchors, append-only tests check fixtures, ASCII-only separators, monotonic seconds ≠ client ms (first-seen poll = local start), grep by `id=`. Edges: `POST /rag/index` unreported; hard crash leaves a stale slot; per-process |

## FUTURE RISKS

| Risk | Trigger | When to fix |
|------|---------|-------------|
| Advice-as-decision is model-independent (three live conveyors observed, drift #159) — B2 attribution must be retested on EVERY model/engine change | any model or engine upgrade on the serving pair | rerun the B2 attribution probe set before adopting the new pair |
| Backup folders accumulate unbounded: every run writes a full corpus copy and old backups are never auto-deleted (deliberate — auto-deleting backups is a data-loss risk, drift #158) | backup disk usage grows visibly (threshold is the owner's call) | manual cleanup of old `backup_*` folders; a rotation policy only if the manual chore actually repeats |
| Parametrized contract fixtures: five dead ones removed (zero consumers, grep-verified; the `:memory:` defect sat undetected because the fixture was dead); `vector_store_adapter` is the live template | a second implementation of a port shows a live divergence class (#120/#146 pattern) | copy the template + write the parity test born from that drift, never before |
| Date-phrase declension: the month table holds nominative/genitive/prepositional after the 2026-09-23 compression | a live date query in an unparsed case (false refusal) | extend the yaml table (owner data, no code) |
| Split date-grounding criteria: producer (`_ground_dates`) accepts verbatim-or-covered, V2 checks covered-only — a date present verbatim in the source but yielding no parsed covering token gives a false V2 error | First observed false V2 flag | Unify into one `_is_grounded` shared by producer and validator |
| `make_atoms` is all-or-nothing: no retry, no per-part checkpoint — a transient HTTP failure mid-run discards the accumulated answers (zero errors measured, #65) | First network failure or lost long run | Bounded retry (3 attempts, single layer); per-part checkpoint only if losses repeat. — CLOSED by #208 (bounded retry shipped) |
| Atom self-sufficiency is a prompt declaration, not a checked property: atoms with unresolved references ("he/it", "see above") or degenerate length pass V1-V6 | Unresolved-reference atoms observed in the live corpus | Add V7 as warn-only heuristics after the owner confirms real cases |
| `_split_for_atoms` cuts hard seams: a fact spanning two parts is extracted per-part (no proven loss to date; overlap would feed the duplication the #90 dedup guards) | A documented fact lost or misattributed specifically at a part seam | Overlap, dedup-aware; no change without a proven seam defect |
| The archivist prompt FINAL instruction still promises cross-part merge / Chronology completeness that independent per-part requests cannot deliver (#90 closed only the mechanical dedup half) | Next planned archivist prompt revision | Drop the unfulfillable sentence or feed prior-parts digests into FINAL (token-budget aware) |
| Atoms output is free-form markdown: a recurring malformed-format class would require regex surgery over the corpus | Malformed atoms become a documented recurring failure class | JSON-mode output — rewrites prompt, validators and corpus; only for a proven syntactic (not semantic) defect class |
| Config migration bloat | >10 migrations in `config.py` | When loading old configs becomes slow |
| Test fatigue | Skipping tests due to mock boilerplate | When test coverage drops below 80% |
| Vector store RAM limit | Hitting 100K chunks | When `max_chunks` reached |
| Async lock complexity | Deadlocks in production | When deadlock rate > 1/month |
| Sibling-source deletion | Watcher reindexes one of 2+ sources sharing a namespace; orphan cleanup sees only that source's URIs and deletes the siblings' chunks | Before mapping a second source to a namespace |
| Phantom empty namespaces | `list_by_filter` on a never-populated namespace creates it in memory; the memory adapter later lists it and persists an empty store file | When namespace lifecycle code is touched |
| Silent fallback prompt | Invalid `prompt_name` (API request or config) renders `prompts/v1/fallback.j2` with degraded RAG instructions; only a log entry, no error to the caller | When prompt versioning/registry work begins |
| RAM headroom shrink | Peak RAM (6.5/15 GB at ~140 bench docs) grows past ~10 GB with real corpus | Before adding any RAM-heavy component; measure first |
| condensation-1 fragility: flips with GPU offload layout (full green 3/3, partial red 5/5, #133) and with `rag_strict` answer-style shifts (first-person examples broke it, #145) — the log line is INFO now (#143) | a surprising condensation red, or any `rag_strict` edit / serving layout change | verify layout first, read `rag.condense` in app.log, re-run the full chat tier after any prompt edit; #207 follow-up: skipped variations no longer MASK a poisoned condensed query — the #164 topic-carry (RAG-answer history pollutes condensation) is now visible in logs as a lexical hit on the wrong topic; the condense-context isolation (user-only history for condensation) is the scheduled fix|
| `atoms-undated-1` date honesty is model-dependent: red on the 4B/7B pair (evasion/confabulation, drift #85), GREEN on the Gemma-4-E4B baseline since 2026-09-22 (re-baseline #170) | any model or engine change on the serving pair | rerun `check_rag`; if `atoms-undated-1` goes red again, re-attempt a generation-side date-phrase guard (prompt-level cure leaks into anti-echo rules, drift #85) |
| Advanced FAISS indices (IVF/PQ) — flat search cost grows linearly past ~100K chunks per namespace | single namespace exceeds 100K chunks (trigger already in `ai_rules` §2) | train IVF index, re-verify atomic upsert (#88) on it, `config_version` bump for the index format (stage 4 — CORE CHANGE, discuss first) |
| Date filters before retrieval — CLOSED 2026-09-18 (built as #149+#151, live-verified: "что я решал в июле" answered from the July doc only). Residual half: source/folder filters remain ranking-only | 3 documented live cases of source-filter misses | source filter in QueryRequest -> port extension (CORE CHANGE, discuss first) |
| `_atomize` demotion leaves stale atoms (merged with the closed #150 probe row): moving a source out of `_atomize/` keeps its atoms file — no deletion cascade on demotion; live-triggered 2026-09-14 (#125); the 2026-09-16 probe file itself was wiped with the owner's documents/ reset | next demotion of an `_atomize` document | extend reconcile to demotions — owner decision |
| 7B atomizer echoes archivist-prompt template fragments as atoms: deterministic (temp 0.0), same 34/141 Latin-letter atoms on re-extraction; V5 flags them (Latin-in-RU). Triggered live 2026-09-14 (THE DECISION TEST served as an answer from the atoms); corpus raw-only since (#92/#125) — echo sleeping | atoms re-enabled on a 14B-class model, or re-observed on any corpus | producer-side template-fragment filter (birth-time corrector, #90 family) or manual atom deletion |
| Same-stem collisions (#2, review 2026-09-13): two files with the same stem in one namespace (chat.md + chat.txt) share `metadata.source = stem` — the per-file indexing loop makes the last writer erase the first file's chunks (batch /rag/index keeps both; chat path protected by the synthetic `__chat__` id). Fix = key change on disk + full reindex — disk format is sacred, no migration warranted while the live tree has no such pair | first observed real collision in the live tree (one file's chunks vanish after another indexes) | owner decision: new key format (e.g. `source_uri`) + backward-compat loader + reindex, or reject duplicate stems at collect time (cheap warning, no migration) |
| e2e archivist gate is red on the serving model by design — a full-green suite requires the atomizer swapped onto 8080 for the run | release checkpoint / full green suite needed | swap procedure per #132 during `check_all` |
| Priority-pair tension (#145): retrieval-2 and priority-1 ask the SAME question in the same namespace; one requires 'guido' in the answer, the other forbids 'snake' — with both docs in context no single answer passes both (the 145-prompt answers guido+snake: retrieval-2 green, priority-1 red) | any attempt to "fix" priority-1 or retrieval-2 | accept the documented tradeoff; a real fix needs answer-side entity disambiguation the 4B class lacks — re-evaluate on a model change |
| Second-resolution mtime (#9, review 2026-09-13): `last_modified` is a "%Y-%m-%d %H:%M:%S" string — two saves within one second compare equal; the watcher sees the change (float mtime) but the pre-read skip and unchanged-filter both match on the truncated string, so the update is deliberately skipped. The watcher then consumes the snapshot — the change never indexes until the next touch | first documented case of a sub-second save missed (stale answer traced to it) | store float mtime in metadata (stored-format change — needs a migration decision), or compare disk float mtime against stored string with a sub-second tolerance |
| Emptied source folder (#10, review 2026-09-13): "0 docs, chunks exist" guard keeps the chunks forever — by design (data-loss protection, #112 tightened it). Since #113 every watcher pass ERROR-logs "No documents found", so the state is loud; cleanup is manual (`/rag/delete` with clear). Half-open: folders whose files are all unreadable also hold chunks silently (WARNING per file) | sustained noise from the ERROR log on an intentionally emptied folder, or a stale answer served long-term | owner decision: a reconcile mode with explicit y/N (like #111 `prepare_docs`), or a documented acceptance with a periodic reminder in the log |
| Double checkpoint write per document (#16, review 2026-09-13): `upsert` persists inside (#88 atomicity) and the per-document checkpoint saves again (#64 crash window) — two full namespace writes per document. At ~3.5K chunks both writes are milliseconds; at 80K chunks ≈ 120 MB x 2 per document. The checkpoint is also the safety net for the port-default upsert contract, so removing it is not a one-liner | namespace approaches `max_chunks` / indexing pass duration grows visibly (measure first) | measure save duration per checkpoint; if dominant, checkpoint every N documents instead of each (crash window grows to N docs — needs an explicit tradeoff decision) |
| Inventory "unseen vs absent": orphan cleanup deletes chunks for any uri missing from the disk inventory; #112 closed the read/stat-failure path, but files dropped before the inventory is built (`Path.is_file()` swallows stat errors, an unreadable subdirectory truncates `rglob`, oversize skip) still count as deleted | Orphan chunks removed for a file that provably exists on disk | Positive-absence design: cleanup deletes only uris whose parent directory was successfully listed; oversize policy is a separate owner decision |
| Unreadable file at index time: chunks preserved (#112) and the failure is loud (#113), but the new content is not retried until the next file change or a manual reindex — retrying only transient failures needs a typed error taxonomy to tell them from deterministic refusals | A changed file serves stale content past the next watcher pass (watch the log for "Watcher reindex failed" + unreadable-file warnings) | Typed error taxonomy in the result channel, then a bounded retry for transient-only failures (one layer — drift #43) |
| Watcher keys snapshots by `str(path)`: two SourceConfigs sharing one path overwrite each other's snapshots every poll — change detection for one of them becomes unreliable | before mapping a second source to the same path | key by (namespace, path) |
| Chunker-shared `custom` dict aliases across frozen chunks — latent until a chunker returns chunks sharing one dict | a chunker that shares one custom dict between chunks | copy on chunk rebuild in IndexingManager |
| Chat UI attach inserts file content as plain text into the message (client-side, max 10 files / 5 MB / 50K chars): works for small documents, but a large document fills the model's context window (8192 tokens) and may fail mid-message | a user attaches a document that exceeds the context window and gets a truncated or failed response | a server-side document indexing endpoint (upload → chunk → index → confirm), or an explicit size guard in the UI with a "use RAG indexing for large documents" hint — the attach button itself is functional |
| Premise-compliance is model behavior: GREEN on QAT since 2026-09-23, red on bartowski (#180) | any model/engine change on the serving pair | add to the B2 retest set (with `atoms-undated-1`) |

## OWNER IDEAS (parked — known, not forgotten; NOT commitments)

| Idea | Essence | Take it when |
|------|---------|--------------|
| Decision timeline | a `prepare_docs` mode builds `timeline.md` from decision atoms + their dates — a personal chronicle "what I decided, when, and on what grounds". No core changes, one script over existing data | the corpus has accumulated a season of atoms; the itch to look back appears |
| Owner-voice namespace | first-person atoms (preferences, choices — the #205 rule already writes them) index into a separate namespace: "what do I think about X" searches only the owner's own words, never assistant advice | timeline proved itself and the atoms are clean |
| Deferred questions | honest refusals queue up; when a new document lands, it offers to close old gaps ("you asked X in July, no evidence then — this new chat may answer it") | #1 and #2 lived a while; the LLM-matching cost is consciously accepted |

Order chosen: 1 → 2 → 3 (each builds on the previous). All live
outside src/ (scripts/features), all explainable to a non-programmer
in one sentence. Nothing here obliges: the table exists so a future
session remembers the options exist.
