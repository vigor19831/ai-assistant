## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-05-26 11:21 UTC
> **Rule:** Check this table before adding try/except or changing error handling.

| Component | Exception | Trigger | Severity |
|-----------|-----------|---------|----------|
| `api.admin` | `HTTPException` | Unknown error | High |
| `api.deps` | `RuntimeError` | State not initialized. Call init_adapters() first. | High |
| `api.security` | `HTTPException` | Unknown error | High |
| `core.config` | `ValueError` | f-string message | High |
| `core.domain.messages` | `ValueError` | UserMessage must contain at least one payload | High |
| `core.io_utils` | `ValueError` | f-string message | High |
| `core.logger` | `ValueError` | f-string message | High |
| `core.metrics` | `RuntimeError` | MetricsLogger.start() must be called within a running event ... | High |
| `core.prompts.__init__` | `ValueError` | f-string message | High |
| `core.registry` | `ValueError` | f-string message | High |
| `core.utils` | `ValueError` | f-string message | High |
| `features.chat.handlers` | `HTTPException` | Unknown error | High |
| `features.chat.manager` | `AdapterError` | Voice recognizer not configured | High |
| `features.chat.manager` | `AdapterError` | f-string message | High |
| `features.image_analysis.handlers` | `HTTPException` | Unknown error | High |
| `features.rag.handlers` | `HTTPException` | Unknown error | High |
| `pipeline.decorators` | `ValueError` | f-string message | High |
| `api.deps` | `Exception` | Handled in init_adapters | Medium |
| `api.deps` | `ValueError` | Handled in init_adapters | Medium |
| `api.lifespan` | `Exception` | Handled in _async_cleanup | Medium |
| `api.lifespan` | `OSError` | Handled in lifespan | Medium |
| `api.lifespan` | `OSError` | Handled in _cleanup | Medium |
| `api.router` | `Exception` | Handled in assemble_routers | Medium |
| `api.security` | `ValueError/IndexError` | Handled in SecurityLimiter._parse_rate_limit | Medium |
| `core.config` | `Exception` | Handled in load_config | Medium |
| `core.io_utils` | `Exception` | Handled in _sync | Medium |
| `core.io_utils` | `OSError` | Handled in _sync | Medium |
| `core.io_utils` | `TypeError` | f-string message | Medium |
| `core.logger` | `OSError` | Handled in setup_logging | Medium |
| `core.metrics` | `Exception` | Handled in MetricsLogger._worker | Medium |
| `core.metrics` | `Exception` | Handled in MetricsLogger.log | Medium |
| `core.metrics` | `Exception` | Handled in MetricsLogger.stop | Medium |
| `core.metrics` | `RuntimeError` | Handled in MetricsLogger.start | Medium |
| `core.metrics` | `SystemExit/KeyboardInterrupt` | Handled in MetricsLogger._worker | Medium |
| `core.metrics` | `TimeoutError` | Handled in MetricsLogger.stop | Medium |
| `core.metrics` | `TypeError` | Handled in module | Medium |
| `core.retry` | `Exception` | Handled in async_wrapper | Medium |
| `core.retry` | `Exception` | Handled in sync_wrapper | Medium |
| `core.retry` | `SystemExit/KeyboardInterrupt` | Handled in async_wrapper | Medium |
| `core.retry` | `SystemExit/KeyboardInterrupt` | Handled in sync_wrapper | Medium |
| `core.retry` | `_PERMANENT_ERRORS` | Handled in async_wrapper | Medium |
| `core.retry` | `_PERMANENT_ERRORS` | Handled in sync_wrapper | Medium |
| `core.retry` | `last_exception` | Unknown error | Medium |
| `core.tool_registry` | `Exception` | Handled in ToolRegistry.dispatch | Medium |
| `core.tool_registry` | `SystemExit/KeyboardInterrupt` | Handled in ToolRegistry.dispatch | Medium |
| `core.utils` | `Exception` | Handled in get_tokenizer | Medium |
| `core.utils` | `Exception` | Handled in count_tokens | Medium |
| `core.utils` | `ImportError` | Handled in module | Medium |
| `core.utils` | `KeyError` | Handled in get_tokenizer | Medium |
| `core.utils` | `OSError` | Handled in _resolve_tokenizer_dir | Medium |
| `features.chat.handlers` | `Exception` | Handled in chat | Medium |
| `features.chat.handlers` | `Exception` | Handled in event_generator | Medium |
| `features.chat.handlers` | `Exception` | Handled in openai_chat_completions | Medium |
| `features.chat.handlers` | `HTTPException` | Handled in chat | Medium |
| `features.chat.handlers` | `HTTPException` | Handled in openai_chat_completions | Medium |
| `features.chat.manager` | `Exception` | Handled in ChatManager.chat | Medium |
| `features.chat.manager` | `Exception` | Handled in ChatManager.stream_chat | Medium |
| `features.chat.manager` | `ValueError` | Handled in ChatManager.chat | Medium |
| `features.chat.manager` | `ValueError` | Handled in ChatManager.stream_chat | Medium |
| `features.chat.manager` | `ValueError/IndexError` | Handled in ChatManager._append_rag_sources | Medium |
| `features.image_analysis.handlers` | `Exception` | Handled in analyze_image | Medium |
| `features.image_analysis.handlers` | `HTTPException` | Handled in analyze_image | Medium |
| `features.image_analysis.manager` | `Exception` | Handled in ImageAnalysisManager.analyze | Medium |
| `features.image_analysis.manager` | `SystemExit/KeyboardInterrupt` | Handled in ImageAnalysisManager.analyze | Medium |
| `features.rag.handlers` | `Exception` | Handled in index_documents | Medium |
| `features.rag.handlers` | `Exception` | Handled in delete_chunks | Medium |
| `features.rag.handlers` | `Exception` | Handled in list_namespaces | Medium |
| `features.rag.handlers` | `Exception` | Handled in save_chat | Medium |
| `features.rag.handlers` | `Exception` | Handled in reindex_documents | Medium |
| `features.rag.handlers` | `FileNotFoundError` | Handled in reindex_documents | Medium |
| `features.rag.handlers` | `TimeoutError` | Handled in reindex_documents | Medium |
| `features.rag.handlers` | `ValueError/IndexError` | Handled in reindex_documents | Medium |
| `features.rag.manager` | `Exception` | Handled in IndexingManager.index_documents | Medium |
| `features.rag.manager` | `Exception` | Handled in RAGManager.health | Medium |
| `features.rag.manager` | `ValueError/IndexError` | Handled in RAGManager.query | Medium |
| `pipeline.steps` | `Exception` | Handled in embed_query | Medium |
| `pipeline.steps` | `Exception` | Handled in retrieve | Medium |
| `pipeline.steps` | `Exception` | Handled in rerank | Medium |
| `pipeline.steps` | `Exception` | Handled in generate | Medium |
| `features.rag.handlers` | `FileNotFoundError` | f-string message | Low |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.
