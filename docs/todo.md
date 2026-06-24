==============================================================================
ПРОМПТ ДЛЯ ЗАПРОСА БАГОВ:
==============================================================================

Ты — senior code reviewer. Проанализируй предоставленный код / контекст и выяви ВСЕ проблемы: баги, костыли, техдолг, нарушения best practices, race conditions, утечки, N+1, XSS/SQL-инъекции, неявные сайд-эффекты, deprecated API, copy-paste, мертвый код, неправильные абстракции.
Формат вывода — строго одна строка на проблему, независимые друг от друга:
[ ] Название проблемы (2-5 слов) | Краткая суть (1 предложение, что именно сломано/плохо) | Тип: [BUG / TECHDEBT / SECURITY / PERF / ARCH / COPYPASTE] | Локация: файл(ы) + строки если видны | ⚠️ CRITICAL если ломает прод / данные / безопасность
Правила:
- Не предлагай решения. Только диагностика.
- Не фантазируй: если не уверен — пиши "предположительно" и указывай почему.
- Если проблема повторяется в нескольких местах — каждое место отдельной строкой.
- Приоритет: CRITICAL → BUG → SECURITY → PERF → ARCH → TECHDEBT → COPYPASTE.
- Если контекста недостаточно для точной локации — укажи "локация неизвестна, требуется уточнение".

==============================================================================
ПРОМПТ ДЛЯ РЕШЕНИЯ БАГА:
==============================================================================

Ты — senior software engineer. Рассмотри проблему детально.
Проблема: [ ]
Твоя задача:
1. Запроси у меня необходимые файлы для анализа (основной код, тесты, конфиги, схемы БД, API-спеки — всё, что нужно для точной диагностики). Не начинай решение пока не получишь файлы.
2. После получения файлов — детальный root cause analysis: почему это работает неправильно / почему это костыль, какие цепочки вызовов затронуты, какие edge cases сломаны.
3. Предложи 2-3 варианта исправления с trade-offs (простой vs правильный vs быстрый).
4. Для выбранного варианта — конкретные правки: что менять, в каких файлах, на каких строках (если известны). Укажи "⚠️ CORE CHANGE" если требует изменения контрактов, миграций, API или ломает обратную совместимость.
5. Тесты: что добавить / изменить / удалить. Укажи файлы тестов. Покрытие edge cases.
6. Проверка: как вручную проверить фикс (шаги), какие логи / метрики / assert'ы должны сработать.
7. Риски отката: что может сломаться, какие системы затронуты.
8. Будь краток, но ответы должны быть четкими.
Формат ответа:
- Сначала список запрашиваемых файлов (буллетами).
- После моего ответа с файлами — полный разбор по пунктам 2-7.

==============================================================================
ПРОМПТ ДЛЯ ПРОВЕРКИ ФИКСА:
==============================================================================

Проведи прогнозный аудит внесённых изменений. Ответь строго по 5 пунктам:
1. Техдолг от фикса
   - Какие компромиссы внесены? Что придётся переделать при масштабировании?
2. Регрессии и скрытые баги
   - Что может сломаться от этих правок через N месяцев / при росте нагрузки / новых фичах?
3. Архитектурные ловушки
   - Усилили ли мы антипаттерн? Стал ли код менее расширяемым? Какие фичи теперь сложнее добавить?
4. Тестовые дыры
   - Какие сценарии всё ещё не покрыты? Что не протестировано, но реалистично сломается?
5. Мониторинг и алерты
   - Что нужно отслеживать в проде, чтобы поймать деградацию раньше пользователей? Какие метрики / логи / алерты добавить?
Итог: [OK / NIT / WARNING] — можно ли мержить, или есть блокер для будущего.

==============================================================================
## TODO ##
==============================================================================

[+] rag_state.tasks race — RAGState.status dict модифицируется без синхронизации, конкурентные reindex-запросы могут потерять задачи или оставить zombie entries.
[+] close() vs active requests — shutdown() закрывает httpx.AsyncClient, но complete()/stream()/embed() не проверяют состояние клиента перед использованием, возможен race при graceful shutdown.
[ ] lost-update save() — delete() меняет индекс в памяти, но save() не вызывается автоматически; при краше между delete() и явным save() диск содержит stale данные, а память — новые.



[ ] Глобальное состояние API-ключа не работает в multiprocess | `_override_api_key` с `threading.Lock()` работает только внутри одного процесса. При `uvicorn --workers 4` или gunicorn каждый worker имеет свой `_override_api_key`. Runtime rotation работает непредсказуемо. Нужно: добавить `logger.warning` при `workers > 1` в `lifespan.py` или документировать ограничение в `docs/drift.md`. | `src/ai_assistant/api/security.py`, `src/ai_assistant/api/lifespan.py` | `tests/test_api.py`

