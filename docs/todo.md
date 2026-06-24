==============================================================================
ПРОМПТ ДЛЯ ЗАПРОСА БАГОВ:
==============================================================================
Ты — архитектор на 30 лет. Найди проблемы, которые сломают проект через 5+ лет, каждый пункт независимый — одна строка, понятен без контекста. Формат вывода:[ ] Название | Последствие | Файл | Проверка |.


==============================================================================
## TODO ##
==============================================================================
[+] SQLite без graceful shutdown — возможна потеря WAL | `lifespan.py` вызывает `adapter.shutdown()` для storage, но `SQLiteStorage.shutdown()` не реализован (только `IClosable` default no-op). WAL-файлы (`*.db-wal`, `*.db-shm`) могут остаться несинхронизированными. Нужно: добавить `PRAGMA wal_checkpoint(TRUNCATE)` и `connection.close()` в `shutdown()`. | `src/ai_assistant/adapters/storage_sqlite.py` | `tests/test_stateful_ports.py`

[ ] Нет проверки namespace на path traversal | `save_chat` использует `namespace` для построения пути. Есть `is_relative_to`, но нет валидации самого `namespace` (может быть `../etc`). Нужно: добавить `pattern=r"^[a-z]+$"` как в `SaveChatRequest` для `namespace` в API endpoint. | `src/ai_assistant/features/rag/handlers.py` | `tests/test_rag.py`

