[х] Фабрика `create_app(state=None, lifespan=None)` | Убрать глобальный `app = FastAPI(...)`, тесты создают свой app без хаков | `main.py` | `test_api_deps.py`, `conftest.py`
[х] Переписать фикстуру `client` | `app = create_app(state=mock_state)` внутри фикстуры, убрать `object.__setattr__` и патч `init_adapters` | `dev/tests/conftest.py` | все тесты
[х] Убрать `reset_global_state` | Через `create_app()` в каждом тесте сброс не нужен | `dev/tests/conftest.py` | все тесты
[х] Убрать inline retry из `generate()` step | Вынести LLM-вызов в `_call_llm()` с `@with_retry` | `pipeline/steps.py` | `test_rag_pipeline.py`
[х] Убрать мутацию config в рантайме | `state.config.security.api_key = req.api_key` → удалить | `api/admin.py` | `test_security.py`
[х] Сделать `ToolResult` frozen dataclass | ⚠️ CORE CHANGE: `core/ports/tools.py`. Заменить `@dataclass` на `@dataclass(frozen=True)`. Все мутации полей (`result.error = ...`, `result.is_error = ...`) заменить на создание нового экземпляра `ToolResult(...)`. Внимание: `core/tool_registry.py` содержит логику диспетчеризации (Known Unknown) — перед изменением запросить его код. | `core/ports/tools.py`, `core/tool_registry.py` | `dev/tests/test_core_critical.py`, `dev/tests/test_contracts.py`
[х] Добавить `finally: os.unlink(tmp)` в `atomic_write` | Упрощение cleanup | `core/io_utils.py` | `test_core_critical.py`
[х] Graceful degradation при недоступном LLM | 500 → 503 + текст | `pipeline/steps.py`, `features/chat/handlers.py` | `test_resilience.py`
[х] TTL cleanup `_reindex_status` | `if len > 1000: pop oldest` | `features/rag/handlers.py` | `test_api_e2e.py`
[х] Backpressure в MetricsLogger | `sys.stderr.write` при drop | `core/metrics.py` | `test_metrics.py`
[х] OpenAI `content: str | list[dict]` | Vision-совместимость | `features/chat/schemas.py`, `features/chat/handlers.py` | `test_api_e2e.py`
[х] Добавить `shutdown()` в `IEmbedder` и `IVectorStore` | ⚠️ CORE CHANGE: порты должны наследовать `IClosable`. Добавить метод `async def shutdown(self) -> None` в оба абстрактных класса. Реализовать во всех адаптерах: `embedder_mock`, `embedder_openai_compatible` (закрыть HTTP-сессии), `vector_store_memory`, `vector_store_faiss` (закрыть индексы). В `api/lifespan.py` расширить graceful shutdown: добавить вызов `shutdown()` для `state.embedder` и `state.vector_store` (сейчас обрабатывается только `llm`). | `core/ports/embedder.py`, `core/ports/vector_store.py`, `adapters/embedder_*.py`, `adapters/vector_store_*.py`, `api/lifespan.py` | `dev/tests/test_contracts.py`, `dev/tests/test_lifespan.py`
[х] Убрать импорт pipeline.steps из ChatManager | Использовать RAGPipeline из AppState | `features/chat/manager.py` | `test_chat_manager_direct.py`
[х] Явные импорты features в router.py или тест compile-time | Динамический importlib скрывает ошибки до runtime | `api/router.py` | `test_smoke_pyproject.py`
[х] PipelineData: убрать `frozen=True` и `object.__setattr__` | Перевести `PipelineData` на обычный `@dataclass` (без `frozen`). Удалить `__post_init__` с принудительной заморозкой через `object.__setattr__`. Убрать `MappingProxyType` для metadata. Оставить хелперы `with_*` / `add_error`, но реализовать их через `dataclasses.replace()` без магии. Это устраняет хрупкий обход frozen-контракта и упрощает чтение кода. | `core/domain/pipeline.py` | `dev/tests/test_core_critical.py`
[х] Убрать глобальный `_static_mounted` | Удалить модуль-level флаг `_static_mounted` из `main.py`. В `_mount_static` проверять наличие маршрута `/ui` в `app.routes` или хранить флаг в `app.state.static_mounted`. Исправляет скрытый баг при создании нескольких инстансов `create_app()` в тестах. | `main.py` | `dev/tests/test_smoke.py`
[х] Сузить `except Exception` до конкретных типов в `init_adapters` | В `api/deps.py` заменить голые `except Exception:` на `except (ImportError, ValueError):` при создании опциональных адаптеров (tools, storage, memory). Не ловить `AttributeError`, `TypeError`, `KeyError` — они сигнализируют о баге, а не об отсутствии зависимости. Приложение должно падать при старте с честным traceback, если конфигурация сломана. | `api/deps.py` | `dev/tests/test_lifespan.py`, `dev/tests/test_deps.py`
[х] Удалить `core/circuit_breaker.py` и его использование | Удалить модуль `core/circuit_breaker.py`. Проверить и вычистить импорты/использование `CircuitBreaker`, `with_circuit_breaker` во всём проекте (включая тесты). Для локального solo-сервера circuit breaker — преждевременная сложность. | `core/circuit_breaker.py`, проверить `adapters/*`, `core/retry.py` | `dev/tests/test_resilience.py` (удалить или очистить)
[х] Удалить `MetricsMiddleware` и `MetricsLogger` | Убрать `MetricsMiddleware` из `main.py` и `api/deps.py`. Удалить `MetricsLogger` из `api/lifespan.py` и связанные импорты (`get_current_metrics`). Заменить на простое `logging.info` с latency в одном месте или убрать полностью. Убирает enterprise-мёртвый вес. | `api/deps.py`, `api/lifespan.py`, `main.py` | `dev/tests/test_smoke.py`
[х] Упростить security-слой: убрать дублирующее middleware | Оставить единый механизм авторизации — `require_api_key` как FastAPI dependency. Удалить `APIKeyMiddleware` (класс) из цепочки middleware в `main.py` — dependency уже покрывает все защищённые роуты. Удалить самописный `SecurityLimiter` / `LimitMiddleware` (in-memory rate limiter): для solo-local сервера это тупиковая архитектура; если понадобится, заменить на `slowapi` позже. | `api/security.py`, `main.py` | `dev/tests/test_security.py`
[х] Удалить voice/vision/long_term_memory из ядра и инициализации | Убрать поля `voice_recognizer`, `voice_synthesizer`, `vision`, `long_term_memory`, `tool_registry` из `AppState`. Удалить соответствующие порты из `core/ports/__init__.py` (или закомментировать для отдельной git-ветки). Убрать блоки инициализации в `init_adapters`. Оставить код voice/vision в git-ветке `feature/voice-vision`, чтобы не раздувать core неработающими абстракциями. | `api/deps.py`, `core/ports/__init__.py` | `dev/tests/test_contracts.py`
[х] Убрать `slots=True` и кучу `Optional` в `AppState` | Удалить `slots=True` из `AppState` (добавляет гибкость для тестов и отладки). Разделить на два класса: `AppState` для старта и `InitializedAppState` для runtime, где поля `llm`, `embedder`, `vector_store`, `pipeline`, `storage` — обязательны (не `None`). Это убирает необходимость в `getattr(app.state, ...)` с дефолтами и ловит неинициализированный стейт на этапе типизации, а не в рантайме. | `api/deps.py` | `dev/tests/test_contracts.py`, `dev/tests/test_smoke.py`
[х] Явные импорты features в `router.py` (убрать reflection) | В `api/router.py` заменить цикл `for attr_name in ("router", "router_oai", "router_legacy"): getattr(module, ...)` на явный список/словарь импортов: `_ROUTERS = [_chat_handlers.router, ...]`. Ловит ошибки на этапе импорта, а не в runtime при первом запросе. | `api/router.py` | `dev/tests/test_smoke.py`
[х] Убрать прямой импорт `pipeline.steps` из `ChatManager` | В `features/chat/manager.py` убрать любые импорты из `pipeline.steps`. Вместо создания pipeline внутри менеджера принимать готовый `RAGPipeline` (retrieval pipeline) через конструктор из `AppState`. `deps.py` уже передаёт `retrieval_pipeline`, но нужно убедиться, что менеджер не тянет шаги напрямую. | `features/chat/manager.py` (запросить код перед правкой) | `test_chat_manager.py`
[х] Добавить `shutdown()` в `IEmbedder` и `IVectorStore` | ⚠️ CORE CHANGE: порты должны наследовать `IClosable`. Добавить `async def shutdown(self) -> None` в `IEmbedder` и `IVectorStore`. Реализовать во всех адаптерах: `embedder_mock`, `embedder_openai_compatible` (закрыть HTTP-сессии), `vector_store_memory`, `vector_store_faiss` (закрыть индексы). В `api/lifespan.py` расширить graceful shutdown: добавить вызов `shutdown()` для `state.embedder` и `state.vector_store` (сейчас обрабатывается только `llm`). | `core/ports/embedder.py`, `core/ports/vector_store.py`, `adapters/embedder_*.py`, `adapters/vector_store_*.py`, `api/lifespan.py` | `dev/tests/test_contracts.py`, `dev/tests/test_lifespan.py`
[х] Убить pipeline step registry (`@step`) → явные импорты | ⚠️ CORE CHANGE: удалить `pipeline/decorators.py` (файл `@step` / `get_step`). В `api/deps.py` в `_build_step_funcs` импортировать шаги напрямую: `from ai_assistant.pipeline.steps import embed_query_step, retrieve_step, ...` и собирать список функций явно. Убрать строковые имена шагов из `rag.steps` в конфиге (или заменить на enum для документации). Убирает глобальное mutable-состояние `_step_registry`. | `pipeline/decorators.py`, `api/deps.py`, `core/config.py` | `dev/tests/test_pipeline.py`, `dev/tests/test_core_critical.py`
[х] Убить Adapter Registry (`@register`) → фабрика if/else | ⚠️ CORE CHANGE: удалить `core/registry.py`. Создать `adapters/factory.py` с явной фабрикой `create_adapter(port, name, config)` через `if/elif` + lazy import (через `importlib` внутри функции). Убрать `@register` из всех адаптеров. Убрать массовые side-effect импорты из `api/deps.py` (типа `import ai_assistant.adapters.llm_mock`). Адаптеры импортируются только внутри фабрики по требованию. | `core/registry.py`, `adapters/factory.py` (создать), `adapters/__init__.py`, `api/deps.py`, все `adapters/*.py` | `dev/tests/test_contracts.py`, `dev/tests/test_smoke.py`
[х] Оборачивать CPU-bound вызовы в `asyncio.to_thread()` | Все синхронные тяжёлые операции (FAISS index search/add, tiktoken encoding, локальные CPU-вычисления) должны выполняться через `asyncio.to_thread()` или `anyio.to_thread.run_sync()` внутри адаптеров. Это предотвращает блокировку event loop uvicorn при локальном CPU-inference. Начать с `vector_store_faiss.py` (search/add) и `embedder_openai_compatible.py` (batch embed). | `adapters/vector_store_faiss.py`, `adapters/embedder_openai_compatible.py`, `core/utils.py` (если есть токенизация) | `dev/tests/test_rag.py`, `dev/tests/test_adapters.py`

