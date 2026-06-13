Выдай список todo по одной строке в формате: [ ] Название + Краткая суть | Подробное описание (что, зачем, и ⚠️ CORE CHANGE если критично) | Файлы для правки | Файлы тестов / где проверять

===============================================================================
# TODO
===============================================================================


## ПРОМПТ 1: АРХИТЕКТУРНЫЙ СКЕЛЕТ — Imports, Boundaries, DI

**Цель:** Убедиться, что слои не протекают и зависимости направлены правильно. Любое нарушение здесь — технический долг на десятилетия.

**Прикрепить:**
- `src/ai_assistant/api/deps.py`
- `src/ai_assistant/api/router.py`
- `src/ai_assistant/api/lifespan.py`
- `src/ai_assistant/core/__init__.py`
- `src/ai_assistant/core/config.py`
- `src/ai_assistant/main.py`
- `context_build_compact.md`

**Проверить:**
1. `core/` импортирует только stdlib (§3)
2. `adapters/` импортирует только `core/*` (§3)
3. `features/` импортирует только `api.deps`, `core/*`, self (§3)
4. `api/` импортирует `core/`, `adapters/`, `features/`, self (§3)
5. Нет циклических зависимостей между модулями
6. Нет cross-feature imports (§2)
7. `AppState` — нет lazy init (`dict[str, Callable]`), нет mutable defaults (§2)
8. Router assembly — явная, не magic discovery (§11)
9. `config.py` в `core/` — Pydantic разрешён здесь, но проверить, что `core/domain/` его не использует

**Формат:** Нарушение → What/Why, Severity, File:Line, Fix (FIND/REPLACE), Verification (grep/pytest).

---

## ПРОМПТ 2: CORE DOMAIN — Immutability, Ports, Contracts

**Цель:** Убедиться, что домен — это камень. Любая мутация здесь разрушает всё выше.

**Прикрепить:**
- `src/ai_assistant/core/domain/pipeline.py`
- `src/ai_assistant/core/domain/documents.py`
- `src/ai_assistant/core/domain/messages.py`
- `src/ai_assistant/core/domain/errors.py`
- `src/ai_assistant/core/domain/configs.py`
- `src/ai_assistant/core/ports/chunker.py`
- `src/ai_assistant/core/ports/closable.py`
- `src/ai_assistant/core/ports/embedder.py`
- `src/ai_assistant/core/ports/initializable.py`
- `src/ai_assistant/core/ports/llm.py`
- `src/ai_assistant/core/ports/reranker.py`
- `src/ai_assistant/core/ports/storage.py`
- `src/ai_assistant/core/ports/tools.py`
- `src/ai_assistant/core/ports/vector_store.py`
- `src/ai_assistant/core/ports/__init__.py`
- `context_build_compact.md`

**Проверить:**
1. Все dataclass — `frozen=True`, `slots=True` (§2)
2. Нет Pydantic в `core/domain/` — только stdlib dataclass (§2)
3. `PipelineData` — только `.with_*()`, `.add_error()`, нет прямой мутации (§5)
4. Порты — нет `**kwargs`, нет `hasattr`/`isinstance`, нет `Any` где виден конкретный тип (§2, §9)
5. Все методы портов — `@abstractmethod` где нужно
6. `IClosable`, `IInitializable` — корректны как mixins
7. `Message` union-type — корректно собран
8. `RerankerConfigData` — корректен и используется консистентно

**Формат:** Нарушение → What/Why, Severity, File:Line, Fix, Verification.

---

## ПРОМПТ 3: PIPELINE — Purity, Retry, Error Handling

**Цель:** Pipeline — сердце. Любой side effect или необработанная ошибка здесь = data loss или silent corruption.

**Прикрепить:**
- `src/ai_assistant/core/pipeline.py`
- `src/ai_assistant/core/pipeline_steps.py`
- `src/ai_assistant/core/retry.py`
- `src/ai_assistant/core/domain/errors.py`
- `context_build_compact.md`

**Проверить:**
1. Все шаги возвращают новый `PipelineData`, не мутируют (§5)
2. Нет `hasattr`/`isinstance` на портах в шагах (§2)
3. Metadata contract IN/OUT — документирован и соблюдён
4. Error handling — только `add_error()`, не raise внутри шагов (кроме `AdapterError` для 503) (§5)
5. Все external calls обернуты в `@with_retry` (§7)
6. `trace_id` в extra во всех логах (§9)
7. `generate()` — корректность token budgeting, truncation, fallback prompt
8. `rerank()` — `assert reranker is not None` заменить на явную проверку (assert отключается при `python -O`)
9. `_PERMANENT_ERRORS` в `retry.py` — корректная классификация

**Формат:** Нарушение → What/Why, Severity, File:Line, Fix, Verification.

---

## ПРОМПТ 4: АДАПТЕРЫ — Discipline, Registration, Drift

**Цель:** Адаптеры — граница с внешним миром. Любой костыль здесь протекает во все слои.

**Прикрепить:**
- `src/ai_assistant/adapters/chunker_simple.py`
- `src/ai_assistant/adapters/embedder_mock.py`
- `src/ai_assistant/adapters/embedder_openai_compatible.py`
- `src/ai_assistant/adapters/factory.py`
- `src/ai_assistant/adapters/llm_mock.py`
- `src/ai_assistant/adapters/llm_openai_compatible.py`
- `src/ai_assistant/adapters/reranker_api.py`
- `src/ai_assistant/adapters/reranker_null.py`
- `src/ai_assistant/adapters/storage_sqlite.py`
- `src/ai_assistant/adapters/vector_store_faiss.py`
- `src/ai_assistant/adapters/vector_store_memory.py`
- `src/ai_assistant/core/domain/errors.py`
- `context_build_compact.md`

