## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-09 10:00 UTC
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
| `adapters.factory` | `ValueError` | No reranker adapter registered for '{...}' | High | 96 |
| `adapters.factory` | `ValueError` | Unknown port: {...} | High | 98 |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High | 159 |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High | 71 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High | 64 |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 254 |
| `adapters.vector_store_memory` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 149 |
| `api.admin` | `HTTPException` | Unknown error | High | 49 |
| `api.deps` | `RuntimeError` | LLM adapter failed to initialize | High | 162 |
| `api.deps` | `RuntimeError` | Embedder adapter failed to initialize | High | 164 |
| `api.deps` | `RuntimeError` | Vector store adapter failed to initialize | High | 166 |
| `api.deps` | `RuntimeError` | Pipeline failed to initialize | High | 168 |
| `api.deps` | `RuntimeError` | Storage adapter failed to initialize | High | 170 |
| `api.deps` | `RuntimeError` | Chunker adapter failed to initialize | High | 172 |
| `api.deps` | `RuntimeError` | Chat manager failed to initialize | High | 174 |
| `api.deps` | `RuntimeError` | State not initialized | High | 193 |
| `api.deps` | `ValueError` | Unknown step: {...} | High | 92 |
| `api.security` | `HTTPException` | Unknown error | High | 61 |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High | 250 |
| `core.config` | `ValueError` | Invalid YAML in {...}: {...} | High | 277 |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High | 29 |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High | 42 |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High | 41 |
| `core.prompts.__init__` | `ValueError` | prompt version is required | High | 71 |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High | 37 |
| `features.chat.handlers` | `HTTPException` | Unknown error | High | 36 |
| `features.chat.manager` | `AdapterError` | LLM call failed: {...} | High | 277 |
| `features.chat.manager` | `AdapterError` | LLM stream failed: {...} | High | 347 |
| `features.rag.handlers` | `HTTPException` | Unknown error | High | 251 |
| `tests.test_api_deps` | `ValueError` | No such reranker | High | 241 |
| `tests.test_api_deps` | `ValueError` | No storage adapter registered for 'sqlite' | High | 264 |
| `tests.test_api_deps` | `ValueError` | Broken config | High | 304 |
| `tests.test_malformed_sse` | `ValueError` | Error with "quotes" and 
 newlines | High | 99 |
