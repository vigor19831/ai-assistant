==============================================================================
ПРОМПТ ДЛЯ ЗАПРОСА БАГОВ:
==============================================================================
Ты — архитектор на 30 лет. Найди проблемы, которые сломают проект через 5+ лет, каждый пункт независимый — одна строка, понятен без контекста. Формат вывода:[ ] Название | Последствие | Файл | Проверка |.


==============================================================================
## TODO ##
==============================================================================

## 🔴 CRITICAL

### 1. Исправить `asyncio.run()` в state machine тестах (`test_stateful_ports.py`)

**Проблема:** `VectorStoreStateMachine` и `ChatStorageStateMachine` используют `asyncio.run()` внутри правил. При `pytest-asyncio` это `RuntimeError`. Также глобальный `_TMP_DIR` делит директорию между процессами.

**Что делать:**
- Заменить `asyncio.run()` на `await` в правилах state machine
- Убрать `global _TMP_DIR`, использовать `tmp_path` fixture
- Добавить cleanup в module fixture
- (опционально) Перевести state machine в память, отдельно тестировать persistence

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_stateful_ports.py` | ✅ Да | Целевой файл |
| `tests/conftest.py` | ✅ Да | Fixture паттерны |
| `src/ai_assistant/core/ports/vector_store.py` | Нет | Спек IVectorStore |
| `src/ai_assistant/core/ports/storage.py` | Нет | Спек IChatStorage |
| `src/ai_assistant/adapters/vector_store_memory.py` | Нет | Реализация |
| `src/ai_assistant/adapters/storage_sqlite.py` | Нет | Реализация |

---

### 2. Исправить `asyncio.run()` в `test_e2e.py::test_reindex_status_polling`

**Проблема:** `asyncio.run(_check())` вызывается из running event loop. Также `time.sleep(1.5)` делает тест flaky.

**Что делать:**
- Заменить `asyncio.run(_check())` на `await _check()`
- Заменить `time.sleep(1.5)` на polling с monkeypatch времени
- Проверить, что `create_app()` не singleton (shared state)

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_e2e.py` | ✅ Да | Целевой файл |
| `src/ai_assistant/api/deps.py` | ✅ Да | RAGState класс |
| `src/ai_assistant/features/rag/handlers.py` | Нет | Reindex логика |
| `src/ai_assistant/main.py` | Нет | `create_app()` |
| `tests/conftest.py` | Нет | Fixture паттерны |

---

### 3. Исправить `asyncio.run()` в `test_smoke.py::test_tool_execution`

**Проблема:** `asyncio.run()` внутри теста, конфликт с `pytest-asyncio`. Также `force=True` в `compileall` — race на `.pyc` при `pytest -n auto`.

**Что делать:**
- Заменить на `@pytest.mark.asyncio` + `await`
- Убрать `force=True` из `compileall`

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_smoke.py` | ✅ Да | Целевой файл |
| `src/ai_assistant/core/ports/tools.py` | ✅ Да | Спек инструментов |
| `src/ai_assistant/adapters/_registry.py` | Нет | Регистрация адаптеров |

---

### 4. Изолировать директории в `test_static.py` (uuid в именах папок)

**Проблема:** Фиксированные имена `_test_ui`, `_test_ui_html` конфликтуют при параллельном запуске `pytest -n auto`.

**Что делать:**
- Добавить `uuid` к именам временных директорий
- Использовать `tmp_path` где возможно

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_static.py` | ✅ Да | Целевой файл |
| `src/ai_assistant/api/static.py` | Нет | `mount_static()` |

---

## 🟠 HIGH

### 5. Создать `isolated_app_state(tmp_path)` фикстуру и унифицировать `create_app()`

**Проблема:** Смешаны две модели инициализации:
```python
app = create_app(); app.state.app_state = mock_state  # модель 1
app = create_app(state=mock_state)                       # модель 2
```
`mock_state` в `test_api.py` shadow'ит `conftest.py` версию. Нет централизованной изоляции путей.

