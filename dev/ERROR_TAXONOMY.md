## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-03 21:42 UTC
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
| `adapters.factory` | `ValueError` | Unknown port: {...} | High | 102 |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High | 122 |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High | 71 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High | 64 |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 250 |
| `api.admin` | `HTTPException` | Unknown error | High | 54 |
| `api.deps` | `RuntimeError` | State not initialized | High | 205 |
| `api.deps` | `ValueError` | Unknown step: {...} | High | 89 |
| `api.deps` | `ValueError` | AppState is not initialized | High | 102 |
| `api.security` | `HTTPException` | Unknown error | High | 61 |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High | 228 |
| `core.config` | `ValueError` | Invalid YAML in {...}: {...} | High | 254 |
| `core.domain.messages` | `ValueError` | UserMessage must contain at least one payload | High | 54 |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High | 29 |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High | 30 |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High | 41 |
| `core.prompts.__init__` | `ValueError` | prompt version is required | High | 71 |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High | 37 |
| `dev.tests.test_api_deps` | `ValueError` | No such reranker | High | 241 |
| `dev.tests.test_api_deps` | `ValueError` | No storage adapter registered for 'sqlite' | High | 264 |
| `dev.tests.test_api_deps` | `ValueError` | Broken config | High | 306 |
| `dev.tests.test_api_e2e` | `RuntimeError` | No app state available | High | 90 |
| `dev.tests.test_malformed_sse` | `ValueError` | Error with "quotes" and 
 newlines | High | 99 |
