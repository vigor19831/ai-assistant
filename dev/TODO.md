[+] Фабрика `create_app(state=None, lifespan=None)` | Убрать глобальный `app = FastAPI(...)`, тесты создают свой app без хаков | `main.py` | `test_api_deps.py`, `conftest.py`
[+] Переписать фикстуру `client` | `app = create_app(state=mock_state)` внутри фикстуры, убрать `object.__setattr__` и патч `init_adapters` | `dev/tests/conftest.py` | все тесты
[+] Убрать `reset_global_state` | Через `create_app()` в каждом тесте сброс не нужен | `dev/tests/conftest.py` | все тесты
[+] Убрать inline retry из `generate()` step | Вынести LLM-вызов в `_call_llm()` с `@with_retry` | `pipeline/steps.py` | `test_rag_pipeline.py`
[+] Убрать мутацию config в рантайме | `state.config.security.api_key = req.api_key` → удалить | `api/admin.py` | `test_security.py`
[+] Сделать `ToolResult` frozen dataclass | ⚠️ CORE CHANGE: `core/ports/tools.py`. Заменить `@dataclass` на `@dataclass(frozen=True)`. Все мутации полей (`result.error = ...`, `result.is_error = ...`) заменить на создание нового экземпляра `ToolResult(...)`. Внимание: `core/tool_registry.py` содержит логику диспетчеризации (Known Unknown) — перед изменением запросить его код. | `core/ports/tools.py`, `core/tool_registry.py` | `dev/tests/test_core_critical.py`, `dev/tests/test_contracts.py`
[+] Добавить `finally: os.unlink(tmp)` в `atomic_write` | Упрощение cleanup | `core/io_utils.py` | `test_core_critical.py`
[+] Graceful degradation при недоступном LLM | 500 → 503 + текст | `pipeline/steps.py`, `features/chat/handlers.py` | `test_resilience.py`
[+] TTL cleanup `_reindex_status` | `if len > 1000: pop oldest` | `features/rag/handlers.py` | `test_api_e2e.py`
[+] Backpressure в MetricsLogger | `sys.stderr.write` при drop | `core/metrics.py` | `test_metrics.py`
[+] OpenAI `content: str | list[dict]` | Vision-совместимость | `features/chat/schemas.py`, `features/chat/handlers.py` | `test_api_e2e.py`
[+] Добавить `shutdown()` в `IEmbedder` и `IVectorStore` | ⚠️ CORE CHANGE: порты должны наследовать `IClosable`. Добавить метод `async def shutdown(self) -> None` в оба абстрактных класса. Реализовать во всех адаптерах: `embedder_mock`, `embedder_openai_compatible` (закрыть HTTP-сессии), `vector_store_memory`, `vector_store_faiss` (закрыть индексы). В `api/lifespan.py` расширить graceful shutdown: добавить вызов `shutdown()` для `state.embedder` и `state.vector_store` (сейчас обрабатывается только `llm`). | `core/ports/embedder.py`, `core/ports/vector_store.py`, `adapters/embedder_*.py`, `adapters/vector_store_*.py`, `api/lifespan.py` | `dev/tests/test_contracts.py`, `dev/tests/test_lifespan.py`
[+] Убрать импорт pipeline.steps из ChatManager | Использовать RAGPipeline из AppState | `features/chat/manager.py` | `test_chat_manager_direct.py`
[+] Явные импорты features в router.py или тест compile-time | Динамический importlib скрывает ошибки до runtime | `api/router.py` | `test_smoke_pyproject.py`


=============================================

[-] PipelineData: убрать `frozen=True` и `object.__setattr__` | Перевести `PipelineData` на обычный `@dataclass` (без `frozen`). Удалить `__post_init__` с принудительной заморозкой через `object.__setattr__`. Убрать `MappingProxyType` для metadata. Оставить хелперы `with_*` / `add_error`, но реализовать их через `dataclasses.replace()` без магии. Это устраняет хрупкий обход frozen-контракта и упрощает чтение кода. | `core/domain/pipeline.py` | `dev/tests/test_core_critical.py`

