# Known Architectural Drift

| ID | File | Broken Rule | Why | Fix | Priority |
|----|------|-------------|-----|-----|----------|
| 1 | Fixed 2026-06-09: get_context_limit() added to ILLM port. All adapters updated. |
| 2 | Fixed 2026-06-09: NullReranker introduced. `rerank()` no longer branches on `None`. `InitializedAppState.reranker` is `IReranker` (non-optional). |
| 3 | Fixed 2026-06-09: getattr(config, "vector_store") removed. Pydantic validation guarantees field presence. |
| 4 | Fixed 2026-06-13: Replaced all `getattr(config, "x", default)` with direct `config.x` access in all adapters. All defaults verified in `AppConfig` Pydantic models. |
| 5 | Fixed 2026-06-14: `ChunkMetadata` schema drift. `vector_store_faiss.py` and `vector_store_memory.py` serialized `created_at` (not in domain model) and missed `total_chunks` in FAISS `add()`. Introduced `dataclass_from_dict` in `core/utils.py` for strict deserialization. |
| 6 | Fixed 2026-06-14: Added `get_logger` to `embedder_openai_compatible.py` and `reranker_api.py`. All `AdapterError` wraps now preceded by `logger.exception`. |
| 7 | `adapters/embedder_openai_compatible.py`, `adapters/llm_openai_compatible.py` | Duplicate HTTP client setup (httpx.AsyncClient, POST, raise_for_status, json parse) | Layer boundaries prevent shared httpx code: core/ is stdlib-only, adapters/ may only import core/*. Extracting to core/ violates stdlib-only rule. Extracting to adapters/_shared violates layer boundaries. | Accept duplication as architectural constraint. Revisit if >3 adapters share pattern. | Low |
| 8 | `src/ai_assistant/core/pipeline_steps.py` (retrieve, rerank, generate) | `typing.cast("PipelineConfig | None", data.metadata.get("pipeline_config"))` | `PipelineData.metadata: dict[str, Any]` is untyped bag. Steps extract values by string key with no static type guarantee. Mypy requires cast; Ruff TC006 requires quoted type in cast. | Accept cast as temporary measure. Fix by structuring PipelineData metadata (TypedDict or explicit fields) — CORE CHANGE REQUIRED. See proposed fix in docs/ai_rules_proposed.md or core refactor backlog. | Low |
| 9 | ~~`src/ai_assistant/core/pipeline_steps.py`~~ (fixed 2026-06-17) | ~~`model: str = "gpt-4o"` default~~ | ~~Default был fallback для тестов/CLI~~ | **Fixed:** убраны все дефолты `"gpt-4o"` из `_estimate_tokens()` и `_truncate_to_fit()`. `tokenizer_model` теперь обязательный ключ в metadata. `ChatManager` всегда передаёт его. Все тесты обновлены. | — |
| 10 | `src/ai_assistant/core/retry.py` | `max_retries=3, delay=1.0, backoff=2.0` хардкод в `@with_retry` на адаптерах | Resilience policy — не бизнес-логика. Меняется раз в 10 лет. Вынесение в config требует CORE CHANGE (новые поля в `EmbedderConfigData`, `LLMConfigData`, `RerankerConfigData`) + inline-фабрики декораторов (костыль). | Accept as architectural constraint. Пересмотреть при добавлении `IRetryPolicy` порта или embedded-режима с 0 retries. | Low |
| 11 | `src/ai_assistant/core/prompts/__init__.py` | Jinja2 import в core/ | Prompt rendering — domain logic, Jinja2 — implementation detail. Для 30-летнего горизонта абстракция `IPromptRenderer` предпочтительна, но требует нового порта + адаптера + обновления factory + всех вызовов. | Accept as grandfathered exception. Документировать при добавлении второго движка шаблонов (Mustache, etc.). | Low |
| 12 | `src/ai_assistant/core/prompts/__init__.py` | `_make_hashable()` без защиты от циклических ссылок | Текущие prompts не содержат self-referencing dataclasses. Защита — YAGNI. | Accept. Добавить при первом `RecursionError` в продакшене. | Low |



Rule: Do not add new drift if old pattern can be fixed properly.
