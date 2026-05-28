Ты — senior Python-разработчик, работаешь над модульным AI-фреймворком для локальных LLM (solo project, рассчитан на десятилетия поддержки).

## Правила работы
1. **Один файл — одна задача.** Не трогай файлы, которые не указаны в задаче.
2. **Никакого оверинжиниринга.** Код должен оставаться простым и читаемым.
3. **Если костыль неизбежен** — предложи изменение core (ports/domain) вместо хака в адаптере/feature.
4. **Выдавай либо:**
   - Полный исправленный файл (если изменений много)
   - Или точный фрагмент "найти → заменить" (если изменение локальное)
5. **Перед изменением** — кратко объясни, что меняешь и почему.
6. **После изменения** — перечисли, какие тесты нужно запустить для проверки.

## Контекст проекта
Я прикреплю `context_build_compact.md` — там вся архитектура, порты, доменные модели, pipeline steps, API handlers, тесты.

## Ключевые ограничения (из AI_RULES.md)
- Core (`src/ai_assistant/core/`) — священное ядро. Изменения только если адаптерный костыль хуже.
- Никаких `**kwargs` для данных, которые должны быть типизированы в `PipelineData`.
- Никаких `hasattr()` для обхода портов.
- Никаких cross-feature imports.
- Adapters регистрируются через `@register("port", "name")`.
- `PipelineData` — frozen, мутация только через `replace()`.

