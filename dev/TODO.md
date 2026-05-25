# TODO — AI Assistant (10-year solo project)
-----

Контекст: {вставляешь context_build_compact.md целиком}

Задача из TODO: {}

Требования:
1. Выдай ПОЛНЫЙ текст каждого изменённого файла — diff не принимаю, мне нужно копировать целиком.
2. Если изменение затрагивает скрытые файлы (P2 в контексте), запроси их через REQUEST CODE перед правкой.
3. Укажи ВСЕ файлы, которые нужно обновить вместе с этим изменением (тесты, зависимые импорты, config).
4. Не предлагай оверинжиниринг. Только то, что в пункте TODO.
5. После кода — краткое пояснение, что изменилось и почему.
6. ⚠️ КОНТЕКСТ ЧАТА ОГРАНИЧЕН — если диалог длинный или сложный, предупреи об окончании контекста и выдай краткий пересказ для нового чата. Формат пересказа:

    Задача: {что делали}
    Решение: {что решили}
    Открытые вопросы: {что не закрыли}
    Файлы в работе: {какие файлы изменяли}
    Следующий шаг: {что делать дальше}

-----
## Фаза 0: Быстрая гигиена (1–2 дня)
- [ ] `pyproject.toml` — ruff: добавить B, SIM, C4, TCH; ignore E501
- [ ] `pyproject.toml` — заморозить мажорные версий (`fastapi>=0.110.0,<1.0.0`, `pydantic>=2.7.0,<3.0.0`, и т.д.)
- [ ] Создать `dev/scripts/pre_commit_check.py` (~50 строк) — блокировать коммит если: `hasattr()` в `adapters/`, `**kwargs` в `core/ports/`, импорты `features.X → features.Y`, мутации `PipelineData`
- [ ] GitHub Actions CI (или аналог): checkout → python 3.13 → pip install → pytest -m 'not online' → ruff check

## Фаза 1: Sacred Core защита (1 неделя)
- [ ] `core/domain/pipeline.py` — `@dataclass(frozen=True, slots=True)`. Удалить `rebuild_context()`. Добавить `with_chunks()`, `with_context()`, `with_response()`, `add_error()` через `replace()`
- [ ] `core/config.py` — `LLMConfig`: оставить только generic поля (`provider`, `model`, `max_tokens`, `temperature`, `timeout`, `stop_sequences`). Все llama.cpp-специфичные (`n_gpu_layers`, `flash_attn`, `mmap`, `split_mode`, `cache_type_k`, `yarn_ext_factor`, `draft_model`) перенести в `extra: dict[str, Any]`. Адаптеры читают `config.extra.get(...)`
- [ ] `api/deps.py` — заменить лямбды в `_build_step_funcs` на классы `EmbedQueryStep`, `RetrieveStep`, `RerankStep`, `GenerateStep` с `async def __call__(self, data)`
- [ ] `dev/tests/test_core_critical.py` — тест: `PipelineData` immutable (попытка мутации падает)
- [ ] `dev/tests/test_contracts.py` — тест: фича не импортирует другую фичу напрямую (AST-проверка)
- [ ] `dev/tests/test_contracts.py` — тест: адаптеры реализуют порты без лишних `**kwargs`
- [ ] Аудит `adapters/` — найти и выпилить `hasattr()`, `isinstance` с конкретными классами, все `# TECH DEBT`
- [ ] Аудит `features/` — найти и выпилить прямые импорты других фич

## Фаза 2: API и Feature гигиена (1 неделя)
- [ ] `api/router.py` + `main.py` — перенести кастомные endpoints под `/api/v1/` (`/api/v1/chat`, `/api/v1/rag/*`, `/api/v1/image/*`, `/api/v1/admin/*`). OpenAI-compatible (`/v1/*`) оставить как есть
- [ ] `features/rag/handlers.py` — разбить на `indexing_handlers.py`, `query_handlers.py`, `admin_handlers.py`
- [ ] `features/rag/handlers.py` — убрать `subprocess`/`importlib` из ручки `reindex`. Запускать через `asyncio.create_task()` + семафор
- [ ] `features/chat/manager.py` — вынести RAG-префиксы `[p]/[w]/[o]` в `features/chat/rag_router.py` (конфигурируемый `_NS_MAP` через `config.yaml`, не хардкод)
- [ ] `features/chat/manager.py` — вынести tool calls в `features/chat/tool_executor.py`. `ChatManager` — только роутер модальностей (text/voice/image → LLM)

## Фаза 3: Данные и наблюдаемость (1–2 недели)
- [ ] `core/domain/pipeline.py` + `pipeline/steps.py` — добавить `trace_id: str` в `PipelineData`. Логировать `[trace:%s] step=%s` в каждом шаге
- [ ] `adapters/vector_store_faiss.py` — `save()` пишет `{"schema_version": 1, "dim": ..., "created": ...}`. `load()` проверяет версию, отклоняет старые с `VersionMismatchError`
- [ ] `adapters/storage_sqlite.py` + `adapters/memory_sqlite.py` — добавить `PRAGMA user_version`. Создать `dev/migrations/` с `.sql` файлами. Создать `ops/scripts/migrate_db.py`
- [ ] `core/prompts/v1/manifest.json` — `{"required_vars": [...]}`. `get_prompt()` проверяет переменные до Jinja2 рендеринга, иначе `ValueError`

## Фаза 4: Документация и ADR (параллельно, не блокирует код)
- [ ] Создать `dev/AI_RULES.md` — перенести архитектурные правила из README
- [ ] Обновить `README.md` — убрать AI-маркеры, оставить чистое описание для пользователей
- [ ] Обновить `dev/scripts/context_build.py` — тянуть `AI_RULES.md` вместо маркеров из README
- [ ] ADR-001: почему sacred core (и почему изменяем)
- [ ] ADR-002: почему adapter pattern (1 файл = 1 провайдер)
- [ ] ADR-003: почему плоские features/

## Фаза 5: Расширение (по требованию, не заранее)
- [ ] Новый LLM/embedder/vector_store → `adapters/<type>_<name>.py` + `@register`. Копировать `llm_mock.py` как шаблон
- [ ] Новая фича → `features/<name>/{handlers,manager,schemas}.py`. Копировать `features/chat/`. Не импортировать другие фичи напрямую — только через порты
- [ ] Новый pipeline шаг → `pipeline/steps.py` + добавить в `config.yaml` `rag.steps`. DAG/parallel — только при реальном кейсе
- [ ] Config расширение — новое поле в `core/config.py` только когда >3 env-override или сложный loader
- [ ] Мониторинг: structlog/JSON только если нужен ELK/Loki; metrics вне файла только для multi-instance; health check с проверкой всех сконфигурированных адаптеров
- [ ] Security: Vault/Redis rate limit/audit middleware — только для multi-instance или compliance
