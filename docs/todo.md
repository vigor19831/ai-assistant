Выдай список todo по одной строке в формате: [ ] Название + Краткая суть | Подробное описание (что, зачем, и ⚠️ CORE CHANGE если критично) | Файлы для правки | Файлы тестов / где проверять

===============================================================================
# TODO
===============================================================================
пройтись по скриптам. есть ошибки
не работает ллм и раг
падает сервер?

1.  [ ] Добавить log_file в AppConfig | lifespan читает config.log_file, но AppConfig не объявляет это поле. Приложение падает с AttributeError на старте. Добавить поле log_file: str | None = None. | src/ai_assistant/core/config.py | tests/test_config.py, tests/test_lifespan.py
2.  [ ] Добавить IClosable в IReranker | lifespan вызывает state.reranker.shutdown(), но порт IReranker не требует этого метода. Graceful shutdown падает с AttributeError. Добавить IClosable в наследование IReranker и реализовать shutdown во всех адаптерах reranker. | src/ai_assistant/core/ports/reranker.py, src/ai_assistant/adapters/reranker_null.py, src/ai_assistant/adapters/reranker_api.py | tests/test_contracts.py, tests/test_lifespan.py
3.  [ ] Защитить embeddings[0] в embed_query от IndexError | Нет проверки что embeddings не пустой перед извлечением [0]. Если embedder вернёт пустой список — IndexError. Добавить проверку if not embeddings: return data.add_error(...). | src/ai_assistant/core/pipeline_steps.py | tests/test_rag_pipeline.py
4.  [ ] Защитить embeddings[0] в hyde_query от IndexError | Аналогично embed_query — embeddings[0] без проверки. Добавить проверку if not embeddings: return data.add_error(...). | src/ai_assistant/core/pipeline_steps.py | tests/test_rag_pipeline.py
5.  [ ] Исправить KeyError prompt_version/prompt_name в generate() | generate() использует data.metadata["prompt_version"] и ["prompt_name"] без .get(). Pipeline падает с KeyError если вызывающий код не передал ключи. Заменить на .get() с fallback на значения из config. | src/ai_assistant/core/pipeline_steps.py | tests/test_rag_pipeline.py, tests/test_core_critical.py
6.  [ ] Перевести observability с Prometheus на логи | Удалить metrics.py, middleware.py, endpoint /metrics. В pipeline_steps заменить increment_counter на _logger.info с extra. | src/ai_assistant/core/metrics.py, src/ai_assistant/api/middleware.py, src/ai_assistant/main.py, src/ai_assistant/core/pipeline_steps.py | tests/test_smoke_pyproject.py
7.  [ ] Удалить tool-calling loop из generate() | IToolRegistry не реализован (FUTURE.md: blocked). Весь while response.tool_calls — мёртвый код, усложняющий чтение generate(). | src/ai_assistant/core/pipeline_steps.py | tests/test_core_critical.py
8.  [ ] Убрать мёртвые проверки if x is None после create_adapter | create_adapter либо возвращает объект, либо выбрасывает ValueError. Проверки в deps.py и lifespan.py — недостижимый шум. | src/ai_assistant/api/deps.py, src/ai_assistant/api/lifespan.py | tests/test_api_deps.py, tests/test_lifespan.py
9.  [ ] Удалить PID-file из lifespan | uvicorn сам управляет процессом. data/server.pid — legacy-декорация, не нужна для соло-запуска. Убрать запись и удаление файла. | src/ai_assistant/api/lifespan.py | tests/test_lifespan.py
10. [ ] Убрать импорт _mount_static из lifespan | Приватный API из другого модуля. Сделать функцию публичной (убрать _) или удалить /ui если не используется. | src/ai_assistant/api/lifespan.py, src/ai_assistant/api/static.py | tests/test_smoke_pyproject.py
11. [ ] Убрать бессмысленный os.unlink(tmp) в atomic_write | os.replace(tmp, target) уже удаляет tmp. Последующий os.unlink(tmp) в finally бросает FileNotFoundError (подавляется suppress). Убрать unlink. | src/ai_assistant/core/io_utils.py | tests/test_core_critical.py
12. [ ] Исправить имя env var для API ключа | os.getenv("AI_API_KEY") вместо AI_SECURITY_API_KEY. Env-переопределение API ключа не работает через стандартный механизм Pydantic Settings. Заменить на AI_SECURITY_API_KEY. | src/ai_assistant/api/security.py | tests/test_security.py
13. [ ] Удалить _model_list_cache | Кэш по id(cfg) для списка из 1–3 строк. CFG immutable, стройте на лету. Убрать глобальный dict и генерацию в list_models. | src/ai_assistant/features/chat/handlers.py | tests/test_api_e2e.py
14. [ ] Добавить Pydantic-схему для reindex_documents | Единственный эндпоинт в проекте без валидации входных данных (req: dict[str, Any]). Создать ReindexRequest с полями folder и clear. | src/ai_assistant/features/rag/handlers.py, src/ai_assistant/features/rag/schemas.py | tests/test_api_e2e.py
15. [ ] Защитить пустой last_user_msg в openai_chat_completions | Если в req.messages нет role="user", last_user_msg остаётся "". Пустая строка уходит в chat_manager.chat() — неопределённое поведение. Добавить проверку и HTTPException 400. | src/ai_assistant/features/chat/handlers.py | tests/test_api_e2e.py, tests/test_malformed_sse.py





    1–5: баги, ломающие runtime (старт, shutdown, pipeline). Делаем первым делом.
    6–7: рефакторинг pipeline_steps.py — тот же файл, что и 3–5, поэтому сразу после багов, пока контекст в голове.
    8–10: deps.py + lifespan.py — группируем по файлам, убираем мёртвый код и PID.
    11–15: атомарные правки в разных файлах, независимые друг от друга.
