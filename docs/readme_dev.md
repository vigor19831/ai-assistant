# docs/ — Developer & AI Workspace

Эта папка содержит всё, что нужно для разработки, тестирования и работы с AI-ассистентом. **Не трогай вручную** файлы, помеченные `[AUTO]` — они генерируются скриптами.

## Архитектурные принципы
См. [`docs/AI_RULES.md`](AI_RULES.md) — единый источник правды для AI и разработчика.

---

## 🔑 Ключевые файлы

### `AI_RULES.md` — Конституция проекта
**Что это:** Правила, которые AI читает перед каждым ответом.
**Как попадает в чат:** `scripts/context_build.py` автоматически вставляет его в `docs/context_build_*.md`.
**Когда редактировать:** Когда меняешь архитектурные принципы (например, разрешил Pydantic в core).
**Разделы:**
- Sacred Core Policy — что можно менять в `core/`, а что нет
- Red Flags — когда AI должен остановиться и предложить core-изменение
- Adapter Discipline — правила для адаптеров
- Feature Isolation — запрет на cross-feature импорты
- Import Discipline — правила импортов между слоями
- Resilience & Retries — таймауты и ретраи
- Error Mapping — обработка ошибок
- Graceful Shutdown — корректное завершение
- Solo Project Guardrails — **что НЕ делать** (Redis, Celery, ленивый AppState и т.д.)

### `ERROR_TAXONOMY.md` — Карта ошибок `[AUTO]`
**Что это:** Таблица всех исключений в проекте (raise, except, :raises:).
**Как формируется:** Автоматически скриптом `scripts/error_taxonomy_build.py`, который запускается внутри `scripts/context_build.py`.
**Зачем нужен:** AI проверяет таблицу перед тем, как предложить try/except — не добавляет лишний retry туда, где уже есть `with_retry`, не ловит `ValueError` там, где ожидается `AdapterError`.
**Когда обновляется:** При каждом запуске `scripts/context_build.py`.
**Не редактировать руками** — изменения перезапишутся при следующей генерации.

### `TODO.md` — Список задач
**Что это:** Единый список задач по фазам (P0, P1, P2).
**Как использовать:** Копируешь один пункт, вставляешь в новый чат с AI, получаешь патч.
**Структура:**
- Фаза 0 — быстрая гигиена (ruff, CI, pre-commit)
- Фаза 1 — защита Sacred Core (frozen PipelineData, config extra, классы-шаги)
- Фаза 2 — API и фичи (versioning, разделение handlers)
- Фаза 3 — данные и observability (trace_id, миграции БД)
- Фаза 4 — документация и ADR

### `TODO_DONE.md` — Выполненные задачи
Завершённые пункты из `TODO.md`. Хранит историю крупных фич и рефакторингов. Мелкие багфиксы не дублируются — просто удаляются из `TODO.md`.

### `pyproject.toml` (в корне) — Единый манифест проекта
**Где лежит:** `D:i\pyproject.toml` (не в `docs/`).
**Структура:**
- `[project]` — runtime-зависимости (fastapi, uvicorn, pydantic, sqlalchemy)
- `[project.optional-dependencies]` — extras:
  - `dev` — pytest, ruff, mypy, mutmut, hypothesis, vulture
  - `faiss` — faiss-cpu (для векторного поиска)
- `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` — конфиги инструментов

---

## 🔄 Workflow перед каждым чатом с AI

```bash
# 1. Обновить контекст (внутри: сначала ERROR_TAXONOMY, потом context_build)
python scripts/context_build.py

# 2. Скопировать docs/context_build_compact.md в чат
# 3. Скопировать один пункт из docs/TODO.md
# 4. Получить патч, применить, коммитить
```

---

## Скрипты

`scripts/audit_project.py` — Анализ мёртвого кода: неиспользуемые символы, методы, константы, зацикленные импорты, дублирующиеся блоки. Режимы: AST-only или coverage-based.

`scripts/check_all.py` — Комплексная проверка проекта: импорты, конфиг, шаблоны, lifespan, PipelineData, RAG-префиксы, mock-прогон pipeline, структура папок, индексы.

`scripts/check_llm.py` — Проверка доступности LLM-сервера: `/v1/models` и тестовый запрос к `/v1/chat/completions`.

`scripts/check_mutations.py` — Мутационное тестирование через `mutmut`. Режимы: полный проект или только sacred core (`--quick`).

`scripts/check_mypy.py` — Запуск `mypy` для `src/`. Поддерживает `--strict` и проверку конкретных пакетов.

`scripts/check_rag.py` — Диагностика RAG: загрузка конфига, инициализация embedder/vector store, проверка namespace'ов, тестовый прогон pipeline.

`scripts/check_ruff.py` — Запуск `ruff check` и `ruff format` для `src/`. Режим `--check` — только проверка без исправлений.

`scripts/check_smoke.py` — Единый smoke-тест: импорты, конфиг, AppState, HTTP-эндпоинты, SSE-формат, RAG pipeline, ChatManager, инструменты, безопасность, lifespan.

`scripts/clean_cache.py` — Очистка кэша: `__pycache__`, `.pytest_cache`, `.mypy_cache`, `.coverage`, логи, временные файлы. Режимы: удаление или только показ.

`scripts/context_build.py` — Генератор AI-контекста: собирает структуру, зависимости, сигнатуры и полный код в markdown. Режимы: `rules`, `compact`, `full`. Внутри автоматически запускает `error_taxonomy_build.py`.

`scripts/download_tokenizers.py` — Скачивание токенизаторов с HuggingFace по моделям из `config.yaml`. Поддержка зеркал и `HF_TOKEN`.

