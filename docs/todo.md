Выдай список по одной строке в формате, все задания независимы друг от друга: [ ] Название + Краткая суть | Подробное описание (что, зачем, и ⚠️ CORE CHANGE если критично) | Файлы для правки (опционально) | Файлы тестов / где проверять.

==============================================================================
# TODO
==============================================================================


## 🔴 Волна 0 — Сегодня (блокеры)

[+] Исправить блокировку event loop: `_trim_history` → `async_count_tokens` | `features/chat/manager.py` вызывает синхронный `count_tokens` (CPU-bound tiktoken/HF) из async метода. При большой истории весь сервер зависает на секунды — не отвечает на другие запросы. Заменить на `async_count_tokens` (обёртка `asyncio.to_thread`). | `src/ai_assistant/features/chat/manager.py` | `tests/test_chat.py`, `tests/test_e2e.py`

[+] Добавить очистку завершённых задач в `RAGState.tasks` | Фоновые задачи индексации сохраняются в `tasks` по `task_id`. `asyncio.Task` после завершения остаётся в словаре, держит ссылку на весь стек. При 1000 reindex'ах — утечка памяти, сервер упадёт. Добавить callback удаления в `_run()` или периодическую уборку. | `src/ai_assistant/features/rag/handlers.py` | `tests/test_rag.py`, стресс-тест многократного reindex

[ ] Сделать сохранение FAISS-индекса атомарным | При `kill -9` во время `save()` — индекс на диске в inconsistent state. `atomic_write` есть для JSON, но FAISS пишет бинарник напрямую. Использовать временный файл + `os.replace`. | `src/ai_assistant/adapters/vector_store_faiss.py` | `tests/test_adapters.py`, ручной тест аварийного прерывания

---

## 🟠 Волна 1 — Неделя 1 (стабильность)

[ ] Проверять согласованность индекса и метаданных при загрузке | При старте `lifespan.py` загружает индексы, но не валидирует соответствие количества векторов и метаданных. Битый индекс после `kill -9` → молчаливое повреждение или поздний крах. Добавить проверку целостности. | `src/ai_assistant/adapters/vector_store_faiss.py`, `src/ai_assistant/api/lifespan.py` | `tests/test_adapters.py`

[ ] Исправить `api/security.py`: использовать `config.security.max_body_size` вместо хардкода | `SECURITY_MAX_BODY = 10_485_760` захардкожен. Конфиг парсит `security.max_body_size`, но `check_request_size()` его не читает. Нельзя изменить лимит без правки кода. ⚠️ Легаси-константа используется в тестах. | `src/ai_assistant/api/security.py` | `tests/test_api.py` (тесты на 413)

[ ] Исправить `scripts/kill.py`: парсинг порта API из корня конфига | Скрипт ищет `data.get("api", {}).get("port")`, но в `config.yaml` `port` лежит в корне (`port: 8000`). Исправить на `data.get("port", 8000)`. | `scripts/kill.py` | Ручный запуск: `python scripts/kill.py` при запущенном сервере на нестандартном порту

[ ] Разделить `rag.chat_exports_root` и `rag.documents_root` по умолчанию | Оба поля по умолчанию `"sources"`. `/save-chat` пишет в ту же папку, откуда читаются документы для RAG. Чат-экспорты попадают в индекс — утечка контекста, мусор в ответах. Изменить `chat_exports_root` на `"chat_exports"`. | `src/ai_assistant/core/config.py`, `config.yaml` | `tests/test_rag.py` (проверка путей сохранения)

[ ] Добавить автоматическую очистку старых записей в `RAGState.status` | `cleanup_status()` есть, но вызывается только вручную в `_run()`. Без гарантированной периодической уборки — неограниченный рост словаря в памяти. Добавить вызов по таймеру или при каждом новом task. | `src/ai_assistant/features/rag/handlers.py`, `src/ai_assistant/api/deps.py` | `tests/test_rag.py`, мониторинг памяти

