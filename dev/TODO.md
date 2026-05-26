`context_build_compact.md`. в новом чате и блок от начала до конца


=== НАЧАЛО БЛОКА: Фаза 2.4 ===

## Промпт

Ты — senior Python-разработчик. Работаешь с проектом AI Assistant (модульный фреймворк для локальных LLM). Проект работает полностью offline, поддерживает RAG, совместим с OpenAI API.

## Статус проекта
Фазы 0, 1, 2.1 выполнены. Все тесты проходят.

## Задача: Фаза 2.4 — SaveChatRequest schema + LLMConfig cleanup

### Контекст
`src/ai_assistant/features/rag/handlers.py`:
```python
@router.post("/save-chat", ...)
async def save_chat(
    req: dict[str, Any],
    state: Annotated[AppState, Depends(get_state)],
) -> dict[str, Any]:
    namespace = req.get("namespace", "personal")
    filename = req.get("filename", "chat.md")
    content = req.get("content", "")
    ...
```

`src/ai_assistant/features/rag/schemas.py`:
```python
class SaveChatRequest(BaseModel):
    content: str = Field(..., min_length=1)
    namespace: str = Field(default="personal", pattern=r"^(personal|work|other)$")
    filename: str = Field(default="chat.md", pattern=r"^[^/\][^\]*$")
```

`src/ai_assistant/core/config.py`:
```python
class LLMConfig(BaseSettings):
    provider: str = "mock"
    model: str = "gpt-4o-mini"
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 300.0
    stop_sequences: list[str] = Field(default_factory=list)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=-1)
    min_p: float = Field(default=0.05, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=0.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    # llama.cpp-specific:
    n_gpu_layers: int = Field(default=-1, ge=-1, le=999)
    split_mode: Literal["layer", "row", "none"] = "layer"
    main_gpu: int = Field(default=0, ge=0)
    tensor_split: list[float] = Field(default_factory=list)
    num_threads: int = Field(default=0, ge=0)
    flash_attn: bool = False
    mmap: bool = True
    mlock: bool = False
    cache_type_k: Literal["f16", "q8_0", "q4_0", "q4_1"] = "f16"
    cache_type_v: Literal["f16", "q8_0", "q4_0", "q4_1"] = "f16"
    rope_scaling: float = Field(default=1.0, gt=0.0)
    yarn_ext_factor: float = -1.0
    yarn_attn_factor: float = 1.0
    draft_model: str | None = None
    draft_n_predict: int = Field(default=16, ge=1)
```

### Что сделать
1. `save_chat` endpoint: заменить `req: dict[str, Any]` на `req: SaveChatRequest`. Убрать ручные проверки path traversal (Pydantic `pattern` уже есть).
2. `LLMConfig`: оставить только generic поля (`provider`, `model`, `max_tokens`, `temperature`, `timeout`, `stop_sequences`, `top_p`, `top_k`, `min_p`, `repeat_penalty`, `presence_penalty`, `frequency_penalty`). Все llama.cpp-специфичные перенести в `extra: dict[str, Any]`. Адаптеры читают `config.extra.get(...)`.
3. Обновить `dev/tests/config.test.yaml` если нужно.

### Тест
- `test_security.py` — path traversal через `SaveChatRequest`, assert 422 от Pydantic.
- `test_contracts.py` — `LLMConfig` не содержит llama-specific полей верхнего уровня.

## Правила
- Не добавляй сложность ради сложности.
- Любое изменение core требует обновления всех зависимых адаптеров и тестов.
- Пиши тесты.

=== КОНЕЦ БЛОКА ===

---

















=== НАЧАЛО БЛОКА: Фаза 3.2 ===

## Промпт

Ты — senior Python-разработчик. Работаешь с проектом AI Assistant (модульный фреймворк для локальных LLM). Проект работает полностью offline, поддерживает RAG, совместим с OpenAI API.

## Статус проекта
Фазы 0, 1, 2.1–2.4 выполнены. Все тесты проходят.

## Задача: Фаза 3.2 — /reindex без subprocess

### Контекст
`src/ai_assistant/features/rag/handlers.py`:
```python
@router.post("/reindex", ...)
async def reindex_documents(
    req: dict[str, Any],
    state: Annotated[AppState, Depends(get_state)],
) -> dict[str, Any]:
    folder = req.get("folder")
    clear = req.get("clear", False)

    try:
        script_path = _resolve_script("scripts.index_documents")
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))

    cmd = [sys.executable, str(script_path)]
    if folder:
        cmd.extend(["--folder", folder])
    if clear:
        cmd.append("--clear")

    proc = await asyncio.create_subprocess_exec(*cmd, ...)
    stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=300)
    ...
```

