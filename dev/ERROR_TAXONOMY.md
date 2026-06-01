## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-01 08:07 UTC
> **Rule:** Check this table before adding try/except or changing error handling.

| Component | Exception | Trigger | Severity |
|-----------|-----------|---------|----------|
| `adapters.voice_piper` | `SystemExit/KeyboardInterrupt` | Handled in PiperRealSynthesizer._check_available | Critical |
| `adapters.voice_whispercpp` | `SystemExit/KeyboardInterrupt` | Handled in WhisperCppRecognizer._check_available | Critical |
| `core.metrics` | `SystemExit/KeyboardInterrupt` | Handled in MetricsLogger._worker | Critical |
| `core.retry` | `SystemExit/KeyboardInterrupt` | Handled in async_wrapper | Critical |
| `core.tool_registry` | `SystemExit/KeyboardInterrupt` | Handled in ToolRegistry.dispatch | Critical |
| `features.image_analysis.manager` | `SystemExit/KeyboardInterrupt` | Handled in ImageAnalysisManager.analyze | Critical |
| `adapters.chunker_simple` | `ValueError` | chunk_size must be > 0, got {...} | High |
| `adapters.embedder_openai_compatible` | `AdapterError` | Unexpected response shape from {...}: {...} | High |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High |
| `api.admin` | `HTTPException` | Unknown error | High |
| `api.deps` | `RuntimeError` | State not initialized. Call init_adapters() first. | High |
| `api.security` | `HTTPException` | Unknown error | High |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High |
| `core.domain.messages` | `ValueError` | UserMessage must contain at least one payload | High |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High |
| `core.registry` | `ValueError` | No adapter registered for {...}/{...} | High |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High |
| `dev.tests.test_api_deps` | `ValueError` | No such reranker | High |
| `dev.tests.test_api_e2e` | `RuntimeError` | No app state available | High |
| `dev.tests.test_malformed_sse` | `ValueError` | Error with "quotes" and 
 newlines | High |
