Выдай список по одной строке в формате, все задания независимы друг от друга: [ ] Название + Краткая суть | Подробное описание (что, зачем, и ⚠️ CORE CHANGE если критично) | Список файлов для правок, без фантазии | Файлы тестов / где проверять.

==============================================================================
# TODO
=========================================================================
[+] OpenAI-роуты без авторизации | `/v1/chat/completions` и `/v1/models` доступны без API key. Любой клиент (Page Assist, Continue.dev) может использовать сервер, но это означает и любой неавторизованный доступ. Добавить опциональный `require_api_key` через конфиг `security.openai_routes_require_auth: bool` (default: false для backward compat) или документировать риск явно. | `src/ai_assistant/api/router.py`, `src/ai_assistant/core/config.py` , src/ai_assistant/main.py| `tests/test_api.py`

[+] Admin API защищён тем же ключом, что и пользовательский | `POST /admin/api-key` позволяет сменить ключ любому, у кого есть обычный API key. Нет разделения ролей. Либо ввести отдельный `admin_api_key` в `SecurityConfig`, либо убрать admin endpoint из production, либо добавить IP-based restriction. | `src/ai_assistant/api/admin.py`, `src/ai_assistant/api/security.py`, `src/ai_assistant/core/config.py` | `tests/test_api.py`

[+] Потеря данных при shutdown — ошибка сохранения индекса подавляется | В `lifespan.py` `except Exception: logger.exception("Index save failed")` молча глотает ошибку записи на диск. После `kill -9` или OOM индекс может остаться в несогласованном состоянии. Добавить retry с экспоненциальным backoff, и при фатальной ошибке — non-zero exit code или явный статус "degraded". | `src/ai_assistant/api/lifespan.py` | `tests/test_api.py`, ручной тест: `kill -9` → старт → проверить индекс

[+] Повреждённый индекс при старте — молчаливая загрузка | `lifespan.py` логирует ошибку загрузки индекса и продолжает старт. RAG работает с пустым/битым индексом, пользователь не понимает почему ответы пустые. Добавить проверку целостности: сравнить количество векторов в FAISS с количеством записей в метаданных. При несоответствии — fail-fast с clear error message или автоочистка с логированием. | `src/ai_assistant/api/lifespan.py`, `src/ai_assistant/adapters/vector_store_faiss.py`, `src/ai_assistant/adapters/vector_store_memory.py` | `tests/test_adapters.py`

[ ] Утечка абсолютных путей в RAG-индексе | `indexing.py` сохраняет `source_uri = Path(abs_path).as_uri()` в `ChunkMetadata`. Это `/home/user/...` или `C:\Users\Admin\...`. Если metadata возвращается в API — утечка инфраструктуры. Заменить на относительный путь от `documents_root` или `chat_exports_root`. | `src/ai_assistant/features/rag/indexing.py`, `src/ai_assistant/core/domain/documents.py` | `tests/test_rag.py`, `tests/test_integration.py`

[ ] Чат-экспорты попадают в RAG-индекс документов | `rag.chat_exports_root` и `rag.documents_root` оба по умолчанию `"sources"`. `/save-chat` пишет в ту же папку, откуда `index_documents` читает. Контекст чатов становится источником для RAG — утечка контекста, мусор в ответах. Изменить `chat_exports_root` на `"chat_exports"` по умолчанию. | `src/ai_assistant/core/config.py`, `config.yaml` | `tests/test_rag.py`

[ ] Нет ограничения размера входного сообщения LLM — body size захардкожен | `security.py` использует `SECURITY_MAX_BODY = 10_485_760` вместо `config.security.max_body_size`. 10MB JSON может содержать 2.5M токенов — OOM или DDOS. Использовать `config.security.max_body_size` в `check_request_size()`. Дополнительно: добавить проверку длины `content` в `ChatRequest`/`OAIChatCompletionRequest` на уровне Pydantic validator. | `src/ai_assistant/api/security.py`, `src/ai_assistant/features/chat/schemas.py`, `src/ai_assistant/features/rag/schemas.py` | `tests/test_api.py`

[ ] Нет аудита административных операций | `admin.py` вызывает `set_api_key()` без логирования security event. После компрометации невозможно установить кто, когда и какой ключ установил. Добавить `logger.warning("Security event: API key changed", extra={"source": "admin_endpoint"})` с явным маркером. | `src/ai_assistant/api/admin.py` | `tests/test_api.py`, ручная проверка логов

[ ] Глобальное состояние API-ключа не работает в multiprocess | `_override_api_key` с `threading.Lock()` работает только внутри одного процесса. При `uvicorn --workers 4` или gunicorn — каждый worker имеет свой `_override_api_key`. Runtime rotation работает непредсказуемо. Документировать ограничение или добавить warning при `workers > 1`. | `src/ai_assistant/api/security.py` | `tests/test_api.py`

