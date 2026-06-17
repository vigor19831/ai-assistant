Выдай список todo по одной строке в формате: [ ] Название + Краткая суть | Подробное описание (что, зачем, и ⚠️ CORE CHANGE если критично) | Файлы для правки | Файлы тестов / где проверять

===============================================================================
# TODO
===============================================================================

[х] token_margin_min/token_margin_pct в config | Убрать константы `TOKEN_MARGIN_MIN`, `TOKEN_MARGIN_PCT`. Прокидывать через `ChatManager`/`RAGManager`. | `core/config.py`, `core/pipeline_steps.py`, `features/chat/manager.py`, `features/rag/manager.py` | `tests/test_config.py`, `tests/test_pipeline.py` ПЕРЕДАЛАЛИ PipelineConfig — stdlib dataclass в core/domain/pipeline.py — содержит все конфигурационные параметры, которые шаги pipeline читают из metadata. Это даёт типизированный контракт вместо "anything dict".

[х] Убрать fallbacks из pipeline steps | `metadata["key"]` вместо `metadata.get(key, default)`. `KeyError` → `ConfigurationError`. Обновить все тестовые `metadata` dicts. | `core/pipeline_steps.py` | `tests/test_pipeline.py` — 27 тестов

[х] Убрать model="gpt-4o" хардкод | `tokenizer_model` из `metadata["tokenizer_model"]`. Прокидывать через `ChatManager`/`RAGManager`. | `core/pipeline_steps.py`, `features/chat/manager.py`, `features/rag/manager.py`, `features/rag/handlers.py` | `tests/test_chat.py`, `tests/test_rag.py`, `tests/test_pipeline.py`

[ ] Перенести max_ctx fallback в адаптеры | `get_context_limit()` возвращает `config.server_context_size or 4096`. Убрать fallback из `pipeline_steps.py`. Обновить `MockLLM`. Переименовать тест `test_max_ctx_none_fallback`. | `adapters/llm_openai_compatible.py`, `adapters/llm_mock.py`, `core/pipeline_steps.py` | `tests/test_adapters.py`, `tests/test_pipeline.py`









## Контекст
Проект: AI Assistant — модульный фреймворк для локальных LLM.
Соло-maintained, ожидаемое время жизни &gt;10 лет.
Архитектурные правила: docs/ai_rules.md, известный drift: docs/drift.md

## Задача
Провести code review изменений в `core/`. Изменённые файлы: {список}

## Проверка

### 0. Self-check
- [ ] Все изменённые файлы перечислены?
- [ ] Нарушен ли абсолютный запрет из ai_rules.md §2?
- [ ] Изменено &gt;3 файлов? → Предложи разбить или обсудить

### 1. Layer Boundaries
Покажи все импорты в изменённых файлах. Для каждого:
- Откуда импорт (stdlib / core / adapters / features / api / third-party)
- Нарушает ли Layer Boundaries (ai_rules.md §3)
- Если нарушает — предложи альтернативу

### 2. PipelineData Immutability
Найди все:
- Создания PipelineData → поля заполнены корректно?
- Чтения из data.metadata → типизированы?
- Мутации PipelineData → есть ли in-place изменения?

### 3. Port Contracts
- Новые методы/поля в портах? → Все адаптеры обновлены?
- Используется ли hasattr/isinstance на портах?
- Используется ли getattr для доступа к config адаптера?

### 4. Типизация
- Есть ли Any, где виден конкретный тип?
- mypy --strict пройдёт?
- Все публичные методы имеют аннотации возвращаемых типов?

### 5. Резilience
- Все внешние вызовы с hard timeout?
- Все внешние вызовы с retry (exponential backoff)?
- Операции идемпотентны?

### 6. Тесты
- Новая функциональность покрыта тестами?
- Существующие тесты обновлены только при рефакторинге/изменении контракта?
- Тесты используют mock адаптеры из adapters/, а не созданные в test файлах?

### 7. Документация
- Docstrings на английском, triple quotes, описывают intent?
- Логирование через get_logger(name)?
- Нет hardcoded secrets?

### 8. Decision Hierarchy (ai_rules.md §10)
Для каждого спорного места:
- Может ли жить в adapters/ или features/? → Сделай там
- Нужен core change, тесты зелёные? → Разрешено
- Breaking port contract / **kwargs? → CORE CHANGE REQUIRED
- Известный drift? → Предложи фикс

## Формат ответа
1. **What and Why** — 1-2 предложения
2. **Changes** — file path + full content или FIND/REPLACE
3. **Verification** — команды pytest, нужны ли обновления тестов?