**Проверить:**
1. Точное соответствие портам, нет duck typing (§6)
2. `@register("port", "name")` в factory (§6)
3. Library-specific exceptions → domain exceptions (`AdapterError`, `VersionMismatchError`) (§6)
4. `logger.exception` before wrapping (§6)
5. Нет `getattr(config, "x", default)` — прямой доступ (drift #4) (§2)
6. `@with_retry` на всех внешних вызовах (§7)
7. Hard timeout на всех external calls (§7)
8. Mock adapters живут в `adapters/`, не в test files (§2)
9. `NullReranker` — корректно реализует `IReranker`, не ломает pipeline
10. `FaissVectorStore` / `MemoryVectorStore` — `save`/`load` idempotent

**Формат:** Нарушение → What/Why, Severity, File:Line, Fix, Verification.

---

## ПРОМПТ 5: API СЛОЙ — FastAPI, Security, Lifespan, Static

**Цель:** API — лицо проекта. Уязвимость здесь = компрометация всего.

**Прикрепить:**
- `src/ai_assistant/api/deps.py`
- `src/ai_assistant/api/lifespan.py`
- `src/ai_assistant/api/security.py`
- `src/ai_assistant/api/middleware.py`
- `src/ai_assistant/api/router.py`
- `src/ai_assistant/api/admin.py`
- `src/ai_assistant/api/static.py`
- `src/ai_assistant/api/__init__.py`
- `src/ai_assistant/main.py`
- `config.yaml`
- `context_build_compact.md`

**Проверить:**
1. FastAPI DI — `Annotated[Depends()]`, нет `request: Any` (§9)
2. Security — нет hardcoded keys, API key rotation работает (§9)
3. `check_request_size` — корректность, не обходится
4. Lifespan — graceful shutdown: persist indices, adapter shutdown, timeout на каждом (§8)
5. Middleware — metrics без утечек, thread-safe
6. Static files — `mount_static` без path traversal
7. Admin endpoints — защита, валидация
8. CORS — не разрешает `*` в production (проверить `config.yaml`)
9. `get_state` — не возвращает `AppState` вместо `InitializedAppState`

**Формат:** Нарушение → What/Why, Severity, File:Line, Fix, Verification.

---

## ПРОМПТ 6: FEATURES — Chat & RAG, Handlers & Managers

**Цель:** Features — бизнес-логика. Cross-feature import = спагетти через 2 года.

**Прикрепить:**
- `src/ai_assistant/features/chat/handlers.py`
- `src/ai_assistant/features/chat/schemas.py`
- `src/ai_assistant/features/chat/manager.py`
- `src/ai_assistant/features/rag/handlers.py`
- `src/ai_assistant/features/rag/schemas.py`
- `src/ai_assistant/features/rag/manager.py`
- `src/ai_assistant/features/rag/indexing.py`
- `context_build_compact.md`

**Проверить:**
1. Нет cross-feature imports — chat не импортирует rag напрямую, и наоборот (§2, §3)
2. Business logic в managers, не в handlers (§11)
3. Error handling — в handlers, не в managers
4. Streaming — корректность SSE, heartbeat, cleanup (нет утечки задач)
5. OpenAI-compatible endpoints — корректность формата
6. RAG `save-chat` — path traversal защита
7. Background reindex — semaphore, cleanup, TTL
8. Нет кириллицы в .py (кроме domain constants) (§9)
9. `ChatManager` — корректность history trimming, token budgeting
10. Namespace prefix parsing — `RAG_PREFIX_RE` используется консистентно

**Формат:** Нарушение → What/Why, Severity, File:Line, Fix, Verification.

---

## ПРОМПТ 7: ТЕСТЫ — Coverage, Mocks, Contracts, Config Fidelity

**Цель:** Тесты — единственная защита от регрессий. Orphaned test = мёртвый код.

**Прикрепить:**
- Все файлы в `tests/`
- `src/ai_assistant/core/domain/configs.py`
- `src/ai_assistant/adapters/factory.py`
- `config.yaml`
- `pyproject.toml`
- `context_build_compact.md`

**Проверить:**
1. Mock adapters — живут в `adapters/`, не в test files (§2, §6)
2. `test_chat.py` — `RerankerConfigData` импортирован (уже фиксили, проверить)
3. `test_contracts.py` — `core/prompts.py` not found (skipped) — почему, нужен ли фикс
4. `test_smoke.py` — `config.test.yaml` not found (skipped) — нужен ли файл
5. Test independence — нет shared mutable state между тестами
6. Нет кириллицы в тестах (§9)
7. Нет `print()`, `logging.basicConfig()` в тестах (§2)
8. `conftest.py` — fixtures не ломают isolation
9. `pytest.ini` — `timeout` установлен, `asyncio_mode` корректен
10. `pyproject.toml` — зависимости актуальны, нет лишних
11. `config.yaml` ↔ `AppConfig` — полное соответствие полей, нет расхождений
12. 0 skipped — любой skip должен быть обоснован комментарием в коде или удалён

**Формат:** Нарушение → What/Why, Severity, File:Line, Fix, Verification.

---

## Как пользоваться

Запускаешь 7 чатов параллельно (или по очереди). Каждый — независим. После всех 7 — собираешь найденные issues, приоритизируешь, фиксишь пачками по 3 файла максимум (§11).

Если чат находит 0 нарушений — пишет "✅ CLEAN" и идёшь дальше. Если находит — фиксишь, перепроверяешь.

Это не оверинжиниринг. Это 7 аудитов на ~15 файлов каждый. Реально — 1-2 дня работы. Фундамент на десятилетия.
