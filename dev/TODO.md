`context_build_compact.md`. в новом чате и блок от начала до конца



## Промпт для Подфазы 2.4.1 — SaveChatRequest schema

```
=== НАЧАЛО БЛОКА: Фаза 2.4.1 ===

## Промпт
Ты — senior Python-разработчик. Работаешь с проектом AI Assistant.

## Задача
В `src/ai_assistant/features/rag/handlers.py` endpoint `save_chat` принимает `req: dict[str, Any]`. Нужно заменить на `req: SaveChatRequest` из `schemas.py`. Убрать ручные проверки namespace и filename — Pydantic `pattern` уже делает это.

## Текущий код (из context_build_compact.md)
```python
@router.post("/save-chat", response_model=None)
async def save_chat(
    req: dict[str, Any],
    state: Annotated[AppState, Depends(get_state)],
) -> dict[str, Any]:
    namespace = req.get("namespace", "personal")
    filename = req.get("filename", "chat.md")
    content = req.get("content", "")
    ...
    # ручные проверки path traversal (убрать)
```

`SaveChatRequest` уже есть в `schemas.py`:
```python
class SaveChatRequest(BaseModel):
    content: str = Field(..., min_length=1)
    namespace: str = Field(default="personal", pattern=r"^(personal|work|other)$")
    filename: str = Field(default="chat.md", pattern=r"^[^/\][^\]*$")
```

## Что сделать
1. Заменить сигнатуру `save_chat` на `req: SaveChatRequest`
2. Убрать `req.get(...)` — использовать `req.namespace`, `req.filename`, `req.content`
3. Убрать ручные проверки `if namespace not in (...)`, проверки `filename.startswith`, `is_absolute()`, `".." in Path(filename).parts`
4. Оставить только `is_relative_to()` проверку после `.resolve()` — это защита от симлинков
5. Добавить `SaveChatRequest` в импорт `from ai_assistant.features.rag.schemas import (...)`

## Тест
В `dev/tests/test_security.py` добавить:
```python
def test_save_chat_path_traversal_blocked_by_pydantic(client):
    payload = {"content": "test", "namespace": "personal", "filename": "../../../etc/passwd"}
    resp = client.post("/api/v1/rag/save-chat", json=payload, headers={"Authorization": "Bearer test-key"})
    assert resp.status_code == 422

def test_save_chat_invalid_namespace_blocked_by_pydantic(client):
    payload = {"content": "test", "namespace": "hacked", "filename": "test.md"}
    resp = client.post("/api/v1/rag/save-chat", json=payload, headers={"Authorization": "Bearer test-key"})
    assert resp.status_code == 422
```

## Правила
- Не добавляй сложность
- Любое изменение core требует обновления зависимых тестов
- Пиши diff-формат: `- старая строка` / `+ новая строка` с номерами строк
=== КОНЕЦ БЛОКА ===
```

---

## Промпт для Подфазы 2.4.2 — LLMConfig cleanup

```
=== НАЧАЛО БЛОКА: Фаза 2.4.2 ===

## Промпт
Ты — senior Python-разработчик. Работаешь с проектом AI Assistant.

## Задача
В `src/ai_assistant/core/config.py` класс `LLMConfig` содержит 15+ llama.cpp-специфичных полей. Нужно оставить только generic поля, а llama-специфичные убрать из класса — они будут читаться адаптерами через `config.model_extra.get(...)`.

## Generic поля (оставить)
provider, model, api_base, api_key, max_tokens, temperature, timeout, server_startup_delay, server_shutdown_timeout, server_context_size, stop_sequences, top_p, top_k, min_p, repeat_penalty, presence_penalty, frequency_penalty

## Llama-поля (убрать из класса)
n_gpu_layers, split_mode, main_gpu, tensor_split, n_batch, n_ubatch, cache_type_k, cache_type_v, num_threads, flash_attn, mmap, mlock, rope_scaling, yarn_ext_factor, yarn_attn_factor, draft_model, draft_n_predict

## Важно
- `model_config = SettingsConfigDict(env_prefix="AI_LLM_", extra="allow")` уже стоит — это значит что неизвестные поля из YAML пойдут в `model_extra` dict
- Не менять `extra="allow"` — это критично для обратной совместимости YAML

## Тест
В `dev/tests/test_contracts.py` добавить:
```python
def test_llm_config_no_llama_specific_fields():
    from ai_assistant.core.config import LLMConfig
    llama_fields = ["n_gpu_layers", "split_mode", "main_gpu", "tensor_split",
                    "n_batch", "n_ubatch", "cache_type_k", "cache_type_v",
                    "num_threads", "flash_attn", "mmap", "mlock",
                    "rope_scaling", "yarn_ext_factor", "yarn_attn_factor",
                    "draft_model", "draft_n_predict"]
    cfg = LLMConfig()
    for field in llama_fields:
        assert not hasattr(cfg, field), f"LLMConfig should not have field: {field}"
