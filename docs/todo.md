==============================================================================
ПРОМПТ ДЛЯ ЗАПРОСА БАГОВ:
==============================================================================
Ты — архитектор на 30 лет. Найди проблемы, которые сломают проект через 5+ лет, каждый пункт независимый — одна строка, понятен без контекста. Формат вывода:[ ] Название | Последствие | Файл | Проверка |.

==============================================================================
## TODO ##
=============================================================================
Заменить dict[str, dict[str, object]] в RAGState на typed dataclass.

Создать:
- src/ai_assistant/core/domain/reindex_status.py — ReindexStatusEntry dataclass

Изменить:
- src/ai_assistant/api/deps.py — RAGState._status: dict[str, ReindexStatusEntry]
- Методы RAGState: start_task, complete_task, fail_task, get_status, cleanup_status

Обновить:
- src/ai_assistant/features/rag/handlers.py — использование get_status
- tests/test_rag.py — все обращения к status["status"] → status.status
- tests/test_stateful_ports.py — типизация expected

Не менять API endpoints (возвращаемый JSON остаётся dict для совместимости).