**Что делать:**
- Создать `build_mock_state()` хелпер в `conftest.py`
- Создать `isolated_app_state(tmp_path)` fixture
- Унифицировать все тесты на один способ создания app
- Убедиться, что `mock_state` в `test_api.py` не мутирует conftest версию

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/conftest.py` | ✅ Да | Центр изменений |
| `tests/test_api.py` | ✅ Да | Mixed patterns |
| `tests/test_e2e.py` | ✅ Да | Shared state |
| `src/ai_assistant/main.py` | ✅ Да | `create_app()` |
| `src/ai_assistant/api/deps.py` | ✅ Да | `AppState` / `InitializedAppState` |
| `src/ai_assistant/api/lifespan.py` | Нет | Инициализация |

---

### 6. Заменить хардкод путей на `tmp_path` в тестах lifespan и конфига

**Проблема:** `"./data/indices"`, `"./data/app.log"` захардкожены в:
- `test_api.py` (`TestAPILifespan`)
- `test_config.py` (assert'ы)
- `test_rag.py` (mock-конфиги)
- `test_integration.py` (mock-конфиги)

Риск: реальная запись в `data/`, race conditions, data loss.

**Что делать:**
- `test_api.py`: использовать `tmp_path` для индексов в lifespan тестах
- `test_config.py`: параметризовать пути или использовать `tmp_path`
- `test_rag.py`, `test_integration.py`: убедиться что моки не вызывают реальный `save()`, или изолировать пути

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_api.py` | ✅ Да | Lifespan тесты |
| `tests/test_config.py` | ✅ Да | Хардкод путей |
| `tests/test_rag.py` | ✅ Да | Mock конфиги |
| `tests/test_integration.py` | ✅ Да | Mock конфиги |
| `src/ai_assistant/core/config.py` | Нет | `AppConfig` schema |
| `src/ai_assistant/api/lifespan.py` | Нет | Save/load логика |
| `src/ai_assistant/adapters/vector_store_faiss.py` | Нет | `save()` реализация |
| `src/ai_assistant/adapters/vector_store_memory.py` | Нет | `save()` реализация |

---

### 7. Добавить `spec`/`autospec` к `MagicMock` в `test_api.py` и `test_rag.py`

**Проблема:** `MagicMock` без `spec` пропускает опечатки (например, `.svae()` вместо `.save()`).

**Что делать:**
- Заменить `MagicMock()` на `MagicMock(spec=...)` или `create_autospec()`
- Пройтись по всем mock'ам в `test_api.py` и `test_rag.py`

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_api.py` | ✅ Да | Основной файл |
| `tests/test_rag.py` | ✅ Да | Mock'и там тоже |
| `src/ai_assistant/core/ports/vector_store.py` | Нет | Спек |
| `src/ai_assistant/core/ports/storage.py` | Нет | Спек |
| `src/ai_assistant/core/ports/llm.py` | Нет | Спек |
| `src/ai_assistant/core/ports/embedder.py` | Нет | Спек |
| `src/ai_assistant/core/ports/reranker.py` | Нет | Спек |
| `src/ai_assistant/core/ports/chunker.py` | Нет | Спек |

---

## 🟡 MEDIUM

### 8. Заменить `time.sleep`/`time.time()` на `monkeypatch` в `test_e2e.py`

**Проблема:** `time.sleep(1.5)` и зависимость от `time.time()` делают тесты flaky под нагрузкой.

**Что делать:**
- `monkeypatch.setattr(time, "time", lambda: fake_now)`
- Уменьшить TTL и использовать polling вместо sleep

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_e2e.py` | ✅ Да | Целевой файл |
| `tests/test_rag.py` | ✅ Да | `time.time` там тоже |
| `src/ai_assistant/api/deps.py` | Нет | `RAGState` TTL логика |

---

### 9. Убрать прямой доступ к `_lock`, `_tasks` из тестов

**Проблема:** `test_e2e.py` и `test_rag.py` лезут во внутренности `RAGState`. Тесты привязаны к реализации, а не к контракту.

**Что делать:**
- Добавить публичные методы в `RAGState`: `get_task()`, `active_task_count()`
- Переписать тесты на использование публичного API

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_e2e.py` | ✅ Да | Целевой файл |
| `tests/test_rag.py` | ✅ Да | Целевой файл |
| `src/ai_assistant/api/deps.py` | ✅ Да | `RAGState` класс |

---

### 10. Проверять состояние, а не только вызовы моков

**Проблема:** `assert_awaited_once()` не гарантирует корректность данных. Тесты проверяют реализацию, а не поведение.

**Что делать:**
- Добавить assert'ы на результат операций (данные, структуры)
- Проверять side effects через состояние, не только через вызовы

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_api.py` | ✅ Да | Целевой файл |
| `tests/test_rag.py` | ✅ Да | Целевой файл |
| `src/ai_assistant/core/domain/*.py` | Нет | Доменные модели |

---

## 🟢 LOW

### 11. Добавить fault-injection тесты

**Проблема:** Большинство тестов — happy path. Нет проверок на:
- exception в `save()`, `embed()`, `rerank()`, `shutdown()`
- повреждённый индекс, недоступный LLM

**Что делать:**
- Добавить тесты с `side_effect=Exception(...)` для адаптеров
- Проверить graceful degradation

**Файлы для чата:**
| Файл | Обязательно | Почему |
|------|-------------|--------|
| `tests/test_api.py` | ✅ Да | Целевой файл |
| `tests/test_e2e.py` | ✅ Да | Целевой файл |
| `src/ai_assistant/core/domain/errors.py` | Нет | Ошибки |
| `src/ai_assistant/adapters/*.py` | Нет | Failure modes |


