[х] Tool loop guard — max 5 итераций | LLM при malformed tool_calls уходит в infinite loop → процесс висит. Добавить max_tool_iterations: int = 5 в config.yaml (rag section), проверять в generate() перед while response.tool_calls. При превышении — return data.add_error(...).with_response(AssistantMessage(text="Tool limit reached")). | pipeline/steps.py (generate()), core/config.py (RAGConfig.max_tool_iterations), config.yaml | test_rag_pipeline.py, test_chat_manager_direct.py
[х] CJK token count fallback | count_tokens() fallback len(text)//4 занижает в 4 раза для китайского/японского → prompt обрезается, LLM получает бред. Детектировать CJK ratio (sum(1 for c in text if '\u4e00' <= c <= '\u9fff') / len(text)), если > 0.3 — использовать len(text) вместо len(text)//4. | core/utils.py (count_tokens()), dev/tests/test_tokenizer.py | test_tokenizer.py, test_rag_pipeline.py (с CJK query)
[х] Rerank metadata cleanup | rerank_scores/rerank_filtered_out остаются в metadata при reranker=None (pass-through) → следующий запрос видит старые данные. При reranker=None очищать rerank_* ключи из metadata перед return data. | pipeline/steps.py (rerank(), строка if reranker is None:) | test_rag_pipeline.py (два запуска подряд, проверить metadata чист)
[х] Step registry в config | Новые pipeline-шаги (hyde, multi_retrieve) требуют правки _STEP_MAP в api/deps.py — 3 файла на каждый шаг. Сделать RAGStep registry: RAGStep StrEnum + _STEP_MAP: dict[RAGStep, Callable] → добавить шаг = 1 строка в _STEP_MAP, конфигурация через rag.steps: [embed_query, hyde_query, retrieve, ...]. | core/config.py (RAGStep), api/deps.py (_STEP_MAP → dynamic), pipeline/steps.py (добавить hyde_query как пример) | test_api_deps.py, test_rag_pipeline.py (кастомный pipeline из config)
[х] Per-namespace config block | Новые namespace'ы ([c]ode, [b]ooks) требуют копировать RAG_NS_MAP + relevance_threshold глобальный. Сделать config.yaml: namespaces: personal: {threshold: 0.1, chunk_size: 512, prompt: rag_strict}, work: {threshold: 0.3, chunk_size: 1024, prompt: rag_creative}. ChatManager._maybe_rag читает state.config.namespaces[namespace] вместо глобальных значений. | core/config.py (NamespaceConfig dataclass), config.yaml, features/chat/manager.py (_maybe_rag()), features/rag/handlers.py | test_chat_manager_direct.py, test_api_e2e.py
[х] Prompt version в config (не hardcoded v1) | Новые промпты (rag_coding.j2) требуют правки кода для добавления директории v2/. Сделать config.yaml: rag.prompt_version: v1 → get_prompt() использует эту версию. Новый промпт = mkdir core/prompts/v1/rag_coding.j2, правка config.yaml. | core/config.py (RAGConfig.prompt_version уже есть, убедиться что используется везде), core/prompts/__init__.py (убрать hardcoded "v1" в fallback), features/chat/manager.py, features/rag/manager.py | test_core_critical.py, test_api_e2e.py (смена версии в config)








