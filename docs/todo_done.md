[+] Фабрика `create_app`: убран глобальный `app`, тесты создают изолированные инстансы без хаков.
[+] Фикстура `client`: `app` создается внутри, убран `object.__setattr__` и патч `init_adapters`.
[+] Убран `reset_global_state`, сброс состояния теперь происходит через `create_app()` в каждом тесте.
[+] Inline retry вынесен из `generate()` в `_call_llm()` с декоратором `@with_retry`.
[+] Удалена мутация `config` в рантайме (`state.config.security.api_key = req.api_key`).
[+] `ToolResult` переведен в `frozen=True` dataclass, все мутации полей заменены на создание нового экземпляра.
[+] Реализован graceful degradation при недоступном LLM: возврат 503 с текстом вместо 500.
[+] Добавлена TTL-очистка `_reindex_status` (удаление старых записей при len > 1000).
[+] Добавлен backpressure в `MetricsLogger`, но впоследствии `MetricsMiddleware` и `MetricsLogger` полностью удалены как избыточный вес.
[+] Добавлена поддержка OpenAI `content: str | list[dict]` для Vision-совместимости.
[+] Добавлен метод `shutdown()` в порты `IEmbedder`, `IVectorStore` и `IReranker` с реализацией graceful shutdown в `lifespan`.
[+] Убран прямой импорт `pipeline.steps` из `ChatManager`, используется `RAGPipeline` из `AppState`.
[+] Заменен динамический `importlib` в `router.py` на явные импорты для отлова ошибок на этапе compile-time.
[+] `PipelineData`: эволюционировал от обычного dataclass к `frozen=True` + `slots=True` для runtime-гарантии иммутабельности и защиты от опечаток.
[+] Убран глобальный флаг `_static_mounted`, проверка перенесена в `app.routes` или `app.state`.
[+] Сужены `except Exception` до конкретных типов (`ImportError`, `ValueError`) в `init_adapters`.
[+] Удален `core/circuit_breaker.py` и все его использования как преждевременная сложность.
[+] Упрощен security-слой: удален дублирующий `APIKeyMiddleware` и самописный `LimitMiddleware`, оставлен `require_api_key`.
[+] Удалены `voice`/`vision`/`long_term_memory` и `tool_registry` из ядра и инициализации `AppState`.
[+] `AppState` разделен на стартовый и `InitializedAppState`, убраны `Optional` и `slots=True` для гибкости тестов.
[+] Убит глобальный pipeline step registry (`@step`), шаги импортируются и собираются явно в `core/pipeline_steps.py`.
[+] Глобальный Adapter Registry заменен на явную фабрику `create_adapter` с локальным декоратором `@register`.
[+] CPU-bound вызовы (FAISS, tiktoken) обернуты в `asyncio.to_thread()` для предотвращения блокировки event loop.
[+] Добавлен guard на max 5 итераций tool loop в `generate()` для предотвращения infinite loop.
[+] Добавлен CJK fallback в `count_tokens()` для корректного подсчета токенов китайского/японского текста.
[+] Добавлена очистка `rerank_*` ключей из metadata при `reranker=None`.
[+] Создан `RAGStep` StrEnum и динамический `_STEP_MAP` для конфигурации шагов через `config.yaml`.
[+] Реализован per-namespace config block в `config.yaml` с индивидуальными threshold, chunk_size и prompt.
[+] Добавлена поддержка `prompt_version` в config для управления версиями промптов без правки кода.
[+] Удалены `ImagePayload`, `VoicePayload` и связанные заглушки из chat-слоя.
[+] Починен `check_smoke.py` после удаления voice/vision (убраны `AttributeError`).
[+] Синхронизирована документация (README, AI_RULES, TODO, config) после удаления voice/vision.
[+] Унифицирован `relevance_threshold` в одном месте, удален из `VectorStoreConfig`.
[+] Добавлены warnings на неизвестные env vars при загрузке конфига с `extra="ignore"`.
[+] `DummyReranker` заменен на `NullReranker`, убраны проверки `if reranker is None` из pipeline.
[+] Добавлен `trace_id` в `PipelineData` с пробросом в логи шагов и HTTP handlers.
[+] Заменены динамические классы `type("C", (), {...})` в скриптах на dataclass-фабрики.
[+] Удалена магическая строка `"__terminal__"` из launcher, заменена на Enum/Literal.
[+] Удален мёртвый комментарий "voice-vision branch" из `test_contracts.py`.
[+] Исправлен CORS fallback crash при отсутствии config.yaml (замена `["*"]` на localhost).
[+] Убран избыточный `__post_init__` в `UserMessage`, поле `text` сделано обязательным `str`.
[+] Синхронизирован `config_version` между `config.yaml` и `AppConfig` (поднят до 1.5.0).
[+] Убрано дублирование вызова `_mount_static`, оставлена единственная точка в `lifespan.py`.
[+] Заменен тип `Any` на `ChatManager` в `AppState` для восстановления типобезопасности.
[+] Перенесен `STEP_REGISTRY` и функции шагов из `pipeline/` в `core/pipeline_steps.py`.
[+] Удалена мёртвая функция `_rehydrate_state` из `deps.py`.
[+] Убраны defensive `getattr` для config в `lifespan`, заменены на прямой доступ.
[+] Типизирован `limiter` в `AppState` (`Callable | None` вместо `Any`).
[+] Типизирован `STEP_REGISTRY` (`dict[str, Callable[[PipelineData], Awaitable[PipelineData]]]`).
[+] Вынесены magic numbers (256, 0.1) в `generate()` в именованные константы (`TOKEN_MARGIN_MIN`, `TOKEN_MARGIN_PCT`).
[+] Добавлен метод `with_metadata()` в `PipelineData` для единообразия API.
[+] Добавлены базовые метрики observability (счетчики, latency) и endpoint `/metrics`.
[+] Синхронизирован `dev/tests/config.test.yaml` с корневым `config.yaml` (добавлены namespaces).
[+] Убран хардкод путей в RAG handlers, вынесен в константы или config.
[+] Вынесен truncation loop из `generate()` в `_truncate_to_fit()` с fallback `max_ctx`.
[+] Исправлен `pre_commit_check.py`: убрано дублирование, добавлена проверка `**kwargs`.
[+] Исправлен `check_mutations.py`: `return 0` заменен на `return 1` при проваленном тесте.
[+] Исправлен `launcher.py`: удален дубль ключа `TEST_FLAGS` "clean_cache".
[+] Исправлен `context_build.py`: `write_text()` заменен на `atomic_write()`.
[+] Исправлена race condition в `_reindex_status` и глобальных dict `metrics.py`.
[+] Переименованы ЗАГЛАВНЫЕ файлы в прописные.
[+] Изменена структура проекта для личного пользования.
[+] Прокинут `rag.top_k` из конфига в `ChatManager`, убран magic number.
[+] Дедуплицирована логика `chat`/`stream_chat` через вынос `_build_messages` и `_retrieve_context`.
[+] Упрощен `launcher` до чистого меню (номер → запуск), убраны `ask_flags` и диалоги.
[+] Скрипты сделаны интерактивными: при отсутствии аргументов запрашивают выбор цифрами.
[+] Удалены мусорные `getattr` из `main.py`, `admin.py`, `chat/manager.py` и `static.py`, заменены на прямой доступ.
[+] Убран underscore prefix из импортов `_chat_handlers`/`_rag_handlers` в `router.py`.
[+] Добавлен `NotImplementedError` в TODO `stream_chat` вместо молчаливого пропуска.
[+] Добавлен метод `get_context_limit()` в порт `ILLM` и реализован в адаптерах.
[+] Добавлено свойство `index_path` в порт `IVectorStore` и реализовано в адаптерах.
[+] Убран defensive `getattr` из `lifespan.py`, заменен на прямой доступ `config.vector_store`.
[+] Добавлен `ToolMessage` dataclass в `domain/messages.py`, обновлен `Message` alias и `generate()`.
[+] Добавлено поле `log_file: str | None` в `AppConfig`.
[+] Добавлен `IClosable` в порт `IReranker` с реализацией `shutdown` во всех адаптерах.
[+] Добавлена защита от `IndexError` при пустом `embeddings` в `embed_query` и `hyde_query`.
[+] Исправлен `KeyError` `prompt_version`/`prompt_name` в `generate()` через использование `.get()` с fallback.
[+] Добавлена защита от пустого `last_user_msg` в `openai_chat_completions` (HTTPException 400).
[+] Удален `getattr` в `llm_mock`, порт теперь принимает строго типизированные `Message`.
[+] Добавлена Pydantic-схема `ReindexRequest` для эндпоинта `reindex_documents`.
[+] Исправлено имя env var для API ключа на `AI_SECURITY_API_KEY`.
[+] Удален мертвый tool-calling loop из `generate()`.
[+] Убрана запись и удаление PID-file из `lifespan`.
[+] Удален `_model_list_cache`, список моделей строится на лету.
[+] `atomic_write`: добавлен и затем удален `os.unlink(tmp)` из `finally`, так как `os.replace` уже удаляет файл.
[+] Убран импорт приватного `_mount_static` из `lifespan`.
[+] Удалено поле `rate_limit` из конфига как нереализованная функциональность.
[+] Добавлен Heartbeat в `features/chat/handlers.py` для решения проблемы "медленного соединения".
[+] Проведен полный рефакторинг тестов, удалены дублирующие скрипты.
[+] Исправлен schema drift `ChunkMetadata`: убран `created_at`, добавлен `total_chunks`, внедрен `dataclass_from_dict`.
[+] Добавлено оборачивание `httpx.HTTPError` в `AdapterError` в LLM, embedder и reranker адаптерах.
[+] Исправлен CORS: чтение из `config.yaml`, убран хардкод `["*"]` и опасное значение `"null"`.
[+] Убран duck typing (`getattr`) в `_build_messages`, заменен на `isinstance` и явные типы.
[+] Заменен `assert` на `if` в `rerank()` для корректной работы при запуске с `python -O`.
[+] Синхронизированы поля `core/domain/configs.py` с `config.yaml` (добавлены missing поля, убраны лишние).
[+] `generate()` теперь поглощает `AdapterError` в `data.add_error()`, сохраняя чистоту pipeline.
[+] Порт `IChatStorage` теперь явно наследует `IInitializable`.
[+] Factory переписана: жесткий `if/elif` заменен на декоратор `@register` для масштабируемости.
[+] Изолированы тестовые фикстуры: убран shared `MagicMock`, добавлены factory/deepcopy для `AppConfig`.
[+] Добавлен guard в `FaissVectorStore` `load()`: бросает `AdapterError` при отсутствии `store.json`.
[+] `query_parser.py`: единый `parse_rag_query()` в `core/` заменил дублирующийся парсинг `[p]`/`[w]` в трёх местах. Namespace не теряется между слоями.
[+] Логирование в 4 адаптерах переведено на `extra={}`; `test_chat.py` синхронизирован с 4-tuple сигнатурой `_retrieve_context()` — 27 тестов восстановлены.
[+] Убраны `ResourceWarning: unclosed database` через `closing()` из `contextlib` в `test_adapters.py`.
[+] `_estimate_tokens` и `_truncate_to_fit` переведены в async; роуты `/metrics` и `/metrics/json` вынесены из `main.py` в `router.py` с единым registry.
[+] SQLite WAL mode (`PRAGMA journal_mode=WAL`) в `init_db()`.
[+] Фильтрация пустых `stop_sequences` в `llm_openai_compatible.py`.
[+] Усовершенствовали тесты, теперь покрывает до 85% проекта.
[+] Log rotation: `logging.max_bytes`, `logging.backup_count` в `LoggingConfig`.
[+] `connect_timeout` в `LLMConfig`/`EmbedderConfig`, единая логика `httpx.AsyncClient` в обоих адаптерах.
[+] `documents_root` в `RAGConfig`, разделён `CHAT_EXPORTS_ROOT`.
[+] `token_margin_min`/`token_margin_pct` в конфиг, убраны константы; `PipelineConfig` перенесён в `core/domain/pipeline.py` как stdlib dataclass.
[+] Убраны fallbacks из pipeline steps: `metadata["key"]` вместо `.get()`, `KeyError` → `ConfigurationError`.
[+] Убран хардкод `model="gpt-4o"`, `tokenizer_model` прокидывается через менеджеры.
[+] `max_ctx` fallback перенесён в адаптеры (`get_context_limit()`), обновлён `MockLLM`.
[+] Убрано дублирование `PipelineConfig`/`ConfigurationError` — импорты из `core/domain/`.
[+] Ужесточены типы в `_call_embed`/`_call_search`/`_call_llm`: `Any` → `IEmbedder`/`IVectorStore`/`ILLM`.
[+] Добавлены docstrings в `core/domain/configs.py`.
[+] CJK threshold вынесен в `_CJK_RATIO_THRESHOLD = 0.3`, убраны magic literals.
[+] Все продакшен-вызовы `count_tokens` явно передают `model` из конфига; `utils.py` задокументирован.
[+] Источники в ответе чата — теперь в конце каждого ответа отображается список использованных файлов с кликабельными ссылками (пользователь видит, откуда взята информация).
[+] Иммутабельность RerankResult и ToolCall — оба объекта заморожены (frozen=True), чтобы предотвратить случайные изменения состояния и race conditions в пайплайне.
[+] Логирование ошибок JSON в SQLite — при чтении из БД теперь логируется JSONDecodeError, чтобы не скрывать повреждение данных и упростить отладку.
[+] Явный экспорт LLM_UNAVAILABLE — константа добавлена в __all__, исправлены проблемы с импортами и проверками mypy.
[+] Удалена мёртвая зависимость sqlmodel — убран неиспользуемый пакет из pyproject.toml, окружение больше не раздувается.
[+] Убрано мёртвое поле limiter — удалено поле из AppState, оставшееся после отказа от rate-limiter'а.
[+] Ужесточены типы в интерфейсах инструментов — config и parameters заменены с Any на object, чтобы избежать неявного Any там, где можно обойтись конкретным типом.
[+] Устранены глобальные переменные состояния RAG — семафор и словарь задач перенесены в явное состояние AppState, убрана глобальная мутабельность.
[+] Типизирован PipelineData.metadata — вместо бестипового словаря используется TypedDict (или явные поля), повышена типобезопасность во всех шагах пайплайна.
[+] Комментарии в скриптах переведены на английский — все комментарии в scripts/ приведены к единому языку (были кириллица).
[+] Убран хардкод портов в kill.py — утилита теперь читает порты из конфига, а не зашивает 8080, 8081, 8000.
[+] Устранено дублирование правил очистки — теперь clean_cache.py и .gitignore используют общий источник правил, чтобы новые артефакты не забывались в одном из мест.
[+] Убран хардкод модели gpt-4o в count_tokens — модель теперь передаётся через менеджеры, а не зашита жёстко.
[+] Исправлена блокировка event loop в `_trim_history` — синхронный `count_tokens` заменён на `async_count_tokens` через `asyncio.to_thread`, сервер не зависает при большой истории.
[+] Добавлена очистка завершённых задач в `RAGState.tasks` — `asyncio.Task` удаляется из словаря по done-callback, устранена утечка памяти при массовых reindex.
[+] Сделано атомарное сохранение FAISS-индекса — бинарник пишется во временный файл с последующим `os.replace`, при `kill -9` индекс остаётся консистентным.
[+] Добавлена опциональная авторизация OpenAI-роутов — `security.openai_routes_require_auth: bool` (default: false), `/v1/chat/completions` и `/v1/models` можно закрыть API key без ломки совместимости.
[+] Admin API защищён флагом `admin_enabled` — endpoint'ы возвращают 404 если не включено явно, риск случайной экспозиции снижен без введения отдельного admin-ключа.
[+] Улучшена обработка ошибок сохранения индекса при shutdown — retry с экспоненциальным backoff, флаг `shutdown_degraded` для non-zero exit кода при фатальной ошибке.
[+] Добавлена проверка целостности индекса при старте — сравнение векторов FAISS с метаданными, fail-fast при рассинхронизации вместо молчаливой работы с пустым индексом.
[+] Устранена утечка абсолютных путей в RAG-индексе — `source_uri` теперь относительный путь от `documents_root`/`chat_exports_root`, инфраструктура не экспонируется в API.
[+] Разделены корни чат-экспортов и документов — `chat_exports_root` по умолчанию `"chat_exports"`, чаты больше не попадают в RAG-индекс документов.
[+] Убран хардкод лимита тела запроса — `check_request_size()` использует `config.security.max_body_size`, 10MB не захардкожен.
[+] Добавлен аудит административных операций — `update_api_key` логирует `SECURITY_AUDIT: api_key_changed` со структурированными полями `security_event`/`actor`/`key_present` в `extra=`.
[+] Lazy AsyncClient race | Конкурентные запросы могут создать несколько httpx.AsyncClient, утечка соединений | BUG |⚠️ CRITICAL — утечка ресурсов при нагрузке
[+] HTTP exceptions not wrapped | httpx.HTTPError прорывается наружу вместо AdapterError, нарушает контракт адаптера | ARCH
[+] Duplicate task cleanup | finally и done_callback оба удаляют задачу — избыточно, но безопасно | TECHDEBT
[+] FAISS delete non-atomic | delete() меняет память, потом сохраняет — при краше между ними индекс рассинхронизирован | BUG
[+] hasattr on credentials | hasattr(credentials, "credentials") — нарушает правило "No hasattr in production", хотя объект не портовый | ARCH
[+] Timing side-channel on API key | != вместо hmac.compare_digest — теоретически возможен timing attack на ключ | SECURITY
[+] rag_state.tasks race — RAGState.status dict модифицируется без синхронизации, конкурентные reindex-запросы могут потерять задачи или оставить zombie entries.
[+] close() vs active requests — shutdown() закрывает httpx.AsyncClient, но complete()/stream()/embed() не проверяют состояние клиента перед использованием, возможен race при graceful shutdown.
[+] lost-update save() — delete() меняет индекс в памяти, но save() не вызывается автоматически; при краше между delete() и явным save() диск содержит stale данные, а память — новые.
[+] Неактуальный `docs/drift.md` — #13, #14, #15 помечены как активные | `#13 source_uri` уже в `ChunkMetadata`, `#14 RAGState.status` уже `dict[str, dict[str, object]]`, `#15 query_embedding` удалён из `_required_fields_for_steps`.
[+] Неактуальный `docs/future.md` — Prometheus помечен как `research` | `core/metrics.py` уже реализует Prometheus exposition format. Блокер `Needs prometheus_client` устарел.
[+] `scripts/kill.py` парсит неверный путь к порту | Ищет `data.get("api", {}).get("port")`, но `port` в корне `config.yaml`.
[+] `security.py`: `isinstance()` → `credentials is None`. Убран дубль импорта, тест на malformed приведён к реальному DI-поведению. | `src/ai_assistant/api/security.py`, `tests/test_api.py`
[+] Удалена мёртвая константа `DOCUMENTS_ROOT` и лишний `pathlib.Path`. | `src/ai_assistant/core/constants.py`
[+] Документировано: `_override_api_key` process-local, не работает в multiprocess. Warning в lifespan при `admin_enabled=True`. | `src/ai_assistant/api/security.py`, `src/ai_assistant/api/lifespan.py`
[+] `test_rag.py`: `chat_exports_root` из `"chat_exports"` (cwd) → `str(tmp_path / "chat_exports")`. | `tests/test_rag.py`
[+] Хардкод `CHUNK_SIZE = 100_000` в `indexing.py` | Документ может съесть память. Не соответствует `config.yaml`. Нужно: вынести в `RAGConfig` или использовать `chunker` config. | `src/ai_assistant/features/rag/indexing.py`, `src/ai_assistant/core/config.py` | `tests/test_rag.py`, `tests/test_integration.py`
[+] Незадокументированный drift: non-stdlib в `core/` | Jinja2 (`core/prompts`), pydantic+yaml (`core/config`), tiktoken+tokenizers (`core/utils`) — все в `core/` при запрете non-stdlib. Только Jinja2 в drift #11. Нужно: дополнить список grandfathered exceptions. | `docs/drift.md` | `grep -c 'Jinja2\|pydantic\|yaml\|tiktoken' src/ai_assistant/core/*.py`
[+] Кириллица в `rag_strict.j2` — переведена на английский | `"У меня недостаточно информации."` → `"I do not have enough information."` | `src/ai_assistant/core/prompts/v1/rag_strict.j2` | `tests/test_smoke.py`
[+] `RAGState._status` — неограниченный рост памяти | `cleanup_status()` добавлен в `start_task()` (write-операция, side effect приемлем). `get_status()` остаётся чистым read. Решает утечку при частых reindex без костылей в read-пути. | `src/ai_assistant/api/deps.py` | `tests/test_rag.py`
[+] SQLite: реализован graceful shutdown (PRAGMA wal_checkpoint + close) для защиты от потери WAL.
[+] RAG: добавлена валидация namespace (regex `^[a-z]+$`) для защиты от path traversal.
