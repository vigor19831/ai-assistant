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