111111111111111111111


**Промпт: Полная зачистка заглушек voice/vision из кодовой базы**

Задача: удалить все остатки voice/vision/image-заглушек, которые больше не используются в production-коде. Проект — AI Assistant (Python, FastAPI, hexagonal architecture). Текущий стек: chat + RAG, нет voice/vision.

**Файлы для изменения:**

1. **`src/ai_assistant/core/domain/messages.py`**
   - Удалить `ImagePayload` и `VoicePayload` dataclasses
   - Упростить `UserMessage.__post_init__`: проверять только `text is None` (единственный payload)
   - Обновить `__all__`

2. **`src/ai_assistant/core/domain/__init__.py`**
   - Убрать `ImagePayload` и `VoicePayload` из импортов и `__all__`

3. **`src/ai_assistant/features/chat/schemas.py`**
   - Удалить поля `image_url`, `image_base64`, `voice_base64` из `ChatRequest`
   - Удалить валидатор `_validate_base64` (больше не нужен)
   - Убедиться, что `ChatStreamChunk` не затронут

4. **`src/ai_assistant/features/chat/handlers.py`**
   - Убрать передачу `image_url`, `image_base64`, `voice_base64` в `chat_manager.chat()` и `chat_manager.stream_chat()`
   - Удалить функцию `_extract_content` (использовалась для image из OpenAI-формата)
   - Упростить OpenAI-compatible endpoints: content всегда `str`, не `list[dict]`