[ ] Сделать лимит стриминга `_max_stream_tokens` конфигурируемым | `adapters/llm_openai_compatible.py` обрывает стрим после `max_tokens * 2`. Пользователь думает, что LLM «заткнулся», а это хардкод. Вынести множитель или абсолютный лимит в `LLMConfig`. | `src/ai_assistant/adapters/llm_openai_compatible.py`, `src/ai_assistant/core/config.py` | `tests/test_resilience.py`, `tests/test_api.py`

[ ] Сделать обработку ошибок шаблонов промптов fail-fast | В `core/pipeline_steps.py` ошибка загрузки или рендеринга prompt-template (`get_prompt` кидает `ValueError` или `Exception`) приводит к автоматическому fallback-промпту `_build_fallback_prompt`. Опечатка в имени шаблона → низкое качество ответов, пользователь не поймёт почему. Добавить режим `strict_prompt_loading` в конфиг: при `True` — прокидывать исключение, при `False` — fallback. | `src/ai_assistant/core/pipeline_steps.py`, `src/ai_assistant/core/config.py` | `tests/test_pipeline.py`, `tests/test_prompts.py`

---

## 🟡 Волна 2 — Неделя 2 (убрать мусор, который мешает править баги)

[ ] Удалить мертвое поле `security.allowed_hosts` или добавить middleware | Поле парсится и валидируется Pydantic, но **нигде не используется** — ни middleware, ни проверки. Ложное чувство безопасности. Либо добавить `TrustedHostMiddleware`, либо удалить поле из `SecurityConfig`. | `src/ai_assistant/core/config.py`, `src/ai_assistant/api/middleware.py` (если добавлять) | `tests/test_config.py`, `tests/test_api.py`

[ ] Удалить мертвый `core/constants.py: DOCUMENTS_ROOT` | Константа `Path("sources")` нигде не импортируется. В `features/rag/indexing.py` используется параметр `documents_root`. Удалить чтобы не путать разработчиков. | `src/ai_assistant/core/constants.py` | `tests/test_domain.py`, `tests/test_smoke.py` (поиск импортов)

[ ] Удалить мертвый `core/ports/tools.py` или задействовать | Интерфейсы `ITool`, `IToolRegistry`, `ToolCall`, `ToolResult` нигде не используются в production (кроме одного импорта в `test_smoke.py`). Обещание функциональности без реализации. Либо удалить, либо интегрировать в `llm_openai_compatible.py` вместо сырых `dict`. | `src/ai_assistant/core/ports/tools.py`, `src/ai_assistant/adapters/llm_openai_compatible.py` | `tests/test_domain.py`, `tests/test_smoke.py`

[ ] Удалить дублирование логики stream/non-stream ответов | В `features/chat/handlers.py` присутствуют отдельные ветки обработки для streaming (`chat_stream`, `openai_chat_completions` со stream) и обычного ответа с частично повторяющейся логикой. Исправляешь баг в одной ветке — забываешь про вторую. Вынести общую часть в единый сервисный слой. | `src/ai_assistant/features/chat/handlers.py` | `tests/test_api.py`, `tests/test_chat.py`

[ ] Обновить `docs/drift.md`: пометить #13, #14, #15 как resolved | Drift #13 (`source_uri` уже в `ChunkMetadata`), #14 (`RAGState.status` уже `dict[str, dict[str, object]]`), #15 (`query_embedding` удалён из `_required_fields_for_steps`). Убрать из активных или пометить `Fixed`. Устарело, но не ломает работу. | `docs/drift.md` | Ручная проверка: `git diff docs/drift.md`

[ ] Обновить `docs/future.md`: пометить Prometheus как implemented | `core/metrics.py` уже реализует нативный Prometheus exposition format. Статус `research` и блоккер `Needs prometheus_client` устарели. Устарело, но не ломает работу. | `docs/future.md` | Ручная проверка: `curl localhost:8000/metrics`

[ ] Зафиксировать дрифт: Jinja2/pydantic/yaml/tiktoken/tokenizers в `core/` | Правило 3 запрещает non-stdlib в `core/`, но нарушают: Jinja2 (`core/prompts`), pydantic+yaml (`core/config`), tiktoken+tokenizers (`core/utils`). Drift #11 упоминает только Jinja2. Дополнить список всех grandfathered exceptions. | `docs/drift.md` | Ручная проверка: `grep -c 'Jinja2\|pydantic\|yaml\|tiktoken' src/ai_assistant/core/*.py`

