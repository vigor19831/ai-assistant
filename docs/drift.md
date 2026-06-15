# Known Architectural Drift

| ID | File | Broken Rule | Why | Fix | Priority |
|----|------|-------------|-----|-----|----------|
| 1 | Fixed 2026-06-09: get_context_limit() added to ILLM port. All adapters updated. |
| 2 | Fixed 2026-06-09: NullReranker introduced. `rerank()` no longer branches on `None`. `InitializedAppState.reranker` is `IReranker` (non-optional). |
| 3 | Fixed 2026-06-09: getattr(config, "vector_store") removed. Pydantic validation guarantees field presence. |
| 4 | Fixed 2026-06-13: Replaced all `getattr(config, "x", default)` with direct `config.x` access in all adapters. All defaults verified in `AppConfig` Pydantic models. |
| 5 | Fixed 2026-06-14: `ChunkMetadata` schema drift. `vector_store_faiss.py` and `vector_store_memory.py` serialized `created_at` (not in domain model) and missed `total_chunks` in FAISS `add()`. Introduced `dataclass_from_dict` in `core/utils.py` for strict deserialization. |
| 6 | Fixed 2026-06-14: Added `get_logger` to `embedder_openai_compatible.py` and `reranker_api.py`. All `AdapterError` wraps now preceded by `logger.exception`. |
| 7 | `adapters/embedder_openai_compatible.py`, `adapters/llm_openai_compatible.py` | Duplicate HTTP client setup (httpx.AsyncClient, POST, raise_for_status, json parse) | Layer boundaries prevent shared httpx code: core/ is stdlib-only, adapters/ may only import core/*. Extracting to core/ violates stdlib-only rule. Extracting to adapters/_shared violates layer boundaries. | Accept duplication as architectural constraint. Revisit if >3 adapters share pattern. | Low |

Rule: Do not add new drift if old pattern can be fixed properly.
