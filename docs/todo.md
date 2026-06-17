Выдай список todo по одной строке в формате: [ ] Название + Краткая суть | Подробное описание (что, зачем, и ⚠️ CORE CHANGE если критично) | Файлы для правки | Файлы тестов / где проверять

===============================================================================
# TODO
===============================================================================

[х] token_margin_min/token_margin_pct в config | Убрать константы `TOKEN_MARGIN_MIN`, `TOKEN_MARGIN_PCT`. Прокидывать через `ChatManager`/`RAGManager`. | `core/config.py`, `core/pipeline_steps.py`, `features/chat/manager.py`, `features/rag/manager.py` | `tests/test_config.py`, `tests/test_pipeline.py` ПЕРЕДАЛАЛИ PipelineConfig — stdlib dataclass в core/domain/pipeline.py — содержит все конфигурационные параметры, которые шаги pipeline читают из metadata. Это даёт типизированный контракт вместо "anything dict".

[ ] Убрать fallbacks из pipeline steps | `metadata["key"]` вместо `metadata.get(key, default)`. `KeyError` → `ConfigurationError`. Обновить все тестовые `metadata` dicts. | `core/pipeline_steps.py` | `tests/test_pipeline.py` — 27 тестов

[ ] Убрать model="gpt-4o" хардкод | `tokenizer_model` из `metadata["tokenizer_model"]`. Прокидывать через `ChatManager`/`RAGManager`. | `core/pipeline_steps.py`, `features/chat/manager.py`, `features/rag/manager.py`, `features/rag/handlers.py` | `tests/test_chat.py`, `tests/test_rag.py`, `tests/test_pipeline.py`

[ ] Перенести max_ctx fallback в адаптеры | `get_context_limit()` возвращает `config.server_context_size or 4096`. Убрать fallback из `pipeline_steps.py`. Обновить `MockLLM`. Переименовать тест `test_max_ctx_none_fallback`. | `adapters/llm_openai_compatible.py`, `adapters/llm_mock.py`, `core/pipeline_steps.py` | `tests/test_adapters.py`, `tests/test_pipeline.py`
