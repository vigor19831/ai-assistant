# Known Architectural Drift

> Rule: Do not add new drift if old pattern can be fixed properly.
> AI reads this file before any architectural output (Document Meta §12).
> ACTIVE entries are constraints — do not "fix" them without explicit user request.
> Git history is unreliable (commits often say "fix"). This file is the source of truth.

## ACTIVE (7)

| ID | Since | Location | Constraint | Exit Criteria |
|----|-------|----------|------------|---------------|
| 11 | 2026-06-09 | `core/prompts/__init__.py` | Jinja2 import in stdlib-only `core/` layer | Second template engine needed OR Jinja2 deprecated |
| 18 | 2026-06-14 | `api/security.py` | `_override_api_key` process-local; does not propagate across uvicorn/gunicorn workers | Multiprocess deployment becomes primary use case |
| 19 | 2026-06-14 | `core/config.py` | Pydantic + PyYAML import in stdlib-only `core/` layer. `config_version` + backward-compat loader in place | Pydantic 2y without release OR critical CVE unpatched >6mo |
| 28 | 2026-07-04 | `api/router.py`, `api/admin.py` | `require_api_key` duplicated on admin router (harmless redundancy) | Remove from `admin.py` OR special-case admin in wrapper |
| 29 | 2026-07-05 | `core/ports/tokenizer.py` | `ITokenizer` simplified; no multi-encoding support | Multi-encoding support needed |
| 34 | 2026-07-08 | `tests/test_stateful_ports.py` | `asyncio.run()` in `ThreadPoolExecutor` for Hypothesis (issue #4107 — no native async) | Hypothesis adds async state machine OR tests removed |
| 38 | 2026-08-12 | `tests/conftest.py` | `AsyncMock` cannot mock async generators → `MagicMock(side_effect=factory)` bypasses `spec=ILLM` | stdlib native async generator mock support OR `ILLM.stream` contract change |

## FIXED → Rule Extracted (see docs, no details needed)

| ID | Fixed | Rule / Location |
|----|-------|-----------------|
| 23 | 2026-06-29 | HTTP client ownership → `architecture.md` §4, §5 |
| 22 | 2026-06-28 | Port objects own config, PipelineData carries references → `architecture.md` §8, `ai_rules.md` §2.2 |
| 7 | 2026-06-28 | Shared CODE ok, shared RESOURCE banned → `architecture.md` §4.3, §8 |
| 14 | 2026-06-26 | Untyped `dict[str, dict]` bags banned → `ai_rules.md` §9 antipatterns |
| 8 | 2026-06-18 | `PipelineData.metadata: dict[str, Any]` replaced with typed fields → `ai_rules.md` §9 antipatterns |
| 31 | 2026-07-10 | Unconditional `shutdown()`, no `_closed` flag → `architecture.md` §6 |
| 30 | 2026-07-10 | `SystemMessage` in domain, removed from `ILLM` port → `architecture.md` §8 |
| 37 | 2026-07-28 | `min_relevance_score` stripped; strict rank-only → `architecture.md` §13 |
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