### Что сделать
1. Вынести логику индексации из `ops/scripts/index_documents.py` в shared library (`features/rag/indexing.py` с `async def index_folder(folder, clear, chunker, embedder, vector_store)`).
2. В handler'е: `asyncio.create_task(index_folder(...))` + `asyncio.Semaphore(1)` (только один reindex одновременно).
3. Вернуть `{status: "started", task_id: ...}` сразу, не ждать 300 секунд.
4. Добавить endpoint `/reindex/status/{task_id}` опционально (можно просто логировать).

### Что НЕ делать
- Не использовать Celery/Redis/RQ (solo guardrail).

### Тест
`test_rag_pipeline.py` — reindex не блокирует event loop, возвращает status immediately.

## Правила
- Не добавляй сложность ради сложности.
- Solo guardrails: нет Celery/Redis, asyncio достаточно.
- Пиши тесты.

=== КОНЕЦ БЛОКА ===

---


















=== НАЧАЛО БЛОКА: Фаза 4.1 === ОБЯЗАТЕЛЬНО 4.1-4.2-4.3 ПОСЛЕДОВАТЕЛЬНОСТЬ

## Промпт

Ты — senior Python-разработчик. Работаешь с проектом AI Assistant (модульный фреймворк для локальных LLM). Проект работает полностью offline, поддерживает RAG, совместим с OpenAI API.

## Статус проекта
Фазы 0, 1, 2.1–2.4, 3.2 выполнены. Все тесты проходят.

## Задача: Фаза 4.1 — logger.exception + generic HTTP errors

### Контекст (фрагменты из разных файлов)
`api/lifespan.py`: `except Exception as exc: logger.warning("%s shutdown failed: %s", name, exc)`
`features/chat/handlers.py`: `except Exception as exc: _logger.exception("Chat failed: %s", exc); raise HTTPException(status_code=500, detail=str(exc))`
`pipeline/steps.py`: `except Exception as e: data.errors.append(f"embed_query failed: {e}")`
`core/tool_registry.py`: `except Exception as e: return ToolResult(..., error=str(e))`

### Что сделать
1. Все `logger.warning("... %s", exc)` → `logger.exception("...")` (автоматически логирует traceback).
2. Все HTTP-ответы клиенту → generic `"Internal server error"`, детали только в лог.
3. `HTTPException` — пропускать как есть (уже правильный status/detail).

### Файлы для обновления
- `api/lifespan.py`
- `api/deps.py`
- `features/chat/handlers.py`
- `features/image_analysis/handlers.py`
- `features/rag/handlers.py`
- `pipeline/steps.py`
- `core/tool_registry.py`

### Тест
`test_resilience.py` — вызвать ошибку в `lifespan._async_cleanup`, assert лог содержит `Traceback (most recent call last)`.

## Правила
- Не добавляй сложность ради сложности.
- Пиши тесты.

=== КОНЕЦ БЛОКА ===

---

















=== НАЧАЛО БЛОКА: Фаза 4.2 === ОБЯЗАТЕЛЬНО 4.1-4.2-4.3 ПОСЛЕДОВАТЕЛЬНОСТЬ

## Промпт

Ты — senior Python-разработчик. Работаешь с проектом AI Assistant (модульный фреймворк для локальных LLM). Проект работает полностью offline, поддерживает RAG, совместим с OpenAI API.

## Статус проекта
Фазы 0, 1, 2.1–2.4, 3.2, 4.1 выполнены. Все тесты проходят.

## Задача: Фаза 4.2 — Удалить dead ports

### Контекст
`src/ai_assistant/core/ports/events.py`:
```python
class IEventBus:
    async def publish(self, event: str, payload: Any) -> None: ...
    async def subscribe(self, event: str, handler: Any) -> None: ...
```

`src/ai_assistant/core/ports/modality.py`:
```python
class IModalityProcessor(ABC):
    async def process(self, data: Any) -> Any: ...
```

`src/ai_assistant/core/ports/__init__.py`:
```python
from .chunker import IChunker
from .embedder import IEmbedder
from .llm import ILLM
from .memory import ILongTermMemory
from .reranker import IReranker, RerankResult
from .storage import IChatStorage, ISettingsStorage
from .transport import ITransport
from .vector_store import IVectorStore
from .vision import IVisionProcessor
from .voice import IVoiceRecognizer, IVoiceSynthesizer
```

### Что сделать
1. Удалить `core/ports/events.py` и `core/ports/modality.py`.
2. Убрать `IEventBus` и `IModalityProcessor` из `core/ports/__init__.py`.
3. Обновить `dev/tests/test_contracts.py`: assert файлы не существуют.

### Тест
`test_contracts.py` — `assert not (PORTS_DIR / "events.py").exists()`.

## Правила
- Не добавляй сложность ради сложности.
- Solo guardrails: нет event bus, modality pipeline.
- Пиши тесты.

=== КОНЕЦ БЛОКА ===

---

