5. **`src/ai_assistant/features/chat/manager.py`**
   - Убрать параметры `image_url`, `image_base64`, `voice_base64` из `chat()` и `stream_chat()`
   - Убрать передачу `image=original_image` в `UserMessage` в `pipeline/steps.py` (generate step)

6. **`src/ai_assistant/pipeline/steps.py`**
   - Убрать `original_image = data.query.image if data.query else None` и передачу `image=original_image` в `UserMessage`

7. **`src/ai_assistant/core/prompts/v1/voice_transcribe.j2`**
   - Удалить файл (orphaned asset)

8. **`dev/tests/conftest.py`**
   - Убрать `voice_recognizer`, `voice_synthesizer`, `vision`, `tool_registry`, `long_term_memory` из `mock_state` (уже закомментировано, но проверить)
   - Убедиться, что `ChatManager` создаётся без image/voice параметров

9. **`dev/tests/test_api_e2e.py`**
   - Удалить тесты `test_with_image_base64`, `test_with_image_url`, `test_stream_with_image` из `TestChatOffline`
   - Удалить тесты `test_chat_completions_with_image_url`, `test_chat_completions_with_image_base64`, `test_chat_completions_stream_with_image` из `TestOpenAICompatibleOffline`

10. **`dev/scripts/check_smoke.py`**
    - Убрать строки:
      ```python
      mock.config.voice.enabled = False
      mock.config.vision.enabled = False
      mock.vision = None
      mock.voice_recognizer = None
      mock.voice_synthesizer = None
      ```
    - Убрать `tool_registry` из mock если он там есть

