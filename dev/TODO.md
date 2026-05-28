

ЗАПУСТИТЬ ЧЕК и тесты проверить все несколько раз в лаунчере












=== НАЧАЛО БЛОКА: Фаза 6.1 ===

## Промпт

Ты — senior Python-разработчик. Работаешь с проектом AI Assistant (модульный фреймворк для локальных LLM). Проект работает полностью offline, поддерживает RAG, совместим с OpenAI API.

## Задача: AI_RULES.md + README cleanup

### Контекст
Проект: `dev/AI_RULES.md` — архитектурные правила. `README.md` — user-facing описание. `dev/scripts/context_build.py` — генерирует `context_build.md`.

### Что сделать
1. Создать/обновить `dev/AI_RULES.md` — перенести архитектурные правила из `README.md` (sacred core, adapter discipline, feature isolation, solo guardrails).
2. Обновить `README.md` — убрать AI-маркеры, оставить чистое описание для пользователей (возможности, быстрый старт, требования).
3. Обновить `dev/scripts/context_build.py` — тянуть `AI_RULES.md` вместо маркеров из `README.md`.

### Тест
`context_build.py` генерирует корректный `context_build.md` с `AI_RULES.md` в блоке guidelines.

## Правила
- Не добавляй сложность ради сложности.
- Пиши чистую документацию.

=== КОНЕЦ БЛОКА ===