=== НАЧАЛО БЛОКА: Фаза 4.3 === ОБЯЗАТЕЛЬНО 4.1-4.2-4.3 ПОСЛЕДОВАТЕЛЬНОСТЬ

## Промпт

Ты — senior Python-разработчик. Работаешь с проектом AI Assistant (модульный фреймворк для локальных LLM). Проект работает полностью offline, поддерживает RAG, совместим с OpenAI API.

## Статус проекта
Фазы 0, 1, 2.1–2.4, 3.2, 4.1–4.2 выполнены. Все тесты проходят.

## Задача: Фаза 4.3 — NO_INFO_PHRASES frozenset + tool_registry error handling

### Контекст
`features/chat/manager.py` + `features/rag/manager.py`:
```python
NO_INFO_PHRASES = ['не достаточно', 'недостаточно', 'не имею', 'не знаю', 'not enough', "don't have", 'no information', 'не найдено', 'not found', "i don't have", 'i do not have', "don't know", 'do not know', 'у меня недостаточно', 'у меня нет']
```

`core/tool_registry.py`:
```python
except Exception as e:
    return ToolResult(
        call_id=call.call_id,
        output="",
        error=str(e),
        is_error=True,
    )
```

### Что сделать
1. `features/chat/manager.py` + `features/rag/manager.py`: вынести `NO_INFO_PHRASES` в `core/constants.py` как `FROZEN_NO_INFO_PHRASES: frozenset[str]`.
2. `core/tool_registry.py`: `dispatch` — заменить `except Exception as e: return ToolResult(...)` на `except Exception: _logger.exception("Tool %s failed", call.tool_name); return ToolResult(..., error="Tool execution failed")`.

### Тест
- `test_core_critical.py` — `assert NO_INFO_PHRASES is frozenset`.
- `test_core_critical.py` — mock tool raising `ValueError`, assert `logger.exception` called.

## Правила
- Не добавляй сложность ради сложности.
- Пиши тесты.

=== КОНЕЦ БЛОКА ===

---




















=== НАЧАЛО БЛОКА: Фаза 4.4 ===

## Промпт

Ты — senior Python-разработчик. Работаешь с проектом AI Assistant (модульный фреймворк для локальных LLM). Проект работает полностью offline, поддерживает RAG, совместим с OpenAI API.

## Статус проекта
Фазы 0, 1, 2.1–2.4, 3.2, 4.1–4.3 выполнены. Все тесты проходят.

## Задача: Фаза 4.4 — Убрать load_config() с уровня модуля main.py

### Контекст
`src/ai_assistant/main.py`:
```python
_config = load_config(os.getenv("AI_CONFIG_PATH", "config.yaml"))

app = FastAPI(...)

for router in assemble_routers():
    app.include_router(router)

static_dir = Path(_config.ui.static_path)
...
app.mount("/ui", StaticFiles(...))
```

### Что сделать
1. Перенести `load_config()` в `lifespan` (уже есть `_load_config()` там).
2. Перенести `assemble_routers()` в `lifespan` или factory, вызываемую в `lifespan`.
3. `main.py` создаёт `app = FastAPI(lifespan=lifespan)` без config.
4. `static_dir` — в lifespan или отложенный mount.

### Тест
`test_api_e2e.py` — импорт `main.py` не вызывает `load_config` (mock, assert 0 calls до стартап).

## Правила
- Не добавляй сложность ради сложности.
- Пиши тесты.

=== КОНЕЦ БЛОКА ===















---

=== НАЧАЛО БЛОКА: Фаза 6.1 ===

## Промпт

Ты — senior Python-разработчик. Работаешь с проектом AI Assistant (модульный фреймворк для локальных LLM). Проект работает полностью offline, поддерживает RAG, совместим с OpenAI API.

## Статус проекта
Фазы 0, 1, 2.1–2.4, 3.2, 4.1–4.4 выполнены. Все тесты проходят.

## Задача: Фаза 6.1 — AI_RULES.md + README cleanup

### Контекст
Проект: `dev/AI_RULES.md` — архитектурные правила. `README.md` — user-facing описание. `dev/scripts/context_build.py` — генерирует `context_build.md`.

### Что сделать
1. Создать/обновить `dev/AI_RULES.md` — перенести архитектурные правила из `README.md` (sacred core, adapter discipline, feature isolation, solo guardrails).
2. Обновить `README.md` — убрать AI-маркеры, оставить чистое описание для пользователей (возможности, быстрый старт, требования).
3. Обновить `dev/scripts/context_build.py` — тянуть `AI_RULES.md` вместо маркеров из `README.md`.

### Тест
`context_build.py` генерирует корректный `context_build.md` с `AI_RULES.md` в блоке guidelines.

## Правила
- Не добавляй сложность ради сложности.
- Пиши чистую документацию.

=== КОНЕЦ БЛОКА ===
