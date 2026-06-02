## 🧨 ERROR TAXONOMY
> Auto-generated from source code. Updated: 2026-06-02 15:26 UTC
> **Rule:** Check this table before adding try/except or changing error handling.

| Component | Exception | Trigger | Severity | Line |
|-----------|-----------|---------|----------|------|
| `core.retry` | `SystemExit/KeyboardInterrupt` | raise | Critical | 49 |
| `core.tool_registry` | `SystemExit/KeyboardInterrupt` | raise | Critical | 67 |
| `adapters.chunker_simple` | `ValueError` | chunk_size must be > 0, got {...} | High | 24 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap must be >= 0, got {...} | High | 26 |
| `adapters.chunker_simple` | `ValueError` | chunk_overlap ({...}) must be < chunk_size ({...}) | High | 28 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Unexpected response shape from {...}: {...} | High | 67 |
| `adapters.embedder_openai_compatible` | `AdapterError` | Dimension mismatch: expected {...}, got {...} for text[{...}... | High | 73 |
| `adapters.llm_openai_compatible` | `AdapterError` | Unexpected response shape: {...} | High | 124 |
| `adapters.reranker_api` | `AdapterError` | Unexpected rerank response shape: {...} | High | 73 |
| `adapters.vector_store_faiss` | `AdapterError` | Dimension mismatch in FAISS add: expected {...}, got {...} (... | High | 67 |
| `adapters.vector_store_faiss` | `VersionMismatchError` | Reindex required: stored dim {...} != config dim {...} | High | 248 |
| `api.admin` | `HTTPException` | Unknown error | High | 54 |
| `api.deps` | `RuntimeError` | State not initialized | High | 206 |
| `api.security` | `HTTPException` | Unknown error | High | 61 |
| `core.config` | `ValueError` | embedder.dim ({...}) must equal vector_store.dim ({...}) | High | 194 |
| `core.config` | `ValueError` | Invalid YAML in {...}: {...} | High | 220 |
| `core.domain.messages` | `ValueError` | UserMessage must contain at least one payload | High | 54 |
| `core.io_utils` | `ValueError` | mode must be 'w' or 'wb', got {...} | High | 29 |
| `core.logger` | `ValueError` | Invalid log level {...}. Use one of: {...} | High | 30 |
| `core.prompts.__init__` | `ValueError` | Prompt version directory not found: {...} | High | 40 |
| `core.registry` | `ValueError` | No adapter registered for {...}/{...} | High | 48 |
| `core.utils` | `ValueError` | API key not found in config or env var {...} | High | 34 |
| `dev.tests.test_api_deps` | `ValueError` | No such reranker | High | 266 |
| `dev.tests.test_api_deps` | `ValueError` | Broken config | High | 395 |
| `dev.tests.test_api_e2e` | `RuntimeError` | No app state available | High | 74 |
| `dev.tests.test_malformed_sse` | `ValueError` | Error with "quotes" and 
 newlines | High | 99 |
| `dev.tests.test_rag_pipeline` | `RuntimeError` | down | High | 226 |
| `dev.tests.test_rag_pipeline` | `RuntimeError` | fail | High | 279 |
| `dev.tests.test_rag_pipeline` | `RuntimeError` | network down | High | 307 |
| `dev.tests.test_rag_pipeline` | `RuntimeError` | connection lost | High | 482 |
| `dev.tests.test_rag_pipeline` | `ValueError` | bad config | High | 458 |
| `dev.tests.test_rag_pipeline` | `ValueError` | bad index | High | 513 |
| `dev.tests.test_resilience` | `RuntimeError` | shutdown boom | High | 185 |
| `features.chat.handlers` | `HTTPException` | Unknown error | High | 36 |
| `features.chat.manager` | `AdapterError` | LLM call failed: {...} | High | 258 |
| `features.chat.manager` | `AdapterError` | LLM stream failed: {...} | High | 363 |
| `features.rag.handlers` | `HTTPException` | Unknown error | High | 83 |
| `pipeline.decorators` | `ValueError` | Unknown step: {...} | High | 57 |
| `adapters.embedder_openai_compatible` | `KeyError/TypeError` | raise AdapterError( | Medium | 66 |
| `adapters.llm_openai_compatible` | `IndexError/KeyError/TypeError` | raise AdapterError(f"Unexpected response shape: {exc}") from | Medium | 123 |
| `adapters.llm_openai_compatible` | `JSONDecodeError` | continue | Medium | 180 |
| `adapters.llm_openai_compatible` | `KeyError/IndexError/TypeError` | _logger.warning("Malformed SSE: %s (%s)", obj, exc) | Medium | 210 |
| `adapters.reranker_api` | `KeyError/TypeError` | raise AdapterError(f"Unexpected rerank response shape: {exc} | Medium | 72 |
| `adapters.reranker_api` | `KeyError/TypeError/ValueError` | continue | Medium | 80 |
| `adapters.storage_sqlite` | `JSONDecodeError` | return default | Medium | 24 |
| `adapters.tools_calculator` | `KeyError/TypeError/ValueError` | return ToolResult( | Medium | 75 |
| `adapters.tools_calculator` | `TypeError/KeyError` | return ToolResult( | Medium | 64 |
| `adapters.tools_calculator` | `TypeError/ValueError` | return ToolResult( | Medium | 104 |
| `adapters.vector_store_faiss` | `ImportError` | faiss: Any = None  # type: ignore[assignment, no-redef] | Medium | 17 |
| `adapters.vector_store_faiss` | `ImportError` | faiss-cpu is not installed but vector_store.provider='faiss'... | Medium | 347 |
| `adapters.vector_store_memory` | `TypeError/ValueError` | threshold = 0.3 | Medium | 98 |
| `api.deps` | `Exception` | raise | Medium | 181 |
| `api.deps` | `ImportError` | _logger.exception( | Medium | 133 |
| `api.deps` | `ValueError` | _logger.exception( | Medium | 122 |
| `api.lifespan` | `Exception` | logger.exception("Index save failed") | Medium | 98 |
| `api.lifespan` | `Exception` | logger.exception("%s shutdown failed", name) | Medium | 110 |
| `api.lifespan` | `OSError` | logger.warning("Failed to write PID file: %s", exc) | Medium | 62 |
| `api.lifespan` | `OSError` | logger.warning("Failed to remove PID file: %s", exc) | Medium | 77 |
| `core.config` | `YAMLError` | raise ValueError(f"Invalid YAML in {config_path}: {exc}") fr | Medium | 219 |
| `core.io_utils` | `TypeError` | Expected bytes for mode={...}, got {...} | Medium | 33 |
| `core.io_utils` | `TypeError` | Expected str for mode={...}, got {...} | Medium | 37 |
| `core.logger` | `OSError` | logger.error("Failed to create log file %s: %s", path, exc) | Medium | 55 |
| `core.retry` | `Exception` | last_exception = e | Medium | 53 |
| `core.retry` | `_PERMANENT_ERRORS` | raise | Medium | 51 |
| `core.tool_registry` | `CancelledError` | raise | Medium | 65 |
| `core.tool_registry` | `Exception` | _logger.exception("Tool %s failed", call.tool_name) | Medium | 69 |
| `core.utils` | `Exception` | pass | Medium | 77 |
| `core.utils` | `Exception` | return len(text) // 4 | Medium | 102 |
| `core.utils` | `ImportError` | tiktoken = None  # type: ignore[assignment] | Medium | 11 |
| `core.utils` | `ImportError` | tokenizers = None  # type: ignore[assignment] | Medium | 16 |
| `core.utils` | `KeyError` | try: | Medium | 74 |
| `core.utils` | `OSError` | return None | Medium | 61 |
| `dev.tests.test_api_deps` | `ImportError` | sqlite3 not available | Medium | 352 |
| `dev.tests.test_api_e2e` | `OSError` | return False | Medium | 533 |
| `dev.tests.test_resilience` | `Exception` | pass  # Acceptable | Medium | 91 |
| `dev.tests.test_resilience` | `Exception` | pass  # Also acceptable if it raises | Medium | 131 |
| `dev.tests.test_resilience` | `OperationalError/PermissionError` | pass  # Expected | Medium | 162 |
| `dev.tests.test_scripts_and_platform` | `ImportError` | Cannot load {...} | Medium | 31 |
| `dev.tests.test_scripts_and_platform` | `ModuleNotFoundError` | pytest.skip("mypy not installed") | Medium | 250 |
| `dev.tests.test_scripts_and_platform` | `ModuleNotFoundError` | pytest.skip("ruff not installed") | Medium | 263 |
| `dev.tests.test_scripts_and_platform` | `ModuleNotFoundError` | pytest.skip("vulture not installed") | Medium | 276 |
| `features.chat.handlers` | `AdapterError` | _logger.warning("LLM unavailable: %s", exc) | Medium | 108 |
| `features.chat.handlers` | `AdapterError` | _logger.warning("LLM unavailable in stream: %s", exc) | Medium | 145 |
| `features.chat.handlers` | `Exception` | _logger.exception("Chat failed") | Medium | 113 |
| `features.chat.handlers` | `Exception` | _logger.exception("Stream failed") | Medium | 153 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI stream failed") | Medium | 234 |
| `features.chat.handlers` | `Exception` | _logger.exception("OpenAI chat failed") | Medium | 253 |
| `features.chat.handlers` | `HTTPException` | raise | Medium | 111 |
| `features.chat.handlers` | `ValueError` | pass | Medium | 76 |
| `features.chat.manager` | `AdapterError` | raise | Medium | 250 |
| `features.chat.manager` | `Exception` | logger.warning( | Medium | 227 |
| `features.chat.manager` | `Exception` | logger.warning("History load failed: %s", exc) | Medium | 245 |
| `features.chat.manager` | `Exception` | logger.error( | Medium | 252 |
| `features.chat.manager` | `Exception` | logger.warning("History save failed: %s", exc) | Medium | 290 |
| `features.chat.manager` | `Exception` | history = ( | Medium | 340 |
| `features.chat.manager` | `Exception` | raise AdapterError(f"LLM stream failed: {exc}") from exc | Medium | 362 |
| `features.chat.manager` | `ValueError/IndexError` | continue | Medium | 52 |
| `features.rag.handlers` | `Exception` | _logger.exception("Auto-save failed") | Medium | 135 |
| `features.rag.handlers` | `Exception` | _logger.exception("Delete chunks failed") | Medium | 190 |
| `features.rag.handlers` | `Exception` | _logger.exception("List namespaces failed") | Medium | 221 |
| `features.rag.handlers` | `Exception` | _logger.exception("Failed to save file") | Medium | 248 |
| `features.rag.handlers` | `Exception` | return { | Medium | 290 |
| `features.rag.handlers` | `Exception` | _logger.exception("Background reindex failed") | Medium | 333 |
| `features.rag.manager` | `Exception` | errors.append(f"Chunking failed for {doc_id}: {e}") | Medium | 56 |
| `features.rag.manager` | `Exception` | errors.append(f"Embedding failed for {doc_id}: {e}") | Medium | 67 |
| `features.rag.manager` | `Exception` | errors.append(f"Vector store add failed: {e}") | Medium | 89 |
| `features.rag.manager` | `Exception` | _logger.debug("RAG health check failed: %s", exc) | Medium | 213 |
| `features.rag.manager` | `ValueError/IndexError` | continue | Medium | 167 |
| `pipeline.steps` | `AdapterError` | _logger.exception("LLM unavailable") | Medium | 275 |
| `pipeline.steps` | `AdapterError` | _logger.exception("LLM unavailable during tool follow-up") | Medium | 321 |
| `pipeline.steps` | `Exception` | _logger.exception("embed_query failed") | Medium | 97 |
| `pipeline.steps` | `Exception` | _logger.exception("retrieve failed") | Medium | 128 |
| `pipeline.steps` | `Exception` | _logger.exception("rerank failed") | Medium | 184 |
| `pipeline.steps` | `Exception` | prompt = _build_fallback_prompt() | Medium | 227 |
| `pipeline.steps` | `Exception` | _logger.exception("generate failed after retries") | Medium | 280 |
| `pipeline.steps` | `Exception` | content = f"Error: {e}" | Medium | 309 |
| `pipeline.steps` | `Exception` | _logger.exception("tool follow-up call failed after retries" | Medium | 325 |
| `dev.tests.test_scripts_and_platform` | `FileNotFoundError` | Config not found: {...} | Low | 298 |

> **Severity:** Critical = startup aborts; High = request fails; Medium = degraded; Low = client error.
