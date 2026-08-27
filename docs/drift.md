# Known Architectural Drift

> Rule: Do not add new drift if old pattern can be fixed properly.
> AI reads this file before any architectural output (Document Meta §12).
> ACTIVE entries are constraints — do not "fix" them without explicit user request.
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

## FIXED → History (one-liners, self-contained)

| ID | Fixed | Summary |
|----|-------|---------|
| 1 | 2026-06-09 | Added `get_context_limit()` to `ILLM` port; all adapters updated |
| 2 | 2026-06-09 | `NullReranker` introduced; `reranker: IReranker` non-optional (Null Object) |
| 3-4 | 2026-06-13 | Replaced `getattr(config, "x", default)` with direct `config.x`; Pydantic guarantees presence |
| 5 | 2026-06-14 | `ChunkMetadata` schema drift on disk; strict `_chunk_to_dict`/`_chunk_from_dict` matching domain model |
| 6 | 2026-06-14 | Added `get_logger` to adapters; all `AdapterError` wraps preceded by `logger.exception()` |
| 9 | 2026-06-17 | Removed hardcoded `model="gpt-4o"`; `_estimate_tokens()` accepts `ITokenizer` |
| 10 | 2026-06-27 | `RetryConfig` dataclass + `retry_with_config()` in `core/retry.py` |
| 12 | 2026-07-08 | `_make_hashable()` cyclic ref guard; returns `"<circular>"` |
| 13 | 2026-06-14 | Added `source_uri: str | None` to `ChunkMetadata` (CORE CHANGE) |
| 15 | 2026-06-18 | `query_embedding` removed from `retrieve` required fields (produced, not input) |
| 16 | 2026-06-14 | `admin_enabled: bool = False`; admin endpoints 404 unless enabled |
| 17 | 2026-06-14 | `delete()` auto-persists with rollback on failure |
| 20 | 2026-06-25 | `ITokenizer` port added; tiktoken/tokenizers adapters moved out of `core/` |
| 21 | 2026-06-25 | `asyncio.Lock` on all `MemoryVectorStore` public async methods |
| 24 | 2026-06-30 | `load()` failures wrapped in `AdapterError`; `isinstance(meta, dict)` guard |
| 25 | 2026-07-02 | `SourceConfig` + `sources: list[SourceConfig]`; backward-compat loader for `documents_root` |
| 26 | 2026-07-02 | `prefix: str | None` in `NamespaceConfig`; `build_prefix_map()` from config |
| 27 | 2026-07-02 | Unified config to `config.yaml` (git-ignored) + `config.example.yaml` |
| 32 | 2026-07-06 | PRAGMA `user_version` migration; `AdapterError` wrapping; WAL check |
| 33 | 2026-07-06 | Copy target mode to tmp before `os.replace` (permission preservation) |
| 40 | 2026-08-27 | Delete-all left stale index files → deleted chunks resurrected on restart; empty namespace now removes its files (both vector store adapters) |
| 41 | 2026-08-27 | Memory store `save()` overwrote skipped namespaces with an empty store on shutdown; never-loaded namespaces no longer touch disk |
| 42 | 2026-08-27 | Watcher consumed the snapshot on failure → partial index frozen as complete; bounded retry (3 attempts), snapshot consumed on success only |
| 43 | 2026-08-27 | Indexing embed call had no retry (ai_rules §7); wrapped in `retry_with_config`, same default policy as the query pipeline |
| 44 | 2026-08-27 | Mid-stream failure persisted a truncated assistant turn into history (save in `finally`); save now runs only after the stream completes |
| 45 | 2026-08-27 | SSE data frames carried multi-line chunks under a single `data:` prefix; strict EventSource clients dropped everything after the first newline (incl. the whole Sources block); every line now carries its own prefix |
| 46 | 2026-08-27 | Encoding fallback tried `utf-8` before `utf-8-sig`, so BOM-prefixed files decoded "successfully" with U+FEFF leaking into chunk text and embeddings; `utf-8-sig` is now first, plain `utf-8` removed as dead |
| 47 | 2026-08-27 | `/rag/reindex` without configured sources crashed the background task with `UnboundLocalError` (masked as 500); explicit 400 "No sources configured" is now returned before spawning the task |
| 48 | 2026-08-27 | `MemoryVectorStore` silently FIFO-evicted oldest chunks on max_chunks overflow (eviction was banned by ai_rules §2 until RAM pressure was measured — it never was), and a later `save()` persisted the loss to disk; eviction machinery removed, `add()` now rejects like the faiss adapter, contract documented in the port |
| 49 | 2026-08-27 | The Sources block was persisted into chat history, spending the context token budget, polluting the condense input, and (with `index_chat_exports`) feeding generated output back as indexed evidence; history now stores the clean answer, API responses keep the block |

## FUTURE RISKS (not fixing now)
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