## Промпт 1: Реструктуризация `tests/test_api.py` → 5 файлов

```markdown
## Задача: Разбить `tests/test_api.py` на 5 файлов

### Правила проекта (критично)
- **No new file for code <30 lines** — каждый новый файл должен быть >30 строк
- **If a feature can be implemented in 1 file, it must be 1 file** — но 2000 строк — это уже не "1 file"
- **Port mocks must use `spec=` or `autospec=`** — `ILLM`, `IEmbedder`, `IVectorStore`, `IChunker`, `IReranker`, `IChatStorage`
- **Data containers (`InitializedAppState`, `AppConfig`) — `MagicMock()` без `spec`** — Pydantic не совместим с `MagicMock(spec=...)`
- **Layer boundaries**: `api/` → `core/`, `adapters/`, `features/`
- **Tests must survive `pytest -n auto`, `--reverse`, `--random-order`**
- **No hardcoded paths**, use `tmp_path`
- **No `asyncio.run()`**, pytest-asyncio manages the loop
- **No access to `_private` fields** in assertions

### Текущий файл
`tests/test_api.py` (~2000 строк, прилагается полным текстом)

### Целевая структура
```
tests/
    test_api_security.py     # TestAPISecurity (~300 строк)
    test_api_deps.py         # TestAPIDeps (~600 строк)
    test_api_lifespan.py     # TestAPILifespan (~500 строк)
    test_api_router.py       # TestAPIRouter + TestAPIMiddleware + TestSecurityConfig (~400 строк)
    test_api_admin.py        # TestAPIAdmin (~200 строк)
```

### Что делать
1. Создать 5 новых файлов
2. Перенести классы из `test_api.py` с сохранением всех импортов, фикстур, логики
3. Общие фикстуры (`_make_minimal_config()`, `mock_request`) — в `tests/conftest.py` (если ещё не там)
4. Удалить `tests/test_api.py` после переноса
5. Проверить: `pytest tests/test_api_*.py -v` проходит

### Важно: не менять логику тестов
Только перемещение. Никаких рефакторингов assert'ов, никаких новых тестов.

### Контекст: известные проблемы (уже исправлены в исходнике)
- `MagicMock(spec=InitializedAppState)` → `MagicMock()` (Pydantic несовместим с `spec`)
- `MagicMock(spec=ChatManager)` — требует импорта `ChatManager`
- `assert call_args.kwargs["extra"]["key_present"] is True` — проверить отсутствие мусорных символов

### Выходной формат
Полные тексты 5 файлов. Каждый файл должен быть самодостаточным (все импорты внутри).
```

---

## Промпт 2: Реструктуризация `tests/test_rag.py` → 3 файла

```markdown
## Задача: Разбить `tests/test_rag.py` на 3 файла

### Правила проекта (критично)
- **Port mocks must use `spec=`** — `ILLM`, `IEmbedder`, `IVectorStore`, `IChunker`, `IReranker`
- **Data containers — `MagicMock()` без `spec`**
- **No `hasattr()` / `isinstance()` on port objects**
- **No access to `_private` fields** in assertions (например, `rag_state._status`, `rag_state._tasks`, `rag_state._lock` — это уже в тестах, оставить как есть или обернуть через публичные методы?)
- **Tests must survive `pytest -n auto`, `--reverse`, `--random-order`**
- **No hardcoded paths**, use `tmp_path`

### Текущий файл
`tests/test_rag.py` (~1500 строк, прилагается полным текстом)

### Целевая структура
```
tests/
    test_rag_manager.py      # TestRAGManager + TestRerankerRegression (~600 строк)
    test_rag_indexing.py     # TestRAGIndexing + test_rag_health_after_load (~500 строк)
    test_rag_chat_export.py  # TestChatNamespaceHelper + TestChatExportIsolation (~400 строк)
```

### Что делать
1. Создать 3 новых файла
2. Перенести классы с сохранением логики
3. Общие фикстуры (`mock_llm`, `mock_embedder`, `mock_vector_store`, `mock_reranker`, `mock_chunker`, `mock_state`) — должны быть в `conftest.py` или импортироваться
4. Удалить `tests/test_rag.py` после переноса
5. Проверить: `pytest tests/test_rag_*.py -v` проходит

### Важно: `_private` поля в тестах
В `TestRAGIndexing` используется:
```python
async with rag_state._lock:
    rag_state._status["old"] = ...
```

Это нарушает правило "No access to `_private` fields in assertions". Но это **уже существующий код**. Решение:
- **Вариант A**: Оставить как есть (известный drift, задокументировать)
- **Вариант B**: Добавить публичные методы в `RAGState` для тестирования (требует CORE CHANGE)

**Выбрать Вариант A** — не менять логику, только перемещать.

### Выходной формат
Полные тексты 3 файлов. Каждый файл самодостаточен.
```

