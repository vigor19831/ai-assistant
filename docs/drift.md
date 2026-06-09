# Known Architectural Drift

| ID | File | Broken Rule | Why | Fix | Priority |
|----|------|-------------|-----|-----|----------|
| 1 | Fixed 2026-06-09: get_context_limit() added to ILLM port. All adapters updated.
| 2 | Fixed 2026-06-09: NullReranker introduced. `rerank()` no longer branches on `None`. `InitializedAppState.reranker` is `IReranker` (non-optional). |
| 3 | Fixed 2026-06-09: getattr(config, "vector_store") removed. Pydantic validation guarantees field presence. |

Rule: Do not add new drift if old pattern can be fixed properly.