[ ] Зафиксировать дрифт: `print()` и `logging.basicConfig()` в скриптах | Правило 2 запрещает `print()` и `logging.basicConfig()`, но все скрипты в `scripts/` и `run_servers.py` их используют. Либо добавить grandfathered exception для `scripts/`, либо заменить на `get_logger`. | `docs/drift.md`, `scripts/*.py`, `run_servers.py` | `tests/test_smoke.py` (проверка отсутствия в `src/`), ручной `grep`

[ ] Зафиксировать дрифт: кириллица в `rag_strict.j2` | Правило 9 запрещает кириллицу, но `rag_strict.j2` содержит `"У меня недостаточно информации."`. Тест `test_smoke.py` сканирует только `*.py`. Либо перевести фразу, либо добавить `.j2` в проверку, либо зафиксировать дрифт. | `src/ai_assistant/core/prompts/v1/rag_strict.j2`, `tests/test_smoke.py`, `docs/drift.md` | `tests/test_smoke.py`

[ ] Исправить опечатки в `docs/ai_rules.md` | Артефакты форматирования: `onl y` (Section 3), `pi peline` (Section 5), `configu ration` (Section 4), `i nitialization` (Section 2), `feat ures/` (Section 2). Убрать лишние пробелы. Косметика. | `docs/ai_rules.md` | Ручная проверка: `grep -E 'onl y|pi peline|configu ration|i nitialization|feat ures/' docs/ai_rules.md` → пусто

---

## 🟢 Волна 3 — Неделя 3-4 (техдолг, упрощающий жизнь)

[ ] ⚠️ CORE CHANGE: Заменить `dict[str, object]` в `RAGState.status` на типизированную модель | Структура `status: dict[str, dict[str, object]]` хранит `finished_at`, `started_at` без контракта. Опечатка в ключе → `None` → баг. Ввести `ReindexStatusEntry` dataclass с полями `status: str`, `started_at: float`, `finished_at: float | None`, `result: dict | None`, `error: str | None`. ⚠️ Меняется схема данных в `core/`. Требует обновления всех потребителей + тестов + drift.md. Не начинать без подтверждения. | `src/ai_assistant/api/deps.py`, `src/ai_assistant/features/rag/handlers.py`, `src/ai_assistant/core/domain/` | `tests/test_rag.py`, `tests/test_contracts.py`

[ ] Вынести скрытый фильтр `FROZEN_NO_INFO_PHRASES` в конфиг | `features/chat/manager.py` содержит бизнес-логику, которая отключает прикрепление источников при наличии определённых фраз в ответе модели. Поведение не документировано, не настраивается, непредсказуемо для пользователя. Добавить `no_info_phrases: frozenset[str]` в `ChatConfig` или задокументировать как часть RAG-логики. | `src/ai_assistant/features/chat/manager.py`, `src/ai_assistant/core/config.py`, `docs/ai_rules.md` | `tests/test_chat.py`

[ ] Убрать магическое число усечения контекста в pipeline | Алгоритм `_truncate_to_fit` удаляет чанки с конца по одному до попадания в лимит токенов. Может выкинуть ключевой чанк. Нельзя настроить (например, summarization вместо truncation). Вынести стратегию усечения в отдельный конфигурируемый компонент. | `src/ai_assistant/core/pipeline_steps.py` | `tests/test_pipeline.py`

[ ] Вынести хардкод `SUPPORTED_EXTENSIONS` и `CHUNK_SIZE` из `indexing.py` в конфиг | `features/rag/indexing.py` хардкодит расширения файлов и лимит `CHUNK_SIZE = 100_000`. Нужно добавить поля в `RAGConfig` или `ChunkerConfig`. | `src/ai_assistant/features/rag/indexing.py`, `src/ai_assistant/core/config.py` | `tests/test_rag.py`, `tests/test_integration.py`

