==============================================================================
ПРОМПТ ДЛЯ ЗАПРОСА БАГОВ:
==============================================================================
Ты — архитектор на 30 лет. Найди проблемы, которые сломают проект через 5+ лет, каждый пункт независимый — одна строка, понятен без контекста. Формат вывода:[ ] Название | Последствие | Файл | Проверка |.


==============================================================================
## TODO ##
==============================================================================
[ ] SQLite без graceful shutdown — возможна потеря WAL | `lifespan.py` вызывает `adapter.shutdown()` для storage, но `SQLiteStorage.shutdown()` не реализован (только `IClosable` default no-op). WAL-файлы (`*.db-wal`, `*.db-shm`) могут остаться несинхронизированными. Нужно: добавить `PRAGMA wal_checkpoint(TRUNCATE)` и `connection.close()` в `shutdown()`. | `src/ai_assistant/adapters/storage_sqlite.py` | `tests/test_stateful_ports.py`

[ ] Нет проверки namespace на path traversal | `save_chat` использует `namespace` для построения пути. Есть `is_relative_to`, но нет валидации самого `namespace` (может быть `../etc`). Нужно: добавить `pattern=r"^[a-z]+$"` как в `SaveChatRequest` для `namespace` в API endpoint. | `src/ai_assistant/features/rag/handlers.py` | `tests/test_rag.py`

[ ] Массовое подавление исключений — скрытые ошибки | Много `except Exception:` в `features/chat/*`, `features/rag/*`, `core/pipeline_steps.py`. Permanent errors (ValueError, TypeError) тоже ловятся. Трудности диагностики, возможное повреждение данных. Нужно: добавить re-raise для `_PERMANENT_ERRORS` как в `retry.py`, или использовать специфичные исключения. | `src/ai_assistant/features/chat/handlers.py`, `src/ai_assistant/features/rag/handlers.py`, `src/ai_assistant/core/pipeline_steps.py` | `tests/test_chat.py`, `tests/test_rag.py`, `tests/test_pipeline.py`

[ ] Хардкод лимита стриминга `max_tokens * 2` | `llm_openai_compatible.py` обрывает стрим после `max_tokens * 2`. Пользователь не понимает почему LLM "заткнулся". Нужно: вынести множитель или абсолютный лимит в `LLMConfig`. ⚠️ CORE CHANGE: новое поле в `LLMConfigData` требует обновления порта + всех адаптеров. | `src/ai_assistant/adapters/llm_openai_compatible.py`, `src/ai_assistant/core/config.py` | `tests/test_resilience.py`, `tests/test_api.py`

[ ] Fail-fast для шаблонов промптов — опечатка = низкое качество | В `pipeline_steps.py` ошибка `get_prompt` приводит к `_build_fallback_prompt`. Опечатка в имени шаблона → низкое качество ответов, пользователь не поймёт почему. Нужно: добавить `strict_prompt_loading: bool` в конфиг: при `True` — прокидывать исключение, при `False` — fallback. ⚠️ CORE CHANGE: новое поле в `RAGConfig` требует `config_version` bump. | `src/ai_assistant/core/pipeline_steps.py`, `src/ai_assistant/core/config.py` | `tests/test_pipeline.py`, `tests/test_prompts.py`

[ ] Дублирование логики stream/non-stream в chat handlers | `chat_stream`, `openai_chat_completions` со stream и обычный ответ — частично повторяющаяся логика. Исправляешь баг в одной ветке — забываешь про вторую. Нужно: вынести общую часть. | `src/ai_assistant/features/chat/handlers.py` | `tests/test_api.py`, `tests/test_chat.py`

[ ] Мертвое поле `security.allowed_hosts` — ложное чувство безопасности | Парсится Pydantic, но нигде не используется. Нужно: либо добавить `TrustedHostMiddleware`, либо удалить поле из `SecurityConfig`. ⚠️ CORE CHANGE: удаление поля из конфига требует backward compat loader + `deprecated=True`. | `src/ai_assistant/core/config.py`, `src/ai_assistant/api/middleware.py` (если добавлять) | `tests/test_config.py`

[ ] Мертвый `core/ports/tools.py` — обещание без реализации | `ITool`, `IToolRegistry`, `ToolCall`, `ToolResult` нигде не используются в production. Нужно: либо интегрировать в `llm_openai_compatible.py`, либо удалить. | `src/ai_assistant/core/ports/tools.py`, `src/ai_assistant/adapters/llm_openai_compatible.py` | `tests/test_domain.py`, `tests/test_smoke.py`

[ ] Незадокументированный drift: `print()` и `logging.basicConfig()` в скриптах | Правило 2 запрещает, но `scripts/` и `run_servers.py` используют. Нужно: добавить grandfathered exception для `scripts/` или заменить на `get_logger`. | `docs/drift.md`, `scripts/*.py`, `run_servers.py` | `tests/test_smoke.py`, `grep -r 'print(\|logging.basicConfig' scripts/ run_servers.py`

[ ] Метрики открыты без авторизации | `/metrics` и `/metrics/json` доступны без API key. Утечка: нагрузка, количество запросов, внутренние характеристики. Нужно: добавить `security.metrics_require_auth: bool` (default: false для backward compat) в `SecurityConfig` и обернуть `_metrics_router` в `router.py` условным `Depends(require_api_key)`. ⚠️ CORE CHANGE: новое поле в `SecurityConfig` требует `config_version` bump + backward compat loader. | `src/ai_assistant/api/router.py`, `src/ai_assistant/core/config.py` | `tests/test_api.py`, `curl localhost:8000/metrics`