11. **`README.md`** (если редактируется вручную)
    - Убрать строки:
      ```
      - 🖼️ Анализ изображений (заглушка, требует настройки)
      - 🔊 Голосовой ввод/вывод (заглушка, требует настройки)
      ```

**Критические правила:**
- Не трогать `TextPayload` — он используется внутри `UserMessage` (хотя и неявно)
- Не трогать `ToolSpec`/`ToolCall`/`ToolResult` в `core/ports/tools.py` — tool calling работает через LLM, это не заглушка
- Не трогать `api/admin.py`, `api/security.py`, `api/router.py`, `api/lifespan.py`, `api/static.py` — не затронуты
- После каждого файла — команда `pytest dev/tests/ -x -q` для проверки
- Если тест падает — фиксить в том же коммите (правило "no orphaned tests")

**Формат ответа:**
1. What and Why — 1-2 предложения
2. Changes — FIND/REPLACE блоки или полный файл
3. Verification — `pytest` команды

---









2222222222222222222222222



**Промпт: Зачистка check_smoke.py — удаление references к удалённым voice/vision/tool_registry**

Задача: починить `dev/scripts/check_smoke.py` — он ссылается на поля `voice`, `vision`, `voice_recognizer`, `voice_synthesizer`, `tool_registry`, которые были удалены из `AppConfig` и `AppState`. Скрипт сейчас упадёт при запуске из-за `AttributeError` на `mock.config.voice.enabled` и `mock.vision = None`.

**Файл для изменения:** `dev/scripts/check_smoke.py`

**Что нужно сделать:**

1. **В `make_mock_state()`** — удалить строки:
   ```python
   mock.config.voice.enabled = False
   mock.config.vision.enabled = False
   mock.vision = None
   mock.voice_recognizer = None
   mock.voice_synthesizer = None
   ```

2. **В `make_mock_state()`** — удалить `tool_registry` из mock (если tool_registry удалён из AppState):
   ```python
   mock.tool_registry = MagicMock()
   mock.tool_registry.register = lambda t: None
   mock.tool_registry.list_tools = lambda: []
   mock.tool_registry.execute = lambda c: MagicMock(output="tool", is_error=False)
   ```
   Проверить: если `tool_registry` удалён из `AppState` в `deps.py` — удалить и здесь. Если `IToolRegistry` port оставлен, но не используется в AppState — удалить из mock.

3. **В `check_http_endpoints()`** — проверить, что endpoint `"/api/v1/chat"` с `json={"message": "hi"}` работает без `Authorization` заголовка в тесте. Сейчас есть:
   ```python
   r4 = client.post("/api/v1/chat", json={"message": "hi"}, headers={"Authorization": "Bearer test"})
   ```
   Это ок, но убедиться, что `client` fixture из `conftest.py` уже добавляет `Authorization: Bearer test-key`.

4. **В `check_chat_manager()`** — убедиться, что `ChatManager` создаётся без `voice_recognizer`, `voice_synthesizer`, `vision`, `tool_registry` параметров. Сейчас:
   ```python
   mgr = ChatManager(llm=llm, embedder=embedder, vector_store=store, history_limit=10)
   ```
   Это корректно, но проверить сигнатуру `ChatManager.__init__` — если она изменилась после удаления параметров, обновить вызов.

5. **В `check_tools()`** — тест `mock_execute` создаёт `_MockTool` вручную. Это ок, но если `tool_registry` удалён из `AppState` — этот тест проверяет только `ToolResult` dataclass, не интеграцию. Решить: оставить как unit-test для `ToolResult` или удалить если бесполезен.

**Критические правила:**
- Не добавлять новые зависимости
- Не менять логику проверок — только удалить references к удалённым полям
- После изменения запустить: `python dev/scripts/check_smoke.py` — должен вернуть 0 (все 11 checks PASS)
- Если `check_tools()` больше не имеет смысла без `tool_registry` в `AppState` — удалить этот check из `main()` и из списка `run_check` вызовов

**Формат ответа:**
1. What and Why — 1-2 предложения
2. Changes — FIND/REPLACE блоки
3. Verification — `python dev/scripts/check_smoke.py` и `pytest dev/tests/test_smoke_pyproject.py -x -q`









333333333333333333333333

**Промпт: Синхронизация документации после удаления voice/vision заглушек**

Задача: обновить все документы проекта, чтобы они отражали актуальный функционал (chat + RAG, без voice/vision/image). Удалённые компоненты не должны упоминаться как "заглушки" или "возможности".