```

## Правила
- Выдавай diff-формат с номерами строк
- Проверь что `extra="allow"` остаётся
- Не забудь убрать `Literal` импорты если они стали неиспользуемыми
=== КОНЕЦ БЛОКА ===
```

---

## Промпт для Подфазы 2.4.3 — Адаптеры под extra

```
=== НАЧАЛО БЛОКА: Фаза 2.4.3 ===

## Промпт
Ты — senior Python-разработчик. Работаешь с проектом AI Assistant.

## Задача
В `src/ai_assistant/adapters/llm_openai_compatible.py` адаптер читает llama.cpp-специфичные поля напрямую из `config` (например `config.n_gpu_layers`). После Фазы 2.4.2 эти поля убраны из `LLMConfig` класса — они теперь в `config.model_extra` dict.

## Что найти и заменить
Все обращения вида `config.<llama_field>` заменить на `config.model_extra.get("<llama_field>", <default>)`:

- `config.n_gpu_layers` → `config.model_extra.get("n_gpu_layers", -1)`
- `config.n_batch` → `config.model_extra.get("n_batch", 512)`
- `config.n_ubatch` → `config.model_extra.get("n_ubatch", 64)`
- `config.mmap` → `config.model_extra.get("mmap", True)`
- `config.mlock` → `config.model_extra.get("mlock", False)`
- `config.num_threads` → `config.model_extra.get("num_threads", 0)`
- `config.flash_attn` → `config.model_extra.get("flash_attn", False)`
- и т.д.

## Как работать
1. Запроси код `llm_openai_compatible.py` через `🔍 REQUEST CODE`
2. Найди все обращения к llama-полям
3. Выдай diff с заменами

## Правила
- Не гадай — запрашивай код если нужно
- Каждое поле должно иметь разумный default
- Если поле не найдено в model_extra — использовать default, не падать
=== КОНЕЦ БЛОКА ===
```

---

## Промпт для Подфазы 2.4.4 — YAML cleanup

```
=== НАЧАЛО БЛОКА: Фаза 2.4.4 ===

## Промпт
Ты — senior Python-разработчик. Работаешь с проектом AI Assistant.

## Задача
Обновить `config.yaml` и `dev/tests/config.test.yaml` — убрать llama.cpp-специфичные поля из основной секции `llm`, оставить их как `extra` поля (они автоматически попадут в `model_extra` благодаря `extra="allow"`).

## config.yaml
Из секции `llm:` убрать поля: `n_gpu_layers`, `n_batch`, `n_ubatch`, `mmap`, `mlock`, `num_threads`, `flash_attn`. Оставить только generic поля + `server_context_size`.

## config.test.yaml
Из секции `llm:` убрать те же поля. Убедиться что `system_message` и `stop_sequences` остаются.

## Важно
- YAML структура — плоский список ключей под `llm:`
- Не нужно никаких специальных секций — просто убрать ключи из YAML
- `extra="allow"` в `LLMConfig` подхватит их если они есть, проигнорирует если нет

## Тест
Запустить `pytest dev/tests/test_contracts.py::test_llm_config_no_llama_specific_fields -v` — должен пройти.

## Правила
- Выдавай diff-формат для YAML
- Не меняй отступы без нужды
- Сохрани комментарии если есть
=== КОНЕЦ БЛОКА ===
```
















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
