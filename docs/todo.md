Выдай список todo по одной строке в формате: [ ] Название + Краткая суть | Подробное описание (что, зачем, и ⚠️ CORE CHANGE если критично) | Файлы для правки | Файлы тестов / где проверять

===============================================================================
# TODO
===============================================================================

[х] Удалить мусорный getattr из main.py и admin.py | Заменить getattr(cfg.llm, "model", "unknown") на прямой доступ cfg.llm.model. Pydantic гарантирует наличие поля, getattr — мертвый код. | src/ai_assistant/main.py:47, src/ai_assistant/api/admin.py:42 | tests/test_api_e2e.py, tests/test_contracts.py

[ ] Удалить мусорный getattr из chat/manager.py | Заменить getattr(self.llm, "system_message", None) на self.llm.system_message. Поле объявлено в ILLM, прямой доступ безопасен. | src/ai_assistant/features/chat/manager.py:82 | tests/test_chat_manager_direct.py, tests/test_api_e2e.py

[ ] Удалить мусорный getattr из static.py | Заменить getattr(config, "ui", None) на config.ui. AppConfig всегда имеет ui: UIConfig. | src/ai_assistant/api/static.py:20 | tests/test_smoke_pyproject.py

[ ] Убрать underscore prefix из импортов router.py | _chat_handlers/_rag_handlers → chat_handlers/rag_handlers. Underscore вводит в заблуждение для публичных импортов. | src/ai_assistant/api/router.py:15-16 | tests/test_router_compile.py

[ ] Добавить NotImplementedError в stream_chat TODO | TODO без владельца = технический долг без срока. Лучше явный краш, чем тихий пропуск. | src/ai_assistant/features/chat/manager.py:240 | tests/test_chat_manager_direct.py

[ ] ⚠️ CORE CHANGE: Добавить get_context_limit() в ILLM | Порт ILLM не объявляет config, но pipeline_steps.py и utils.py используют getattr(llm, "config"). Новый адаптер без .config сломает pipeline тихо. Добавить get_context_limit() -> int | None в ILLM, реализовать в адаптерах, удалить core/utils.get_context_limit(). | core/ports/llm.py, core/utils.py, core/pipeline_steps.py, adapters/llm_mock.py, adapters/llm_openai_compatible.py, features/chat/manager.py | tests/test_contracts.py, tests/test_core_critical.py, tests/test_rag_pipeline.py

[ ] ⚠️ CORE CHANGE: Добавить index_path в IVectorStore | Порт IVectorStore не объявляет index_path, но lifespan.py и rag/manager.py обращаются к .config.index_path. Новый адаптер без .config сломает health check. Добавить @property index_path -> str, реализовать в адаптерах. | core/ports/vector_store.py, adapters/vector_store_faiss.py, adapters/vector_store_memory.py, features/rag/manager.py, api/lifespan.py | tests/test_contracts.py, tests/test_lifespan.py, tests/test_resilience.py

[ ] ⚠️ CORE CHANGE: Создать NullReranker и убрать if reranker is None из pipeline | Шаг rerank() проверяет if reranker is None — нарушение чистоты. Создать NullReranker (no-op), зарегистрировать в factory. В deps.py: если reranker не настроен — NullReranker. Убрать if из pipeline_steps.py. | core/pipeline_steps.py, adapters/reranker_null.py, adapters/factory.py, api/deps.py | tests/test_rag_pipeline.py, tests/test_contracts.py, tests/test_api_deps.py

[ ] Убрать defensive getattr из lifespan.py (дрейф #3) | Заменить getattr(config, "vector_store", None) на config.vector_store. Валидация Pydantic гарантирует наличие. | src/ai_assistant/api/lifespan.py:52 | tests/test_lifespan.py, tests/test_resilience.py

[ ] ⚠️ CORE CHANGE: Добавить ToolMessage в domain/messages.py | Тип Message = ... | dict[str, Any] размывает типовую систему. Добавить ToolMessage(role="tool", content, tool_call_id) dataclass. Обновить Message alias. Обновить generate() для использования ToolMessage вместо dict. | core/domain/messages.py, core/ports/llm.py, core/pipeline_steps.py | tests/test_core_critical.py, tests/test_contracts.py, tests/test_rag_pipeline.py

[ ] Обновить drift.md после исправления дрейфов | Пометить #1, #2, #3, #6 как исправленные. Добавить новые если остались. | docs/drift.md | python scripts/check_all.py, git diff

[ ] Обновить error_taxonomy.md если добавлены исключения | Проверить синхронизацию с кодом. | docs/error_taxonomy.md | python scripts/error_taxonomy_build.py