[ ] Синхронизировать тип `list_by_filter` в порту и адаптерах | `IVectorStore.list_by_filter` требует `dict[str, str | int | float | bool | None]`, но адаптеры (`faiss`, `memory`) реализуют как `dict[str, Any]`. `mypy --strict` лжёт или игнорируется. Контракт порта не соблюдается. | `src/ai_assistant/adapters/vector_store_faiss.py`, `src/ai_assistant/adapters/vector_store_memory.py` | `tests/test_contracts.py`, `tests/test_stateful_ports.py`

[ ] Разделить ответственности `ChatManager` | Текущий менеджер 300+ строк одновременно отвечает за историю, RAG, промпты и взаимодействие с LLM. Страх трогать → код гниёт. Выделить отдельные сервисы для prompt-building и history-management. >3 файлов, высокий риск регрессий. | `src/ai_assistant/features/chat/manager.py` | Полный прогон `tests/test_chat.py`

[ ] Разделить ответственности `pipeline_steps.py` | Модуль 400+ строк объединяет retrieval, rerank, truncation, prompt-building и generation. Разделить на специализированные шаги для уменьшения связности. >3 файлов, высокий риск регрессий. | `src/ai_assistant/core/pipeline_steps.py` | `tests/test_pipeline.py`

[ ] Убрать использование `dict[str, Any]` в адаптерах в пользу типизированных моделей | В адаптерах и менеджерах остаются структуры с `Any`, что ослабляет статическую проверку и затрудняет рефакторинг. Рефакторинг — russian roulette. 15+ файлов. Большой типизационный рефакторинг, риск сломать незаметно. | `src/ai_assistant/adapters/*`, `src/ai_assistant/features/*` | `mypy`, `tests/test_contracts.py`

---

## 🔵 Волна 4 — После стабилизации (новые фичи RAG, только после волн 0-3)

[ ] Query Expansion | LLM переписывает query в 2-3 варианта, retrieve по всем, merge через RRF. Зачем: улучшает recall для сложных/коротких запросов. ⚠️ CORE CHANGE: PipelineData.expanded_queries, RAGStep.EXPAND_QUERY | `src/ai_assistant/core/domain/pipeline.py`, `src/ai_assistant/core/pipeline_steps.py`, `src/ai_assistant/core/config.py`, `src/ai_assistant/core/prompts/v1/query_expand.j2` | `tests/test_pipeline.py`, `tests/test_integration.py`

[ ] Contextual Compression | Новый step compress_context между rerank и build_context. Маленький LLM извлекает 2-3 релевантных предложения из каждого chunk. Зачем: больше chunk'ов в context window, каждый dense. | `src/ai_assistant/core/pipeline_steps.py`, `src/ai_assistant/core/prompts/v1/compress_context.j2` | `tests/test_pipeline.py`, `tests/test_integration.py`

[ ] Hybrid Search BM25 + Vector | Новый adapter BM25Retriever + step hybrid_retrieve. BM25 (keyword) + vector search через RRF. Зачем: ловит exact matches, которые vector пропускает. ⚠️ CORE CHANGE: новый port IRetriever, PipelineData.hybrid_results | `src/ai_assistant/core/ports/retriever.py`, `src/ai_assistant/adapters/retriever_bm25.py`, `src/ai_assistant/core/pipeline_steps.py`, `src/ai_assistant/api/deps.py` | `tests/test_adapters.py`, `tests/test_pipeline.py`, `tests/test_integration.py`

[ ] Re-ranker Cross-Encoder | Новый adapter CrossEncoderReranker вместо NullReranker. Локальная модель (bge-reranker-v2-m3). Зачем: точнее чем score-based. | `src/ai_assistant/adapters/reranker_cross_encoder.py`, `src/ai_assistant/core/domain/configs.py` (RerankerConfigData.model_path), `pyproject.toml` (+transformers) | `tests/test_adapters.py`, `tests/test_properties.py`

