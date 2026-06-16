Выдай список todo по одной строке в формате: [ ] Название + Краткая суть | Подробное описание (что, зачем, и ⚠️ CORE CHANGE если критично) | Файлы для правки | Файлы тестов / где проверять

===============================================================================
# TODO
===============================================================================

[х] SQLite WAL mode | `PRAGMA journal_mode=WAL` при `init_db()`. Одна строка, нет зависимостей. | `adapters/storage_sqlite.py`, `.gitignore` | `tests/test_adapters.py`

[х] stop_sequences фильтрация | `payload["stop"] = [s for s in stop_sequences if s]`. Одна строка, чистый багфикс. | `adapters/llm_openai_compatible.py` | `tests/test_adapters.py`

[ ] Log rotation config | `logging.max_bytes`, `logging.backup_count` в `LoggingConfig`. Изолировано, не трогает pipeline. | `core/config.py`, `core/logger.py` | `tests/test_config.py`, `tests/test_smoke.py`

[ ] connect_timeout в config | `LLMConfig`/`EmbedderConfig` + `httpx.AsyncClient`. Два адаптера, одинаковая логика. | `core/config.py`, `adapters/llm_openai_compatible.py`, `adapters/embedder_openai_compatible.py` | `tests/test_adapters.py`, `tests/test_integration.py`

[ ] documents_root в config | `RAGConfig` + разделение `CHAT_EXPORTS_ROOT`. | `core/config.py`, `core/constants.py`, `features/rag/handlers.py`, `scripts/index_documents.py` | `tests/test_rag.py`, `tests/test_e2e.py`

[ ] token_margin_min/token_margin_pct в config | Убрать константы `TOKEN_MARGIN_MIN`, `TOKEN_MARGIN_PCT`. Прокидывать через `ChatManager`/`RAGManager`. | `core/config.py`, `core/pipeline_steps.py`, `features/chat/manager.py`, `features/rag/manager.py` | `tests/test_config.py`, `tests/test_pipeline.py`

[ ] Убрать fallbacks из pipeline steps | `metadata["key"]` вместо `metadata.get(key, default)`. `KeyError` → `ConfigurationError`. Обновить все тестовые `metadata` dicts. | `core/pipeline_steps.py` | `tests/test_pipeline.py` — 27 тестов

[ ] Убрать model="gpt-4o" хардкод | `tokenizer_model` из `metadata["tokenizer_model"]`. Прокидывать через `ChatManager`/`RAGManager`. | `core/pipeline_steps.py`, `features/chat/manager.py`, `features/rag/manager.py`, `features/rag/handlers.py` | `tests/test_chat.py`, `tests/test_rag.py`, `tests/test_pipeline.py`

[ ] Перенести max_ctx fallback в адаптеры | `get_context_limit()` возвращает `config.server_context_size or 4096`. Убрать fallback из `pipeline_steps.py`. Обновить `MockLLM`. Переименовать тест `test_max_ctx_none_fallback`. | `adapters/llm_openai_compatible.py`, `adapters/llm_mock.py`, `core/pipeline_steps.py` | `tests/test_adapters.py`, `tests/test_pipeline.py`
