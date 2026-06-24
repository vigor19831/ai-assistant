==============================================================================
ПРОМПТ ДЛЯ ЗАПРОСА БАГОВ:
==============================================================================
Ты — архитектор на 30 лет. Найди проблемы, которые сломают проект через 5+ лет, каждый пункт независимый — одна строка, понятен без контекста. Формат вывода:[ ] Название | Последствие | Файл | Проверка |.


==============================================================================
## TODO ##
==============================================================================

Вот список в формате по задачам:

---

[ ] Убрать `global _TMP_DIR` в `test_stateful_ports.py` | Все stateful тесты делят одну директорию; при `pytest -n auto` процессы конфликтуют за файлы | `test_stateful_ports.py` | `pytest -n auto test_stateful_ports.py`

[ ] Заменить `asyncio.run()` на `await` в `VectorStoreStateMachine` | Каждое правило создаёт/закрывает event loop; при `--reverse` или нагрузке — `RuntimeError` или зависание | `test_stateful_ports.py` | `pytest --reverse test_stateful_ports.py`

[ ] Заменить `asyncio.run()` на `await` в `ChatStorageStateMachine` | Аналогично: `asyncio.run()` внутри правил state machine | `test_stateful_ports.py` | `pytest --reverse test_stateful_ports.py`

[ ] Убрать `asyncio.run(_check())` в `test_e2e.py::test_reindex_status_polling` | `RuntimeError: asyncio.run() cannot be called from a running event loop` при любом запуске через pytest-asyncio | `test_e2e.py` | `pytest test_e2e.py::TestE2ERAG::test_reindex_status_polling -v`

[ ] Проверить `create_app()` не singleton в `test_e2e.py` | `app.state.app_state` shared между тестами; mutation в одном тесте влияет на другой | `test_e2e.py` | `pytest --reverse test_e2e.py`

[ ] Заменить хардкод `"./data/indices"` на `tmp_path` в `test_api.py::TestAPILifespan` | Тесты lifespan пишут в реальную директорию; при параллельном запуске — race на файлы | `test_api.py` | `grep -n 'data/indices' test_api.py`

[ ] Заменить `asyncio.run()` на `@pytest.mark.asyncio` в `test_smoke.py::test_tool_execution` | `RuntimeError` если pytest-asyncio уже управляет loop; несовместимость с async fixtures | `test_smoke.py` | `pytest test_smoke.py::TestToolPortContract::test_tool_execution -v`

[ ] Добавить `uuid` в имена директорий `test_static.py` | Фиксированные `_test_ui`, `_test_ui_html` конфликтуют при `pytest -n auto` | `test_static.py` | `pytest -n auto test_static.py`

[ ] Убрать `force=True` из `compileall` в `test_smoke.py` | Перезапись `.pyc` файлов в `src/` при параллельном запуске — race condition | `test_smoke.py` | `pytest -n auto test_smoke.py::TestCompileAll`

[ ] Проверить `mock_state` fixture в `test_api.py` не мутирует `conftest.py` версию | `test_api.py` определяет свой `mock_state`, который shadow'ит `conftest.py`; риск разной семантики | `test_api.py` + `conftest.py` | `pytest test_api.py --collect-only` и сравнить fixture scope

[ ] Заменить хардкод путей в assert'ах `test_config.py` на `tmp_path` | Тесты не пишут реально, но значения конфига захардкожены; если `load_config` начнёт создавать файлы — проблема | `test_config.py` | `grep -n 'data/.*\.log' test_config.py`

[ ] Проверить `test_rag.py` mock-конфиги не вызывают реальный `save()` | Хардкод `"./data/indices"` в mock-значениях; если mock заменится на real adapter — data loss | `test_rag.py` | `grep -n 'data/indices' test_rag.py`

[ ] Проверить `test_integration.py` mock-конфиги не вызывают реальный `save()` | Аналогично: хардкод путей в тестовых конфигах | `test_integration.py` | `grep -n 'data/indices' test_integration.py`

[ ] Добавить cleanup в `test_stateful_ports.py` module fixture | `test_tmp.mkdir(exist_ok=True)` без `rmdir()` — мусор между запусками | `test_stateful_ports.py` | Проверить `.test_tmp` после `pytest test_stateful_ports.py`

[ ] Создать `isolated_app_state(tmp_path)` фикстуру | Централизованная изоляция всех путей в `AppState` для e2e/api тестов | `conftest.py` | `pytest test_api.py test_e2e.py -n auto --reverse`