[ ] Метрики открыты без авторизации | `/metrics` и `/metrics/json` доступны без API key. Утечка: нагрузка, количество запросов, внутренние характеристики. Добавить `security.metrics_require_auth: bool` (default: false для backward compat) или документировать риск. | `src/ai_assistant/api/router.py`, `src/ai_assistant/core/config.py` | `tests/test_api.py`, `curl localhost:8000/metrics`

[ ] Хардкод `CHUNK_SIZE = 100_000` в `indexing.py` | Один документ может съесть память и вызвать скачки токенов. Не соответствует `config.yaml` (`chunk_size: 512`). Вынести в `RAGConfig` или использовать `chunker` config. | `src/ai_assistant/features/rag/indexing.py`, `src/ai_assistant/core/config.py` | `tests/test_rag.py`, `tests/test_integration.py`

[ ] `hasattr()` в `security.py` нарушает правила проекта | Правило Section 2: "Never: `hasattr()` / `isinstance()` on port objects in production code". `credentials` — не port object, но нарушает дух правил. Заменить на явную проверку `if credentials is None:` (HTTPAuthorizationCredentials всегда имеет поле `credentials`). | `src/ai_assistant/api/security.py` | `tests/test_api.py`

[ ] Массовое подавление исключений — скрытые ошибки | Много `except Exception:` в `features/chat/*`, `features/rag/*`, `core/pipeline_steps.py`. Permanent errors (ValueError, TypeError) тоже ловятся. Трудности диагностики, возможное повреждение данных. Добавить re-raise для `_PERMANENT_ERRORS` как в `retry.py`, или использовать специфичные исключения. | `src/ai_assistant/features/chat/handlers.py`, `src/ai_assistant/features/rag/handlers.py`, `src/ai_assistant/core/pipeline_steps.py` | `tests/test_chat.py`, `tests/test_rag.py`, `tests/test_pipeline.py`

[ ] SQLite без graceful shutdown — возможна потеря WAL | `lifespan.py` вызывает `adapter.shutdown()` для storage, но `SQLiteStorage.shutdown()` не реализован (только `IClosable` default no-op). WAL-файлы (`*.db-wal`, `*.db-shm`) могут остаться несинхронизированными. Добавить `PRAGMA wal_checkpoint(TRUNCATE)` и `connection.close()` в `shutdown()`. | `src/ai_assistant/adapters/storage_sqlite.py` | `tests/test_stateful_ports.py`

[ ] Нет проверки namespace на path traversal | `save_chat` использует `namespace` для построения пути. Есть `is_relative_to`, но нет валидации самого `namespace` (может быть `../etc`). Добавить `pattern=r"^[a-z]+$"` как в `SaveChatRequest` для `namespace` в API endpoint. | `src/ai_assistant/features/rag/handlers.py` | `tests/test_rag.py`

[ ] `RAGState.status` — неограниченный рост памяти | `cleanup_status()` вызывается только в `_run()` reindex. Без периодической уборки — утечка памяти при частых reindex-запросах. Добавить вызов `cleanup_status()` при каждом новом task или по таймеру. | `src/ai_assistant/features/rag/handlers.py`, `src/ai_assistant/api/deps.py` | `tests/test_rag.py`, мониторинг памяти

[ ] Хардкод лимита стриминга `max_tokens * 2` | `llm_openai_compatible.py` обрывает стрим после `max_tokens * 2`. Пользователь не понимает почему LLM "заткнулся". Вынести множитель или абсолютный лимит в `LLMConfig`. | `src/ai_assistant/adapters/llm_openai_compatible.py`, `src/ai_assistant/core/config.py` | `tests/test_resilience.py`, `tests/test_api.py`

[ ] Fail-fast для шаблонов промптов — опечатка = низкое качество | В `pipeline_steps.py` ошибка `get_prompt` приводит к `_build_fallback_prompt`. Опечатка в имени шаблона → низкое качество ответов, пользователь не поймёт почему. Добавить `strict_prompt_loading: bool` в конфиг: при `True` — прокидывать исключение, при `False` — fallback. | `src/ai_assistant/core/pipeline_steps.py`, `src/ai_assistant/core/config.py` | `tests/test_pipeline.py`, `tests/test_prompts.py`

[ ] `scripts/kill.py` парсит неверный путь к порту | Ищет `data.get("api", {}).get("port")`, но `port` в корне `config.yaml`. Исправить на `data.get("port", 8000)`. | `scripts/kill.py` | Ручной запуск: `python scripts/kill.py` при нестандартном порту

[ ] Мертвое поле `security.allowed_hosts` — ложное чувство безопасности | Парсится Pydantic, но нигде не используется. Либо добавить `TrustedHostMiddleware`, либо удалить поле из `SecurityConfig`. | `src/ai_assistant/core/config.py`, `src/ai_assistant/api/middleware.py` (если добавлять) | `tests/test_config.py`