| `tests.test_rag_pipeline` | `RuntimeError` | down | High | 303 |
| `tests.test_rag_pipeline` | `RuntimeError` | fail | High | 369 |
| `tests.test_rag_pipeline` | `RuntimeError` | network down | High | 397 |
| `tests.test_rag_pipeline` | `RuntimeError` | connection lost | High | 636 |
| `tests.test_rag_pipeline` | `ValueError` | bad config | High | 612 |
| `tests.test_rag_pipeline` | `ValueError` | bad index | High | 667 |
| `tests.test_resilience` | `RuntimeError` | shutdown boom | High | 271 |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | raise AdapterError(f"Unexpected response shape from {model!r | Medium | 25 |
| `adapters.factory` | `ImportError` | raise ValueError( | Medium | 63 |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | raise AdapterError(f"Unexpected response shape: {exc}") from | Medium | 158 |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | continue | Medium | 214 |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | _logger.warning("Malformed SSE: %s (%s)", obj, exc) | Medium | 238 |
| `adapters.reranker_api` | `KeyError/TypeError` | raise AdapterError(f"Unexpected rerank response shape: {exc} | Medium | 70 |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | continue | Medium | 78 |
| `adapters.storage_sqlite` | `JSONDecodeError` | return default | Medium | 23 |
| `adapters.vector_store_faiss` | `ImportError` | faiss: Any = None  # type: ignore[assignment, no-redef] | Medium | 17 |
| `adapters.vector_store_faiss` | `ImportError` | faiss-cpu is not installed but vector_store.provider='faiss'... | Medium | 352 |
| `api.deps` | `ValueError` | _logger.exception( | Medium | 123 |
| `api.deps` | `ValueError/ImportError` | _logger.exception( | Medium | 131 |
| `api.lifespan` | `AttributeError` | logger.warning("No app state found during shutdown") | Medium | 96 |
| `api.lifespan` | `Exception` | logger.exception("Index load failed on startup") | Medium | 66 |
| `api.lifespan` | `Exception` | logger.exception("Index save failed") | Medium | 117 |
| `api.lifespan` | `Exception` | logger.exception("%s shutdown failed", name) | Medium | 135 |
| `api.lifespan` | `OSError` | logger.warning("Failed to write PID file: %s", exc) | Medium | 73 |
| `api.lifespan` | `OSError` | logger.warning("Failed to remove PID file: %s", exc) | Medium | 88 |
| `api.lifespan` | `TimeoutError` | logger.warning("Index save timed out: %s/%s", index_path, ns | Medium | 114 |
| `core.config` | `YAMLError` | raise ValueError(f"Invalid YAML in {config_path}: {exc}") fr | Medium | 276 |
| `core.io_utils` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium | 60 |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium | 33 |
| `core.io_utils` | `TypeError` | Expected str for mode={...}, got {...} | Medium | 37 |
| `core.logger` | `OSError` | logger.error("Failed to create log file %s: %s", path, exc) | Medium | 67 |
| `core.pipeline_steps` | `AdapterError` | _logger.exception("LLM unavailable", extra={"trace_id": data | Medium | 373 |
| `core.pipeline_steps` | `AdapterError` | _logger.exception( | Medium | 432 |
| `core.pipeline_steps` | `Exception` | _logger.exception("embed_query failed", extra={"trace_id": d | Medium | 129 |
| `core.pipeline_steps` | `Exception` | _logger.exception("retrieve failed", extra={"trace_id": data | Medium | 170 |
| `core.pipeline_steps` | `Exception` | _logger.exception("rerank failed", extra={"trace_id": data.t | Medium | 244 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(current_data.chunks, query_t | Medium | 309 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(data.chunks, query_text) | Medium | 337 |
| `core.pipeline_steps` | `Exception` | _logger.exception( | Medium | 378 |
| `core.pipeline_steps` | `Exception` | content = f"Error: {e}" | Medium | 420 |
| `core.retry` | `Exception` | last_exception = e | Medium | 53 |
| `core.retry` | `_PERMANENT_ERRORS` | raise | Medium | 51 |
| `core.retry` | `last_exception` | Raised last_exception | Medium | 64 |
| `core.utils` | `AttributeError` | return len(enc.encode(text)) | Medium | 124 |
| `core.utils` | `Exception` | pass | Medium | 80 |
| `core.utils` | `Exception` | if _cjk_ratio(text) > 0.3: | Medium | 127 |
| `core.utils` | `ImportError` | tiktoken = None  # type: ignore[assignment] | Medium | 12 |
| `core.utils` | `ImportError` | tokenizers = None  # type: ignore[assignment] | Medium | 17 |
| `core.utils` | `KeyError` | try: | Medium | 77 |
| `core.utils` | `OSError` | return None | Medium | 64 |
| `features.chat.handlers` | `AdapterError` | _logger.warning("LLM unavailable: %s", exc, extra={"trace_id | Medium | 65 |
| `features.chat.handlers` | `AdapterError` | _logger.warning( | Medium | 99 |
| `features.chat.handlers` | `Exception` | _logger.exception("Chat failed", extra={"trace_id": trace_id | Medium | 70 |
| `features.chat.handlers` | `Exception` | _logger.exception("Stream failed", extra={"trace_id": trace_ | Medium | 109 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI stream failed", extra={"trace_id": | Medium | 188 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI chat failed", extra={"trace_id": t | Medium | 206 |
| `features.chat.handlers` | `HTTPException` | raise | Medium | 68 |
| `features.chat.manager` | `AdapterError` | raise | Medium | 268 |
| `features.chat.manager` | `Exception` | logger.warning( | Medium | 214 |
| `features.chat.manager` | `Exception` | logger.warning("History load failed: %s", exc) | Medium | 231 |
| `features.chat.manager` | `Exception` | logger.error( | Medium | 270 |
| `features.chat.manager` | `Exception` | logger.warning("History save failed: %s", exc) | Medium | 310 |
| `features.chat.manager` | `Exception` | raise AdapterError(f"LLM stream failed: {exc}") from exc | Medium | 346 |
| `features.chat.manager` | `ValueError/IndexError` | continue | Medium | 58 |
| `features.rag.handlers` | `Exception` | _logger.exception("Auto-save failed") | Medium | 139 |
| `features.rag.handlers` | `Exception` | _logger.exception("Delete chunks failed") | Medium | 200 |
| `features.rag.handlers` | `Exception` | _logger.exception("List namespaces failed") | Medium | 229 |
| `features.rag.handlers` | `Exception` | _logger.exception("Failed to save file") | Medium | 260 |
| `features.rag.handlers` | `Exception` | return { | Medium | 298 |
| `features.rag.handlers` | `Exception` | _logger.exception("Background reindex failed") | Medium | 344 |
| `features.rag.manager` | `Exception` | errors.append(f"Chunking failed for {doc_id}: {e}") | Medium | 63 |
| `features.rag.manager` | `Exception` | errors.append(f"Embedding failed for {doc_id}: {e}") | Medium | 74 |
| `features.rag.manager` | `Exception` | errors.append(f"Vector store add failed: {e}") | Medium | 96 |
| `features.rag.manager` | `Exception` | _logger.debug("RAG health check failed: %s", exc) | Medium | 213 |
| `features.rag.manager` | `ValueError/IndexError` | continue | Medium | 171 |
| `tests.test_api_deps` | `ImportError` | sqlite3 not available | Medium | 284 |
| `tests.test_api_e2e` | `OSError` | return False | Medium | 518 |
| `tests.test_resilience` | `Exception` | pass  # Acceptable | Medium | 95 |
| `tests.test_resilience` | `Exception` | pass  # Also acceptable if it raises | Medium | 217 |
| `tests.test_resilience` | `OperationalError/PermissionError` | pass  # Expected | Medium | 248 |
| `tests.test_scripts_and_platform` | `ImportError` | Cannot load {...} | Medium | 28 |
| `tests.test_smoke_pyproject` | `AssertionError` | {...} not found in dependencies | Medium | 65 |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.