[-] Убрать глобальный `_static_mounted` | Удалить модуль-level флаг `_static_mounted` из `main.py`. В `_mount_static` проверять наличие маршрута `/ui` в `app.routes` или хранить флаг в `app.state.static_mounted`. Исправляет скрытый баг при создании нескольких инстансов `create_app()` в тестах. | `main.py` | `dev/tests/test_smoke.py`

[-] Сузить `except Exception` до конкретных типов в `init_adapters` | В `api/deps.py` заменить голые `except Exception:` на `except (ImportError, ValueError):` при создании опциональных адаптеров (tools, storage, memory). Не ловить `AttributeError`, `TypeError`, `KeyError` — они сигнализируют о баге, а не об отсутствии зависимости. Приложение должно падать при старте с честным traceback, если конфигурация сломана. | `api/deps.py` | `dev/tests/test_lifespan.py`, `dev/tests/test_deps.py`

[-] Удалить `core/circuit_breaker.py` и его использование | Удалить модуль `core/circuit_breaker.py`. Проверить и вычистить импорты/использование `CircuitBreaker`, `with_circuit_breaker` во всём проекте (включая тесты). Для локального solo-сервера circuit breaker — преждевременная сложность. | `core/circuit_breaker.py`, проверить `adapters/*`, `core/retry.py` | `dev/tests/test_resilience.py` (удалить или очистить)

=============================================

[-] Удалить `MetricsMiddleware` и `MetricsLogger` | Убрать `MetricsMiddleware` из `main.py` и `api/deps.py`. Удалить `MetricsLogger` из `api/lifespan.py` и связанные импорты (`get_current_metrics`). Заменить на простое `logging.info` с latency в одном месте или убрать полностью. Убирает enterprise-мёртвый вес. | `api/deps.py`, `api/lifespan.py`, `main.py` | `dev/tests/test_smoke.py`

[-] Упростить security-слой: убрать дублирующее middleware | Оставить единый механизм авторизации — `require_api_key` как FastAPI dependency. Удалить `APIKeyMiddleware` (класс) из цепочки middleware в `main.py` — dependency уже покрывает все защищённые роуты. Удалить самописный `SecurityLimiter` / `LimitMiddleware` (in-memory rate limiter): для solo-local сервера это тупиковая архитектура; если понадобится, заменить на `slowapi` позже. | `api/security.py`, `main.py` | `dev/tests/test_security.py`

[-] Удалить voice/vision/long_term_memory из ядра и инициализации | Убрать поля `voice_recognizer`, `voice_synthesizer`, `vision`, `long_term_memory`, `tool_registry` из `AppState`. Удалить соответствующие порты из `core/ports/__init__.py` (или закомментировать для отдельной git-ветки). Убрать блоки инициализации в `init_adapters`. Оставить код voice/vision в git-ветке `feature/voice-vision`, чтобы не раздувать core неработающими абстракциями. | `api/deps.py`, `core/ports/__init__.py` | `dev/tests/test_contracts.py`

=============================================

[-] Убрать `slots=True` и кучу `Optional` в `AppState` | Удалить `slots=True` из `AppState` (добавляет гибкость для тестов и отладки). Разделить на два класса: `AppState` для старта и `InitializedAppState` для runtime, где поля `llm`, `embedder`, `vector_store`, `pipeline`, `storage` — обязательны (не `None`). Это убирает необходимость в `getattr(app.state, ...)` с дефолтами и ловит неинициализированный стейт на этапе типизации, а не в рантайме. | `api/deps.py` | `dev/tests/test_contracts.py`, `dev/tests/test_smoke.py`

[-] Явные импорты features в `router.py` (убрать reflection) | В `api/router.py` заменить цикл `for attr_name in ("router", "router_oai", "router_legacy"): getattr(module, ...)` на явный список/словарь импортов: `_ROUTERS = [_chat_handlers.router, ...]`. Ловит ошибки на этапе импорта, а не в runtime при первом запросе. | `api/router.py` | `dev/tests/test_smoke.py`

