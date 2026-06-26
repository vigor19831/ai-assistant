==============================================================================
ПРОМПТ ДЛЯ ЗАПРОСА БАГОВ:
==============================================================================
Ты — архитектор на 30 лет. Найди проблемы, которые сломают проект через 5+ лет, каждый пункт независимый — одна строка, понятен без контекста.

==============================================================================
## TODO ##
=============================================================================



## Баги (6 штук)

```
[+] Fix get_chunker_for_config ignoring chunk_size | Namespace chunk_size overrides silently fail, all namespaces use base chunk_size | api/deps.py | Test: create chunker with chunk_size=1024, assert config.chunk_size == 1024
```

```
[+] Fix rag.relevance_threshold default mismatch | Default 0.3 in code vs 0.1 in config.yaml causes unexpected strict filtering when YAML absent | core/config.py | Test: AppConfig() default relevance_threshold == 0.1; test_config.py passes
```

```
[+] Fix metrics path explosion (cardinality leak) | Each unique URL path (UUIDs, task_ids) creates infinite time series, eventual OOM | api/middleware.py | Test: request with path /reindex/status/abc-123 produces label path="/reindex/status/{task_id}" or route pattern
```

```
[+] Fix generate crash on None context limit | int(None * 0.1) raises TypeError, pipeline crashes completely | core/pipeline_steps.py | Test: mock llm.get_context_limit() returns None, pipeline returns error message without exception
```

```
[+] Add retry wrapper for rerank step | Network failure in reranker causes full RAG failure without recovery | core/pipeline_steps.py | Test: mock reranker raises on first call, succeeds on second; pipeline completes
```

```
[+] Add trace_id to RAG handlers | Impossible to correlate chat and RAG logs for same request | features/rag/handlers.py | Test: all RAG handler log calls include extra={"trace_id": ...}
```

---

## Архитектурные риски (7 штук)

[ ] Add config migration tests | Untested migrations will break backward compatibility on config_version bump | tests/test_config.py | Test: parametrize old configs → AppConfig loads without error; fields migrated correctly

[ ] Lower requires-python to >=3.10 | >=3.13 blocks LTS deployment (Debian 12, RHEL 9); no 3.13-specific features used | pyproject.toml | Test: CI passes on 3.10, 3.11, 3.12, 3.13; syntax check (str | None works since 3.10)

[ ] Add RetryConfig dataclass + env loading | Hardcoded retry policy prevents operational tuning per adapter (embedder fast/LLM slow) | core/domain/configs.py, core/retry.py | Test: RetryConfig(delay=0.1) overrides decorator default; existing tests pass unchanged

[ ] Prepare PipelineData extension point for tool/vision context | Adding 5+ flat fields will create god object; composition prevents future core schema break | core/domain/pipeline.py | Test: PipelineData can carry ToolContext without adding fields; existing .with_*() methods work





[ ] Unpin numpy <2.0.0 | numpy 2.0+ released, missing security patches and performance improvements | pyproject.toml | Test: pytest suite passes with numpy>=2.0.0; FAISS index operations correct

[ ] Extract HTTP client base to adapters/_http_base.py | 3rd HTTP adapter (MCP/A2A) will duplicate httpx setup, error-prone | adapters/_http_base.py (new), adapters/embedder_openai_compatible.py, adapters/llm_openai_compatible.py | Test: OpenAICompatibleEmbedder still works; no behavior change; _http_base covered by unit test

[ ] Move adapter imports from factory.py to __init__.py | Adding new adapter requires editing factory.py despite @register decorator; violates "explicit but scalable" | adapters/__init__.py, adapters/factory.py | Test: create_adapter works for all existing adapters; new adapter can be added by import only
