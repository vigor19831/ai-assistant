```markdown
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
# 1. Подготовь LLM-сервер с OpenAI-compatible API
#    Варианты:
#    • llama-server:  llama-server.exe -m model.gguf --port 8080
#    • Ollama:        ollama serve  (порт 11434)
#    • vLLM:          python -m vllm.entrypoints.openai.api_server --model ...
#    • OpenAI:        https://api.openai.com/v1 (api_key нужен)

# 2. Пропиши endpoint в config.yaml:
#    llm:
#      provider: openai_compatible
#      api_base: http://127.0.0.1:8080/v1   # или 11434 для Ollama
#      model: gemma-3-4b-it                  # имя модели на сервере

# 3. Установи зависимости проекта
pip install -e .[dev]

# 4. Запусти сервер
python main.py
# или через uvicorn напрямую:
# uvicorn main:app --host 0.0.0.0 --port 8000

# 5. UI: браузерное расширение с OpenAI-compatible API → http://localhost:8000
```

## Рекомендуемые модели
- **LLM:** `gemma-3-4b-it`, `qwen2.5-7b-instruct`, `llama-3.2-3b-instruct` — быстрые, качественные, мультиязычные
- **Embedder:** `nomic-embed-text-v1.5`, `mxbai-embed-large-v1` — проверь размерность выходного вектора!

> 💡 Совет: убедись, что модель загружена в память/VRAM перед первым запросом, иначе первый ответ будет медленным.


-------------------------------------------------------------------------------
## Оффлайн токенайзеры
tiktoken используется для OpenAI-моделей (GPT-4/4o/3.5) — работает офлайн после pip install, интернет не нужен.
Для остальных моделей (Qwen, Llama, Gemma, Phi, Mistral, DeepSeek) скачайте токенизатор один раз:

```bash
# Автоопределение из config.yaml
python scripts/download_tokenizers.py --auto

# Или вручную по имени модели
python scripts/download_tokenizers.py --model gemma-3-4b-it
python scripts/download_tokenizers.py --model microsoft/Phi-4-mini-instruct
```
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
3. Ограничения: Python 3.13+, Sacred Core неизменяем, offline-first
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
- LLM не отвечает → проверь, что сервер запущен и `AI_LLM_API_BASE` / `config.yaml → llm.api_base` указывают на правильный порт
- 401 Unauthorized → в config.yaml пропиши `api_key: sk-...` (если сервер требует ключ; локальные серверы обычно игнорируют любую строку)
- FAISS не ставится → vector_store.provider: memory в config.yaml
- Индекс не грузится → проверь права на data/indices/ и index_path в конфиге
- Несовпадение dim → embedder.dim и vector_store.dim должны быть равны (смотри спецификацию модели эмбеддеров)
- Не хватает зависимостей → `pip install -e .[dev]` из корня проекта
-------------------------------------------------------------------------------
## ЛИЦЕНЗИЯ

Copyright (c) 2026 [МОЕ ИМЯ ИЛИ НИК]

Этот проект распространяется под лицензией **Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International** (CC BY-NC-SA 4.0).

### Разрешено (бесплатно)
- ✅ Изучать код, делиться ссылками
- ✅ Использовать в личных/некоммерческих проектах
- ✅ Форкать и модифицировать (при сохранении той же лицензии)

### Запрещено (без письменного разрешения)
- ❌ Коммерческое использование (включая SaaS, продажу, встраивание в платные продукты)
- ❌ Закрытие исходного кода производных работ

### Исключение для автора
Автор сохраняет право использовать этот код в коммерческих продуктах и услугах, включая развёртывание в модели SaaS, без каких-либо ограничений.

### Коммерческая лицензия
Для коммерческого использования свяжитесь со мной:
**Email:** [МОЯ ПОЧТА]

Полный текст лицензии: https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode
-------------------------------------------------------------------------------

# Frozen Invariants (не менять без обсуждения)

- `api/deps.py`: `_state` инициализируется ровно один раз через `asyncio.Event`
- `api/lifespan.py`: shutdown таргетит только PID, никогда process group
- `core/ports/`, `core/registry.py`, `core/pipeline.py`: immutable
- `features/*/`: новые фичи только через новые директории, существующие handlers не трогать
```