[ ] Метрики открыты без авторизации | `/metrics` и `/metrics/json` доступны без API key. Утечка: нагрузка, количество запросов, внутренние характеристики. Нужно: добавить `security.metrics_require_auth: bool` (default: false для backward compat) в `SecurityConfig` и обернуть `_metrics_router` в `router.py` условным `Depends(require_api_key)`. ⚠️ CORE CHANGE: новое поле в `SecurityConfig` требует `config_version` bump + backward compat loader. | `src/ai_assistant/api/router.py`, `src/ai_assistant/core/config.py` | `tests/test_api.py`, `curl localhost:8000/metrics`

[ ] Хардкод `CHUNK_SIZE = 100_000` в `indexing.py` | Один документ может съесть память и вызвать скачки токенов. Не соответствует `config.yaml` (`chunk_size: 512`). Нужно: вынести в `RAGConfig` или использовать `chunker` config. | `src/ai_assistant/features/rag/indexing.py`, `src/ai_assistant/core/config.py` | `tests/test_rag.py`, `tests/test_integration.py`

[ ] `hasattr()` в `security.py` нарушает правила проекта | Правило Section 2: "Never: `hasattr()` / `isinstance()` on port objects in production code". `credentials` — не port object, но нарушает дух правил. Нужно: заменить `if not credentials or not hasattr(credentials, "credentials"):` на `if credentials is None:` (HTTPAuthorizationCredentials всегда имеет поле `credentials`). | `src/ai_assistant/api/security.py` | `tests/test_api.py`

[ ] Массовое подавление исключений — скрытые ошибки | Много `except Exception:` в `features/chat/*`, `features/rag/*`, `core/pipeline_steps.py`. Permanent errors (ValueError, TypeError) тоже ловятся. Трудности диагностики, возможное повреждение данных. Нужно: добавить re-raise для `_PERMANENT_ERRORS` как в `retry.py`, или использовать специфичные исключения. | `src/ai_assistant/features/chat/handlers.py`, `src/ai_assistant/features/rag/handlers.py`, `src/ai_assistant/core/pipeline_steps.py` | `tests/test_chat.py`, `tests/test_rag.py`, `tests/test_pipeline.py`

[ ] SQLite без graceful shutdown — возможна потеря WAL | `lifespan.py` вызывает `adapter.shutdown()` для storage, но `SQLiteStorage.shutdown()` не реализован (только `IClosable` default no-op). WAL-файлы (`*.db-wal`, `*.db-shm`) могут остаться несинхронизированными. Нужно: добавить `PRAGMA wal_checkpoint(TRUNCATE)` и `connection.close()` в `shutdown()`. | `src/ai_assistant/adapters/storage_sqlite.py` | `tests/test_stateful_ports.py`

[ ] Нет проверки namespace на path traversal | `save_chat` использует `namespace` для построения пути. Есть `is_relative_to`, но нет валидации самого `namespace` (может быть `../etc`). Нужно: добавить `pattern=r"^[a-z]+$"` как в `SaveChatRequest` для `namespace` в API endpoint. | `src/ai_assistant/features/rag/handlers.py` | `tests/test_rag.py`

[ ] `RAGState.status` — неограниченный рост памяти | `cleanup_status()` вызывается только в `_run()` reindex. Без периодической уборки — утечка памяти при частых reindex-запросах. Нужно: добавить вызов `cleanup_status()` при каждом новом task или по таймеру. | `src/ai_assistant/features/rag/handlers.py`, `src/ai_assistant/api/deps.py` | `tests/test_rag.py`, мониторинг памяти

[ ] Хардкод лимита стриминга `max_tokens * 2` | `llm_openai_compatible.py` обрывает стрим после `max_tokens * 2`. Пользователь не понимает почему LLM "заткнулся". Нужно: вынести множитель или абсолютный лимит в `LLMConfig`. ⚠️ CORE CHANGE: новое поле в `LLMConfigData` требует обновления порта + всех адаптеров. | `src/ai_assistant/adapters/llm_openai_compatible.py`, `src/ai_assistant/core/config.py` | `tests/test_resilience.py`, `tests/test_api.py`

