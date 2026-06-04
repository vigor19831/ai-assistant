# dev/ — Developer & AI Workspace

Эта папка содержит всё, что нужно для разработки, тестирования и работы с AI-ассистентом. **Не трогай вручную** файлы, помеченные `[AUTO]` — они генерируются скриптами.

## Архитектурные принципы
См. [`dev/AI_RULES.md`](AI_RULES.md) — единый источник правды для AI и разработчика.

---

## 📁 Структура

dev/
├── README_DEV.md            # ← ты здесь
├── AI_RULES.md              # Правила для AI (читаются при каждом чате)
├── ERROR_TAXONOMY.md        # [AUTO] Таблица ошибок (автогенерация)
├── TODO.md                  # Текущие задачи проекта
├── launcher.py              # Интерактивный лаунчер скриптов и тестов
├── ADR-001.md               # Архитектурные решения (при необходимости)
├── migrations/              # SQL-миграции базы данных (когда появятся)
├── scripts/                 # Скрипты для разработки и CI
│   ├── context_build.py          # [AUTO] Сборщик контекста для AI
│   ├── error_taxonomy_build.py   # [AUTO] Генератор ERROR_TAXONOMY.md
│   ├── check_llm.py              # Проверка LLM-сервера
│   ├── check_rag.py              # Проверка RAG pipeline
│   ├── check_ruff.py             # Линтер
│   ├── check_mypy.py             # Типизация
│   ├── check_smoke.py            # Дымовой тест
│   └── ...
└── tests/                   # Тесты
    ├── conftest.py          # Фикстуры pytest (моки, конфиг)
    ├── config.test.yaml     # Тестовая конфигурация
    └── test_*.py            # Тесты по модулям

---

## 🔑 Ключевые файлы

### `AI_RULES.md` — Конституция проекта
**Что это:** Правила, которые AI читает перед каждым ответом.  
**Как попадает в чат:** `context_build.py` автоматически вставляет его в `context_build_compact.md`.  
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
**Как формируется:** Автоматически скриптом `error_taxonomy_build.py`.  
**Зачем нужен:** AI проверяет таблицу перед тем, как предложить try/except — не добавляет лишний retry туда, где уже есть `with_retry`, не ловит `ValueError` там, где ожидается `AdapterError`.  
**Когда обновляется:** При каждом запуске `context_build.py` (автоматически).  
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

### `pyproject.toml` (в корне) — Единый манифест проекта
**Где лежит:** `D:\ai\pyproject.toml` (не в `dev/`).  
**Структура:**
- `[project]` — runtime-зависимости (fastapi, uvicorn, pydantic, sqlalchemy)
- `[project.optional-dependencies]` — extras:
  - `dev` — pytest, ruff, mypy, mutmut, hypothesis, vulture
  - `faiss` — faiss-cpu (для векторного поиска)
- `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest.ini_options]` — конфиги инструментов

---

## Установка
```bash
cd D:\ai
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,faiss]"
```

🔄 Workflow перед каждым чатом с AI
# 1. Обновить контекст (внутри: сначала ERROR_TAXONOMY, потом context_build)
python dev/scripts/context_build.py

# 2. Скопировать dev/context_build_compact.md в чат
# 3. Скопировать один пункт из dev/TODO.md
# 4. Получить патч, применить, коммитить

⚠️ Файлы [AUTO] — не трогать руками
Table
Файл    Что будет, если править руками
ERROR_TAXONOMY.md   Изменения перезапишутся при следующем context_build.py
context_build_compact.md    Перегенерируется полностью
context_build_full.md   Перегенерируется полностью


🆘 Troubleshooting
pytest падает с RuntimeError: State not initialized:

    Проверь, что conftest.py вызывает deps.set_state(mock_state) или app.state.app_state = mock_state
    Проверь, что reset_global_state фикстура не очищает state после установки

RAG возвращает пустой контекст:

    Проверь embedder.dim == vector_store.dim в config
    Проверь, что индексы загружены (vector_store.load() вызван)
    Проверь relevance_threshold — возможно, слишком высокий

context_build.py падает с ошибкой:

    Проверь, что README.md и pyproject.toml есть в корне проекта (D:\ai\)
    Проверь, что запускаешь из корня: cd D:\ai && python dev/scripts/context_build.py

ERROR_TAXONOMY.md не обновляется:

    Проверь, что error_taxonomy_build.py лежит рядом с context_build.py в dev/scripts/
    Запусти вручную: python dev/scripts/error_taxonomy_build.py

AI не видит свежие правила из AI_RULES.md:

    Убедись, что запустил context_build.py после правки
    Проверь дату в начале context_build_compact.md — должна быть свежей

TODO.md разросся:

    Переноси выполненные пункты в раздел ## Done внизу файла
    Или создавай TODO-2026-05.md, TODO-2026-06.md по месяцам

### Описание скриптов

check_llm.py    Диагностика LLM-сервера: GET /models + POST /chat/completions
check_mutations.py  Mutation testing через mutmut (требует WSL на Windows)
check_mypy.py   Статический анализ типов
check_rag.py    Диагностика RAG: embed → retrieve → build_context
check_ruff.py   Линтер и форматтер
check_smoke.py  Универсальный smoke-тест: импорты, endpoints, pipeline, tools
context_build.py    [AUTO] Сборщик контекста для AI
error_taxonomy_build.py [AUTO] Генератор таблицы ошибок
pre_commit_check.py Архитектурные guardrails: hasattr, kwargs, cross-feature imports
structure.py    Генератор дерева проекта с метриками
audit_project.py    Поиск мусора

### Полный вывод тестов в файл:

# Windows
pytest dev/tests/ --tb=long -v > test_failures_full.txt 2>&1
pytest dev/tests -vvs --tb=long > test_failures.txt 2>&1
pytest dev/tests -vvs --tb=long --show-capture=all > test_failures.txt 2>&1

# Unix
pytest dev/tests/ --tb=long -v 2>&1 | tee test_failures_full.txt

# Новые фичи через config.yaml или новый файл в adapters/
