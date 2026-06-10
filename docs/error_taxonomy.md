## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-10 07:50 UTC
> **Rule:** Check this table before adding try/except or changing error handling.

| Component | Exception | Trigger | Severity | Line |
|-----------|-----------|---------|----------|------|
| `core.retry` | `SystemExit/KeyboardInterrupt` | raise | Critical | 49 |
| `adapters.chunker_simple` | `ValueError` | chunk_size must be > 0, got {...} | High | 22 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap must be >= 0, got {...} | High | 24 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap ({...}) must be < chunk_size ({...}) | High | 26 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Unexpected response shape from {...}: {...} | High | 26 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Dimension mismatch: expected {...}, got {...} for text[{...}... | High | 30 |
| `adapters.factory` | `ValueError` | No LLM adapter registered for '{...}' | High | 38 |
| `adapters.factory` | `ValueError` | No embedder adapter registered for '{...}' | High | 52 |
| `adapters.factory` | `ValueError` | faiss-cpu is not installed but vector_store.provider='faiss' | High | 64 |
| `adapters.factory` | `ValueError` | No vector_store adapter registered for '{...}' | High | 68 |
| `adapters.factory` | `ValueError` | No chunker adapter registered for '{...}' | High | 76 |
| `adapters.factory` | `ValueError` | sqlite3 not available but storage.provider='sqlite' | High | 84 |
| `adapters.factory` | `ValueError` | No storage adapter registered for '{...}' | High | 88 |
| `adapters.factory` | `ValueError` | No reranker adapter registered for '{...}' | High | 100 |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High | 169 |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High | 75 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High | 70 |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 256 |
| `adapters.vector_store_memory` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 155 |
| `api.admin` | `HTTPException` | Unknown error | High | 49 |
| `api.deps` | `RuntimeError` | LLM adapter failed to initialize | High | 157 |
| `api.deps` | `RuntimeError` | Embedder adapter failed to initialize | High | 159 |
| `api.deps` | `RuntimeError` | Vector store adapter failed to initialize | High | 161 |
| `api.deps` | `RuntimeError` | Pipeline failed to initialize | High | 163 |
| `api.deps` | `RuntimeError` | Storage adapter failed to initialize | High | 165 |
| `api.deps` | `RuntimeError` | Chunker adapter failed to initialize | High | 167 |
| `api.deps` | `RuntimeError` | Chat manager failed to initialize | High | 169 |
| `api.deps` | `RuntimeError` | State not initialized | High | 188 |
| `api.deps` | `ValueError` | Unknown step: {...} | High | 92 |
| `api.security` | `HTTPException` | Unknown error | High | 63 |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High | 250 |
| `core.config` | `ValueError` | Invalid YAML in {...}: {...} | High | 277 |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High | 29 |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High | 42 |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High | 41 |
| `core.prompts.__init__` | `ValueError` | prompt version is required | High | 71 |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High | 36 |
| `features.chat.handlers` | `HTTPException` | Unknown error | High | 36 |
| `features.chat.manager` | `AdapterError` | LLM call failed: {...} | High | 279 |
| `features.rag.handlers` | `HTTPException` | Unknown error | High | 249 |
| `tests.test_api_deps` | `ValueError` | No storage adapter registered for 'sqlite' | High | 265 |
| `tests.test_api_deps` | `ValueError` | Broken config | High | 305 |
| `tests.test_malformed_sse` | `ValueError` | Error with "quotes" and 
 newlines | High | 99 |
| `tests.test_rag_pipeline` | `RuntimeError` | down | High | 310 |
| `tests.test_rag_pipeline` | `RuntimeError` | fail | High | 376 |
| `tests.test_rag_pipeline` | `RuntimeError` | network down | High | 407 |
| `tests.test_rag_pipeline` | `RuntimeError` | connection lost | High | 649 |
| `tests.test_rag_pipeline` | `ValueError` | bad config | High | 625 |
| `tests.test_rag_pipeline` | `ValueError` | bad index | High | 680 |
| `tests.test_resilience` | `RuntimeError` | shutdown boom | High | 272 |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | raise AdapterError(f"Unexpected response shape from {model!r | Medium | 25 |
| `adapters.factory` | `ImportError` | raise ValueError( | Medium | 63 |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | raise AdapterError(f"Unexpected response shape: {exc}") from | Medium | 168 |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | continue | Medium | 226 |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | _logger.warning("Malformed SSE: %s (%s)", obj, exc) | Medium | 250 |
| `adapters.reranker_api` | `KeyError/TypeError` | raise AdapterError(f"Unexpected rerank response shape: {exc} | Medium | 74 |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | continue | Medium | 82 |
| `adapters.storage_sqlite` | `JSONDecodeError` | return default | Medium | 23 |
| `adapters.vector_store_faiss` | `ImportError` | faiss: Any = None  # type: ignore[assignment, no-redef] | Medium | 17 |
| `adapters.vector_store_faiss` | `ImportError` | faiss-cpu is not installed but vector_store.provider='faiss'... | Medium | 354 |
| `api.deps` | `ValueError/ImportError` | _logger.exception( | Medium | 126 |
| `api.lifespan` | `AttributeError` | logger.warning("No app state found during shutdown") | Medium | 96 |
| `api.lifespan` | `Exception` | logger.exception("Index load failed on startup") | Medium | 66 |
| `api.lifespan` | `Exception` | logger.exception("Index save failed") | Medium | 117 |
| `api.lifespan` | `Exception` | logger.exception("Adapter '%s' shutdown failed", name) | Medium | 135 |
| `api.lifespan` | `OSError` | logger.warning("Failed to write PID file: %s", exc) | Medium | 73 |
| `api.lifespan` | `OSError` | logger.warning("Failed to remove PID file: %s", exc) | Medium | 88 |
| `api.lifespan` | `TimeoutError` | logger.warning("Index save timed out: %s/%s", index_path, ns | Medium | 114 |
| `api.security` | `ValueError` | raise HTTPException( | Medium | 64 |
| `core.config` | `YAMLError` | raise ValueError(f"Invalid YAML in {config_path}: {exc}") fr | Medium | 276 |
| `core.io_utils` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium | 60 |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium | 33 |
| `core.io_utils` | `TypeError` | Expected str for mode={...}, got {...} | Medium | 37 |
| `core.logger` | `OSError` | logger.error("Failed to create log file %s: %s", path, exc) | Medium | 67 |
| `core.pipeline_steps` | `AdapterError` | _logger.exception("LLM unavailable", extra={"trace_id": data | Medium | 366 |
| `core.pipeline_steps` | `AdapterError` | _logger.exception( | Medium | 424 |
| `core.pipeline_steps` | `Exception` | _logger.exception("embed_query failed", extra={"trace_id": d | Medium | 132 |
| `core.pipeline_steps` | `Exception` | _logger.exception("retrieve failed", extra={"trace_id": data | Medium | 173 |
| `core.pipeline_steps` | `Exception` | _logger.exception("rerank failed", extra={"trace_id": data.t | Medium | 238 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(current_data.chunks, query_t | Medium | 303 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(data.chunks, query_text) | Medium | 331 |
| `core.pipeline_steps` | `Exception` | _logger.exception( | Medium | 371 |
| `core.pipeline_steps` | `Exception` | content = f"Error: {e}" | Medium | 413 |
| `core.retry` | `Exception` | last_exception = e | Medium | 53 |
| `core.retry` | `_PERMANENT_ERRORS` | raise | Medium | 51 |
| `core.retry` | `last_exception` | Raised last_exception | Medium | 64 |
| `core.utils` | `AttributeError` | return len(enc.encode(text)) | Medium | 123 |
| `core.utils` | `Exception` | pass | Medium | 79 |
| `core.utils` | `Exception` | if _cjk_ratio(text) > 0.3: | Medium | 126 |
| `core.utils` | `ImportError` | tiktoken = None  # type: ignore[assignment] | Medium | 12 |
| `core.utils` | `ImportError` | tokenizers = None  # type: ignore[assignment] | Medium | 17 |
| `core.utils` | `KeyError` | try: | Medium | 76 |
| `core.utils` | `OSError` | return None | Medium | 63 |
| `features.chat.handlers` | `AdapterError` | _logger.warning("LLM unavailable: %s", exc, extra={"trace_id | Medium | 65 |
| `features.chat.handlers` | `AdapterError` | _logger.warning( | Medium | 99 |
| `features.chat.handlers` | `Exception` | _logger.exception("Chat failed", extra={"trace_id": trace_id | Medium | 70 |
| `features.chat.handlers` | `Exception` | _logger.exception("Stream failed", extra={"trace_id": trace_ | Medium | 109 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI stream failed", extra={"trace_id": | Medium | 188 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI chat failed", extra={"trace_id": t | Medium | 206 |
| `features.chat.handlers` | `HTTPException` | raise | Medium | 68 |
| `features.chat.manager` | `AdapterError` | raise | Medium | 270 |
| `features.chat.manager` | `Exception` | logger.warning( | Medium | 216 |
| `features.chat.manager` | `Exception` | logger.warning("History load failed: %s", exc) | Medium | 233 |
| `features.chat.manager` | `Exception` | logger.error( | Medium | 272 |
| `features.chat.manager` | `Exception` | logger.warning("History save failed: %s", exc) | Medium | 312 |
| `features.chat.manager` | `NotImplementedError` | stream_chat tool calls are not handled | Medium | 326 |
| `features.chat.manager` | `ValueError/IndexError` | continue | Medium | 58 |
| `features.rag.handlers` | `Exception` | _logger.exception("Auto-save failed") | Medium | 137 |
| `features.rag.handlers` | `Exception` | _logger.exception("Delete chunks failed") | Medium | 198 |
| `features.rag.handlers` | `Exception` | _logger.exception("List namespaces failed") | Medium | 227 |
| `features.rag.handlers` | `Exception` | _logger.exception("Failed to save file") | Medium | 258 |
| `features.rag.handlers` | `Exception` | return { | Medium | 296 |
| `features.rag.handlers` | `Exception` | _logger.exception("Background reindex failed") | Medium | 342 |
| `features.rag.manager` | `Exception` | _logger.exception("Health check failed") | Medium | 146 |
| `tests.test_api_deps` | `ImportError` | sqlite3 not available | Medium | 285 |
| `tests.test_api_e2e` | `OSError` | return False | Medium | 519 |
| `tests.test_resilience` | `Exception` | pass  # Acceptable | Medium | 96 |
| `tests.test_resilience` | `Exception` | pass  # Also acceptable if it raises | Medium | 218 |
| `tests.test_resilience` | `OperationalError/PermissionError` | pass  # Expected | Medium | 249 |
| `tests.test_scripts_and_platform` | `ImportError` | Cannot load {...} | Medium | 28 |
| `tests.test_smoke_pyproject` | `AssertionError` | {...} not found in dependencies | Medium | 65 |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.