[ ] Parent-Child Chunking | Два уровня chunk'ов: small (retrieval) + large parent (context). Small chunk ссылается на parent. При retrieval берём small, в context подаём parent. Зачем: точный поиск + полный контекст. ⚠️ CORE CHANGE: Chunk.parent_id, Chunk.parent_text, IChunker, IVectorStore (два индекса), PipelineData | `src/ai_assistant/core/domain/documents.py`, `src/ai_assistant/core/ports/chunker.py`, `src/ai_assistant/core/pipeline_steps.py`, `src/ai_assistant/adapters/chunker_simple.py`, `src/ai_assistant/adapters/vector_store_faiss.py`, `src/ai_assistant/adapters/vector_store_memory.py` | `tests/test_domain.py`, `tests/test_pipeline.py`, `tests/test_integration.py`

[ ] Semantic Cache для Retrieval | Кэш query_embedding → chunks в LRU (memory) или диск. Проверка по cosine similarity > 0.95. Зачем: ускоряет повторные запросы, снижает нагрузку. | `src/ai_assistant/adapters/cache_semantic.py`, `src/ai_assistant/core/pipeline_steps.py` (embed_query проверять cache first), `src/ai_assistant/core/domain/configs.py` (CacheConfigData) | `tests/test_pipeline.py`, `tests/test_adapters.py`

[ ] Multi-hop Self-Query | Если ответ неполный/неточный — автоматически reformulate query и повторить retrieval. Зачем: находит информацию, разбросанную по разным chunk'ам. ⚠️ CORE CHANGE: pipeline loop вместо linear, PipelineData.iteration_count | `src/ai_assistant/core/pipeline.py` (step loop), `src/ai_assistant/core/pipeline_steps.py` (self_query step), `src/ai_assistant/core/prompts/v1/self_query.j2` | `tests/test_pipeline.py`, `tests/test_integration.py`

[ ] Read-only внешние каталоги | Скрипт index_external.py + config rag.external_sources. Индексирует папки вне проекта без копирования/удаления оригиналов. Зачем: подключить Obsidian, Documents. | `scripts/index_external.py` (новый), `src/ai_assistant/core/config.py` (ExternalSourceConfig), `src/ai_assistant/core/domain/documents.py` (ChunkMetadata.original_path уже есть) | `tests/test_config.py`, `tests/test_rag.py`

[ ] RAGAS Eval / Faithfulness Check | Offline скрипт eval_rag.py. Оценивает context relevancy, faithfulness, answer relevancy. Зачем: измеряем качество RAG, видим регрессии. | `scripts/eval_rag.py` (новый), `src/ai_assistant/core/metrics.py` (RAG метрики), `src/ai_assistant/adapters/judge_llm.py` (small LLM для оценки) | `tests/test_metrics.py`, `tests/test_e2e.py`

[ ] Citations / Источники в ответе | LLM цитирует [1], [2] в ответе, API возвращает список sources. Зачем: пользователь видит откуда информация. ⚠️ CORE CHANGE: AssistantMessage.citations, Citation dataclass | `src/ai_assistant/core/domain/messages.py`, `src/ai_assistant/features/chat/manager.py`, `src/ai_assistant/features/chat/schemas.py`, `src/ai_assistant/core/prompts/v1/rag_strict.j2` | `tests/test_chat.py`, `tests/test_api.py`

---

## Что НЕ входит в план (отложено навсегда или до появления боли)

| Задача | Почему отложена |
|---|---|
| Заменить самописный metrics на `prometheus_client` | Работает. 120 строк кода не горят. |
| Упростить `RAGState` (semaphore, lock, cleanup) | Работает. Переинженеринг, но не баг. |
| Удалить лишние поля из `PipelineData` | 13 полей — много, но не ломает. |
| Упростить Jinja2 prompt loader | 4 шаблона, кэш не нужен, но работает. |
| Кэшировать повторные вычисления токенов | Без профиля неясно, является ли это узким местом. |
| Добавить проверку использования всех полей конфигурации | Требует deprecation политики. Не блокер. |
| Архитектурные тесты (AST, `except Exception`, соответствие rules) | Требует CI. Сейчас нет `.github/workflows/`. |
| Исправить `run_servers.py`: читать порты из конфига | Скрипт convenience, не критичен для продакшена. |
| Исправить `README.md`: документировать `vendor/` | Документация. Не ломает работу. |
| Исправить `[tool.mutmut]` в `pyproject.toml` | Mutmut не в CI. Не ломает работу. |

