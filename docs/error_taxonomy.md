## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-24 10:02 UTC
> **Rule:** Check this table before adding try/except or changing error handling.
> **Note:** This is heuristic output — verify against source before acting.

## AI Usage Notes
> For AI assistants: apply these filters when using this table for analysis.

- **Skip `tests/` entries** for production analysis unless explicitly asked about test coverage.
- **Merge pairs**: `logger.exception("...")` + `raise AdapterError("...")` in same block = single error flow, count once.
- **Line numbers are approximate** ±10 lines due to code drift; always verify against current source.
- **Severity is heuristic** — trust `Critical`, verify `High`, question `Medium/Low` in context:
  - `Critical` = startup aborts (SystemExit, KeyboardInterrupt) — always real
  - `High` = request fails (ValueError, HTTPException, AdapterError) — usually real
  - `Medium` = degraded (OSError, JSONDecodeError) — check if recoverable
  - `Low` = client error / test artifact — often skip
- **When in doubt**: prefer reading source over trusting this table.

| Component | Exception | Trigger | Severity |
|-----------|-----------|---------|----------|
| `core.retry` | `SystemExit/KeyboardInterrupt` | raise | Critical |
| `tests.test_retry` | `KeyboardInterrupt` | Raised KeyboardInterrupt | Critical |
| `adapters.chunker_simple` | `ValueError` | chunk_size must be > 0, got {...} | High |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap must be >= 0, got {...} | High |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap ({...}) must be < chunk_size ({...}) | High |
| `adapters.embedder_openai_compatible` | `AdapterError` | Unexpected response shape from {...}: {...} | High |
| `adapters.embedder_openai_compatible` | `AdapterError` | Dimension mismatch: expected {...}, got {...} for text[{...}... | High |
| `adapters.embedder_openai_compatible` | `AdapterError` | Embedder adapter is shutting down | High |
| `adapters.embedder_openai_compatible` | `AdapterError` | Embedder HTTP request failed: {...} | High |
| `adapters.factory` | `ValueError` | faiss-cpu is not installed but vector_store.provider='faiss' | High |
| `adapters.factory` | `ValueError` | sqlite3 not available but storage.provider='sqlite' | High |
| `adapters.factory` | `ValueError` | Unknown adapter port '{...}' | High |
| `adapters.factory` | `ValueError` | No {...} adapter registered for '{...}' | High |
| `adapters.llm_openai_compatible` | `AdapterError` | LLM adapter is shutting down | High |
| `adapters.llm_openai_compatible` | `AdapterError` | LLM HTTP request failed: {...} | High |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High |
| `adapters.llm_openai_compatible` | `AdapterError` | LLM stream request failed: {...} | High |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS search: expected {...}, got {...... | High |
| `adapters.vector_store_faiss` | `AdapterError` | Index metadata missing for namespace '{...}': {...} not foun... | High |
| `adapters.vector_store_faiss` | `AdapterError` | Index file missing for namespace '{...}': {...} not found. P... | High |
| `adapters.vector_store_faiss` | `AdapterError` | Invalid store.json for namespace '{...}': {...} | High |
| `adapters.vector_store_faiss` | `AdapterError` | Index integrity check failed for namespace '{...}': FAISS ha... | High |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored metric '{...}' != config metric '{.... | High |
| `adapters.vector_store_memory` | `AdapterError` | Index load failed for namespace '{...}': chunk '{...}' has e... | High |
| `adapters.vector_store_memory` | `AdapterError` | Index integrity check failed for namespace '{...}': embeddin... | High |
| `adapters.vector_store_memory` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High |
| `api.admin` | `HTTPException` | Unknown error | High |
| `api.deps` | `RuntimeError` | LLM adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Embedder adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Vector store adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Pipeline failed to initialize | High |
| `api.deps` | `RuntimeError` | Storage adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Chunker adapter failed to initialize | High |
| `api.deps` | `RuntimeError` | Chat manager failed to initialize | High |
| `api.deps` | `RuntimeError` | State not initialized | High |
| `api.deps` | `ValueError` | Unknown step: {...} | High |
| `api.security` | `HTTPException` | Unknown error | High |
| `core.config` | `ValueError` | Unknown error | High |
| `core.config` | `ValueError` | path must be non-empty | High |
| `core.config` | `ValueError` | path must be relative, got: {...} | High |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High |
| `core.config` | `ValueError` | Invalid YAML in {...}: {...} | High |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High |
| `core.logger` | `ValueError` | Invalid log format {...}. Use 'text' or 'json'. | High |
| `core.pipeline` | `ConfigurationError` | Missing required PipelineData fields: {...} | High |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High |
| `core.prompts.__init__` | `ValueError` | prompt version is required | High |
| `core.retry` | `RuntimeError` | last_exception is None after retry loop | High |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High |
| `features.chat.handlers` | `HTTPException` | Unknown error | High |
| `features.chat.manager` | `AdapterError` | LLM call failed: {...} | High |
| `features.chat.manager` | `AdapterError` | LLM stream failed: {...} | High |
| `features.rag.handlers` | `HTTPException` | Unknown error | High |
| `tests.test_api` | `HTTPException` | Unknown error | High |
| `tests.test_api` | `RuntimeError` | boom | High |
| `tests.test_api` | `ValueError` | No storage adapter registered | High |
| `tests.test_e2e` | `ValueError` | Error with "quotes" and 
 newlines | High |
| `tests.test_pipeline` | `AdapterError` | LLM down | High |
| `tests.test_pipeline` | `RuntimeError` | transient | High |
| `tests.test_pipeline` | `RuntimeError` | fail | High |
| `tests.test_pipeline` | `RuntimeError` | attempt {...} | High |
| `tests.test_pipeline` | `ValueError` | permanent | High |
| `tests.test_properties` | `ValueError` | Unknown embedder: {...} | High |
| `tests.test_properties` | `ValueError` | Unknown llm: {...} | High |
| `tests.test_properties` | `ValueError` | Unknown reranker: {...} | High |
| `tests.test_properties` | `ValueError` | Unknown chunker: {...} | High |
| `tests.test_rag` | `HTTPException` | Unknown error | High |
| `tests.test_retry` | `exc` | fail #{...} | High |
| `tests.test_stateful_ports` | `RuntimeError` | TMP_DIR not set. Call _set_tmp_dir() first. | High |
| `adapters.embedder_openai_compatible` | `HTTPError` | _logger.exception( | Medium |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | _logger.exception( | Medium |
| `adapters.factory` | `ImportError` | raise ValueError( | Medium |
| `adapters.llm_openai_compatible` | `AttributeError` | _logger.warning( | Medium |
| `adapters.llm_openai_compatible` | `HTTPError` | _logger.exception( | Medium |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | raise AdapterError(f"Unexpected response shape: {exc}") from | Medium |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | continue | Medium |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | _logger.warning( | Medium |
| `adapters.llm_openai_compatible` | `TypeError` | return [] | Medium |
| `adapters.reranker_api` | `KeyError/TypeError` | _logger.exception( | Medium |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | continue | Medium |
| `adapters.storage_sqlite` | `JSONDecodeError` | _logger.warning("JSON decode failed in storage", extra={"err | Medium |
| `adapters.vector_store_faiss` | `Exception` | _logger.exception( | Medium |
| `adapters.vector_store_faiss` | `Exception` | with contextlib.suppress(OSError): | Medium |
| `adapters.vector_store_faiss` | `ImportError` | faiss = None  # type: ignore[assignment, no-redef] | Medium |
| `adapters.vector_store_faiss` | `ImportError` | faiss-cpu is not installed but vector_store.provider='faiss' | Medium |
| `adapters.vector_store_faiss` | `JSONDecodeError` | _logger.error( | Medium |
| `adapters.vector_store_faiss` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium |
| `adapters.vector_store_memory` | `Exception` | _logger.exception( | Medium |
| `api.deps` | `ValueError/ImportError` | _logger.exception( | Medium |
| `api.lifespan` | `AttributeError` | logger.warning("No app state found during shutdown") | Medium |
| `api.lifespan` | `Exception` | logger.exception("Index load failed on startup") | Medium |
| `api.lifespan` | `Exception` | logger.exception( | Medium |
| `api.lifespan` | `Exception` | logger.exception("Index save failed") | Medium |
| `api.lifespan` | `Exception` | logger.exception("Adapter shutdown failed", extra={"adapter" | Medium |
| `api.lifespan` | `TimeoutError` | logger.warning( | Medium |
| `api.lifespan` | `TimeoutError` | logger.warning("Adapter shutdown timed out", extra={"adapter | Medium |
| `api.security` | `ValueError` | raise HTTPException( | Medium |
| `core.config` | `YAMLError` | raise ValueError(f"Invalid YAML in {config_path}: {exc}") fr | Medium |
| `core.io_utils` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium |
| `core.io_utils` | `TypeError` | Expected str for mode={...}, got {...} | Medium |
| `core.logger` | `OSError` | sys.stderr.write(f"Failed to create log file {path}: {exc}\n | Medium |
| `core.pipeline_steps` | `AdapterError` | _logger.exception("LLM unavailable", extra={"trace_id": data | Medium |
| `core.pipeline_steps` | `Exception` | _logger.exception("embed_query failed", extra={"trace_id": d | Medium |
| `core.pipeline_steps` | `Exception` | _logger.exception("retrieve failed", extra={"trace_id": data | Medium |
| `core.pipeline_steps` | `Exception` | _logger.exception("rerank failed", extra={"trace_id": data.t | Medium |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(current_data.chunks, query_t | Medium |
| `core.pipeline_steps` | `Exception` | prompt = _build_fallback_prompt(data.chunks, query_text) | Medium |
| `core.pipeline_steps` | `Exception` | _logger.exception( | Medium |
| `core.retry` | `Exception` | last_exception = e | Medium |
| `core.retry` | `_PERMANENT_ERRORS` | raise | Medium |
| `core.retry` | `last_exception` | Raised last_exception | Medium |
| `core.utils` | `AttributeError` | return len(enc.encode(text)) | Medium |
| `core.utils` | `Exception` | pass | Medium |
| `core.utils` | `Exception` | if _cjk_ratio(text) > _CJK_RATIO_THRESHOLD: | Medium |
| `core.utils` | `ImportError` | tiktoken = None  # type: ignore[assignment] | Medium |
| `core.utils` | `ImportError` | tokenizers = None  # type: ignore[assignment] | Medium |
| `core.utils` | `KeyError` | try: | Medium |
| `core.utils` | `OSError` | return None | Medium |
| `features.chat.handlers` | `AdapterError` | _logger.warning( | Medium |
| `features.chat.handlers` | `AdapterError` | payload = json.dumps( | Medium |
| `features.chat.handlers` | `Exception` | await queue.put(exc) | Medium |
| `features.chat.handlers` | `Exception` | _logger.exception("Chat failed", extra={"trace_id": trace_id | Medium |
| `features.chat.handlers` | `Exception` | _logger.exception("Stream failed", extra={"trace_id": trace_ | Medium |
| `features.chat.handlers` | `Exception` | payload = json.dumps({"error": "Internal server error"}) | Medium |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI stream failed", extra={"trace_id": | Medium |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI chat failed", extra={"trace_id": t | Medium |
| `features.chat.handlers` | `HTTPException` | raise | Medium |
| `features.chat.handlers` | `TimeoutError` | yield ": ping\n\n" | Medium |
| `features.chat.handlers` | `item` | Raised item | Medium |
| `features.chat.manager` | `AdapterError` | raise | Medium |
| `features.chat.manager` | `Exception` | logger.warning( | Medium |
| `features.chat.manager` | `Exception` | logger.warning("History load failed", extra={"error": str(ex | Medium |
| `features.chat.manager` | `Exception` | duration_ms = int((time.perf_counter() - start) * 1000) | Medium |
| `features.chat.manager` | `Exception` | logger.warning("History save failed", extra={"error": str(ex | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("Auto-save failed") | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("Delete chunks failed") | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("List namespaces failed") | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("Failed to save file") | Medium |
| `features.rag.handlers` | `Exception` | return { | Medium |
| `features.rag.handlers` | `Exception` | _logger.warning( | Medium |
| `features.rag.handlers` | `Exception` | _logger.exception("Background reindex failed") | Medium |
| `features.rag.manager` | `Exception` | _logger.exception("Health check failed") | Medium |
| `tests.test_api` | `Exception` | errors.append(e) | Medium |
| `tests.test_api` | `ImportError` | sqlite3 not available | Medium |
| `tests.test_chat` | `StopAsyncIteration` | Raised StopAsyncIteration | Medium |
| `tests.test_rag` | `TimeoutError` | pass | Medium |
| `tests.test_retry` | `exc_cls` | permanent | Medium |
| `tests.test_smoke` | `Exception` | return req, None, None | Medium |
| `tests.test_stateful_ports` | `RuntimeError` | loop = asyncio.new_event_loop() | Medium |
| `tests.test_adapters` | `OSError` | simulated write failure | Low |
| `tests.test_domain` | `OSError` | no dir fsync | Low |
| `tests.test_logger` | `OSError` | disk full | Low |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.
