Выдай список todo по одной строке в формате, все задания независимы друг от друга: [ ] Название + Краткая суть | Подробное описание (что, зачем, и ⚠️ CORE CHANGE если критично) | Файлы для правки | Файлы тестов / где проверять.

===============================================================================
# TODO
===============================================================================
Вот список задач по RAG — все независимы, можно брать в любом порядке:

[+] Источники в ответе чата | Добавить в конец ответа список использованных источников с гиперссылками на файлы. Формат: `[1] filename.md`. Путь должен быть кликабельным (file:/// или кастомный протокол). Зачем: пользователь видит, откуда взята информация. | `src/ai_assistant/features/chat/manager.py` (`_append_rag_sources`), `src/ai_assistant/core/domain/documents.py` (`ChunkMetadata` добавить `original_path`) | `tests/test_chat.py` (проверить формат sources), `tests/test_integration.py` (проверить metadata)

[ ] Read-only внешние каталоги | Скрипт `index_external.py` + config поле `rag.external_sources: list[{path, namespace, read_only}]`. Индексирует папки вне проекта, не копирует файлы, не удаляет оригиналы. Зачем: подключить Obsidian, Documents и т.д. без изменения структуры. | `scripts/index_external.py` (новый), `src/ai_assistant/core/config.py` (`RAGConfig` + `ExternalSourceConfig`), `src/ai_assistant/core/domain/documents.py` (`ChunkMetadata.original_path`) | `tests/test_config.py` (проверить парсинг config), `tests/test_rag.py` (проверить read-only guard)

[ ] Contextual Compression | Новый pipeline step `compress_context` между `rerank` и `build_context`. Использует маленький LLM (1-2B, локальный) для извлечения 2-3 релевантных предложений из каждого chunk. Зачем: больше chunk'ов помещается в context window, каждый dense. | `src/ai_assistant/core/pipeline_steps.py` (новый `compress_context`), `src/ai_assistant/core/ports/compressor.py` (новый port `ICompressor`, ⚠️ новый port = регистрация в factory), `src/ai_assistant/adapters/compressor_llm.py` (реализация через тот же LLM) | `tests/test_pipeline.py` (новый `TestCompressContext`), `tests/test_integration.py` (проверить end-to-end)

[ ] Hybrid Search BM25 + Vector | Новый adapter `BM25Retriever` + step `hybrid_retrieve`. Объединяет BM25 (keyword) и vector search через RRF (Reciprocal Rank Fusion). Зачем: ловит exact matches, которые vector пропускает. | `src/ai_assistant/adapters/retriever_bm25.py` (новый), `src/ai_assistant/core/ports/retriever.py` (новый port `IRetriever`, ⚠️ CORE CHANGE: новый port), `src/ai_assistant/core/pipeline_steps.py` (новый `hybrid_retrieve`), `src/ai_assistant/api/deps.py` (init в `AppState`) | `tests/test_adapters.py` (тест BM25), `tests/test_pipeline.py` (тест hybrid), `tests/test_integration.py` (end-to-end)

[ ] Query Expansion | Новый step `expand_query` перед `embed_query`. LLM переписывает query в 2-3 варианта, retrieve по всем, merge results через RRF. Зачем: улучшает recall для сложных/коротких запросов. | `src/ai_assistant/core/pipeline_steps.py` (новый `expand_query`), `src/ai_assistant/core/prompts/v1/query_expand.j2` (новый prompt template) | `tests/test_pipeline.py` (тест expand_query), `tests/test_integration.py` (проверить merge results)

[ ] Re-ranker Cross-Encoder | Новый adapter `CrossEncoderReranker` вместо `NullReranker`. Использует локальную модель (например `bge-reranker-v2-m3` через `transformers`). Зачем: точнее чем score-based NullReranker. | `src/ai_assistant/adapters/reranker_cross_encoder.py` (новый, ⚠️ новая зависимость `transformers` или `sentence-transformers`), `src/ai_assistant/core/domain/configs.py` (`RerankerConfigData` добавить `model_path`) | `tests/test_adapters.py` (тест cross-encoder), `tests/test_properties.py` (проверить регистрацию)

[ ] Parent-Child Chunking | Два уровня chunk'ов: small (retrieval) + large parent (context). Small chunk ссылается на parent. При retrieval берём small, но в context подаём parent. Зачем: точный поиск + полный контекст. ⚠️ CORE CHANGE: меняет `Chunk` schema, `IChunker`, `IVectorStore` (два индекса), `PipelineData`. | `src/ai_assistant/core/domain/documents.py` (`Chunk.parent_id`, `Chunk.parent_text`), `src/ai_assistant/core/ports/chunker.py` (`IChunker` возвращает пары), `src/ai_assistant/core/pipeline_steps.py` (`retrieve` загружает parent), `src/ai_assistant/adapters/vector_store_*.py` (два индекса или joined storage) | `tests/test_domain.py` (Chunk schema), `tests/test_pipeline.py` (retrieve с parent), `tests/test_integration.py` (end-to-end)

[ ] Semantic Cache для Retrieval | Кэшировать `query_embedding → chunks` в LRU (memory) или на диске. Проверять по cosine similarity > threshold (0.95). Зачем: ускоряет повторные запросы, снижает нагрузку на embedder/vector store. | `src/ai_assistant/adapters/cache_semantic.py` (новый), `src/ai_assistant/core/pipeline_steps.py` (`embed_query` проверять cache first), `src/ai_assistant/core/domain/configs.py` (`CacheConfigData`) | `tests/test_pipeline.py` (тест hit/miss), `tests/test_adapters.py` (тест cache eviction)

[ ] Multi-hop Self-Query | Если после `generate` ответ неполный/неточный — автоматически reformulate query и повторить retrieval. Зачем: находит информацию, разбросанную по разным chunk'ам. | `src/ai_assistant/core/pipeline_steps.py` (новый `self_query` step после `generate` или loop в `RAGPipeline`), `src/ai_assistant/core/prompts/v1/self_query.j2` (prompt для reformulation) | `tests/test_pipeline.py` (тест multi-hop loop), `tests/test_integration.py` (end-to-end с reformulation)

[ ] RAGAS Eval / Faithfulness Check | Offline скрипт `scripts/eval_rag.py`. Берёт N query из history, прогоняет через pipeline, оценивает: context relevancy, faithfulness (ответ grounded?), answer relevancy. Зачем: измеряем качество RAG, видим регрессии. | `scripts/eval_rag.py` (новый), `src/ai_assistant/core/metrics.py` (добавить RAG метрики), `src/ai_assistant/adapters/judge_llm.py` (small LLM для оценки) | `tests/test_metrics.py` (тест метрик), `tests/test_e2e.py` (end-to-end eval)







core
[ ] RerankResult не frozen | Датакласс RerankResult не имеет frozen=True, нарушая правило иммутабельности портовых объектов и позволяя мутировать результаты ранжирования | src/ai_assistant/core/ports/reranker.py | tests/test_contracts.py, tests/test_adapters.py
[ ] ToolCall не frozen | Датакласс ToolCall не имеет frozen=True, нарушая контракт иммутабельности и позволяя изменять аргументы вызова инструмента после создания | src/ai_assistant/core/ports/tools.py | tests/test_contracts.py, tests/test_domain.py
[ ] ITool использует Any для конфига | Конструктор ITool принимает config: Any, что нарушает правило чистоты типов (запрет Any там, где виден конкретный тип) | src/ai_assistant/core/ports/tools.py | tests/test_contracts.py, tests/test_smoke.py
[ ] ToolSpec.parameters использует Any | Поле parameters имеет тип dict[str, Any] вместо dict[str, object], что нарушает строгую типизацию и правило запрета Any | src/ai_assistant/core/ports/tools.py | tests/test_contracts.py, tests/test_smoke.py
[ ] PipelineData.metadata использует Any | Словарь metadata имеет тип dict[str, Any], создавая untyped bag. ⚠️ CORE CHANGE: требуется замена на TypedDict или явные поля для обеспечения типобезопасности | src/ai_assistant/core/domain/pipeline.py, src/ai_assistant/core/pipeline_steps.py | tests/test_contracts.py, tests/test_domain.py, docs/drift.md
[ ] Jinja2 импортируется в core/ | Прямой импорт jinja2 в core/prompts нарушает абсолютное ограничение "stdlib-only" для ядра. ⚠️ CORE CHANGE: требуется абстракция IPromptRenderer и перенос реализации в adapters/ | src/ai_assistant/core/prompts/__init__.py | tests/test_contracts.py, docs/drift.md



adapters
[ ] Unwrapped HTTP errors in Embedder | httpx.HTTPError пробрасывается напрямую, нарушая AI Rules §6 (бизнес-слой не должен видеть внешние библиотеки). Требуется оборачивание в AdapterError с logger.exception. | src/ai_assistant/adapters/embedder_openai_compatible.py | tests/test_resilience.py
[ ] Unwrapped HTTP/JSON errors in Reranker | Ошибки сети и парсинга JSON не обернуты в AdapterError. Утечка httpx-исключений в пайплайн нарушает контракт адаптера. | src/ai_assistant/adapters/reranker_api.py | tests/test_resilience.py
[ ] Unwrapped HTTP/JSON errors in LLM | _complete_impl и _stream_impl не ловят httpx.HTTPError и json.JSONDecodeError. Сбой сети или невалидный SSE отдают чужеродные исключения в features/. | src/ai_assistant/adapters/llm_openai_compatible.py | tests/test_resilience.py
[ ] Silent JSON corruption in SQLite | _safe_json_loads глотает json.JSONDecodeError без логирования. Это скрывает повреждение данных в БД и усложняет отладку. | src/ai_assistant/adapters/storage_sqlite.py | tests/test_adapters.py
[ ] Unhandled JSON error in Memory Store | load() не обрабатывает json.JSONDecodeError при чтении memory_store.json. Падение с необработанным исключением вместо AdapterError. | src/ai_assistant/adapters/vector_store_memory.py | tests/test_adapters.py
[ ] Wrong exception type in Factory | factory.py бросает ValueError при отсутствии faiss-cpu/sqlite3. По домену это ошибка конфигурации, требуется ConfigurationError для единообразия таксономии ошибок. | src/ai_assistant/adapters/factory.py | tests/test_adapters.py, docs/error_taxonomy.md





features
[ ] Orphaned `limiter` field | В `AppState` и `InitializedAppState` осталось поле `limiter: object | None` после удаления rate-limiter'а; нарушает правило "Orphaned code — remove callee". | `src/ai_assistant/api/deps.py` | `tests/test_api.py`, `tests/conftest.py`
[ ] Missing `LLM_UNAVAILABLE` export | Константа `LLM_UNAVAILABLE` определена в `core/domain/errors.py`, но отсутствует в `__all__`, что ломает явные импорты и строгие контракты. | `src/ai_assistant/core/domain/errors.py` | `tests/test_domain.py`, `mypy`
[ ] Adapter leakage in Core | Поля `n_gpu_layers`, `n_batch`, `mmap`, `mlock` в `LLMConfigData` специфичны для llama.cpp, но находятся в неизменяемом ядре; ⚠️ CORE CHANGE (удаление из dataclass). | `src/ai_assistant/core/domain/configs.py`, `src/ai_assistant/core/config.py` | `tests/test_config.py`, `tests/test_contracts.py`
[ ] Implicit `anyio` dependency | В `vector_store_faiss.py` используется `import anyio`, но библиотека отсутствует в явных зависимостях `pyproject.toml` (работает только как транзитивная). | `pyproject.toml`, `src/ai_assistant/adapters/vector_store_faiss.py` | `pyproject.toml`, `scripts/check_all.py`
[ ] Global mutable state in RAG | Глобальные переменные `_reindex_semaphore`, `_reindex_tasks` в `handlers.py` нарушают принцип явного состояния и требуют хаков в `conftest.py` для сброса. | `src/ai_assistant/features/rag/handlers.py` | `tests/test_rag.py`, `tests/conftest.py`
[ ] Magic string `gpt-4o` in Core | В `core/utils.py` (`count_tokens`) захардкожен дефолт `model="gpt-4o"`; нарушает правило "No bare literals" и "Explicit over implicit". | `src/ai_assistant/core/utils.py` | `tests/test_tokenizer.py`










tests/, scripts/, config.yaml
[ ] Мертвая зависимость `sqlmodel` | В `pyproject.toml` указан `sqlmodel`, но в проекте используется только `aiosqlite` и стандартный `sqlite3`. Нарушает абсолютное ограничение "No orphaned code / dependencies". Раздувает окружение без причины. | `pyproject.toml` | `grep -r sqlmodel src/`, `scripts/check_all.py` (AST audit)
[ ] Некорректный путь в `mutmut` | В `pyproject.toml` в `paths_to_mutate` указана несуществующая директория `src/ai_assistant/pipeline/` (файл лежит в `core/pipeline.py`). Мутационное тестирование конфигурируется некорректно. | `pyproject.toml` | `ls src/ai_assistant/`, запуск `mutmut run`
[ ] Кириллица в скриптах | `scripts/context_build.py` и `scripts/error_taxonomy_build.py` содержат кириллицу в комментариях, строках и логах. Нарушает Output Protocol (`ai_rules.md`: "No Cyrillic in code/comments"). | `scripts/context_build.py`, `scripts/error_taxonomy_build.py` | `tests/test_smoke.py::TestNoCyrillic` (требуется расширение на `scripts/`)
[ ] Хардкод портов в `kill.py` | Порты `8080, 8081, 8000` захардкожены в константах. Если пользователь изменит их в `config.yaml`, экстренный kill switch не найдет процессы. Необходимо читать из конфига или env. | `scripts/kill.py` | Изменить порты в `config.yaml`, запустить `python scripts/kill.py`
[ ] Слепая зона AST-аудита в тестах | `test_smoke.py` (классы `TestNoPrintPprintAST`, `TestNoCyrillic`) сканирует только `_src_dir()`, полностью игнорируя `scripts/`. Это позволяет утилитам нарушать правила без падения CI. | `tests/test_smoke.py` | `pytest tests/test_smoke.py -v`
[ ] Рассинхрон паттернов очистки | `SAFE_PATTERNS` в `scripts/clean_cache.py` и правила в `.gitignore` дублируются вручную. При добавлении новых артефактов (например, кэшей новых тулов) они забываются в одном из мест. | `scripts/clean_cache.py`, `.gitignore` | Ручной аудит, запуск `python scripts/clean_cache.py`
[ ] Утечка llama.cpp-полей в `config.yaml` | Поля `n_gpu_layers`, `mmap`, `mlock` присутствуют в секциях `embedder` и `llm`. Они специфичны для llama.cpp и игнорируются Ollama/vLLM, но строго валидируются Pydantic. Засоряют универсальный конфиг. | `config.yaml`, `src/ai_assistant/core/config.py` | ⚠️ CORE CHANGE (если трогать домен `configs.py`) или зафиксировать как Known Drift в `docs/drift.md`.
