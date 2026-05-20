# AI Assistant — Модульный фреймворк для локальных LLM
-------------------------------------------------------------------------------

## ПРАВИЛА (СВЯЩЕННОЕ ЯДРО — НЕ ТРОГАТЬ)
- core/ports/, core/pipeline.py, core/registry.py, api/router.py — НЕИЗМЕНЯЕМЫ
- Новый адаптер: adapters/<port>_<name>.py + @register("<port>", "<name>")
- Новая фича: features/<name>/{handlers,manager,schemas}.py
- Новый шаг pipeline: @step("name") в pipeline/steps.py
- Новый промпт: core/prompts/v2/name.j2 (v1/ не трогать)
-------------------------------------------------------------------------------

## Слои
- core/ 🔒 Ядро: порты, домен, pipeline, registry, prompts/v1/*.j2
- adapters/ 🔌 Plug-and-play: llm_*, embedder_*, vector_store_*, memory_sqlite.py, tools_*.py
- features/ 📦 Изолированные: chat/, rag/, image_analysis(заглушка), voice_chat(заглушка)

-------------------------------------------------------------------------------

## Вспомогательное:
- pipeline/ 🔄 steps.py: embed_query→retrieve→rerank→build_context→generate
- api/ 🌐 lifespan.py, deps.py, router.py
- tests/ 🧪 233 pytest-теста, check_mutations.py

-------------------------------------------------------------------------------

## КОНФИГ (config.yaml + pyproject.toml — единый источник правды)
- llm.provider: openai_compatible | mock
- embedder.dim ДОЛЖЕН совпадать с vector_store.dim (по умолчанию: 768)
- rag.steps: [embed_query,retrieve,rerank,build_context,generate]
- rag.namespaces: personal/work/other → префиксы [p]/[w]/[o] в чате

-------------------------------------------------------------------------------

## БЫСТРЫЙ СТАРТ

```bash
# 1. Установи Ollama: https://ollama.com/download
#    и убедись, что сервер запущен:
ollama serve

# 2. Скачай нужные модели
ollama pull gemma3:4b
ollama pull nomic-embed-text

# 3. Установи зависимости проекта
pip install -e .[dev]

# 4. Запусти сервер
python main.py
# или через uvicorn напрямую:
# uvicorn main:app --host 0.0.0.0 --port 8000

# 5. UI: браузерное расширение с OpenAI-compatible API → http://localhost:8000
```

## Рекомендуемые модели для Ollama
- **LLM:** `gemma3:4b`, `qwen2.5:7b`, `llama3.2:3b` — быстрые, качественные, мультиязычные
- **Embedder:** `nomic-embed-text`, `mxbai-embed-large` — проверь размерность выходного вектора!

> 💡 Совет: запускай `ollama ps`, чтобы увидеть загруженные модели и их размер в VRAM.

-------------------------------------------------------------------------------

## RAG
- Индексация: `python scripts/index_documents.py --folder <personal|work|other>`
- Префикс в чате: `[p] запрос` — ищет только в personal namespace
- API переиндексации: POST /rag/reindex {folder, clear}

-------------------------------------------------------------------------------

## ВОРОТА КАЧЕСТВА (ОБЯЗАТЕЛЬНЫ ДЛЯ ЛЮБЫХ ИЗМЕНЕНИЙ)
```bash
pytest tests -v                           # 233 теста + hypothesis fuzz
python scripts/check_mutations.py --quick # mutmut, score >= 80% (core/)
python scripts/check_mutations.py         # mutmut, score >= 80% (полный)
python scripts/check_ruff.py --check      # lint чисто
python scripts/check_mypy.py              # типы чисто
```

-------------------------------------------------------------------------------

## ЧЕК-ЛИСТ ИНТЕГРАЦИИ AI (когда просишь помощи)
1. Прикрепи: context_build.md (из `python scripts/context_build.py --compact`)
2. Формат задачи: "Исправить/Добавить [X] в [файл/путь]"
3. Ограничения: Python 3.11+, Sacred Core неизменяем, offline-first
4. Прикрепи примеры: существующий адаптер/фича для справки
5. Требуй: pytest + mutation + ruff/mypy чисто в ответе
6. Проверь перед мержем: все ворота выше пройдены
-------------------------------------------------------------------------------

## ФОРМАТ ОТВЕТА ДЛЯ AI (строго)
- Отвечай ТОЛЬКО: code diff / путь к файлу / точная команда
- БЕЗ объяснений, БЕЗ markdown-ограждений, кроме показа кода
- Если не уверен: запроси конкретный файл/строку, не гадай
- Всегда уважай границы Sacred Core
-------------------------------------------------------------------------------

## ТРАБЛШУТИНГ
- Ollama не отвечает → проверь `ollama serve` и `OLLAMA_HOST=127.0.0.1:11434`
- 401 от Ollama → в config.yaml пропиши `api_key: ollama` (любая строка, Ollama игнорирует)
- FAISS не ставится → vector_store.provider: memory в config.yaml
- Индекс не грузится → проверь права на data/indices/ и index_path в конфиге
- Несовпадение dim → embedder.dim и vector_store.dim должны быть равны (см. `ollama show <model>`)
- Не хватает зависимостей → `pip install -e .[dev]` из корня проекта
-------------------------------------------------------------------------------

> 📝 **Примечание про llama.cpp:** поддержка нативного llama.cpp планируется, но требует значительного объёма кода и времени на стабилизацию. Будет допилена в свободное время; текущий фокус — стабильная работа через Ollama.

-------------------------------------------------------------------------------

## ЛИЦЕНЗИЯ: MIT
-------------------------------------------------------------------------------

# Frozen Invariants (не менять без обсуждения)

- `api/deps.py`: `_state` инициализируется ровно один раз через `asyncio.Event`
- `api/lifespan.py`: shutdown таргетит только PID, никогда process group
- `core/ports/`, `core/registry.py`, `core/pipeline.py`: immutable
- `features/*/`: новые фичи только через новые директории, существующие handlers не трогать