[ ] Мертвая константа `DOCUMENTS_ROOT` | `Path("sources")` в `core/constants.py` нигде не импортируется. В `indexing.py` используется параметр `documents_root`. Удалить чтобы не путать. | `src/ai_assistant/core/constants.py` | `tests/test_domain.py`, `tests/test_smoke.py`

[ ] Мертвый `core/ports/tools.py` — обещание без реализации | `ITool`, `IToolRegistry`, `ToolCall`, `ToolResult` нигде не используются в production. Либо интегрировать в `llm_openai_compatible.py`, либо удалить. | `src/ai_assistant/core/ports/tools.py`, `src/ai_assistant/adapters/llm_openai_compatible.py` | `tests/test_domain.py`, `tests/test_smoke.py`

[ ] Дублирование логики stream/non-stream в chat handlers | `chat_stream`, `openai_chat_completions` со stream и обычный ответ — частично повторяющаяся логика. Исправляешь баг в одной ветке — забываешь про вторую. Вынести общую часть. | `src/ai_assistant/features/chat/handlers.py` | `tests/test_api.py`, `tests/test_chat.py`

[ ] Неактуальный `docs/drift.md` — #13, #14, #15 помечены как активные | `#13 source_uri` уже в `ChunkMetadata`, `#14 RAGState.status` уже `dict[str, dict[str, object]]`, `#15 query_embedding` удалён из `_required_fields_for_steps`. Убрать из активных или пометить `Fixed`. | `docs/drift.md` | Ручная проверка: `git diff docs/drift.md`

[ ] Неактуальный `docs/future.md` — Prometheus помечен как `research` | `core/metrics.py` уже реализует Prometheus exposition format. Блокер `Needs prometheus_client` устарел. | `docs/future.md` | Ручная проверка: `curl localhost:8000/metrics`

[ ] Незадокументированный drift: non-stdlib в `core/` | Jinja2 (`core/prompts`), pydantic+yaml (`core/config`), tiktoken+tokenizers (`core/utils`) — все в `core/` при запрете non-stdlib. Только Jinja2 упомянут в drift #11. Дополнить список grandfathered exceptions. | `docs/drift.md` | Ручная проверка: `grep -c 'Jinja2\|pydantic\|yaml\|tiktoken' src/ai_assistant/core/*.py`

[ ] Незадокументированный drift: `print()` и `logging.basicConfig()` в скриптах | Правило 2 запрещает, но `scripts/` и `run_servers.py` используют. Добавить grandfathered exception для `scripts/` или заменить на `get_logger`. | `docs/drift.md`, `scripts/*.py`, `run_servers.py` | `tests/test_smoke.py`, `grep -r 'print(\|logging.basicConfig' scripts/ run_servers.py`

[ ] Кириллица в `rag_strict.j2` — нарушение правила 9 | `"У меня недостаточно информации."` в шаблоне. Правило 9: "No Cyrillic in code/comments/docstrings (domain constants exempt)". Шаблон — не domain constant. Либо перевести, либо добавить `.j2` в проверку, либо зафиксировать drift. | `src/ai_assistant/core/prompts/v1/rag_strict.j2`, `tests/test_smoke.py`, `docs/drift.md` | `tests/test_smoke.py`

[ ] Опечатки в `docs/ai_rules.md` | Артефакты: `onl y`, `pi peline`, `configu ration`, `i nitialization`, `feat ures/`. Лишние пробелы внутри слов. | `docs/ai_rules.md` | Ручная проверка: `grep -E 'onl y|pi peline|configu ration|i nitialization|feat ures/' docs/ai_rules.md` → пусто

---

## Что НЕ входит в план (отложено навсегда или до появления боли)

| Задача | Почему отложена |
|---|---|
| Заменить самописный metrics на `prometheus_client` | Работает. 120 строк кода не горят. |
| Упростить `RAGState` (semaphore, lock, cleanup) | Работает. Переинженеринг, но не баг. |
| Удалить лишние поля из `PipelineData` | 13 полей — много, но не ломает. |
| Упростить Jinja2 prompt loader | 4 шаблона, кэш не нужен, но работает. |
| Кэшировать повторные вычисления токенов | Без профиля неясно, является ли это узким местом. |
| Добавить проверку использования всех полей конфигурации | Требует deprecation политики. Не блокер. |
| Архитектурные тесты (AST, `except Exception`, соответствие rules) | Требует CI. Сейчас нет `.github/workflows/`. |
| Исправить `run_servers.py`: читать порты из конфига | Скрипт convenience, не критичен для продакшена. |
| Исправить `README.md`: документировать `vendor/` | Документация. Не ломает работу. |
| Исправить `[tool.mutmut]` в `pyproject.toml` | Mutmut не в CI. Не ломает работу. |

