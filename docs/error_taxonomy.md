## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-13 19:32 UTC
> **Rule:** Check this table before adding try/except or changing error handling.

| Component | Exception | Trigger | Severity | Line |
|-----------|-----------|---------|----------|------|
| `core.retry` | `SystemExit/KeyboardInterrupt` | raise | Critical | 49 |
| `adapters.chunker_simple` | `ValueError` | chunk_size must be > 0, got {...} | High | 22 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap must be >= 0, got {...} | High | 24 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap ({...}) must be < chunk_size ({...}) | High | 26 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Unexpected response shape from {...}: {...} | High | 27 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Dimension mismatch: expected {...}, got {...} for text[{...}... | High | 31 |
| `adapters.factory` | `ValueError` | No LLM adapter registered for '{...}' | High | 48 |
| `adapters.factory` | `ValueError` | No embedder adapter registered for '{...}' | High | 62 |
| `adapters.factory` | `ValueError` | faiss-cpu is not installed but vector_store.provider='faiss' | High | 74 |
| `adapters.factory` | `ValueError` | No vector_store adapter registered for '{...}' | High | 78 |
| `adapters.factory` | `ValueError` | No chunker adapter registered for '{...}' | High | 86 |
| `adapters.factory` | `ValueError` | sqlite3 not available but storage.provider='sqlite' | High | 94 |
| `adapters.factory` | `ValueError` | No storage adapter registered for '{...}' | High | 98 |
| `adapters.factory` | `ValueError` | No reranker adapter registered for '{...}' | High | 110 |
| `adapters.factory` | `ValueError` | Unknown adapter port '{...}' | High | 113 |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High | 177 |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High | 75 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High | 71 |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 257 |
| `adapters.vector_store_memory` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 156 |
| `api.admin` | `HTTPException` | Unknown error | High | 49 |
| `api.deps` | `RuntimeError` | LLM adapter failed to initialize | High | 231 |
| `api.deps` | `RuntimeError` | Embedder adapter failed to initialize | High | 233 |
| `api.deps` | `RuntimeError` | Vector store adapter failed to initialize | High | 235 |
| `api.deps` | `RuntimeError` | Pipeline failed to initialize | High | 237 |
| `api.deps` | `RuntimeError` | Storage adapter failed to initialize | High | 239 |
| `api.deps` | `RuntimeError` | Chunker adapter failed to initialize | High | 241 |
| `api.deps` | `RuntimeError` | Chat manager failed to initialize | High | 243 |
| `api.deps` | `RuntimeError` | State not initialized | High | 262 |
| `api.deps` | `ValueError` | Unknown step: {...} | High | 99 |
| `api.security` | `HTTPException` | Unknown error | High | 63 |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High | 262 |
| `core.config` | `ValueError` | Invalid YAML in {...}: {...} | High | 289 |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High | 28 |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High | 43 |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High | 41 |
| `core.prompts.__init__` | `ValueError` | prompt version is required | High | 71 |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High | 36 |
| `features.chat.handlers` | `HTTPException` | Unknown error | High | 38 |
| `features.chat.manager` | `AdapterError` | LLM call failed: {...} | High | 281 |
| `features.chat.manager` | `AdapterError` | LLM stream failed: {...} | High | 361 |
| `features.rag.handlers` | `HTTPException` | Unknown error | High | 250 |
| `tests.test_api` | `HTTPException` | Unknown error | High | 1401 |
| `tests.test_api` | `RuntimeError` | boom | High | 1466 |
| `tests.test_api` | `ValueError` | No storage adapter registered | High | 653 |
| `tests.test_e2e` | `ValueError` | Error with "quotes" and 
 newlines | High | 212 |
| `tests.test_pipeline` | `RuntimeError` | transient | High | 552 |
| `tests.test_pipeline` | `RuntimeError` | fail | High | 582 |
| `tests.test_pipeline` | `RuntimeError` | attempt {...} | High | 604 |
| `tests.test_pipeline` | `ValueError` | permanent | High | 559 |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | raise AdapterError(f"Unexpected response shape from {model!r | Medium | 26 |
| `adapters.factory` | `ImportError` | raise ValueError( | Medium | 73 |
| `adapters.llm_openai_compatible` | `AttributeError` | _logger.warning("Skipping non-dict tool_call: %s", tc) | Medium | 116 |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | raise AdapterError(f"Unexpected response shape: {exc}") from | Medium | 176 |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | continue | Medium | 238 |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | _logger.warning("Malformed SSE: %s (%s)", obj, exc) | Medium | 256 |
| `adapters.llm_openai_compatible` | `TypeError` | return [] | Medium | 107 |
| `adapters.reranker_api` | `KeyError/TypeError` | raise AdapterError(f"Unexpected rerank response shape: {exc} | Medium | 74 |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | continue | Medium | 82 |
| `adapters.storage_sqlite` | `JSONDecodeError` | return default | Medium | 24 |
| `adapters.vector_store_faiss` | `ImportError` | faiss: Any = None  # type: ignore[assignment, no-redef] | Medium | 17 |
| `adapters.vector_store_faiss` | `ImportError` | faiss-cpu is not installed but vector_store.provider='faiss'... | Medium | 355 |
| `api.deps` | `ValueError/ImportError` | _logger.exception( | Medium | 200 |
| `api.lifespan` | `AttributeError` | logger.warning("No app state found during shutdown") | Medium | 78 |
| `api.lifespan` | `Exception` | logger.exception("Index load failed on startup") | Medium | 65 |
| `api.lifespan` | `Exception` | logger.exception("Index save failed") | Medium | 99 |
| `api.lifespan` | `Exception` | logger.exception("Adapter '%s' shutdown failed", name) | Medium | 119 |
| `api.lifespan` | `TimeoutError` | logger.warning("Index save timed out: %s/%s", index_path, ns | Medium | 96 |
| `api.lifespan` | `TimeoutError` | logger.warning("Adapter '%s' shutdown timed out", name) | Medium | 117 |
| `api.security` | `ValueError` | raise HTTPException( | Medium | 64 |
| `core.config` | `YAMLError` | raise ValueError(f"Invalid YAML in {config_path}: {exc}") fr | Medium | 288 |
| `core.io_utils` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium | 59 |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium | 32 |
| `core.io_utils` | `TypeError` | Expected str for mode={...}, got {...} | Medium | 36 |
| `core.logger` | `OSError` | logger.error("Failed to create log file %s: %s", path, exc) | Medium | 73 |
| `core.pipeline_steps` | `AdapterError` | _logger.exception("LLM unavailable", extra={"trace_id": data | Medium | 364 |
| `core.pipeline_steps` | `Exception` | _logger.exception("embed_query failed", extra={"trace_id": d | Medium | 129 |
| `core.pipeline_steps` | `Exception` | _logger.exception("retrieve failed", extra={"trace_id": data | Medium | 170 |
| `core.pipeline_steps` | `Exception` | _logger.exception("rerank failed", extra={"trace_id": data.t | Medium | 236 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(current_data.chunks, query_t | Medium | 301 |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(data.chunks, query_text) | Medium | 329 |
| `core.pipeline_steps` | `Exception` | _logger.exception( | Medium | 369 |
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
| `features.chat.handlers` | `AdapterError` | _logger.warning("LLM unavailable: %s", exc, extra={"trace_id | Medium | 118 |
| `features.chat.handlers` | `AdapterError` | _logger.warning( | Medium | 151 |
| `features.chat.handlers` | `AdapterError` | payload = json.dumps( | Medium | 164 |
| `features.chat.handlers` | `Exception` | await queue.put(exc) | Medium | 66 |
| `features.chat.handlers` | `Exception` | _logger.exception("Chat failed", extra={"trace_id": trace_id | Medium | 123 |
| `features.chat.handlers` | `Exception` | _logger.exception("Stream failed", extra={"trace_id": trace_ | Medium | 156 |
| `features.chat.handlers` | `Exception` | payload = json.dumps({"error": "Internal server error"}) | Medium | 171 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI stream failed", extra={"trace_id": | Medium | 239 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI chat failed", extra={"trace_id": t | Medium | 271 |
| `features.chat.handlers` | `HTTPException` | raise | Medium | 121 |
| `features.chat.handlers` | `TimeoutError` | yield ": ping\n\n" | Medium | 79 |
| `features.chat.handlers` | `item` | Raised item | Medium | 90 |
| `features.chat.manager` | `AdapterError` | raise | Medium | 272 |
| `features.chat.manager` | `Exception` | logger.warning( | Medium | 218 |
| `features.chat.manager` | `Exception` | logger.warning("History load failed: %s", exc) | Medium | 235 |
| `features.chat.manager` | `Exception` | logger.error( | Medium | 274 |
| `features.chat.manager` | `Exception` | logger.warning("History save failed: %s", exc) | Medium | 313 |
| `features.chat.manager` | `ValueError/IndexError` | continue | Medium | 59 |
| `features.rag.handlers` | `Exception` | _logger.exception("Auto-save failed") | Medium | 138 |
| `features.rag.handlers` | `Exception` | _logger.exception("Delete chunks failed") | Medium | 199 |
| `features.rag.handlers` | `Exception` | _logger.exception("List namespaces failed") | Medium | 228 |
| `features.rag.handlers` | `Exception` | _logger.exception("Failed to save file") | Medium | 259 |
| `features.rag.handlers` | `Exception` | return { | Medium | 297 |
| `features.rag.handlers` | `Exception` | _logger.exception("Background reindex failed") | Medium | 342 |
| `features.rag.manager` | `Exception` | _logger.exception("Health check failed") | Medium | 150 |
| `tests.test_api` | `Exception` | errors.append(e) | Medium | 350 |
| `tests.test_api` | `ImportError` | sqlite3 not available | Medium | 676 |
| `tests.test_chat` | `StopAsyncIteration` | Raised StopAsyncIteration | Medium | 44 |
| `tests.test_smoke` | `Exception` | return req, None, None | Medium | 480 |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.