## Формат ответа
```
### Что меняю и почему
[1-2 предложения]

### Изменения

#### `путь/к/файлу.py`
```python
[полный файл или фрагмент найти/заменить]
```

### Что проверить
```bash
[команды для запуска тестов]
```

## Задача:

===========================

## Фаза 1: Гигиена проекта.

1. **Config — fail-fast валидация `embedder.dim == vector_store.dim`**
**Почему первой:** Меняет `core/config.py` — фундамент. Если сломаем, тесты сразу покажут на старте.

**Файлы:** `src/ai_assistant/core/config.py`  
**Тест:** `dev/tests/test_api_deps.py`

2. **Security — `get_expected_api_key` ломается при `AI_API_KEY=""`**
**Почему второй:** `security.py` — изолированный модуль, нет зависимостей от других задач. Тесты простые.

**Файлы:** `src/ai_assistant/api/security.py`  
**Тест:** `dev/tests/test_security.py`

3. **Metrics — `record_metric` не валидирует тип значения**
**Почему третьей:** `core/metrics.py` — тоже изолирован, но зависит от `logger.py`. После security, чтобы не мешать.

**Файлы:** `src/ai_assistant/core/metrics.py`  
**Тест:** `dev/tests/test_metrics.py`

4. **Pipeline steps — константы ошибок вместо magic strings**
**Почему четвёртой:** Меняет `core/domain/errors.py` + `pipeline/steps.py`. До docstring-задачи, чтобы сначала стабилизировать код, потом документировать.

**Файлы:** `src/ai_assistant/core/domain/errors.py`, `src/ai_assistant/pipeline/steps.py`  
**Тест:** `dev/tests/test_rag_pipeline.py`

5. **Pipeline steps — docstring контракты metadata**
**Почему пятой:** Только документация, зависит от задачи 4 (константы уже введены, код стабилен). Не ломает тесты.

**Файлы:** `src/ai_assistant/pipeline/steps.py`  
**Тест:** Не нужен

6. **ChatManager — убрать дублирование `_maybe_rag` prefix regex**
**Почему шестой:** Меняет `core/constants.py` + `features/chat/manager.py` + `dev/scripts/check_rag.py`. После pipeline, чтобы не конфликтовать с `steps.py`.

**Файлы:** `src/ai_assistant/core/constants.py`, `src/ai_assistant/features/chat/manager.py`, `dev/scripts/check_rag.py`  
**Тест:** `dev/tests/test_chat_manager_direct.py`

7. **ToolRegistry — `dispatch` не логирует имя несуществующего инструмента**
**Почему седьмой:** `core/tool_registry.py` — изолирован, но после pipeline и chat, чтобы core-изменения шли пачкой.

**Файлы:** `src/ai_assistant/core/tool_registry.py`  
**Тест:** `dev/tests/test_core_critical.py`

8. **RAG handlers — `reindex` не очищает завершённые задачи из `_reindex_tasks`**
**Почему восьмой:** `features/rag/handlers.py` — зависит от задачи 6 (если менялся `check_rag.py`, лучше стабилизировать). Также memory leak — важно, но не критично для тестов.

**Файлы:** `src/ai_assistant/features/rag/handlers.py`  
**Тест:** `dev/tests/test_api_e2e.py`

9. **Lifespan — `_async_cleanup` не логирует успешное сохранение индексов**
**Почему девятой:** `api/lifespan.py` — зависит от задачи 8 (reindex cleanup), чтобы не пересекаться с task-логикой. Логирование — не ломает API.

**Файлы:** `src/ai_assistant/api/lifespan.py`  
**Тест:** `dev/tests/test_lifespan.py`

10. **OpenAI-compatible handlers — `list_models` не кэширует результат**
**Почему последней:** `features/chat/handlers.py` — чистая оптимизация, никаких зависимостей. Если что-то пойдёт не так, не сломает остальное.

**Файлы:** `src/ai_assistant/features/chat/handlers.py`  
**Тест:** `dev/tests/test_api_e2e.py`



---


## Фаза 2: Надёжность (после гигиены)

| # | Задача | Почему | Файлы |
|---|--------|--------|-------|
| 2.1 | PipelineData — глубокая immutability | `data.chunks.append()` работает тихо, frozen не спасает | `core/domain/pipeline.py` |
| 2.2 | Retry в `embed_query` / `retrieve` | Сетевой embedder падает → весь RAG мёртв | `pipeline/steps.py`, `core/retry.py` |
| 2.3 | Circuit breaker для LLM | Сервер лежит → бесконечные таймауты | новый `core/circuit_breaker.py` |
| 2.4 | Убрать `**kwargs` из портов | Ломает type checking, скрытые контракты | `core/ports/*.py` |
| 2.5 | Graceful degradation при `vector_store = None` | Сейчас 500-я ошибка, должно быть "RAG недоступен" | `features/chat/manager.py` |

---

## Фаза 3: Производительность

| # | Задача | Триггер | Файлы |
|---|--------|---------|-------|
| 3.1 | Batch embedding при индексации | 1000 документов = 1000 HTTP-запросов | `features/rag/indexing.py` |
| 3.2 | Pagination для chat history | 10k сообщений → тормоза | `adapters/storage_sqlite.py` |
| 3.3 | Asyncio gather для RAG steps | embed + retrieve последовательно | `core/pipeline.py` |
| 3.4 | FAISS index — IVF при >100k | Правила запрещают до 100k, потом нужно | `adapters/vector_store_faiss.py` |
| 3.5 | Кэширование `get_prompt()` | Jinja2 рендерит каждый раз | `core/prompts/__init__.py` |

---

## Фаза 4: Фичи (без нарушения правил)

| # | Задача | Блокер сейчас | Файлы |
|---|--------|---------------|-------|
| 4.1 | Streaming RAG (chunks → LLM) | Нет `IModalityPipeline` — правильно | `pipeline/steps.py` + новый step |
| 4.2 | Multi-modal chat (текст + картинка) | Vision port — заглушка | `features/chat/manager.py` |
| 4.3 | Tool calling с циклами (ReAct) | `ToolRegistry.dispatch` — один shot | `features/chat/manager.py` |
| 4.4 | Conversation memory (LTM) | `ILongTermMemory` есть, но не интегрирован | `features/chat/manager.py` |
| 4.5 | RAG namespace auto-detection | Префиксы `[p]` ручные | `features/chat/manager.py` |

---

## Фаза 5: Инфраструктура (когда проект стабилен)

| # | Задача | Когда нужно | Файлы |
|---|--------|-------------|-------|
| 5.1 | Миграции БД (alembic/ручные) | Схема меняется, `init_db()` не масштабируется | `dev/migrations/` |
| 5.2 | Prometheus metrics endpoint | Нужна observability | `api/admin.py` |
| 5.3 | Health check с dependency probe | `/health` сейчас тупой "ok" | `api/router.py` |
| 5.4 | Graceful shutdown с drain | Сейчас `await` без таймаута на active tasks | `api/lifespan.py` |
| 5.5 | Docker image + compose | Деплой | `Dockerfile`, `docker-compose.yml` |




### ЧТО МЕНЯТЬ ПО МЕРЕ ВЫПОЛНЕНИЯ ФАЗ 1-5
| Файл                | Фаза 1   | Фаза 2  | Фаза 3  | Фаза 4  | Фаза 5  |
| ------------------- | -------- | ------- | ------- | ------- | ------- |
| `src/**/*.py`       | ✅        | ✅       | ✅       | ✅       | ✅       |
| `dev/tests/*.py`    | ✅        | ✅✅      | ✅       | ✅       | ✅       |
| `dev/scripts/*.py`  | ✅ (1 шт) | ❌       | ❌       | ❌       | ❌       |
| `dev/AI_RULES.md`   | ❌        | ✅       | ✅       | ❌       | ❌       |
| `README.md`         | ❌        | ❌       | ❌       | ✅       | ❌       |
| `dev/README_DEV.md` | ❌        | ❌       | ❌       | ❌       | ✅       |
| `ERROR_TAXONOMY.md` | \[AUTO]  | \[AUTO] | \[AUTO] | \[AUTO] | \[AUTO] |