=============================================

[-] Убрать прямой импорт `pipeline.steps` из `ChatManager` | В `features/chat/manager.py` убрать любые импорты из `pipeline.steps`. Вместо создания pipeline внутри менеджера принимать готовый `RAGPipeline` (retrieval pipeline) через конструктор из `AppState`. `deps.py` уже передаёт `retrieval_pipeline`, но нужно убедиться, что менеджер не тянет шаги напрямую. | `features/chat/manager.py` (запросить код перед правкой) | `test_chat_manager.py`

=============================================

[-] Добавить `shutdown()` в `IEmbedder` и `IVectorStore` | ⚠️ CORE CHANGE: порты должны наследовать `IClosable`. Добавить `async def shutdown(self) -> None` в `IEmbedder` и `IVectorStore`. Реализовать во всех адаптерах: `embedder_mock`, `embedder_openai_compatible` (закрыть HTTP-сессии), `vector_store_memory`, `vector_store_faiss` (закрыть индексы). В `api/lifespan.py` расширить graceful shutdown: добавить вызов `shutdown()` для `state.embedder` и `state.vector_store` (сейчас обрабатывается только `llm`). | `core/ports/embedder.py`, `core/ports/vector_store.py`, `adapters/embedder_*.py`, `adapters/vector_store_*.py`, `api/lifespan.py` | `dev/tests/test_contracts.py`, `dev/tests/test_lifespan.py`

[-] Убить pipeline step registry (`@step`) → явные импорты | ⚠️ CORE CHANGE: удалить `pipeline/decorators.py` (файл `@step` / `get_step`). В `api/deps.py` в `_build_step_funcs` импортировать шаги напрямую: `from ai_assistant.pipeline.steps import embed_query_step, retrieve_step, ...` и собирать список функций явно. Убрать строковые имена шагов из `rag.steps` в конфиге (или заменить на enum для документации). Убирает глобальное mutable-состояние `_step_registry`. | `pipeline/decorators.py`, `api/deps.py`, `core/config.py` | `dev/tests/test_pipeline.py`, `dev/tests/test_core_critical.py`

=============================================

[-] Убить Adapter Registry (`@register`) → фабрика if/else | ⚠️ CORE CHANGE: удалить `core/registry.py`. Создать `adapters/factory.py` с явной фабрикой `create_adapter(port, name, config)` через `if/elif` + lazy import (через `importlib` внутри функции). Убрать `@register` из всех адаптеров. Убрать массовые side-effect импорты из `api/deps.py` (типа `import ai_assistant.adapters.llm_mock`). Адаптеры импортируются только внутри фабрики по требованию. | `core/registry.py`, `adapters/factory.py` (создать), `adapters/__init__.py`, `api/deps.py`, все `adapters/*.py` | `dev/tests/test_contracts.py`, `dev/tests/test_smoke.py`

=============================================

[-] Оборачивать CPU-bound вызовы в `asyncio.to_thread()` | Все синхронные тяжёлые операции (FAISS index search/add, tiktoken encoding, локальные CPU-вычисления) должны выполняться через `asyncio.to_thread()` или `anyio.to_thread.run_sync()` внутри адаптеров. Это предотвращает блокировку event loop uvicorn при локальном CPU-inference. Начать с `vector_store_faiss.py` (search/add) и `embedder_openai_compatible.py` (batch embed). | `adapters/vector_store_faiss.py`, `adapters/embedder_openai_compatible.py`, `core/utils.py` (если есть токенизация) | `dev/tests/test_rag.py`, `dev/tests/test_adapters.py`



Чат 1: «Мёртвый вес» (пункты 1+2+3+4)
Чат 2: «Инфраструктура» (пункты 5+6+7)
Чат 3: «AppState + Router» (пункты 8+9)
Чат 4: «ChatManager» (пункт 10)
Чат 5: «Core: shutdown + steps» (пункты 11+12)
Чат 6: «Core: Adapter Registry» (пункт 13)
Чат 7: «Performance: to_thread» (пункт 14)