[ ] Fail-fast для шаблонов промптов — опечатка = низкое качество | В `pipeline_steps.py` ошибка `get_prompt` приводит к `_build_fallback_prompt`. Опечатка в имени шаблона → низкое качество ответов, пользователь не поймёт почему. Нужно: добавить `strict_prompt_loading: bool` в конфиг: при `True` — прокидывать исключение, при `False` — fallback. ⚠️ CORE CHANGE: новое поле в `RAGConfig` требует `config_version` bump. | `src/ai_assistant/core/pipeline_steps.py`, `src/ai_assistant/core/config.py` | `tests/test_pipeline.py`, `tests/test_prompts.py`

[ ] `scripts/kill.py` парсит неверный путь к порту | Ищет `data.get("api", {}).get("port")`, но `port` в корне `config.yaml`. Нужно: исправить на `data.get("port", 8000)`. | `scripts/kill.py` | Ручной запуск: `python scripts/kill.py` при нестандартном порту

[ ] Мертвое поле `security.allowed_hosts` — ложное чувство безопасности | Парсится Pydantic, но нигде не используется. Нужно: либо добавить `TrustedHostMiddleware`, либо удалить поле из `SecurityConfig`. ⚠️ CORE CHANGE: удаление поля из конфига требует backward compat loader + `deprecated=True`. | `src/ai_assistant/core/config.py`, `src/ai_assistant/api/middleware.py` (если добавлять) | `tests/test_config.py`

[ ] Мертвая константа `DOCUMENTS_ROOT` | `Path("sources")` в `core/constants.py` нигде не импортируется. В `indexing.py` используется параметр `documents_root`. Нужно: удалить чтобы не путать. | `src/ai_assistant/core/constants.py` | `tests/test_domain.py`, `tests/test_smoke.py`

[ ] Мертвый `core/ports/tools.py` — обещание без реализации | `ITool`, `IToolRegistry`, `ToolCall`, `ToolResult` нигде не используются в production. Нужно: либо интегрировать в `llm_openai_compatible.py`, либо удалить. | `src/ai_assistant/core/ports/tools.py`, `src/ai_assistant/adapters/llm_openai_compatible.py` | `tests/test_domain.py`, `tests/test_smoke.py`

[ ] Дублирование логики stream/non-stream в chat handlers | `chat_stream`, `openai_chat_completions` со stream и обычный ответ — частично повторяющаяся логика. Исправляешь баг в одной ветке — забываешь про вторую. Нужно: вынести общую часть. | `src/ai_assistant/features/chat/handlers.py` | `tests/test_api.py`, `tests/test_chat.py`

[ ] Неактуальный `docs/drift.md` — #13, #14, #15 помечены как активные | `#13 source_uri` уже в `ChunkMetadata`, `#14 RAGState.status` уже `dict[str, dict[str, object]]`, `#15 query_embedding` удалён из `_required_fields_for_steps`. Нужно: убрать из активных или пометить `Fixed`. | `docs/drift.md` | Ручная проверка: `git diff docs/drift.md`

[ ] Неактуальный `docs/future.md` — Prometheus помечен как `research` | `core/metrics.py` уже реализует Prometheus exposition format. Блокер `Needs prometheus_client` устарел. Нужно: обновить статус. | `docs/future.md` | Ручная проверка: `curl localhost:8000/metrics`

[ ] Незадокументированный drift: non-stdlib в `core/` | Jinja2 (`core/prompts`), pydantic+yaml (`core/config`), tiktoken+tokenizers (`core/utils`) — все в `core/` при запрете non-stdlib. Только Jinja2 упомянут в drift #11. Нужно: дополнить список grandfathered exceptions. | `docs/drift.md` | Ручная проверка: `grep -c 'Jinja2\|pydantic\|yaml\|tiktoken' src/ai_assistant/core/*.py`

[ ] Незадокументированный drift: `print()` и `logging.basicConfig()` в скриптах | Правило 2 запрещает, но `scripts/` и `run_servers.py` используют. Нужно: добавить grandfathered exception для `scripts/` или заменить на `get_logger`. | `docs/drift.md`, `scripts/*.py`, `run_servers.py` | `tests/test_smoke.py`, `grep -r 'print(\|logging.basicConfig' scripts/ run_servers.py`

[ ] Кириллица в `rag_strict.j2` — нарушение правила 9 | `"У меня недостаточно информации."` в шаблоне. Правило 9: "No Cyrillic in code/comments/docstrings (domain constants exempt)". Шаблон — не domain constant. Нужно: либо перевести, либо добавить `.j2` в проверку, либо зафиксировать drift. | `src/ai_assistant/core/prompts/v1/rag_strict.j2`, `tests/test_smoke.py`, `docs/drift.md` | `tests/test_smoke.py`