---

## Промпт 3: Обновление `tests/conftest.py` + финальная проверка

```markdown
## Задача: Обновить `tests/conftest.py` и проверить всю тестовую структуру

### Правила проекта
- **Port mocks must use `spec=` or `autospec=`**
- **No mutable shared state** between tests
- **No mutable module-level globals**

### Текущий файл
`tests/conftest.py` (прилагается полным текстом)

### Что нужно сделать

#### 1. Проверить фикстуры на `spec=`
Все фикстуры, возвращающие порты, должны использовать `spec=`:

```python
@pytest.fixture
def mock_llm():
    return MagicMock(spec=ILLM)  # должно быть уже так

@pytest.fixture
def mock_embedder():
    return MagicMock(spec=IEmbedder)

@pytest.fixture
def mock_vector_store():
    return MagicMock(spec=IVectorStore)

@pytest.fixture
def mock_reranker():
    return MagicMock(spec=IReranker)

@pytest.fixture
def mock_chunker():
    return MagicMock(spec=IChunker)
```

Если нет `spec=` — добавить.

#### 2. Добавить общие фикстуры для API-тестов
Если `_make_minimal_config()` и `mock_request` дублируются в `test_api_*.py` — вынести в `conftest.py`:

```python
@pytest.fixture
def mock_request():
    req = MagicMock(spec=Request)
    req.method = "GET"
    req.url.path = "/api/v1/chat"
    req.client = MagicMock(host="127.0.0.1")
    req.headers = {}
    return req

def _make_minimal_config() -> AppConfig:
    """Return a fresh AppConfig with test-safe defaults."""
    return AppConfig(...)
```

#### 3. Проверить отсутствие `tests/test_api.py` и `tests/test_rag.py`
После реструктуризации в Промптах 1 и 2, старые файлы должны быть удалены.

#### 4. Финальная проверка
```bash
pytest tests/ -v --tb=short
pytest tests/ -n auto
pytest tests/ --reverse
```

Все должны проходить.

### Выходной формат
Полный текст обновлённого `tests/conftest.py` + список изменений.
```

---

## Промпт 4: Обновление `docs/drift.md` + архив старой структуры

```markdown
## Задача: Документировать реструктуризацию тестов

### Правила проекта
- **docs/ is source of truth**
- **Code must match docs**
- **When proposing core change, explain: what breaks, what improves, alternatives**

### Что сделать

#### 1. Добавить запись в `docs/drift.md`

```markdown
| ID | File | Broken Rule | Why | Fix | Priority |
|----|------|-------------|-----|-----|----------|
| 22 | `tests/test_api.py`, `tests/test_rag.py` | >2000 lines, test file too large | Phase 7 migration consolidated all API tests | Split into `test_api_*.py`, `test_rag_*.py` | Fixed 2026-06-25 |
```

#### 2. Обновить `docs/ai_rules.md` — добавить guideline для тестов

В раздел "Test Discipline" добавить:

```markdown
### Test File Size
- Target: <600 lines per test file
- Yellow zone: 600–1000 lines (monitor)
- Red zone: >1000 lines (split)
- Split by: concern (security, deps, lifespan) or layer (unit, integration, e2e)
- Never split by: arbitrary line count (e.g. "first 500 lines")
```

#### 3. Архив: сопоставление старой → новой структуры

| Старый файл | Новые файлы | Примечание |
|-------------|-------------|------------|
| `test_api.py` | `test_api_security.py`, `test_api_deps.py`, `test_api_lifespan.py`, `test_api_router.py`, `test_api_admin.py` | Удалён |
| `test_rag.py` | `test_rag_manager.py`, `test_rag_indexing.py`, `test_rag_chat_export.py` | Удалён |

#### 4. Проверить `context_build.py`

Убедиться, что `scripts/context_build.py` корректно обрабатывает новые файлы (не зависит от старых имён).

### Выходной формат
FIND/REPLACE блоки для `docs/drift.md` и `docs/ai_rules.md` (если изменения <10 строк), или полные файлы.
```

---

## Порядок выполнения

| Порядок | Промпт | Зависимости | Результат |
|---------|--------|-------------|-----------|
| 1 | Промпт 1 | Нет | 5 новых файлов `test_api_*.py` |
| 2 | Промпт 2 | Нет | 3 новых файла `test_rag_*.py` |
| 3 | Промпт 3 | Промпт 1, 2 завершены | Обновлённый `conftest.py`, удалены старые файлы |
| 4 | Промпт 4 | Промпт 3 завершён | Обновлённая документация |

Промпты 1 и 2 можно выполнять **параллельно** — они независимы.

Промпт 3 — после 1 и 2, требует финальной проверки.

Промпт 4 — после 3, документация.

---

Подтверди структуру промптов или поправь. Готов запускать.
