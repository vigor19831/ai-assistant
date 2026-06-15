[x] Фабрика `create_app`: убран глобальный `app`, тесты создают изолированные инстансы без хаков.
[x] Фикстура `client`: `app` создается внутри, убран `object.__setattr__` и патч `init_adapters`.
[x] Убран `reset_global_state`, сброс состояния теперь происходит через `create_app()` в каждом тесте.
[x] Inline retry вынесен из `generate()` в `_call_llm()` с декоратором `@with_retry`.
[x] Удалена мутация `config` в рантайме (`state.config.security.api_key = req.api_key`).
[x] `ToolResult` переведен в `frozen=True` dataclass, все мутации полей заменены на создание нового экземпляра.
[x] Реализован graceful degradation при недоступном LLM: возврат 503 с текстом вместо 500.
[x] Добавлена TTL-очистка `_reindex_status` (удаление старых записей при len > 1000).
[x] Добавлен backpressure в `MetricsLogger`, но впоследствии `MetricsMiddleware` и `MetricsLogger` полностью удалены как избыточный вес.
[x] Добавлена поддержка OpenAI `content: str | list[dict]` для Vision-совместимости.
[x] Добавлен метод `shutdown()` в порты `IEmbedder`, `IVectorStore` и `IReranker` с реализацией graceful shutdown в `lifespan`.
[x] Убран прямой импорт `pipeline.steps` из `ChatManager`, используется `RAGPipeline` из `AppState`.
[x] Заменен динамический `importlib` в `router.py` на явные импорты для отлова ошибок на этапе compile-time.
[x] `PipelineData`: эволюционировал от обычного dataclass к `frozen=True` + `slots=True` для runtime-гарантии иммутабельности и защиты от опечаток.
[x] Убран глобальный флаг `_static_mounted`, проверка перенесена в `app.routes` или `app.state`.
[x] Сужены `except Exception` до конкретных типов (`ImportError`, `ValueError`) в `init_adapters`.
[x] Удален `core/circuit_breaker.py` и все его использования как преждевременная сложность.
[x] Упрощен security-слой: удален дублирующий `APIKeyMiddleware` и самописный `LimitMiddleware`, оставлен `require_api_key`.
[x] Удалены `voice`/`vision`/`long_term_memory` и `tool_registry` из ядра и инициализации `AppState`.
[x] `AppState` разделен на стартовый и `InitializedAppState`, убраны `Optional` и `slots=True` для гибкости тестов.
[x] Убит глобальный pipeline step registry (`@step`), шаги импортируются и собираются явно в `core/pipeline_steps.py`.
[x] Глобальный Adapter Registry заменен на явную фабрику `create_adapter` с локальным декоратором `@register`.
[x] CPU-bound вызовы (FAISS, tiktoken) обернуты в `asyncio.to_thread()` для предотвращения блокировки event loop.
[x] Добавлен guard на max 5 итераций tool loop в `generate()` для предотвращения infinite loop.
[x] Добавлен CJK fallback в `count_tokens()` для корректного подсчета токенов китайского/японского текста.
[x] Добавлена очистка `rerank_*` ключей из metadata при `reranker=None`.
[x] Создан `RAGStep` StrEnum и динамический `_STEP_MAP` для конфигурации шагов через `config.yaml`.
[x] Реализован per-namespace config block в `config.yaml` с индивидуальными threshold, chunk_size и prompt.
[x] Добавлена поддержка `prompt_version` в config для управления версиями промптов без правки кода.
[x] Удалены `ImagePayload`, `VoicePayload` и связанные заглушки из chat-слоя.
[x] Починен `check_smoke.py` после удаления voice/vision (убраны `AttributeError`).
[x] Синхронизирована документация (README, AI_RULES, TODO, config) после удаления voice/vision.
[x] Унифицирован `relevance_threshold` в одном месте, удален из `VectorStoreConfig`.
[x] Добавлены warnings на неизвестные env vars при загрузке конфига с `extra="ignore"`.
[x] `DummyReranker` заменен на `NullReranker`, убраны проверки `if reranker is None` из pipeline.
[x] Добавлен `trace_id` в `PipelineData` с пробросом в логи шагов и HTTP handlers.
[x] Заменены динамические классы `type("C", (), {...})` в скриптах на dataclass-фабрики.
[x] Удалена магическая строка `"__terminal__"` из launcher, заменена на Enum/Literal.
[x] Удален мёртвый комментарий "voice-vision branch" из `test_contracts.py`.
[x] Исправлен CORS fallback crash при отсутствии config.yaml (замена `["*"]` на localhost).
[x] Убран избыточный `__post_init__` в `UserMessage`, поле `text` сделано обязательным `str`.
[x] Синхронизирован `config_version` между `config.yaml` и `AppConfig` (поднят до 1.5.0).
[x] Убрано дублирование вызова `_mount_static`, оставлена единственная точка в `lifespan.py`.
[x] Заменен тип `Any` на `ChatManager` в `AppState` для восстановления типобезопасности.
[x] Перенесен `STEP_REGISTRY` и функции шагов из `pipeline/` в `core/pipeline_steps.py`.
[x] Удалена мёртвая функция `_rehydrate_state` из `deps.py`.
[x] Убраны defensive `getattr` для config в `lifespan`, заменены на прямой доступ.
[x] Типизирован `limiter` в `AppState` (`Callable | None` вместо `Any`).
[x] Типизирован `STEP_REGISTRY` (`dict[str, Callable[[PipelineData], Awaitable[PipelineData]]]`).
[x] Вынесены magic numbers (256, 0.1) в `generate()` в именованные константы (`TOKEN_MARGIN_MIN`, `TOKEN_MARGIN_PCT`).
[x] Добавлен метод `with_metadata()` в `PipelineData` для единообразия API.
[x] Добавлены базовые метрики observability (счетчики, latency) и endpoint `/metrics`.
[x] Синхронизирован `dev/tests/config.test.yaml` с корневым `config.yaml` (добавлены namespaces).
[x] Убран хардкод путей в RAG handlers, вынесен в константы или config.
[x] Вынесен truncation loop из `generate()` в `_truncate_to_fit()` с fallback `max_ctx`.
[x] Исправлен `pre_commit_check.py`: убрано дублирование, добавлена проверка `**kwargs`.
[x] Исправлен `check_mutations.py`: `return 0` заменен на `return 1` при проваленном тесте.
[x] Исправлен `launcher.py`: удален дубль ключа `TEST_FLAGS` "clean_cache".
[x] Исправлен `context_build.py`: `write_text()` заменен на `atomic_write()`.
[x] Исправлена race condition в `_reindex_status` и глобальных dict `metrics.py`.
[x] Переименованы ЗАГЛАВНЫЕ файлы в прописные.
[x] Изменена структура проекта для личного пользования.
[x] Прокинут `rag.top_k` из конфига в `ChatManager`, убран magic number.
[x] Дедуплицирована логика `chat`/`stream_chat` через вынос `_build_messages` и `_retrieve_context`.
[x] Упрощен `launcher` до чистого меню (номер → запуск), убраны `ask_flags` и диалоги.
[x] Скрипты сделаны интерактивными: при отсутствии аргументов запрашивают выбор цифрами.
[x] Удалены мусорные `getattr` из `main.py`, `admin.py`, `chat/manager.py` и `static.py`, заменены на прямой доступ.
[x] Убран underscore prefix из импортов `_chat_handlers`/`_rag_handlers` в `router.py`.
[x] Добавлен `NotImplementedError` в TODO `stream_chat` вместо молчаливого пропуска.
[x] Добавлен метод `get_context_limit()` в порт `ILLM` и реализован в адаптерах.
[x] Добавлено свойство `index_path` в порт `IVectorStore` и реализовано в адаптерах.
[x] Убран defensive `getattr` из `lifespan.py`, заменен на прямой доступ `config.vector_store`.
[x] Добавлен `ToolMessage` dataclass в `domain/messages.py`, обновлен `Message` alias и `generate()`.
[x] Добавлено поле `log_file: str | None` в `AppConfig`.
[x] Добавлен `IClosable` в порт `IReranker` с реализацией `shutdown` во всех адаптерах.
[x] Добавлена защита от `IndexError` при пустом `embeddings` в `embed_query` и `hyde_query`.
[x] Исправлен `KeyError` `prompt_version`/`prompt_name` в `generate()` через использование `.get()` с fallback.
[x] Добавлена защита от пустого `last_user_msg` в `openai_chat_completions` (HTTPException 400).
[x] Удален `getattr` в `llm_mock`, порт теперь принимает строго типизированные `Message`.
[x] Добавлена Pydantic-схема `ReindexRequest` для эндпоинта `reindex_documents`.
[x] Исправлено имя env var для API ключа на `AI_SECURITY_API_KEY`.
[x] Удален мертвый tool-calling loop из `generate()`.
[x] Убрана запись и удаление PID-file из `lifespan`.
[x] Удален `_model_list_cache`, список моделей строится на лету.
[x] `atomic_write`: добавлен и затем удален `os.unlink(tmp)` из `finally`, так как `os.replace` уже удаляет файл.
[x] Убран импорт приватного `_mount_static` из `lifespan`.
[x] Удалено поле `rate_limit` из конфига как нереализованная функциональность.
[x] Добавлен Heartbeat в `features/chat/handlers.py` для решения проблемы "медленного соединения".
[x] Проведен полный рефакторинг тестов, удалены дублирующие скрипты.
[x] Исправлен schema drift `ChunkMetadata`: убран `created_at`, добавлен `total_chunks`, внедрен `dataclass_from_dict`.
[x] Добавлено оборачивание `httpx.HTTPError` в `AdapterError` в LLM, embedder и reranker адаптерах.
[x] Исправлен CORS: чтение из `config.yaml`, убран хардкод `["*"]` и опасное значение `"null"`.
[x] Убран duck typing (`getattr`) в `_build_messages`, заменен на `isinstance` и явные типы.
[x] Заменен `assert` на `if` в `rerank()` для корректной работы при запуске с `python -O`.
[x] Синхронизированы поля `core/domain/configs.py` с `config.yaml` (добавлены missing поля, убраны лишние).
[x] `generate()` теперь поглощает `AdapterError` в `data.add_error()`, сохраняя чистоту pipeline.
[x] Порт `IChatStorage` теперь явно наследует `IInitializable`.
[x] Factory переписана: жесткий `if/elif` заменен на декоратор `@register` для масштабируемости.
[x] Изолированы тестовые фикстуры: убран shared `MagicMock`, добавлены factory/deepcopy для `AppConfig`.
[x] Добавлен guard в `FaissVectorStore` `load()`: бросает `AdapterError` при отсутствии `store.json`.
[x] `query_parser.py`: единый `parse_rag_query()` в `core/` заменил дублирующийся парсинг `[p]`/`[w]` в `ChatManager`, `rag/handlers.py` и `check_rag.py`. Устранена размазанность, теперь namespace не теряется между слоями.
[x] query_parser.py: единый parse_rag_query() в core/ устранил дублирование парсинга [p]/[w] между ChatManager, rag/handlers.py и check_rag.py. Namespace больше не теряется при правках чата. (2026-06-15)
[x] adapters/logging + test_chat.py: 16 вызовов логирования в 4 адаптерах переведены на extra={}; тесты test_chat.py синхронизированы с 4-tuple сигнатурой _retrieve_context() — 27 тестов восстановлены. (2026-06-15)
[x] Убраны `ResourceWarning: unclosed database`, закрытие SQLite-соединений теперь происходит через `closing()` из `contextlib` в трёх тестах `test_adapters.py`.