---

**Файлы для изменения:**

### 1. `README.md` — пользовательская документация

**Удалить из раздела "Возможности":**
```
- 🖼️ Анализ изображений (заглушка, требует настройки)
- 🔊 Голосовой ввод/вывод (заглушка, требует настройки)
```

**Обновить раздел "Быстрый старт":**
- Убрать упоминания voice/vision в примерах использования
- Проверить, что все примеры команд актуальны (chat + RAG только)

**Обновить раздел "Требования":**
- Убрать пункты про микрофон/камеру если были

---

### 2. `dev/README_DEV.md` — документация разработчика

**Проверить разделы:**
- **"Архитектурные принципы"** — убрать voice/vision из списка features
- **"Структура"** — убрать `features/voice/`, `features/vision/` если упоминались
- **"Ключевые файлы"** — убрать `voice_transcribe.j2` из примеров промптов
- **Troubleshooting** — убрать пункты про voice/vision ошибки

---

### 3. `dev/AI_RULES.md` — конституция проекта

**Проверить и обновить:**
- **Section 11 "Solo Project Guardrails"** — если там есть `IModalityPipeline` или voice/vision порты в списке запрещённого — убрать, они уже удалены
- **Section 2 "Absolute Constraints"** — убрать упоминания voice/vision-specific правил если были
- **Section 4 "Core Modification Protocol"** — убрать `IModalityPipeline` из примеров если есть

---

### 4. `dev/TODO.md` — список задач (если существует)

**Удалить/закрыть пункты:**
- "Реализовать voice input"
- "Добавить vision анализ"
- "Настроить TTS/STT"
- Перенести выполненные в раздел `## Done` с пометкой "removed — out of scope"

---

### 5. `config.yaml` — пример конфигурации

**Проверить:**
- Убрать секции `voice:` и `vision:` если остались
- Убрать `image_base64`, `voice_base64` из примеров
- Проверить, что `namespaces` актуальны (personal, work, other, code, books)

---

### 6. `dev/tests/config.test.yaml` — тестовая конфигурация

**Проверить:**
- Убрать `voice.enabled`, `vision.enabled` если есть
- Убедиться, что `chat` секция не ссылается на voice/vision параметры

---

### 7. `pyproject.toml` — манифест проекта

**Проверить:**
- Убрать voice/vision зависимости из `dependencies` или `optional-dependencies` если были (например, `speechrecognition`, `pyttsx3`, `pillow` и т.д.)
- Проверить `tool.mypy.overrides` — убрать модули voice/vision если есть

---

### 8. `dev/ERROR_TAXONOMY.md` — [AUTO], но проверить после генерации

**После запуска `python dev/scripts/context_build.py`:**
- Убедиться, что ошибки voice/vision не появляются в таблице
- Если появляются — значит остатки в коде, вернуться к зачистке

---

### 9. `dev/launcher.py` — меню лаунчера

**Проверить:**
- Убрать voice/vision скрипты из `SCRIPT_ORDER` или `TEST_FLAGS` если были

---

### 10. `.gitignore` — если есть voice/vision-specific игноры

**Проверить:**
- Убрать `*.wav`, `*.mp3`, `*.png` из `.gitignore` если добавлялись специально для voice/vision

---

**Критические правила:**
- Не добавлять новый функционал — только удалять упоминания удалённого
- Не менять архитектурные принципы в `AI_RULES.md` — только убрать устаревшие примеры
- `ERROR_TAXONOMY.md` — [AUTO], не редактировать руками, только проверить после `context_build.py`
- После всех изменений запустить: `python dev/scripts/context_build.py` и убедиться, что `voice_transcribe.j2`, `ImagePayload`, `VoicePayload` не упоминаются

**Формат ответа:**
1. What and Why — 1-2 предложения
2. Changes — FIND/REPLACE блоки или полный файл (если >3 строк)
3. Verification — `python dev/scripts/context_build.py` + `pytest dev/tests/ -x -q`

---

**Порядок выполнения:**
1. `README.md`
2. `dev/README_DEV.md`
3. `dev/AI_RULES.md`
4. `config.yaml`
5. `dev/tests/config.test.yaml`
6. `pyproject.toml` (проверить)
7. `dev/TODO.md` (если есть)
8. `python dev/scripts/context_build.py` — финальная проверка

---





















ЗАТЕМ новые фичи через config.yaml или новый файл в adapters/