`scripts/error_taxonomy_build.py` — Автогенерация `docs/error_taxonomy.md`: сканирует `raise`, `except`, `:raises:` в docstrings, `TECH DEBT`/`FIXME` комментарии. Запускается только через `context_build.py`, не руками.

`scripts/index_documents.py` — Индексация документов из `sources/` в RAG namespace'ы. Проверка доступности embedder, авто-запуск адаптеров.

`scripts/pre_commit_check.py` — Лёгкий regex-сканер для pre-commit: `hasattr`/`isinstance` в production, `**kwargs`, cross-feature импорты, мутация PipelineData, `print`/`logging.basicConfig`.

`scripts/run_all_tests.py` — Запуск тестов с выбором режима: default, online (с e2e), coverage. Логирование в файл.

`scripts/start.py` — Запуск сервера: авто-старт `llama-server` (LLM + embedder) и `uvicorn`. Режим foreground/background, отслеживание PID.

`scripts/stop.py` — Остановка сервера: graceful shutdown по PID-файлам, fallback по портам, очистка `llama-server`.

`scripts/structure.py` — Генерация дерева проекта с метриками (файлы, LOC, размер). Учёт `.gitignore`, цветной вывод.

---

## Тесты

`tests/test_adapters_integration.py` — Параметризованные тесты всех адаптеров: chunker, embedder (mock + OpenAI), LLM (mock + OpenAI), vector store (FAISS + Memory), reranker, storage.

`tests/test_api_deps.py` — Зависимости API: `AppState`, `init_adapters`, `get_state`, сборка pipeline-шагов.

`tests/test_api_e2e.py` — End-to-end тесты HTTP API: health, chat, stream, RAG, OpenAI-compatible endpoints.

`tests/test_chat_manager_direct.py` — Прямое тестирование `ChatManager`: RAG-префиксы, история, тримминг токенов, streaming.

`tests/test_contracts.py` — Контрактные тесты портов: проверка сигнатур `ILLM`, `IEmbedder`, `IVectorStore` и т.д.

`tests/test_core_critical.py` — Критические тесты ядра: `PipelineData` immutable, `RAGPipeline` sequential execution, retry logic.

`tests/test_fuzz.py` — Фаззинг-тесты: случайные входные данные для pipeline, chunker, tokenizer через `hypothesis`.

`tests/test_lifespan.py` — Жизненный цикл приложения: startup/shutdown, загрузка/сохранение индексов, graceful cleanup.

`tests/test_malformed_sse.py` — Обработка malformed SSE-ответов от LLM: неполные JSON, пропущенные поля, некорректные `data:` строки.

`tests/test_pipeline_frozen_compat.py` — Совместимость frozen `PipelineData`: все шаги возвращают новые инстансы, нет мутаций.

`tests/test_rag_pipeline.py` — Интеграция RAG pipeline: embed → retrieve → rerank → build_context → generate с mock-адаптерами.

`tests/test_resilience.py` — Отказоустойчивость: retry decorator, circuit breaker (если есть), обработка timeout'ов.

`tests/test_router_compile.py` — Компиляция роутеров: корректная сборка `assemble_routers`, префиксы, теги, зависимости.

`tests/test_scripts_and_platform.py` — Платформенные тесты скриптов: корректность путей, Windows/Unix совместимость, кодировки.

`tests/test_security.py` — Безопасность: API key validation, rate limiting, request size limits, path traversal в `save-chat`.

`tests/test_smoke_pyproject.py` — Smoke-тест `pyproject.toml`: валидность TOML, зависимости, версии, конфигурация инструментов.

`tests/test_stress.py` — Нагрузочные тесты: множественные параллельные запросы, большие payload'ы, утечки памяти.

`tests/test_tokenizer.py` — Тесты токенизации: `tiktoken` vs `tokenizers`, подсчёт CJK-символов, fallback на `len//4`.

---

## ⚠️ Файлы `[AUTO]` — не трогать руками

| Файл | Что будет, если править руками |
|------|-------------------------------|
| `ERROR_TAXONOMY.md` | Изменения перезапишутся при следующем `scripts/context_build.py` |
| `context_build_compact.md` | Перегенерируется полностью |
| `context_build_full.md` | Перегенерируется полностью |
| `context_build_rules.md` | Перегенерируется полностью |

---

## 🆘 Troubleshooting

**pytest падает с `RuntimeError: State not initialized`:**
Проверь, что `conftest.py` вызывает `deps.set_state(mock_state)` или `app.state.app_state = mock_state`. Проверь, что `reset_global_state` фикстура не очищает state после установки.

**RAG возвращает пустой контекст:**
Проверь `embedder.dim == vector_store.dim` в config. Проверь, что индексы загружены (`vector_store.load()` вызван). Проверь `relevance_threshold` — возможно, слишком высокий.

**`context_build.py` падает с ошибкой:**
Проверь, что `README.md` и `pyproject.toml` есть в корне проекта (`D:i\`). Проверь, что запускаешь из корня: `cd D:i && python scripts/context_build.py`.

**`ERROR_TAXONOMY.md` не обновляется:**
Проверь, что `error_taxonomy_build.py` лежит рядом с `context_build.py` в `scripts/`. Запусти вручную: `python scripts/error_taxonomy_build.py`.

**AI не видит свежие правила из `AI_RULES.md`:**
Убедись, что запустил `scripts/context_build.py` после правки. Проверь дату в начале `docs/context_build_compact.md` — должна быть свежей.

**`TODO.md` разросся:**
Переноси выполненные крупные пункты в `TODO_DONE.md`. Мелкие багфиксы просто удаляй.