| `dev.tests.test_rag_pipeline` | `RuntimeError` | down | High |
| `dev.tests.test_rag_pipeline` | `ValueError` | bad config | High |
| `dev.tests.test_resilience` | `RuntimeError` | shutdown boom | High |
| `features.chat.manager` | `AdapterError` | Voice recognizer not configured | High |
| `features.image_analysis.handlers` | `HTTPException` | Unknown error | High |
| `features.rag.handlers` | `HTTPException` | Unknown error | High |
| `pipeline.decorators` | `ValueError` | Unknown step: {...} | High |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | Handled in OpenAICompatibleEmbedder.embed | Medium |
| `adapters.llm_mock` | `AttributeError` | Handled in MockLLM.complete | Medium |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | Handled in OpenAICompatibleLLM._complete_impl | Medium |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | Handled in OpenAICompatibleLLM._stream_impl | Medium |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | Handled in OpenAICompatibleLLM._stream_impl | Medium |
| `adapters.llm_openai_compatible` | `expected_exception` | Handled in OpenAICompatibleLLM.stream | Medium |
| `adapters.memory_sqlite` | `JSONDecodeError` | Handled in _safe_json_loads | Medium |
| `adapters.memory_sqlite` | `OperationalError` | Handled in SQLiteMemory.init_db | Medium |
| `adapters.reranker_api` | `KeyError/TypeError` | Handled in APIReranker.rerank | Medium |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | Handled in APIReranker.rerank | Medium |
| `adapters.storage_sqlite` | `JSONDecodeError` | Handled in _safe_json_loads | Medium |
| `adapters.tools_calculator` | `KeyError/TypeError/ValueError` | Handled in CalculatorTool.execute | Medium |
| `adapters.tools_calculator` | `TypeError/KeyError` | Handled in CalculatorTool.execute | Medium |
| `adapters.tools_calculator` | `TypeError/ValueError` | Handled in CalculatorTool.execute | Medium |
| `adapters.vector_store_faiss` | `ImportError` | Handled in module | Medium |
| `adapters.vector_store_memory` | `TypeError/ValueError` | Handled in MemoryVectorStore.search | Medium |
| `adapters.voice_piper` | `Exception` | Handled in PiperRealSynthesizer._check_available | Medium |
| `adapters.voice_piper` | `TimeoutError` | Handled in PiperRealSynthesizer.synthesize | Medium |
| `adapters.voice_whispercpp` | `Exception` | Handled in WhisperCppRecognizer._check_available | Medium |
| `api.deps` | `Exception` | Handled in init_adapters | Medium |
| `api.deps` | `ValueError` | Handled in init_adapters | Medium |
| `api.lifespan` | `Exception` | Handled in _async_cleanup | Medium |
| `api.lifespan` | `OSError` | Handled in lifespan | Medium |
| `api.lifespan` | `TimeoutError` | Handled in _async_cleanup | Medium |
| `api.router` | `Exception` | Handled in assemble_routers | Medium |
| `api.security` | `ValueError/IndexError` | Handled in SecurityLimiter._parse_rate_limit | Medium |
| `core.circuit_breaker` | `CircuitBreakerOpenError` | Circuit breaker OPEN for {...}s | Medium |
| `core.circuit_breaker` | `expected_exception` | Handled in CircuitBreaker.call | Medium |
| `core.config` | `YAMLError` | Handled in load_config | Medium |
| `core.io_utils` | `Exception` | Handled in _sync | Medium |
| `core.io_utils` | `OSError` | Handled in _sync | Medium |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium |
| `core.logger` | `OSError` | Handled in setup_logging | Medium |
| `core.metrics` | `CancelledError` | Handled in MetricsLogger.stop | Medium |
| `core.metrics` | `Exception` | Handled in MetricsLogger._worker | Medium |
| `core.metrics` | `QueueFull` | Handled in MetricsLogger.log | Medium |
| `core.metrics` | `RuntimeError` | Handled in MetricsLogger.start | Medium |
| `core.metrics` | `TimeoutError` | Handled in MetricsLogger.stop | Medium |
| `core.metrics` | `TypeError` | Handled in module | Medium |
| `core.retry` | `Exception` | Handled in async_wrapper | Medium |
| `core.retry` | `_PERMANENT_ERRORS` | Handled in async_wrapper | Medium |
| `core.tool_registry` | `CancelledError` | Handled in ToolRegistry.dispatch | Medium |
| `core.tool_registry` | `Exception` | Handled in ToolRegistry.dispatch | Medium |
| `core.utils` | `Exception` | Handled in get_tokenizer | Medium |
| `core.utils` | `ImportError` | Handled in module | Medium |
| `core.utils` | `KeyError` | Handled in get_tokenizer | Medium |
| `core.utils` | `OSError` | Handled in _resolve_tokenizer_dir | Medium |
| `dev.tests.test_metrics` | `CancelledError` | Handled in TestMetricsLogger.test_stop_logs_timeout | Medium |
| `dev.tests.test_resilience` | `Exception` | Handled in TestCorruptedPersistence.test_faiss_load_corrupte... | Medium |
| `dev.tests.test_resilience` | `OperationalError/PermissionError` | Handled in TestDiskErrors.test_sqlite_readonly_db | Medium |
| `dev.tests.test_scripts_and_platform` | `ImportError` | Cannot load {...} | Medium |
| `dev.tests.test_scripts_and_platform` | `ModuleNotFoundError` | Handled in TestCheckScripts.test_check_mypy_runs | Medium |
| `features.chat.handlers` | `Exception` | Handled in chat | Medium |
| `features.chat.handlers` | `HTTPException` | Handled in chat | Medium |
| `features.chat.manager` | `Error/ValueError` | Handled in ChatManager.chat | Medium |
| `features.chat.manager` | `Exception` | Handled in ChatManager.chat | Medium |
| `features.chat.manager` | `ValueError/IndexError` | Handled in ChatManager._append_rag_sources | Medium |
| `features.image_analysis.handlers` | `Exception` | Handled in analyze_image | Medium |
| `features.image_analysis.manager` | `Exception` | Handled in ImageAnalysisManager.analyze | Medium |
| `features.rag.handlers` | `Exception` | Handled in index_documents | Medium |
| `features.rag.manager` | `Exception` | Handled in IndexingManager.index_documents | Medium |
| `features.rag.manager` | `ValueError/IndexError` | Handled in RAGManager.query | Medium |
| `pipeline.steps` | `CancelledError` | Handled in generate | Medium |
| `pipeline.steps` | `Exception` | Handled in embed_query | Medium |
| `dev.tests.test_scripts_and_platform` | `FileNotFoundError` | Config not found: {...} | Low |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.
