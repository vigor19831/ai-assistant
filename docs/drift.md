# Known Architectural Drift

| ID | File | Broken Rule | Why | Fix | Priority |
|----|------|-------------|-----|-----|----------|
| 1 | core/pipeline_steps.py:~312 | getattr(llm, "config") -- ILLM has no config field | Need context window size | Add get_context_limit() to ILLM, implement in all adapters | Medium |
| 2 | core/pipeline_steps.py:rerank() | if reranker is None inside step | Reranker is optional by config | Make rerank optional in rag.steps, or NullReranker | Low |
| 3 | api/lifespan.py | getattr(config, "vector_store") | Defensive against bad config | Direct access, fail at validation | Low |

Rule: Do not add new drift if old pattern can be fixed properly.
