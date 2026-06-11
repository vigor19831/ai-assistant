# Known Architectural Drift

| ID | File | Broken Rule | Why | Fix | Priority |
|----|------|-------------|-----|-----|----------|
| 1 | Fixed 2026-06-09: get_context_limit() added to ILLM port. All adapters updated.
| 2 | Fixed 2026-06-09: NullReranker introduced. `rerank()` no longer branches on `None`. `InitializedAppState.reranker` is `IReranker` (non-optional). |
| 3 | Fixed 2026-06-09: getattr(config, "vector_store") removed. Pydantic validation guarantees field presence. |
| 4 | `adapters/embedder_openai_compatible.py`, `adapters/llm_openai_compatible.py`, `adapters/reranker_api.py`, `adapters/storage_sqlite.py`, `adapters/vector_store_faiss.py`, `adapters/vector_store_memory.py` | Pydantic guarantees field presence via `default=` in BaseSettings/BaseModel. `getattr(config, "field", default)` masks typing issues and creates drift between port contract and adapter implementation. | Historical: added defensively before Pydantic validation was strict. | Replace all `getattr(config, "x", default)` with direct `config.x` access. Update `AppConfig` defaults if any field is optional. | Low |

Rule: Do not add new drift if old pattern can be fixed properly.