| `dev.tests.test_rag_pipeline` | `RuntimeError` | down | High | 251 |
| `dev.tests.test_rag_pipeline` | `RuntimeError` | fail | High | 304 |
| `dev.tests.test_rag_pipeline` | `RuntimeError` | network down | High | 332 |
| `dev.tests.test_rag_pipeline` | `RuntimeError` | connection lost | High | 562 |
| `dev.tests.test_rag_pipeline` | `ValueError` | bad config | High | 538 |
| `dev.tests.test_rag_pipeline` | `ValueError` | bad index | High | 593 |
| `dev.tests.test_resilience` | `RuntimeError` | shutdown boom | High | 185 |
| `features.chat.handlers` | `HTTPException` | Unknown error | High | 36 |
| `features.chat.manager` | `AdapterError` | LLM call failed: {...} | High | 265 |
| `features.chat.manager` | `AdapterError` | LLM stream failed: {...} | High | 370 |
| `features.rag.handlers` | `HTTPException` | Unknown error | High | 83 |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | raise AdapterError(f"Unexpected response shape from {model!r | Medium | 25 |
| `adapters.factory` | `ImportError` | raise ValueError( | Medium | 63 |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | raise AdapterError(f"Unexpected response shape: {exc}") from | Medium | 121 |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | continue | Medium | 178 |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | _logger.warning("Malformed SSE: %s (%s)", obj, exc) | Medium | 208 |
| `adapters.reranker_api` | `KeyError/TypeError` | raise AdapterError(f"Unexpected rerank response shape: {exc} | Medium | 70 |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | continue | Medium | 78 |
| `adapters.storage_sqlite` | `JSONDecodeError` | return default | Medium | 23 |
| `adapters.vector_store_faiss` | `ImportError` | faiss: Any = None  # type: ignore[assignment, no-redef] | Medium | 17 |
| `adapters.vector_store_faiss` | `ImportError` | faiss-cpu is not installed but vector_store.provider='faiss'... | Medium | 348 |
| `adapters.vector_store_memory` | `TypeError/ValueError` | threshold = 0.3 | Medium | 97 |
| `api.deps` | `ValueError` | _logger.exception( | Medium | 138 |
| `api.deps` | `ValueError/ImportError` | _logger.exception( | Medium | 146 |
| `api.lifespan` | `Exception` | logger.exception("Index save failed") | Medium | 96 |
| `api.lifespan` | `Exception` | logger.exception("%s shutdown failed", name) | Medium | 108 |
| `api.lifespan` | `OSError` | logger.warning("Failed to write PID file: %s", exc) | Medium | 60 |
| `api.lifespan` | `OSError` | logger.warning("Failed to remove PID file: %s", exc) | Medium | 75 |
| `core.config` | `YAMLError` | raise ValueError(f"Invalid YAML in {config_path}: {exc}") fr | Medium | 253 |
| `core.io_utils` | `OSError` | pass  # Windows or filesystem without directory fsync suppor | Medium | 57 |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium | 33 |
| `core.io_utils` | `TypeError` | Expected str for mode={...}, got {...} | Medium | 37 |
| `core.logger` | `OSError` | logger.error("Failed to create log file %s: %s", path, exc) | Medium | 55 |
| `core.retry` | `Exception` | last_exception = e | Medium | 53 |
| `core.retry` | `_PERMANENT_ERRORS` | raise | Medium | 51 |
| `core.utils` | `AttributeError` | return len(enc.encode(text)) | Medium | 124 |
| `core.utils` | `Exception` | pass | Medium | 80 |
| `core.utils` | `Exception` | if _cjk_ratio(text) > 0.3: | Medium | 127 |
| `core.utils` | `ImportError` | tiktoken = None  # type: ignore[assignment] | Medium | 12 |
| `core.utils` | `ImportError` | tokenizers = None  # type: ignore[assignment] | Medium | 17 |
| `core.utils` | `KeyError` | try: | Medium | 77 |
| `core.utils` | `OSError` | return None | Medium | 64 |
| `dev.tests.test_api_deps` | `ImportError` | sqlite3 not available | Medium | 285 |
| `dev.tests.test_api_e2e` | `OSError` | return False | Medium | 599 |
| `dev.tests.test_resilience` | `Exception` | pass  # Acceptable | Medium | 91 |
| `dev.tests.test_resilience` | `Exception` | pass  # Also acceptable if it raises | Medium | 131 |
| `dev.tests.test_resilience` | `OperationalError/PermissionError` | pass  # Expected | Medium | 162 |
| `dev.tests.test_scripts_and_platform` | `ImportError` | Cannot load {...} | Medium | 31 |
| `dev.tests.test_scripts_and_platform` | `ModuleNotFoundError` | pytest.skip("mypy not installed") | Medium | 250 |
| `dev.tests.test_scripts_and_platform` | `ModuleNotFoundError` | pytest.skip("ruff not installed") | Medium | 263 |
| `features.chat.handlers` | `AdapterError` | _logger.warning("LLM unavailable: %s", exc) | Medium | 108 |
| `features.chat.handlers` | `AdapterError` | _logger.warning("LLM unavailable in stream: %s", exc) | Medium | 145 |
| `features.chat.handlers` | `Exception` | _logger.exception("Chat failed") | Medium | 113 |
| `features.chat.handlers` | `Exception` | _logger.exception("Stream failed") | Medium | 153 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI stream failed") | Medium | 234 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI chat failed") | Medium | 253 |
| `features.chat.handlers` | `HTTPException` | raise | Medium | 111 |
| `features.chat.handlers` | `ValueError` | pass | Medium | 76 |
| `features.chat.manager` | `AdapterError` | raise | Medium | 257 |
| `features.chat.manager` | `Exception` | logger.warning( | Medium | 234 |
| `features.chat.manager` | `Exception` | logger.warning("History load failed: %s", exc) | Medium | 252 |
| `features.chat.manager` | `Exception` | logger.error( | Medium | 259 |
| `features.chat.manager` | `Exception` | logger.warning("History save failed: %s", exc) | Medium | 297 |
| `features.chat.manager` | `Exception` | history = ( | Medium | 347 |
| `features.chat.manager` | `Exception` | raise AdapterError(f"LLM stream failed: {exc}") from exc | Medium | 369 |
| `features.chat.manager` | `ValueError/IndexError` | continue | Medium | 52 |
| `features.rag.handlers` | `Exception` | _logger.exception("Auto-save failed") | Medium | 135 |
| `features.rag.handlers` | `Exception` | _logger.exception("Delete chunks failed") | Medium | 198 |
| `features.rag.handlers` | `Exception` | _logger.exception("List namespaces failed") | Medium | 229 |
| `features.rag.handlers` | `Exception` | _logger.exception("Failed to save file") | Medium | 256 |
| `features.rag.handlers` | `Exception` | return { | Medium | 298 |
| `features.rag.handlers` | `Exception` | _logger.exception("Background reindex failed") | Medium | 341 |
| `features.rag.manager` | `Exception` | errors.append(f"Chunking failed for {doc_id}: {e}") | Medium | 56 |
| `features.rag.manager` | `Exception` | errors.append(f"Embedding failed for {doc_id}: {e}") | Medium | 67 |
| `features.rag.manager` | `Exception` | errors.append(f"Vector store add failed: {e}") | Medium | 89 |
| `features.rag.manager` | `Exception` | _logger.debug("RAG health check failed: %s", exc) | Medium | 209 |
| `features.rag.manager` | `ValueError/IndexError` | continue | Medium | 167 |
| `pipeline.steps` | `AdapterError` | _logger.exception("LLM unavailable") | Medium | 301 |
| `pipeline.steps` | `AdapterError` | _logger.exception("LLM unavailable during tool follow-up") | Medium | 358 |
| `pipeline.steps` | `Exception` | _logger.exception("embed_query failed") | Medium | 116 |
| `pipeline.steps` | `Exception` | _logger.exception("retrieve failed") | Medium | 147 |
| `pipeline.steps` | `Exception` | _logger.exception("rerank failed") | Medium | 210 |
| `pipeline.steps` | `Exception` | prompt = _build_fallback_prompt() | Medium | 253 |
| `pipeline.steps` | `Exception` | _logger.exception("generate failed after retries") | Medium | 306 |
| `pipeline.steps` | `Exception` | content = f"Error: {e}" | Medium | 346 |
| `pipeline.steps` | `Exception` | _logger.exception("tool follow-up call failed after retries" | Medium | 362 |
| `pipeline.steps` | `Exception` | _logger.exception("hyde_query: LLM call failed") | Medium | 401 |
| `pipeline.steps` | `Exception` | _logger.exception("hyde_query: embedding failed") | Medium | 412 |
| `dev.tests.test_scripts_and_platform` | `FileNotFoundError` | Config not found: {...} | Low | 294 |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.
