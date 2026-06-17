## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-17 11:10 UTC
> **Rule:** Check this table before adding try/except or changing error handling.

| Component | Exception | Trigger | Severity | Line |
|-----------|-----------|---------|----------|------|
| `core.retry` | `SystemExit/KeyboardInterrupt` | raise | Critical | 49 |
| `tests.test_retry` | `KeyboardInterrupt` | Raised KeyboardInterrupt | Critical | 132 |
| `adapters.chunker_simple` | `ValueError` | chunk_size must be > 0, got {...} | High | 24 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap must be >= 0, got {...} | High | 26 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap ({...}) must be < chunk_size ({...}) | High | 28 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Unexpected response shape from {...}: {...} | High | 35 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Dimension mismatch: expected {...}, got {...} for text[{...}... | High | 39 |
| `adapters.factory` | `ValueError` | faiss-cpu is not installed but vector_store.provider='faiss' | High | 54 |
| `adapters.factory` | `ValueError` | sqlite3 not available but storage.provider='sqlite' | High | 63 |
| `adapters.factory` | `ValueError` | Unknown adapter port '{...}' | High | 69 |
| `adapters.factory` | `ValueError` | No {...} adapter registered for '{...}' | High | 73 |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High | 174 |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High | 84 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High | 133 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS search: expected {...}, got {...... | High | 182 |
| `adapters.vector_store_faiss` | `AdapterError` | Index metadata missing for namespace '{...}': {...} not foun... | High | 272 |
| `adapters.vector_store_faiss` | `AdapterError` | Index file missing for namespace '{...}': {...} not found. P... | High | 290 |
| `adapters.vector_store_faiss` | `AdapterError` | Invalid store.json for namespace '{...}': {...} | High | 311 |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 324 |
| `adapters.vector_store_memory` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 158 |
| `api.admin` | `HTTPException` | Unknown error | High | 49 |
| `api.deps` | `RuntimeError` | LLM adapter failed to initialize | High | 255 |
| `api.deps` | `RuntimeError` | Embedder adapter failed to initialize | High | 257 |
| `api.deps` | `RuntimeError` | Vector store adapter failed to initialize | High | 259 |
| `api.deps` | `RuntimeError` | Pipeline failed to initialize | High | 261 |
| `api.deps` | `RuntimeError` | Storage adapter failed to initialize | High | 263 |
| `api.deps` | `RuntimeError` | Chunker adapter failed to initialize | High | 265 |
| `api.deps` | `RuntimeError` | Chat manager failed to initialize | High | 267 |
| `api.deps` | `RuntimeError` | State not initialized | High | 286 |
| `api.deps` | `ValueError` | Unknown step: {...} | High | 99 |
| `api.security` | `HTTPException` | Unknown error | High | 63 |
| `core.config` | `ValueError` | path must be non-empty | High | 179 |
| `core.config` | `ValueError` | path must be relative, got: {...} | High | 181 |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High | 290 |
| `core.config` | `ValueError` | Invalid YAML in {...}: {...} | High | 317 |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High | 28 |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High | 84 |
| `core.logger` | `ValueError` | Invalid log format {...}. Use 'text' or 'json'. | High | 89 |
| `core.pipeline` | `ConfigurationError` | Missing required metadata keys: {...} | High | 62 |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High | 41 |
| `core.prompts.__init__` | `ValueError` | prompt version is required | High | 71 |
| `core.retry` | `RuntimeError` | last_exception is None after retry loop | High | 64 |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High | 36 |
| `features.chat.handlers` | `HTTPException` | Unknown error | High | 38 |
| `features.chat.manager` | `AdapterError` | LLM call failed: {...} | High | 296 |
| `features.chat.manager` | `AdapterError` | LLM stream failed: {...} | High | 393 |
| `features.rag.handlers` | `HTTPException` | Unknown error | High | 214 |
| `tests.test_api` | `HTTPException` | Unknown error | High | 1429 |
| `tests.test_api` | `RuntimeError` | boom | High | 1494 |
| `tests.test_api` | `ValueError` | No storage adapter registered | High | 673 |
| `tests.test_e2e` | `ValueError` | Error with "quotes" and 
 newlines | High | 218 |
| `tests.test_pipeline` | `AdapterError` | LLM down | High | 535 |
| `tests.test_pipeline` | `RuntimeError` | transient | High | 635 |
| `tests.test_pipeline` | `RuntimeError` | fail | High | 665 |
| `tests.test_pipeline` | `RuntimeError` | attempt {...} | High | 687 |
| `tests.test_pipeline` | `ValueError` | permanent | High | 642 |
| `tests.test_properties` | `ValueError` | Unknown embedder: {...} | High | 41 |
| `tests.test_properties` | `ValueError` | Unknown llm: {...} | High | 60 |
| `tests.test_properties` | `ValueError` | Unknown reranker: {...} | High | 73 |
| `tests.test_properties` | `ValueError` | Unknown chunker: {...} | High | 86 |
| `tests.test_rag` | `HTTPException` | Unknown error | High | 179 |
| `tests.test_retry` | `exc` | fail #{...} | High | 38 |
| `tests.test_stateful_ports` | `RuntimeError` | TMP_DIR not set. Call _set_tmp_dir() first. | High | 42 |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | _logger.exception( | Medium | 30 |
| `adapters.factory` | `ImportError` | raise ValueError( | Medium | 53 |
| `adapters.llm_openai_compatible` | `AttributeError` | _logger.warning( | Medium | 96 |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | raise AdapterError(f"Unexpected response shape: {exc}") from | Medium | 173 |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | continue | Medium | 246 |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | _logger.warning( | Medium | 264 |
| `adapters.llm_openai_compatible` | `TypeError` | return [] | Medium | 87 |
| `adapters.reranker_api` | `KeyError/TypeError` | _logger.exception( | Medium | 79 |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | continue | Medium | 91 |
| `adapters.storage_sqlite` | `JSONDecodeError` | return default | Medium | 24 |
| `adapters.vector_store_faiss` | `ImportError` | faiss = None  # type: ignore[assignment, no-redef] | Medium | 30 |
| `adapters.vector_store_faiss` | `ImportError` | faiss-cpu is not installed but vector_store.provider='faiss' | Medium | 89 |
| `adapters.vector_store_faiss` | `JSONDecodeError` | _logger.error( | Medium | 303 |
| `api.deps` | `ValueError/ImportError` | _logger.exception( | Medium | 222 |
| `api.lifespan` | `AttributeError` | logger.warning("No app state found during shutdown") | Medium | 85 |
| `api.lifespan` | `Exception` | logger.exception("Index load failed on startup") | Medium | 72 |
| `api.lifespan` | `Exception` | logger.exception("Index save failed") | Medium | 114 |
| `api.lifespan` | `Exception` | logger.exception("Adapter shutdown failed", extra={"adapter" | Medium | 134 |
| `api.lifespan` | `TimeoutError` | logger.warning( | Medium | 105 |
| `api.lifespan` | `TimeoutError` | logger.warning("Adapter shutdown timed out", extra={"adapter | Medium | 132 |
| `api.security` | `ValueError` | raise HTTPException( | Medium | 64 |
| `core.config` | `YAMLError` | raise ValueError(f"Invalid YAML in {config_path}: {exc}") fr | Medium | 316 |
| `core.io_utils` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium | 59 |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium | 32 |
| `core.io_utils` | `TypeError` | Expected str for mode={...}, got {...} | Medium | 36 |
| `core.logger` | `OSError` | sys.stderr.write(f"Failed to create log file {path}: {exc}\n | Medium | 120 |
| `core.pipeline_steps` | `AdapterError` | _logger.exception("LLM unavailable", extra={"trace_id": data | Medium | 380 |
| `core.pipeline_steps` | `Exception` | _logger.exception("embed_query failed", extra={"trace_id": d | Medium | 127 |
| `core.pipeline_steps` | `Exception` | _logger.exception("retrieve failed", extra={"trace_id": data | Medium | 170 |
| `core.pipeline_steps` | `Exception` | _logger.exception("rerank failed", extra={"trace_id": data.t | Medium | 237 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(current_data.chunks, query_t | Medium | 303 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(data.chunks, query_text) | Medium | 343 |
| `core.pipeline_steps` | `Exception` | _logger.exception( | Medium | 387 |
| `core.retry` | `Exception` | last_exception = e | Medium | 53 |
| `core.retry` | `_PERMANENT_ERRORS` | raise | Medium | 51 |
| `core.retry` | `last_exception` | Raised last_exception | Medium | 65 |
| `core.utils` | `AttributeError` | return len(enc.encode(text)) | Medium | 123 |
| `core.utils` | `Exception` | pass | Medium | 79 |
| `core.utils` | `Exception` | if _cjk_ratio(text) > 0.3: | Medium | 126 |
| `core.utils` | `ImportError` | tiktoken = None  # type: ignore[assignment] | Medium | 12 |
| `core.utils` | `ImportError` | tokenizers = None  # type: ignore[assignment] | Medium | 17 |
| `core.utils` | `KeyError` | try: | Medium | 76 |
| `core.utils` | `OSError` | return None | Medium | 63 |
| `features.chat.handlers` | `AdapterError` | _logger.warning( | Medium | 121 |
| `features.chat.handlers` | `AdapterError` | payload = json.dumps( | Medium | 177 |
| `features.chat.handlers` | `Exception` | await queue.put(exc) | Medium | 66 |
| `features.chat.handlers` | `Exception` | _logger.exception("Chat failed", extra={"trace_id": trace_id | Medium | 129 |
| `features.chat.handlers` | `Exception` | _logger.exception("Stream failed", extra={"trace_id": trace_ | Medium | 169 |
| `features.chat.handlers` | `Exception` | payload = json.dumps({"error": "Internal server error"}) | Medium | 184 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI stream failed", extra={"trace_id": | Medium | 256 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI chat failed", extra={"trace_id": t | Medium | 291 |
| `features.chat.handlers` | `HTTPException` | raise | Medium | 127 |
| `features.chat.handlers` | `TimeoutError` | yield ": ping\n\n" | Medium | 79 |
| `features.chat.handlers` | `item` | Raised item | Medium | 90 |
| `features.chat.manager` | `AdapterError` | raise | Medium | 283 |
| `features.chat.manager` | `Exception` | logger.warning( | Medium | 222 |
| `features.chat.manager` | `Exception` | logger.warning("History load failed", extra={"error": str(ex | Medium | 239 |
| `features.chat.manager` | `Exception` | duration_ms = int((time.perf_counter() - start) * 1000) | Medium | 285 |
| `features.chat.manager` | `Exception` | logger.warning("History save failed", extra={"error": str(ex | Medium | 334 |
| `features.chat.manager` | `ValueError/IndexError` | continue | Medium | 53 |
| `features.rag.handlers` | `Exception` | _logger.exception("Auto-save failed") | Medium | 144 |
| `features.rag.handlers` | `Exception` | _logger.exception("Delete chunks failed") | Medium | 244 |
| `features.rag.handlers` | `Exception` | _logger.exception("List namespaces failed") | Medium | 273 |
| `features.rag.handlers` | `Exception` | _logger.exception("Failed to save file") | Medium | 305 |
| `features.rag.handlers` | `Exception` | return { | Medium | 343 |
| `features.rag.handlers` | `Exception` | _logger.exception("Background reindex failed") | Medium | 389 |
| `features.rag.manager` | `Exception` | _logger.exception("Health check failed") | Medium | 187 |
| `tests.test_api` | `Exception` | errors.append(e) | Medium | 369 |
| `tests.test_api` | `ImportError` | sqlite3 not available | Medium | 696 |
| `tests.test_chat` | `StopAsyncIteration` | Raised StopAsyncIteration | Medium | 44 |
| `tests.test_retry` | `exc_cls` | permanent | Medium | 264 |
| `tests.test_smoke` | `Exception` | return req, None, None | Medium | 538 |
| `tests.test_logger` | `OSError` | disk full | Low | 214 |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.
