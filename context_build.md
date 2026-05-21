# Project Context
**Generated:** 2026-05-21T12:45:47.891979
**Project:** ai
**Files:** 81
---
# AI Assistant — A modular, cross-platform framework for local LLMs — 10+ years of evolution

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
#      model: gemma-3-4b-it-Q4_K_M          # имя модели на сервере

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

## ЛИЦЕНЗИЯ: MIT
-------------------------------------------------------------------------------

# Frozen Invariants (не менять без обсуждения)

- `api/deps.py`: `_state` инициализируется ровно один раз через `asyncio.Event`
- `api/lifespan.py`: shutdown таргетит только PID, никогда process group
- `core/ports/`, `core/registry.py`, `core/pipeline.py`: immutable
- `features/*/`: новые фичи только через новые директории, существующие handlers не трогать

---

## [PKG] Runtime & Excluded Info
- **Environment:** `.venv/` — dependencies, excluded from context
- **Data:** `data/`, `documents/`, `logs/` — runtime files, excluded
- **Indices:** `data/indices/`, `*.faiss`, `*.db` — binaries/databases, excluded
- **Test cache:** `.hypothesis/` — property-based testing artifacts, excluded
- **Tasks:** `TODO.txt` — dev planner/checklist, excluded (external context)
## Architecture Summary
- **Core:** Sacred/Immutable
- **Adapters:** Plug-and-play
- **Features:** Isolated
## Runtime Context

- **Python:** 3.13+
- **Entry points:** `launcher.py`, `main.py`
- **Configuration:** `config.yaml`, `pyproject.toml`

---
## Directory Structure
```
├── LICENSE
├── README.md
├── adapters
│   ├── __init__.py
│   ├── chunker_simple.py
│   ├── embedder_mock.py
│   ├── embedder_openai_compatible.py
│   ├── llm_mock.py
│   ├── llm_openai_compatible.py
│   ├── memory_sqlite.py
│   ├── reranker_api.py
│   ├── reranker_dummy.py
│   ├── storage_sqlite.py
│   ├── tools_calculator.py
│   ├── transport_fastapi.py
│   ├── vector_store_faiss.py
│   ├── vector_store_memory.py
│   ├── vision_clip_local.py
│   ├── voice_piper.py
│   ├── voice_whisper_local.py
│   └── voice_whispercpp.py
├── api
│   ├── __init__.py
│   ├── admin.py
│   ├── deps.py
│   ├── lifespan.py
│   ├── router.py
│   └── security.py
├── config.yaml
├── core
│   ├── __init__.py
│   ├── config.py
│   ├── domain
│   │   ├── __init__.py
│   │   ├── documents.py
│   │   ├── errors.py
│   │   ├── messages.py
│   │   └── pipeline.py
│   ├── io_utils.py
│   ├── logger.py
│   ├── metrics.py
│   ├── pipeline.py
│   ├── ports
│   │   ├── __init__.py
│   │   ├── chunker.py
│   │   ├── embedder.py
│   │   ├── events.py
│   │   ├── llm.py
│   │   ├── memory.py
│   │   ├── modality.py
│   │   ├── reranker.py
│   │   ├── storage.py
│   │   ├── tools.py
│   │   ├── transport.py
│   │   ├── vector_store.py
│   │   ├── vision.py
│   │   └── voice.py
│   ├── prompts
│   │   ├── __init__.py
│   │   └── v1
│   │       ├── rag_creative.j2
│   │       ├── rag_default.j2
│   │       ├── rag_strict.j2
│   │       ├── summarize.j2
│   │       └── voice_transcribe.j2
│   ├── registry.py
│   ├── retry.py
│   ├── tool_registry.py
│   └── utils.py
├── features
│   ├── __init__.py
│   ├── chat
│   │   ├── __init__.py
│   │   ├── handlers.py
│   │   ├── manager.py
│   │   └── schemas.py
│   ├── image_analysis
│   │   ├── __init__.py
│   │   ├── handlers.py
│   │   ├── manager.py
│   │   └── schemas.py
│   └── rag
│       ├── __init__.py
│       ├── handlers.py
│       ├── manager.py
│       └── schemas.py
├── launcher.py
├── main.py
├── pipeline
│   ├── __init__.py
│   ├── decorators.py
│   └── steps.py
└── pyproject.toml
```
---
## File Index

1. `LICENSE` — 553 B, 14 lines · 2026-05-21 08:38
2. `README.md` — 9.0 KB, 155 lines · 2026-05-21 11:43 [CRIT]
3. `adapters/__init__.py` — 869 B, 43 lines · 2026-05-20 13:45
4. `adapters/chunker_simple.py` — 1.6 KB, 57 lines · 2026-05-14 16:58 [CRIT]
5. `adapters/embedder_mock.py` — 687 B, 26 lines · 2026-05-16 21:41 [CRIT]
6. `adapters/embedder_openai_compatible.py` — 1.7 KB, 51 lines · 2026-05-16 21:41 [CRIT]
7. `adapters/llm_mock.py` — 982 B, 30 lines · 2026-05-19 00:19 [CRIT]
8. `adapters/llm_openai_compatible.py` — 4.9 KB, 123 lines · 2026-05-19 07:53 [CRIT]
9. `adapters/memory_sqlite.py` — 7.1 KB, 178 lines · 2026-05-19 07:53 [CRIT]
10. `adapters/reranker_api.py` — 2.7 KB, 79 lines · 2026-05-16 21:41 [CRIT]
11. `adapters/reranker_dummy.py` — 950 B, 29 lines · 2026-05-16 21:41 [CRIT]
12. `adapters/storage_sqlite.py` — 3.4 KB, 105 lines · 2026-05-19 00:20 [CRIT]
13. `adapters/tools_calculator.py` — 2.6 KB, 83 lines · 2026-05-19 07:53 [CRIT]
14. `adapters/transport_fastapi.py` — 715 B, 30 lines · 2026-05-14 16:58 [CRIT]
15. `adapters/vector_store_faiss.py` — 12.7 KB, 329 lines · 2026-05-19 00:21 [CRIT]
16. `adapters/vector_store_memory.py` — 6.8 KB, 185 lines · 2026-05-19 00:22 [CRIT]
17. `adapters/vision_clip_local.py` — 698 B, 23 lines · 2026-05-19 00:22 [CRIT]
18. `adapters/voice_piper.py` — 3.1 KB, 93 lines · 2026-05-18 08:03 [CRIT]
19. `adapters/voice_whisper_local.py` — 726 B, 23 lines · 2026-05-19 00:23 [CRIT]
20. `adapters/voice_whispercpp.py` — 1.8 KB, 53 lines · 2026-05-18 08:03 [CRIT]
21. `api/__init__.py` — 44 B, 1 lines · 2026-05-10 22:01
22. `api/admin.py` — 767 B, 29 lines · 2026-05-20 13:49 [CRIT]
23. `api/deps.py` — 7.6 KB, 224 lines · 2026-05-20 14:54
24. `api/lifespan.py` — 2.1 KB, 63 lines · 2026-05-20 13:47
25. `api/router.py` — 1.5 KB, 48 lines · 2026-05-19 13:09
26. `api/security.py` — 2.9 KB, 87 lines · 2026-05-19 00:13
27. `config.yaml` — 3.8 KB, 137 lines · 2026-05-21 12:43
28. `core/__init__.py` — 290 B, 15 lines · 2026-05-14 16:58
29. `core/config.py` — 6.7 KB, 203 lines · 2026-05-21 09:51
30. `core/domain/__init__.py` — 600 B, 27 lines · 2026-05-16 21:41
31. `core/domain/documents.py` — 715 B, 32 lines · 2026-05-18 10:24
32. `core/domain/errors.py` — 277 B, 19 lines · 2026-05-13 08:35
33. `core/domain/messages.py` — 1.3 KB, 53 lines · 2026-05-16 21:41
34. `core/domain/pipeline.py` — 514 B, 19 lines · 2026-05-14 16:58
35. `core/io_utils.py` — 857 B, 29 lines · 2026-05-19 00:24
36. `core/logger.py` — 1.1 KB, 41 lines · 2026-05-16 21:41
37. `core/metrics.py` — 3.0 KB, 101 lines · 2026-05-19 00:24
38. `core/pipeline.py` — 597 B, 22 lines · 2026-05-16 21:41
39. `core/ports/__init__.py` — 701 B, 28 lines · 2026-05-16 21:41
40. `core/ports/chunker.py` — 441 B, 20 lines · 2026-05-16 21:41
41. `core/ports/embedder.py` — 507 B, 24 lines · 2026-05-16 21:41
42. `core/ports/events.py` — 95 B, 3 lines · 2026-05-14 23:08
43. `core/ports/llm.py` — 694 B, 28 lines · 2026-05-16 21:41
44. `core/ports/memory.py` — 1.8 KB, 58 lines · 2026-05-16 21:41
45. `core/ports/modality.py` — 112 B, 3 lines · 2026-05-14 23:08
46. `core/ports/reranker.py` — 1.1 KB, 44 lines · 2026-05-16 21:41
47. `core/ports/storage.py` — 824 B, 36 lines · 2026-05-16 21:41
48. `core/ports/tools.py` — 2.3 KB, 93 lines · 2026-05-16 07:52
49. `core/ports/transport.py` — 375 B, 19 lines · 2026-05-16 21:41
50. `core/ports/vector_store.py` — 1.6 KB, 54 lines · 2026-05-16 21:41
51. `core/ports/vision.py` — 360 B, 16 lines · 2026-05-16 21:41
52. `core/ports/voice.py` — 611 B, 28 lines · 2026-05-16 21:41
53. `core/prompts/__init__.py` — 775 B, 27 lines · 2026-05-14 16:58
54. `core/prompts/v1/rag_creative.j2` — 284 B, 10 lines · 2026-05-10 22:01
55. `core/prompts/v1/rag_default.j2` — 323 B, 10 lines · 2026-05-10 22:01
56. `core/prompts/v1/rag_strict.j2` — 534 B, 17 lines · 2026-05-13 22:44
57. `core/prompts/v1/summarize.j2` — 85 B, 5 lines · 2026-05-10 22:01
58. `core/prompts/v1/voice_transcribe.j2` — 125 B, 5 lines · 2026-05-10 22:01
59. `core/registry.py` — 1.4 KB, 52 lines · 2026-05-17 10:37
60. `core/retry.py` — 2.2 KB, 72 lines · 2026-05-16 21:41
61. `core/tool_registry.py` — 1.5 KB, 48 lines · 2026-05-16 21:38
62. `core/utils.py` — 3.2 KB, 109 lines · 2026-05-21 11:26
63. `features/__init__.py` — 53 B, 1 lines · 2026-05-10 22:01
64. `features/chat/__init__.py` — 46 B, 1 lines · 2026-05-10 22:01
65. `features/chat/handlers.py` — 5.2 KB, 171 lines · 2026-05-20 22:10 [CRIT]
66. `features/chat/manager.py` — 13.0 KB, 369 lines · 2026-05-19 00:25
67. `features/chat/schemas.py` — 2.3 KB, 98 lines · 2026-05-21 00:13
68. `features/image_analysis/__init__.py` — 30 B, 1 lines · 2026-05-10 22:01
69. `features/image_analysis/handlers.py` — 1.3 KB, 41 lines · 2026-05-18 08:05 [CRIT]
70. `features/image_analysis/manager.py` — 1.6 KB, 53 lines · 2026-05-19 00:25
71. `features/image_analysis/schemas.py` — 496 B, 20 lines · 2026-05-15 15:08
72. `features/rag/__init__.py` — 59 B, 1 lines · 2026-05-10 22:01
73. `features/rag/handlers.py` — 9.3 KB, 292 lines · 2026-05-19 10:41 [CRIT]
74. `features/rag/manager.py` — 6.0 KB, 200 lines · 2026-05-16 21:41
75. `features/rag/schemas.py` — 1.8 KB, 76 lines · 2026-05-16 21:41
76. `launcher.py` — 8.7 KB, 319 lines · 2026-05-21 12:23
77. `main.py` — 2.5 KB, 87 lines · 2026-05-21 00:13 [CRIT]
78. `pipeline/__init__.py` — 231 B, 6 lines · 2026-05-14 16:58
79. `pipeline/decorators.py` — 990 B, 44 lines · 2026-05-16 21:41
80. `pipeline/steps.py` — 8.1 KB, 237 lines · 2026-05-18 23:46 [CRIT]
81. `pyproject.toml` — 2.2 KB, 97 lines · 2026-05-21 09:50

**Total:** 183.8 KB

---
## File Contents

### `./`

#### `LICENSE`

```text
Copyright (c) 2026 [МОЕ ИМЯ]

Licensed under the Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.

You may obtain a copy of the License at:
    https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode

COMMERCIAL USE IS PROHIBITED WITHOUT A SEPARATE WRITTEN AGREEMENT.
For commercial licensing inquiries, contact: [МОЯ ПОЧТА]

Commercial licensing exception: The author retains the right
to use this code in commercial products and services, including
SaaS deployments, without restriction.
```

#### `README.md`

```md
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
```

#### `config.yaml`

```yaml
# ═══════════════════════════════════════════════════════════════
# AI Assistant — Универсальная конфигурация
# Работает с любым OpenAI-compatible API: llama-server, Ollama, vLLM, OpenAI
# Переменные окружения с префиксом AI_* переопределяют значения ниже
# ═══════════════════════════════════════════════════════════════

# ── Приложение ──
app_name: ai-assistant
debug: false
host: 0.0.0.0
port: 8000
config_version: "2.0.0"

# ── CORS ──
cors:
  allow_origins:
    - "http://localhost"
    - "http://127.0.0.1"
    - "null"
  allow_credentials: true
  allow_methods: ["*"]
  allow_headers: ["*"]

# ── Chat ──
chat:
  history_limit: 10
  max_context_tokens: 4096
  tokenizer_model: "gpt-4o"
  tokenizer_local_dir: "./data/tokenizers"

# ── Chunker ──
chunker:
  provider: simple
  chunk_size: 512
  chunk_overlap: 50

# ── Embedder ──
embedder:
  provider: openai_compatible
  api_base: http://127.0.0.1:8080/v1
  api_key: null
  model: embeddinggemma-300m-q8_0
  dim: 768
  timeout: 60.0
  # === GPU/CPU offload ===
  n_gpu_layers: 0        # -1 = все слои на GPU, 0 = только CPU, 10 = 10 слоёв на GPU
  n_batch: 512            # размер батча для обработки
  n_ubatch: 64            # микро-батч
  mmap: true              # memory-mapped файлы (экономия RAM)
  mlock: false            # блокировка страниц в RAM (не выгружать в swap)

# ── LLM ──
llm:
  provider: openai_compatible
  api_base: http://127.0.0.1:8080/v1
  api_key: null
  model: gemma-4-e2b-it
  available_models:
    - gemma-4-e2b-it
    - phi-4-mini-reasoning
    - qwen3.5-4b
  max_tokens: 4096
  temperature: 0.7
  top_p: 0.95
  top_k: 40
  min_p: 0.05
  repeat_penalty: 1.1
  presence_penalty: 0.0
  frequency_penalty: 0.0
  stop_sequences: []
  timeout: 300.0
  # === GPU/CPU offload ===
  n_gpu_layers: 99        # -1 = все на GPU, 0 = CPU only, N = N слоёв на GPU
  n_batch: 512
  n_ubatch: 64
  mmap: true
  mlock: false
  # === Sampling (уже есть выше) ===
  # === Context ===
  server_context_size: 4096
  # === Performance ===
  num_threads: 0          # 0 = авто (все ядра), N = N потоков
  flash_attn: false       # Flash Attention (ускорение, требует поддержки)

# ── Vector Store ──
vector_store:
  provider: memory
  index_path: ./data/indices
  metric: l2
  dim: 768                # ← ОБЯЗАТЕЛЬНО равно embedder.dim
  relevance_threshold: 0.3

# ── Storage ──
storage:
  provider: sqlite
  db_path: ./data/storage.db

# ── Voice ──
voice:
  enabled: false
  recognizer_provider: whisper_local
  synthesizer_provider: piper

# ── Vision ──
vision:
  enabled: false
  provider: clip_local

# ── Reranker ──
reranker:
  provider: dummy
  model: rerank-multilingual-v3.0
  api_base: https://api.cohere.com
  api_key: null
  timeout: 30.0
  threshold: 0.3

# ── RAG ──
rag:
  steps:
    - embed_query
    - retrieve
    - rerank
    - build_context
    - generate
  prompt_version: v1
  prompt_name: rag_strict
  top_k: 5
  default_namespace: "default"
  relevance_threshold: 0.3

# ── Безопасность ──
security:
  api_key: null
  rate_limit: "100/minute"
  max_body_size: 10485760
  allowed_hosts: ["localhost", "127.0.0.1"]
```

#### `launcher.py`

```py
#!/usr/bin/env python3
"""Launcher — two columns, green active marker, timestamps."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# --- config ---------------------------------------------------------------

SCRIPT_ORDER = [
    "start",
    "stop",
    "clean_cache",
    "context_build",
    "index_documents",
    "terminal",
]
BACKGROUND = {"start"}
TEST_FLAGS = {
    "clean_cache": ["--clean"],
    "context_build": ["--full"],
    "download_tokenizers": ["--auto"],
}

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"

TERMINAL_CMD = {
    "nt": 'start cmd /k "{venv}\\Scripts\\activate.bat && cd /d {root}"',
    "posix": (
        'gnome-terminal -- bash -c "source {venv}/bin/activate'
        ' && cd {root} && exec bash"'
    ),
}

# --- helpers --------------------------------------------------------------

def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")

def enable_ansi() -> None:
    """Включить ANSI-цвета в Windows-консоли."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        h_out = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
            mode.value |= 0x0004
            kernel32.SetConsoleMode(h_out, mode)
    except Exception:
        pass

def pad_ansi(text: str, width: int) -> str:
    plain = re.sub(r"\033\[[0-9;]*m", "", text)
    pad = width - len(plain)
    return text + " " * pad if pad > 0 else text

def get_python(root: Path) -> str:
    venv = root / ".venv"
    name = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    exe = venv / name
    return str(exe) if exe.exists() else sys.executable

def collect(root: Path, subdir: str) -> list[Path]:
    d = root / subdir
    if not d.is_dir():
        return []
    return sorted(p for p in d.rglob("*.py") if p.is_file() and p.name != "__init__.py")

def sort_scripts(files: list[Path]) -> list[Path]:
    order = {name: i for i, name in enumerate(SCRIPT_ORDER)}

    def key(p: Path) -> tuple[int, str]:
        return (order.get(p.stem, 999), p.stem)

    return sorted(files, key=key)

def flag_hint(target: str) -> str:
    flags = TEST_FLAGS.get(Path(target).stem)
    return " ".join(flags) if flags else ""

def ask_flags(target: str) -> list[str]:
    flags = TEST_FLAGS.get(Path(target).stem)
    if not flags:
        return []
    try:
        ans = input(f"Add flags {' '.join(flags)}? [y/n]: ").strip().lower()
    except EOFError:
        return []
    return flags if ans in ("y", "yes") else []

def print_menu(scripts, tests, last):
    w = 38
    rows = max(len(scripts), len(tests))
    total = w * 2 + 4

    print("\n" + "=" * total)
    print(f"{'SCRIPTS':^{w}}    {'TESTS':^{w}}")
    print("-" * total)

    for i in range(rows):
        left = ""
        if i < len(scripts):
            n, label, target = scripts[i]
            star = f"{GREEN}*{RESET}" if n == last else " "
            bg = " [bg]" if Path(target).stem in BACKGROUND else ""
            left = f" [{n:2d}]{star} {label}{bg}"

        right = ""
        if i < len(tests):
            n, label, target = tests[i]
            star = f"{GREEN}*{RESET}" if n == last else " "
            hint = flag_hint(target)
            right = f" [{n:2d}]{star} {label}"
            if hint:
                right += f"  ({hint})"

        print(f"{pad_ansi(left, w)}    {right}")

    print("-" * total)
    print(" [r]  Rerun last")
    print(" [0]  Exit")
    print("=" * total)

def run(python, target, root, extra):
    ts = timestamp()
    if target.startswith("pytest:"):
        cmd = [python, "-m", "pytest", target.split(":", 1)[1], "-v"] + extra
        print(f"\n>>> [{ts}] pytest tests")
    else:
        cmd = [python, target] + extra
        print(f"\n>>> [{ts}] {Path(target).relative_to(root)}")
        if extra:
            print(f">>> [{ts}] (extra: {' '.join(extra)})")

    print(f">>> [{ts}] {' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=root)

    # Color-coded exit status
    if res.returncode == 0:
        status = f"{GREEN}OK{RESET}"
    else:
        status = f"{RED}FAILED (exit {res.returncode}){RESET}"

    print(f"\n>>> [{timestamp()}] {status}")

    try:
        input(">>> Press Enter to return to menu... ")
    except EOFError:
        print(">>> (non-interactive, pausing 15s)")
        time.sleep(15)

    return res.returncode

def run_bg(python, target, root, extra):
    target_path = Path(target)
    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)

    log_file = data_dir / f"{target_path.stem}.log"
    pid_file = data_dir / f"{target_path.stem}.pid"

    with open(log_file, "a", encoding="utf-8") as log_fp:
        kwargs = {
            "cwd": root,
            "stdout": log_fp,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

        proc = subprocess.Popen([python, target_path] + extra, **kwargs)

    pid_file.write_text(str(proc.pid), encoding="utf-8")

    ts = timestamp()
    print(f"\n>>> [{ts}] {GREEN}{target_path.name} running in background{RESET}")
    print(f">>> [{ts}] PID: {proc.pid}")
    print(f">>> [{ts}] Log: {log_file.relative_to(root)}")
    return 0

def run_terminal(root: Path) -> int:
    """Open system terminal with activated venv."""
    venv = root / ".venv"
    if not venv.exists():
        print(f">>> {RED}No .venv found. Run setup first.{RESET}")
        return 1
    cmd_template = TERMINAL_CMD.get(os.name, TERMINAL_CMD["posix"])
    cmd = cmd_template.format(venv=str(venv), root=str(root))
    ts = timestamp()
    print(f"\n>>> [{ts}] Opening terminal with .venv")
    print(f">>> [{ts}] {cmd}")
    subprocess.Popen(cmd, shell=True)
    return 0

def find_target(num, scripts, tests):
    for n, label, target in scripts + tests:
        if n == num:
            return label, target
    return None, None

def main() -> int:
    enable_ansi()

    root = Path(__file__).parent.resolve()
    py = get_python(root)

    script_files = sort_scripts(collect(root, "scripts"))
    test_files = collect(root, "tests")

    scripts = []
    tests = []
    n = 1

    for f in script_files:
        scripts.append((n, f.name, str(f)))
        n += 1

    # Terminal launcher
    scripts.append((n, "TERMINAL (.venv)", "__terminal__"))
    n += 1

    if test_files:
        tests.append((n, "RUN ALL TESTS", f"pytest:{root / 'tests'}"))
        n += 1
        for f in test_files:
            tests.append((n, f.name, str(f)))
            n += 1

    if not scripts and not tests:
        print("Nothing to run.")
        return 1

    last_num = None
    last_target = None
    last_extra = []

    while True:
        print_menu(scripts, tests, last_num)

        try:
            choice = input("\nEnter number: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return 0

        if not choice or choice in ("0", "exit", "quit"):
            print("Bye.")
            return 0

        if choice.lower() == "r":
            if last_target:
                if Path(last_target).stem in BACKGROUND and not last_target.startswith(
                    "pytest:"
                ):
                    run_bg(py, last_target, root, last_extra)
                else:
                    run(py, last_target, root, last_extra)
            else:
                print("No previous run.")
            continue

        parts = choice.split(maxsplit=1)
        try:
            num = int(parts[0])
        except ValueError:
            print("Invalid input.")
            continue

        extra = parts[1].split() if len(parts) > 1 else []
        label, target = find_target(num, scripts, tests)
        if target is None:
            print("Number not found.")
            continue

        if not target.startswith("pytest:") and not extra:
            extra = ask_flags(target)

        if target == "__terminal__":
            run_terminal(root)
            continue

        last_num, last_target, last_extra = num, target, extra

        if Path(target).stem in BACKGROUND and not target.startswith("pytest:"):
            run_bg(py, target, root, extra)
        else:
            run(py, target, root, extra)

if __name__ == "__main__":
    sys.exit(main())
```

#### `main.py`

```py
"""Entry point — Uvicorn + FastAPI + Static UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.deps import AppState, MetricsMiddleware, get_state
from api.lifespan import lifespan
from api.router import assemble_routers
from api.security import LimitMiddleware, _load_security_cfg
from core.config import load_config

_config = load_config()

app = FastAPI(
    title="AI Assistant",
    description="Modular AI Framework with Sacred Core",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(MetricsMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

sec_cfg = _load_security_cfg()

app.add_middleware(LimitMiddleware)
if sec_cfg.get("allowed_hosts") and not _config.debug:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=sec_cfg["allowed_hosts"])

@app.get("/")
async def root() -> dict[str, str]:
    return {"status": "ok", "service": "ai-assistant"}

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "ai-assistant"}

async def _safe_get_state(request: Request) -> AppState | None:
    app = request.app
    override: Any = app.dependency_overrides.get(get_state)
    try:
        if override is not None:
            return override()
        return get_state(request)
    except RuntimeError:
        return None

@app.get("/info")
async def get_info(state: AppState | None = Depends(_safe_get_state)) -> dict[str, str]:
    if state is None:
        return {"provider": "unknown", "model": "unknown"}
    provider = state.config.llm.provider
    if provider == "mock":
        model = "mock"
    elif provider == "openai_compatible":
        model = getattr(state.config.llm, "model", None) or "unknown"
    else:
        model = provider
    return {"provider": provider, "model": model}

for router in assemble_routers():
    app.include_router(router)

static_dir = Path(_config.ui.static_path)
if not static_dir.is_absolute():
    static_dir = Path(__file__).parent / static_dir
if static_dir.exists():
    app.mount("/ui", StaticFiles(directory=str(static_dir), html=True), name="static")
```

#### `pyproject.toml`

```toml
[build-system]
requires = ["setuptools>=61.0", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "ai-assistant"
version = "1.0.0"
description = "Модульный AI-фреймворк с неизменяемым ядром"
requires-python = ">=3.13"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.2.0",
    "pyyaml>=6.0.1",
    "numpy>=1.26.0",
    "httpx>=0.27.0",
    "aiofiles>=23.2.1",
    "tiktoken>=0.7.0",
    "tokenizers>=0.19.0",
    "jinja2>=3.1.3",
    "sqlmodel>=0.0.18",
    "sqlalchemy[asyncio]>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "respx>=0.21.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
    "types-PyYAML>=6.0.12",
    "types-aiofiles>=23.2.0",
    "pre-commit>=3.7.0",
    "pytest-timeout>=2.3.0",
    "mutmut>=2.4.0",
    "hypothesis>=6.100.0",
    "vulture>=2.11",
]
faiss = [
    "faiss-cpu>=1.8.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["core*", "adapters*", "features*", "pipeline*", "api*"]

[tool.ruff]
line-length = 88
target-version = "py313"
extend-exclude = ["scripts/"]

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "ASYNC"]
ignore = []

[tool.mypy]
python_version = "3.13"
strict = true
ignore_missing_imports = true
exclude = ["tests/", "scripts/"]

# ── FastAPI DI false positives ──
warn_return_any = false

# ── Registry / dynamic code ──
disallow_untyped_calls = false
disallow_untyped_defs = false

# ── False positives для Any ──
warn_no_return = false

# ── Игнорировать известные проблемные модули ──
[[tool.mypy.overrides]]
module = [
    "api.deps",
    "api.security",
    "pipeline.steps",
    "features.chat.manager",
    "features.image_analysis.manager",
    "adapters.*",
]
warn_return_any = false
disallow_untyped_defs = false
disallow_untyped_calls = false

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
timeout = 240
addopts = "-m 'not online'"

[tool.mutmut]
paths_to_mutate = ["core/", "adapters/", "features/", "api/", "pipeline/"]
pytest_add_cli_args_test_selection = ["tests/"]
backup = false
```

### `adapters/`

#### `adapters/__init__.py`

```py
__all__ = [
    "chunker_simple",
    "embedder_mock",
    "embedder_openai_compatible",
    "llm_mock",
    "llm_openai_compatible",
    "memory_sqlite",
    "reranker_api",
    "reranker_dummy",
    "storage_sqlite",
    "tools_calculator",
    "transport_fastapi",
    "vector_store_faiss",
    "vector_store_memory",
    "vision_clip_local",
    "voice_piper",
    "voice_whisper_local",
    "voice_whispercpp",
]

from . import (
    chunker_simple,
    embedder_mock,
    embedder_openai_compatible,
    llm_mock,
    llm_openai_compatible,
    memory_sqlite,
    reranker_api,
    reranker_dummy,
    storage_sqlite,
    tools_calculator,
    transport_fastapi,
    vector_store_memory,
    vision_clip_local,
    voice_piper,
    voice_whisper_local,
    voice_whispercpp,
)

try:
    from . import vector_store_faiss  # noqa: F401
except ImportError:
    pass
```

#### `adapters/chunker_simple.py`

```py
"""Simple fixed-size chunker."""

from __future__ import annotations

import uuid
from typing import Any

from core.domain.documents import Chunk, ChunkMetadata, Document
from core.ports.chunker import IChunker
from core.registry import register

@register("chunker", "simple")
class SimpleChunker(IChunker):
    """Split text into fixed-size chunks with overlap."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.chunk_size: int = config.chunk_size
        self.chunk_overlap: int = config.chunk_overlap

    async def chunk(self, document: Document) -> list[Chunk]:
        text = document.content
        if not text:
            return []

        size = self.chunk_size
        overlap = self.chunk_overlap
        step = max(1, size - overlap)

        chunks: list[Chunk] = []
        total = max(1, (len(text) + step - 1) // step)
        idx = 0
        for i in range(0, len(text), step):
            chunk_text = text[i : i + size]
            if not chunk_text.strip():
                continue
            meta = ChunkMetadata(
                source=document.id,
                index=idx,
                total_chunks=total,
                custom=document.metadata,
            )
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    text=chunk_text,
                    metadata=meta,
                )
            )
            idx += 1

        # Update total_chunks accurately
        for c in chunks:
            if c.metadata:
                object.__setattr__(c.metadata, "total_chunks", len(chunks))
        return chunks
```

#### `adapters/embedder_mock.py`

```py
"""Mock embedder — deterministic fake vectors, no network."""

from __future__ import annotations

import random
from typing import Any

from core.ports.embedder import IEmbedder
from core.registry import register

@register("embedder", "mock")
class MockEmbedder(IEmbedder):
    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self._dim: int = config.dim

    @property
    def dimension(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [
            [random.Random(t + str(i)).random() for i in range(self._dim)]
            for t in texts
        ]
```

#### `adapters/embedder_openai_compatible.py`

```py
"""OpenAI-compatible embedder (works with any OpenAI-compatible API)."""

from __future__ import annotations

from typing import Any

import httpx

from core.ports.embedder import IEmbedder
from core.registry import register
from core.retry import with_retry
from core.utils import resolve_api_key

@register("embedder", "openai_compatible")
class OpenAICompatibleEmbedder(IEmbedder):
    """Embedder using OpenAI-compatible REST API."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.model: str = getattr(config, "model", "text-embedding-3-small")
        self.api_base: str = getattr(config, "api_base", "https://api.openai.com/v1")
        self.api_key: str = resolve_api_key(
            getattr(config, "api_key", None), "OPENAI_API_KEY"
        )
        self._dim: int = getattr(config, "dim", 1536)
        self._timeout: float = config.timeout

    @property
    def dimension(self) -> int:
        return self._dim

    @with_retry(max_retries=3, delay=1.0)
    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        url = f"{self.api_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "input": texts,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        embeddings = [item["embedding"] for item in data["data"]]
        return embeddings
```

#### `adapters/llm_mock.py`

```py
"""Mock LLM — works without API keys or local models."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from core.domain.messages import AssistantMessage, UserMessage
from core.ports.llm import ILLM
from core.registry import register

@register("llm", "mock")
class MockLLM(ILLM):
    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def complete(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AssistantMessage:
        last = messages[-1].text if messages else "..."
        return AssistantMessage(text=f"[MOCK LLM] Echo: {last}")

    async def stream(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AsyncIterator[str]:
        yield (
            "[MOCK] Server is running. Switch config.yaml to 'llamacpp' "
            "or 'openai_compatible' for real responses."
        )
```

#### `adapters/llm_openai_compatible.py`

```py
"""OpenAI-compatible LLM (works with any OpenAI-compatible API)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from core.domain.messages import AssistantMessage, UserMessage
from core.ports.llm import ILLM
from core.registry import register
from core.retry import with_retry
from core.utils import resolve_api_key

@register("llm", "openai_compatible")
class OpenAICompatibleLLM(ILLM):
    """LLM using OpenAI-compatible REST API."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.model: str = getattr(config, "model", "gpt-4o-mini")
        self.api_base: str = getattr(config, "api_base", "https://api.openai.com/v1")
        self.api_key: str = resolve_api_key(
            getattr(config, "api_key", None), "OPENAI_API_KEY"
        )
        self.max_tokens: int = getattr(config, "max_tokens", 4096)
        self.temperature: float = getattr(config, "temperature", 0.7)
        self._timeout: float = config.timeout

    def _build_messages(self, messages: list[Any]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for m in messages:
            if isinstance(m, dict):
                out.append(m)
            elif isinstance(m, UserMessage):
                content = m.text or ""
                if m.image:
                    content_parts: list[dict[str, Any]] = [
                        {"type": "text", "text": content}
                    ]
                    if m.image.url:
                        content_parts.append(
                            {"type": "image_url", "image_url": {"url": m.image.url}}
                        )
                    elif m.image.base64_data:
                        data_url = (
                            f"data:{m.image.mime_type};base64,{m.image.base64_data}"
                        )
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": data_url},
                            }
                        )
                    out.append({"role": "user", "content": content_parts})
                else:
                    out.append({"role": "user", "content": content})
            elif isinstance(m, AssistantMessage):
                msg: dict[str, Any] = {"role": "assistant", "content": m.text or ""}
                if m.tool_calls:
                    msg["tool_calls"] = m.tool_calls
                out.append(msg)
        return out

    @with_retry(max_retries=3, delay=1.0)
    async def complete(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AssistantMessage:
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        choice = data["choices"][0]
        msg = choice.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        return AssistantMessage(text=msg.get("content", ""), tool_calls=tool_calls)

    async def stream(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AsyncIterator[str]:
        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": self._build_messages(messages),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST", url, headers=headers, json=payload
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk = line[6:]
                        if chunk == "[DONE]":
                            break
                        try:
                            obj = json.loads(chunk)
                            delta = obj["choices"][0].get("delta", {})
                            if "content" in delta and delta["content"]:
                                yield delta["content"]
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
```

#### `adapters/memory_sqlite.py`

```py
"""SQLite-based long-term memory."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from core.ports.memory import ILongTermMemory, MemoryEntry
from core.registry import register

@register("memory", "sqlite")
class SQLiteMemory(ILongTermMemory):
    """Persistent memory using SQLite with FTS5 full-text search."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.db_path: str = getattr(config, "db_path", "./data/memory.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._fts5_available = False
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT DEFAULT 'conversation',
                    importance REAL DEFAULT 1.0,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)
            """)
            # Attempt FTS5 setup with graceful fallback
            try:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                        content, content='memories', content_rowid='id'
                    )
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS memories_ai
                    AFTER INSERT ON memories BEGIN
                        INSERT INTO memories_fts(rowid, content)
                        VALUES (new.id, new.content);
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS memories_ad
                    AFTER DELETE ON memories BEGIN
                        INSERT INTO memories_fts(
                            memories_fts, rowid, content
                        )
                        VALUES ('delete', old.id, old.content);
                    END
                """)
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS memories_au
                    AFTER UPDATE ON memories BEGIN
                        INSERT INTO memories_fts(
                            memories_fts, rowid, content
                        )
                        VALUES ('delete', old.id, old.content);
                        INSERT INTO memories_fts(rowid, content)
                        VALUES (new.id, new.content);
                    END
                """)
                count = conn.execute("SELECT COUNT(*) FROM memories_fts").fetchone()[0]
                if count == 0:
                    conn.execute(
                        "INSERT INTO memories_fts(rowid, content) "
                        "SELECT id, content FROM memories"
                    )
                self._fts5_available = True
            except sqlite3.OperationalError:
                self._fts5_available = False
            conn.commit()

    async def add(self, user_id: str, entry: MemoryEntry) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO memories
                   (user_id, content, source, importance, tags, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    entry.content,
                    entry.source,
                    entry.importance,
                    json.dumps(entry.tags),
                    json.dumps(entry.metadata),
                ),
            )
            conn.commit()

    async def get(
        self, user_id: str, query: str | None = None, limit: int = 20
    ) -> list[MemoryEntry]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows: list[sqlite3.Row] = []
            if query:
                if self._fts5_available:
                    try:
                        rows = conn.execute(
                            """SELECT m.* FROM memories m
                               JOIN memories_fts f ON m.id = f.rowid
                               WHERE m.user_id = ? AND f.content MATCH ?
                               ORDER BY m.importance DESC, m.created_at DESC
                               LIMIT ?""",
                            (user_id, query, limit),
                        ).fetchall()
                    except sqlite3.OperationalError:
                        rows = conn.execute(
                            """SELECT * FROM memories
                               WHERE user_id = ? AND content LIKE ?
                               ORDER BY importance DESC, created_at DESC
                               LIMIT ?""",
                            (user_id, f"%{query}%", limit),
                        ).fetchall()
                else:
                    rows = conn.execute(
                        """SELECT * FROM memories
                           WHERE user_id = ? AND content LIKE ?
                           ORDER BY importance DESC, created_at DESC
                           LIMIT ?""",
                        (user_id, f"%{query}%", limit),
                    ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT * FROM memories
                       WHERE user_id = ?
                       ORDER BY importance DESC, created_at DESC
                       LIMIT ?""",
                    (user_id, limit),
                ).fetchall()

            return [
                MemoryEntry(
                    id=str(r["id"]),
                    content=r["content"],
                    source=r["source"],
                    importance=r["importance"],
                    tags=json.loads(r["tags"]) if r["tags"] else [],
                    created_at=r["created_at"],
                    metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                )
                for r in rows
            ]

    async def forget(self, user_id: str, entry_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE user_id = ? AND id = ?",
                (user_id, entry_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    async def consolidate(self, user_id: str) -> None:
        """Remove old low-importance memories."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """DELETE FROM memories
                   WHERE user_id = ?
                   AND importance < 0.3
                   AND created_at < datetime('now', '-30 days')""",
                (user_id,),
            )
            conn.commit()
```

#### `adapters/reranker_api.py`

```py
"""Cross-encoder reranker via OpenAI-compatible /rerank API."""

from __future__ import annotations

from typing import Any

import httpx

from core.domain.documents import Chunk
from core.ports.reranker import IReranker, RerankResult
from core.registry import register
from core.retry import with_retry
from core.utils import resolve_api_key

@register("reranker", "api")
class APIReranker(IReranker):
    """Cross-encoder reranker using external API (OpenAI-compatible /rerank).

    Compatible with:
    - Cohere /rerank
    - Jina AI /rerank
    - Any OpenAI-compatible rerank endpoint
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.api_base: str = getattr(config, "api_base", "https://api.cohere.com")
        self.api_key: str = resolve_api_key(
            getattr(config, "api_key", None), "RERANK_API_KEY"
        )
        self.model: str = getattr(config, "model", "rerank-multilingual-v3.0")
        self._timeout: float = getattr(config, "timeout", 30.0)
        self._threshold: float = getattr(config, "threshold", 0.3)

    @with_retry(max_retries=2, delay=1.0)
    async def rerank(
        self, query: str, chunks: list[Chunk], top_k: int | None = None
    ) -> list[RerankResult]:
        """Rerank chunks via API and filter by relevance threshold."""
        if not chunks:
            return []

        url = f"{self.api_base}/v1/rerank"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        docs = [c.text for c in chunks if c.text]
        if not docs:
            return []
        payload = {
            "model": self.model,
            "query": query,
            "documents": docs,
            "top_n": top_k or len(chunks),
            "return_documents": False,
        }

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()

        # Map API results back to chunks
        results: list[RerankResult] = []
        for item in data.get("results", []):
            idx = item.get("index", 0)
            score = item.get("relevance_score", 0.0)
            if idx < len(chunks) and score >= self._threshold:
                results.append(RerankResult(chunk=chunks[idx], score=score))

        # Sort by score descending (API usually returns sorted, but ensure)
        results.sort(key=lambda r: r.score, reverse=True)

        if top_k is not None:
            results = results[:top_k]

        return results
```

#### `adapters/reranker_dummy.py`

```py
"""Dummy reranker — transparent pass-through, no-op fallback."""

from __future__ import annotations

from typing import Any

from core.domain.documents import Chunk
from core.ports.reranker import IReranker, RerankResult
from core.registry import register

@register("reranker", "dummy")
class DummyReranker(IReranker):
    """Transparent reranker — returns chunks as-is with uniform scores.

    Used when no real reranker is configured. Maintains backward compatibility.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def rerank(
        self, query: str, chunks: list[Chunk], top_k: int | None = None
    ) -> list[RerankResult]:
        """Return chunks with score=1.0, preserving original order."""
        results = [RerankResult(chunk=c, score=1.0) for c in chunks]
        if top_k is not None:
            results = results[:top_k]
        return results
```

#### `adapters/storage_sqlite.py`

```py
"""SQLite storage adapter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from core.ports.storage import IChatStorage, ISettingsStorage
from core.registry import register

@register("storage", "sqlite")
class SQLiteStorage(IChatStorage, ISettingsStorage):
    """Combined chat and settings storage."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.db_path: str = config.db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

    async def save_message(self, conversation_id: str, message: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO chat_messages
                (conversation_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    message.get("role", ""),
                    message.get("content", ""),
                    json.dumps(message.get("metadata", {})),
                ),
            )
            conn.commit()

    async def get_history(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT role, content, metadata, created_at
                FROM chat_messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
            return [
                {
                    "role": r["role"],
                    "content": r["content"],
                    "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                    "created_at": r["created_at"],
                }
                for r in reversed(rows)
            ]

    async def get(self, key: str, default: Any = None) -> Any:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row:
                return json.loads(row[0])
            return default

    async def set(self, key: str, value: Any) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?
                """,
                (key, json.dumps(value), json.dumps(value)),
            )
            conn.commit()
```

#### `adapters/tools_calculator.py`

```py
"""Calculator tool — allows LLM to perform math operations."""

from __future__ import annotations

import json
import operator
from typing import Any

from core.ports.tools import ITool, ToolResult, ToolSpec
from core.registry import register

@register("tool", "calculator")
class CalculatorTool(ITool):
    """Simple calculator for LLM function calling."""

    def __init__(self, config: Any = None) -> None:
        self._ops = {
            "add": operator.add,
            "subtract": operator.sub,
            "multiply": operator.mul,
            "divide": operator.truediv,
        }

    @property
    def spec(self) -> ToolSpec:
        """Schema describing the calculator for LLM."""
        return ToolSpec(
            name="calculator",
            description=(
                "Perform basic math operations: add, subtract, multiply, divide"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "Math operation to perform",
                    },
                    "a": {"type": "number", "description": "First number"},
                    "b": {"type": "number", "description": "Second number"},
                },
                "required": ["operation", "a", "b"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the calculation."""
        try:
            op_name = arguments.get("operation")
            a = float(arguments.get("a", 0))
            b = float(arguments.get("b", 0))

            if op_name not in self._ops:
                return ToolResult(
                    call_id="",
                    output="",
                    error=f"Unknown operation: {op_name}",
                    is_error=True,
                )

            if op_name == "divide" and b == 0:
                return ToolResult(
                    call_id="",
                    output="",
                    error="Division by zero",
                    is_error=True,
                )

            result = self._ops[op_name](a, b)
            return ToolResult(
                call_id="",
                output=json.dumps({"result": result}),
            )

        except Exception as e:
            return ToolResult(
                call_id="",
                output="",
                error=str(e),
                is_error=True,
            )
```

#### `adapters/transport_fastapi.py`

```py
"""FastAPI transport adapter."""

from __future__ import annotations

from typing import Any

from core.ports.transport import ITransport
from core.registry import register

@register("transport", "fastapi")
class FastAPITransport(ITransport):
    """FastAPI HTTP/WebSocket server."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.host: str = config.host
        self.port: int = config.port

    async def start(self) -> None:
        import uvicorn

        from main import app

        config = uvicorn.Config(app, host=self.host, port=self.port)
        server = uvicorn.Server(config)
        await server.serve()

    async def stop(self) -> None:
        pass
```

#### `adapters/vector_store_faiss.py`

```py
"""FAISS vector store with namespace (collection) support."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

try:
    import faiss

    _FAISS_AVAILABLE = True
except ImportError:
    faiss = None
    _FAISS_AVAILABLE = False

from core.domain.documents import Chunk, ChunkMetadata
from core.domain.errors import VersionMismatchError
from core.io_utils import atomic_write
from core.ports.vector_store import IVectorStore
from core.registry import register

logger = logging.getLogger(__name__)

if _FAISS_AVAILABLE:

    @register("vector_store", "faiss")
    class FaissVectorStore(IVectorStore):
        """Thread-safe FAISS vector store with multi-namespace support.

        Each namespace is an isolated index stored under:
            {path}/{namespace}/index.faiss
            {path}/{namespace}/index_meta.json
            {path}/{namespace}/store.json
        """

        def __init__(self, config: Any) -> None:
            super().__init__(config)
            self.dim: int = config.dim
            self.metric: str = config.metric
            self._namespaces: dict[str, _NamespaceData] = {}
            self._lock = asyncio.Lock()

        def _create_index(self) -> faiss.Index:
            if self.metric == "ip":
                return faiss.IndexFlatIP(self.dim)
            return faiss.IndexFlatL2(self.dim)

        def _get_ns(self, name: str) -> _NamespaceData:
            if name not in self._namespaces:
                self._namespaces[name] = _NamespaceData(
                    index=None,
                    chunks={},
                    metadata={},
                    id_map={},
                    next_id=0,
                )
            return self._namespaces[name]

        async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
            if not chunks:
                return
            async with self._lock:
                ns = self._get_ns(namespace)
                if ns.index is None:
                    ns.index = self._create_index()

                embeddings: list[list[float]] = []
                valid_chunks: list[Chunk] = []
                for c in chunks:
                    if c.embedding is None:
                        continue
                    embeddings.append(c.embedding)
                    valid_chunks.append(c)

                if not embeddings:
                    return

                vectors = np.array(embeddings, dtype=np.float32)
                start_id = ns.next_id
                ns.index.add(vectors)

                for i, chunk in enumerate(valid_chunks):
                    faiss_id = start_id + i
                    ns.chunks[faiss_id] = chunk
                    ns.id_map[chunk.id] = faiss_id
                    meta = (
                        chunk.metadata.custom
                        if chunk.metadata and chunk.metadata.custom
                        else {}
                    )
                    meta["source"] = chunk.metadata.source if chunk.metadata else ""
                    meta["index"] = chunk.metadata.index if chunk.metadata else 0
                    ns.metadata[chunk.id] = meta

                ns.next_id += len(valid_chunks)

        async def search(
            self,
            query_embedding: list[float],
            top_k: int = 5,
            namespace: str = "default",
        ) -> list[Chunk]:
            async with self._lock:
                ns = self._get_ns(namespace)
                if ns.index is None or ns.index.ntotal == 0:
                    return []
                q = np.array([query_embedding], dtype=np.float32)
                distances, indices = ns.index.search(q, top_k)
                results: list[Chunk] = []
                for idx in indices[0]:
                    if idx < 0:
                        continue
                    chunk = ns.chunks.get(int(idx))
                    if chunk:
                        results.append(chunk)
                return results

        async def delete(
            self, chunk_ids: list[str], namespace: str = "default"
        ) -> None:
            async with self._lock:
                ns = self._get_ns(namespace)
                ids_to_remove = set(chunk_ids)
                remaining: list[Chunk] = []
                for fid, chunk in ns.chunks.items():
                    if chunk.id not in ids_to_remove:
                        if chunk.embedding:
                            remaining.append(chunk)

                ns.index = self._create_index()
                ns.chunks.clear()
                ns.id_map.clear()
                ns.metadata = {
                    k: v for k, v in ns.metadata.items() if k not in ids_to_remove
                }
                ns.next_id = 0

                if remaining:
                    embeddings: list[list[float]] = []
                    valid_chunks: list[Chunk] = []
                    for c in remaining:
                        if c.embedding is None:
                            continue
                        embeddings.append(c.embedding)
                        valid_chunks.append(c)

                    if embeddings:
                        vectors = np.array(embeddings, dtype=np.float32)
                        start_id = ns.next_id
                        ns.index.add(vectors)

                        for i, chunk in enumerate(valid_chunks):
                            faiss_id = start_id + i
                            ns.chunks[faiss_id] = chunk
                            ns.id_map[chunk.id] = faiss_id
                            meta = (
                                chunk.metadata.custom
                                if chunk.metadata and chunk.metadata.custom
                                else {}
                            )
                            meta["source"] = (
                                chunk.metadata.source if chunk.metadata else ""
                            )
                            meta["index"] = (
                                chunk.metadata.index if chunk.metadata else 0
                            )
                            ns.metadata[chunk.id] = meta

                        ns.next_id += len(valid_chunks)

        async def save(self, path: str, namespace: str = "default") -> None:
            async with self._lock:
                ns = self._get_ns(namespace)
                if ns.index is None:
                    return
                p = Path(path) / namespace
                p.mkdir(parents=True, exist_ok=True)
                faiss.write_index(ns.index, str(p / "index.faiss"))

                meta = {
                    "version": "1.0",
                    "embedder_model": getattr(self.config, "embedder_model", "unknown"),
                    "embedder_dim": self.dim,
                    "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
                    "chunk_count": len(ns.chunks),
                    "metric": self.metric,
                }
                await atomic_write(p / "index_meta.json", json.dumps(meta, indent=2))

                store = {
                    "chunks": {
                        str(k): {
                            "id": c.id,
                            "text": c.text,
                            "embedding": c.embedding,
                            "metadata": {
                                "source": c.metadata.source if c.metadata else "",
                                "index": c.metadata.index if c.metadata else 0,
                                "total_chunks": c.metadata.total_chunks
                                if c.metadata
                                else 0,
                                "created_at": c.metadata.created_at
                                if c.metadata
                                else "",
                                "custom": c.metadata.custom if c.metadata else {},
                            }
                            if c.metadata
                            else None,
                        }
                        for k, c in ns.chunks.items()
                    },
                    "metadata": ns.metadata,
                    "id_map": ns.id_map,
                    "next_id": ns.next_id,
                }
                await atomic_write(p / "store.json", json.dumps(store, indent=2))

        async def load(self, path: str, namespace: str = "default") -> None:
            p = Path(path) / namespace
            if not await asyncio.to_thread((p / "index.faiss").exists):
                return

            async with self._lock:
                ns = self._get_ns(namespace)
                ns.index = faiss.read_index(str(p / "index.faiss"))

                meta_path = p / "index_meta.json"
                if await asyncio.to_thread(meta_path.exists):
                    meta_text = await asyncio.to_thread(meta_path.read_text)
                    meta = json.loads(meta_text)
                    stored_dim = meta.get("embedder_dim")
                    if stored_dim is not None and stored_dim != self.dim:
                        raise VersionMismatchError(
                            f"Reindex required: stored dim {stored_dim} "
                            f"!= config dim {self.dim}"
                        )

                store_path = p / "store.json"
                if await asyncio.to_thread(store_path.exists):
                    store_text = await asyncio.to_thread(store_path.read_text)
                    store = json.loads(store_text)
                    ns.chunks = {}
                    for k, v in store.get("chunks", {}).items():
                        meta = v.get("metadata")
                        chunk_meta = None
                        if meta:
                            chunk_meta = ChunkMetadata(
                                source=meta.get("source", ""),
                                index=meta.get("index", 0),
                                total_chunks=meta.get("total_chunks", 0),
                                created_at=meta.get("created_at", ""),
                                custom=meta.get("custom", {}),
                            )
                        ns.chunks[int(k)] = Chunk(
                            id=v["id"],
                            text=v["text"],
                            embedding=v.get("embedding"),
                            metadata=chunk_meta,
                        )
                    ns.metadata = store.get("metadata", {})
                    ns.id_map = store.get("id_map", {})
                    ns.next_id = store.get("next_id", 0)

        async def list_by_filter(
            self, filter: dict[str, Any], namespace: str = "default"
        ) -> list[tuple[str, dict[str, Any]]]:
            async with self._lock:
                ns = self._get_ns(namespace)
                results: list[tuple[str, dict[str, Any]]] = []
                for chunk_id, meta in ns.metadata.items():
                    match = True
                    for key, value in filter.items():
                        if meta.get(key) != value:
                            match = False
                            break
                    if match:
                        results.append((chunk_id, meta))
                return results

        async def list_namespaces(self, path: str) -> list[str]:
            p = Path(path)
            if not await asyncio.to_thread(p.exists):
                return []
            entries = await asyncio.to_thread(lambda: list(p.iterdir()))
            result: list[str] = []
            for d in entries:
                is_dir = await asyncio.to_thread(d.is_dir)
                has_index = await asyncio.to_thread((d / "index.faiss").exists)
                if is_dir and has_index:
                    result.append(d.name)
            return result

    class _NamespaceData:
        """Internal per-namespace state container."""

        def __init__(
            self,
            index: faiss.Index | None,
            chunks: dict[int, Chunk],
            metadata: dict[str, dict[str, Any]],
            id_map: dict[str, int],
            next_id: int,
        ) -> None:
            self.index = index
            self.chunks = chunks
            self.metadata = metadata
            self.id_map = id_map
            self.next_id = next_id

else:
    from adapters.vector_store_memory import MemoryVectorStore

    @register("vector_store", "faiss")
    class FaissVectorStore(MemoryVectorStore):  # type: ignore[no-redef]
        """Fallback to MemoryVectorStore when faiss-cpu is not installed."""

        def __init__(self, config: Any) -> None:
            logger.warning(
                "faiss-cpu not installed. "
                "FaissVectorStore falls back to MemoryVectorStore."
            )
            super().__init__(config)
```

#### `adapters/vector_store_memory.py`

```py
"""In-memory vector store with namespace support and strict relevance filtering."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np

from core.domain.documents import Chunk
from core.io_utils import atomic_write
from core.ports.vector_store import IVectorStore
from core.registry import register

@register("vector_store", "memory")
class MemoryVectorStore(IVectorStore):
    """Simple in-memory vector store with multi-namespace support.

    Uses cosine similarity with strict threshold to prevent irrelevant results.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.dim: int = config.dim
        self._namespaces: dict[str, _NamespaceData] = {}
        self._lock = asyncio.Lock()

    def _get_ns(self, name: str) -> _NamespaceData:
        if name not in self._namespaces:
            self._namespaces[name] = _NamespaceData(
                chunks={},
                embeddings={},
                metadata={},
                dim=self.dim,
            )
        return self._namespaces[name]

    def _normalize(self, v: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(v)
        return v / norm if norm > 0 else v

    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        if not chunks:
            return
        async with self._lock:
            ns = self._get_ns(namespace)
            for chunk in chunks:
                if chunk.embedding is None:
                    continue
                emb = np.array(chunk.embedding, dtype=np.float32)
                if emb.shape[0] != self.dim:
                    continue
                ns.chunks[chunk.id] = chunk
                ns.embeddings[chunk.id] = self._normalize(emb)
                meta = (
                    chunk.metadata.custom
                    if chunk.metadata and chunk.metadata.custom
                    else {}
                )
                meta["source"] = chunk.metadata.source if chunk.metadata else ""
                meta["index"] = chunk.metadata.index if chunk.metadata else 0
                ns.metadata[chunk.id] = meta

    async def search(
        self, query_embedding: list[float], top_k: int = 5, namespace: str = "default"
    ) -> list[Chunk]:
        """Search for relevant chunks with strict similarity threshold.

        Returns empty list if no chunks meet the relevance threshold,
        preventing irrelevant results from being returned.
        """
        async with self._lock:
            ns = self._get_ns(namespace)
            if not ns.embeddings:
                return []

            try:
                q = self._normalize(np.array(query_embedding, dtype=np.float32))
                ids = list(ns.embeddings.keys())
                matrix = np.stack([ns.embeddings[i] for i in ids])
                scores = matrix @ q
            except Exception:
                return []

            # Dynamic threshold from config
            raw_threshold = getattr(self.config, "relevance_threshold", 0.3)
            try:
                threshold = float(raw_threshold)
            except (TypeError, ValueError):
                threshold = 0.3

            # Filter by similarity threshold - STRICT
            valid_indices = np.where(scores >= threshold)[0]
            if len(valid_indices) == 0:
                return []

            # Sort valid results by score descending
            valid_scores = scores[valid_indices]
            sorted_order = np.argsort(valid_scores)[::-1]
            top_indices = valid_indices[sorted_order[:top_k]]

            return [ns.chunks[ids[i]] for i in top_indices]

    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        async with self._lock:
            ns = self._get_ns(namespace)
            for cid in chunk_ids:
                ns.chunks.pop(cid, None)
                ns.embeddings.pop(cid, None)
                ns.metadata.pop(cid, None)

    async def save(self, path: str, namespace: str = "default") -> None:
        p = Path(path) / namespace
        p.parent.mkdir(parents=True, exist_ok=True)
        ns = self._get_ns(namespace)
        data = {
            "dim": ns.dim,
            "chunks": {
                cid: {"id": c.id, "text": c.text} for cid, c in ns.chunks.items()
            },
            "embeddings": {cid: emb.tolist() for cid, emb in ns.embeddings.items()},
            "metadata": ns.metadata,
        }
        await atomic_write(p / "memory_store.json", json.dumps(data, indent=2))

    async def load(self, path: str, namespace: str = "default") -> None:
        p = Path(path) / namespace / "memory_store.json"
        if not await asyncio.to_thread(p.exists):
            return
        data_text = await asyncio.to_thread(p.read_text)
        data = json.loads(data_text)
        async with self._lock:
            ns = self._get_ns(namespace)
            ns.dim = data.get("dim", self.dim)
            ns.chunks = {
                cid: Chunk(id=c["id"], text=c["text"])
                for cid, c in data.get("chunks", {}).items()
            }
            ns.embeddings = {
                cid: np.array(emb, dtype=np.float32)
                for cid, emb in data.get("embeddings", {}).items()
            }
            ns.metadata = data.get("metadata", {})

    async def list_by_filter(
        self, filter: dict[str, Any], namespace: str = "default"
    ) -> list[tuple[str, dict[str, Any]]]:
        async with self._lock:
            ns = self._get_ns(namespace)
            results: list[tuple[str, dict[str, Any]]] = []
            for chunk_id, meta in ns.metadata.items():
                match = all(meta.get(k) == v for k, v in filter.items())
                if match:
                    results.append((chunk_id, meta))
            return results

    async def list_namespaces(self, path: str) -> list[str]:
        p = Path(path)
        if not await asyncio.to_thread(p.exists):
            return []
        entries = await asyncio.to_thread(lambda: list(p.iterdir()))
        result: list[str] = []
        for d in entries:
            is_dir = await asyncio.to_thread(d.is_dir)
            has_store = await asyncio.to_thread((d / "memory_store.json").exists)
            if is_dir and has_store:
                result.append(d.name)
        return result

class _NamespaceData:
    def __init__(
        self,
        chunks: dict[str, Chunk],
        embeddings: dict[str, np.ndarray],
        metadata: dict[str, dict[str, Any]],
        dim: int,
    ) -> None:
        self.chunks = chunks
        self.embeddings = embeddings
        self.metadata = metadata
        self.dim = dim
```

#### `adapters/vision_clip_local.py`

```py
"""Local CLIP vision processor — friendly fallback."""

from __future__ import annotations

from typing import Any

from core.ports.vision import IVisionProcessor
from core.registry import register

@register("vision", "clip_local")
class CLIPLocalVision(IVisionProcessor):
    """Stub with graceful fallback message."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def describe(self, image_base64: str, prompt: str | None = None) -> str:
        return (
            "🔧 Vision analysis is not yet configured. "
            "To enable image understanding, install transformers and set "
            "vision.enabled=true in config.yaml."
        )
```

#### `adapters/voice_piper.py`

```py
"""Piper TTS synthesizer — friendly fallback and real implementation."""

from __future__ import annotations

import asyncio
import subprocess
from typing import Any

import httpx

from core.ports.voice import IVoiceSynthesizer
from core.registry import register

@register("voice_synthesizer", "piper")
class PiperSynthesizer(IVoiceSynthesizer):
    """Stub with graceful fallback."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        return b""  # silent placeholder — TTS not configured

@register("voice_synthesizer", "piper_real")
class PiperRealSynthesizer(IVoiceSynthesizer):
    """Real TTS using Piper HTTP server or local executable."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.api_base: str | None = getattr(config, "api_base", None)
        self.local_bin: str | None = getattr(config, "local_bin", None)
        self.model_path: str | None = getattr(config, "model_path", None)
        self._timeout: float = getattr(config, "timeout", 30.0)
        self._available: bool | None = None

    async def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        if self.api_base:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{self.api_base}/health")
                    self._available = resp.status_code < 500
                    return self._available
            except Exception:
                pass
        if self.local_bin:
            import shutil

            self._available = shutil.which(self.local_bin) is not None
            return self._available
        self._available = False
        return self._available

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        if not await self._check_available():
            return b""

        if self.api_base:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{self.api_base}/synthesize",
                        json={"text": text, "voice": voice},
                    )
                    resp.raise_for_status()
                    return resp.content
            except Exception:
                pass

        if self.local_bin and self.model_path:
            try:
                proc = await asyncio.create_subprocess_exec(
                    self.local_bin,
                    "--model",
                    self.model_path,
                    "--output_file",
                    "-",
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(text.encode()),
                    timeout=self._timeout,
                )
                return stdout
            except Exception:
                pass

        return b""
```

#### `adapters/voice_whisper_local.py`

```py
"""Local Whisper voice recognizer — friendly fallback."""

from __future__ import annotations

from typing import Any

from core.ports.voice import IVoiceRecognizer
from core.registry import register

@register("voice_recognizer", "whisper_local")
class WhisperLocalRecognizer(IVoiceRecognizer):
    """Stub with graceful fallback message."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
        return (
            "🔧 Voice transcription is not yet configured. "
            "To enable speech-to-text, install faster-whisper and set "
            "voice.enabled=true in config.yaml."
        )
```

#### `adapters/voice_whispercpp.py`

```py
"""Local voice recognizer via whisper.cpp HTTP server."""

from __future__ import annotations

from typing import Any

import httpx

from core.ports.voice import IVoiceRecognizer
from core.registry import register

@register("voice_recognizer", "whispercpp")
class WhisperCppRecognizer(IVoiceRecognizer):
    """Speech-to-text using whisper.cpp HTTP API."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.api_base: str = getattr(config, "api_base", "http://127.0.0.1:8082")
        self._timeout: float = getattr(config, "timeout", 60.0)
        self._available: bool | None = None

    async def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.api_base}/health")
                self._available = resp.status_code < 500
        except Exception:
            self._available = False
        return self._available

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
        if not await self._check_available():
            return ""

        files = {"file": ("audio.wav", audio_bytes, mime_type)}
        data = {"language": getattr(self.config, "language", "auto")}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self.api_base}/inference",
                    files=files,
                    data=data,
                )
                resp.raise_for_status()
                result = resp.json()
                text = result.get("text", "")
                return text.strip()
        except Exception:
            return ""
```

### `api/`

#### `api/__init__.py`

```py
"""API layer — transport, DI, routing."""
```

#### `api/admin.py`

```py
"""Admin endpoints — diagnostics."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import AppState, get_state

router = APIRouter(prefix="/admin", tags=["admin"])

class _CurrentModelResponse(BaseModel):
    model: str
    provider: str

@router.get("/current-model", response_model=_CurrentModelResponse)
async def get_current_model(
    state: Annotated[AppState, Depends(get_state)],
) -> _CurrentModelResponse:
    """Return currently configured model info from config.yaml."""
    cfg = state.config.llm
    return _CurrentModelResponse(
        model=getattr(cfg, "model", "unknown"),
        provider=cfg.provider,
    )
```

#### `api/deps.py`

```py
"""API dependencies — AppState, get_state, MetricsMiddleware."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware

# ── Eager-load adapters to trigger @register side-effects ──
import adapters.chunker_simple  # noqa: F401
import adapters.embedder_mock  # noqa: F401
import adapters.embedder_openai_compatible  # noqa: F401
import adapters.llm_mock  # noqa: F401
import adapters.llm_openai_compatible  # noqa: F401
import adapters.memory_sqlite  # noqa: F401
import adapters.reranker_api  # noqa: F401
import adapters.reranker_dummy  # noqa: F401
import adapters.storage_sqlite  # noqa: F401
import adapters.tools_calculator  # noqa: F401
import adapters.vector_store_faiss  # noqa: F401
import adapters.vector_store_memory  # noqa: F401
import adapters.vision_clip_local  # noqa: F401
import adapters.voice_piper  # noqa: F401
import adapters.voice_whisper_local  # noqa: F401
import adapters.voice_whispercpp  # noqa: F401
from core.config import AppConfig
from core.metrics import get_metrics_logger
from core.pipeline import RAGPipeline
from core.registry import create as registry_create
from core.tool_registry import ToolRegistry
from pipeline.decorators import get_step

@dataclass
class AppState:
    """Application state container — initialized once at startup."""

    config: AppConfig
    llm: Any = None
    embedder: Any = None
    vector_store: Any = None
    chunker: Any = None
    reranker: Any = None
    pipeline: Any = None
    storage: Any = None
    voice_recognizer: Any = None
    voice_synthesizer: Any = None
    vision: Any = None
    tool_registry: Any = None
    long_term_memory: Any = None

# Global state — initialized exactly once via asyncio.Event
_state: AppState | None = None
_init_event = asyncio.Event()
_initializing = False

async def init_adapters(config: AppConfig | AppState) -> AppState:
    """Initialize all adapters via Registry and return populated AppState."""

    global _state, _initializing

    # Normalize input: tests may pass AppState, production passes AppConfig
    if isinstance(config, AppState):
        state = config
        cfg = state.config
    else:
        cfg = config
        state = AppState(config=cfg)

    if _init_event.is_set() and _state is not None:
        return _state

    if _initializing:
        await _init_event.wait()
        if _state is not None:
            return _state

    _initializing = True
    # Сбрасываем event, если он был установлен при предыдущем падении
    if _init_event.is_set():
        _init_event.clear()

    try:
        if not isinstance(config, AppState):
            state = AppState(config=cfg)
        state.tool_registry = ToolRegistry()

        try:
            tool = registry_create("tool", "calculator", cfg)
            state.tool_registry.register(tool)
        except Exception:
            pass

        state.chunker = registry_create("chunker", cfg.chunker.provider, cfg.chunker)
        state.embedder = registry_create(
            "embedder", cfg.embedder.provider, cfg.embedder
        )
        state.llm = registry_create("llm", cfg.llm.provider, cfg.llm)
        state.vector_store = registry_create(
            "vector_store", cfg.vector_store.provider, cfg.vector_store
        )

        if getattr(cfg, "reranker", None) and getattr(cfg.reranker, "provider", None):
            try:
                state.reranker = registry_create(
                    "reranker", cfg.reranker.provider, cfg.reranker
                )
            except ValueError:
                pass

        try:
            state.storage = registry_create(
                "storage", cfg.storage.provider, cfg.storage
            )
        except ValueError as e:
            import logging

            logging.getLogger("ai_assistant.deps").warning(
                "Storage adapter '%s' not available: %s", cfg.storage.provider, e
            )
            state.storage = None

        try:
            state.long_term_memory = registry_create("memory", "sqlite", cfg.storage)
        except Exception as e:
            import logging

            logging.getLogger("ai_assistant.deps").warning(
                "Long-term memory not available: %s", e
            )
            state.long_term_memory = None

        if cfg.voice.enabled:
            state.voice_recognizer = registry_create(
                "voice_recognizer", cfg.voice.recognizer_provider, cfg.voice
            )
            state.voice_synthesizer = registry_create(
                "voice_synthesizer", cfg.voice.synthesizer_provider, cfg.voice
            )

        if cfg.vision.enabled:
            state.vision = registry_create("vision", cfg.vision.provider, cfg.vision)

        index_path = getattr(cfg.vector_store, "index_path", None)
        if index_path:
            try:
                namespaces = await state.vector_store.list_namespaces(index_path)
                for ns in namespaces:
                    await state.vector_store.load(index_path, namespace=ns)
            except Exception:
                try:
                    await state.vector_store.load(index_path, namespace="default")
                except Exception:
                    pass

        step_funcs: list[Any] = []
        for name in cfg.rag.steps:
            func = get_step(name)
            if name == "embed_query":
                step_funcs.append(
                    lambda d, e=state.embedder, _f=func: _f(d, embedder=e)
                )
            elif name == "retrieve":
                step_funcs.append(
                    lambda d, vs=state.vector_store, _f=func: _f(d, vector_store=vs)
                )
            elif name == "rerank":
                step_funcs.append(
                    lambda d, r=state.reranker, _f=func: _f(d, reranker=r)
                )
            elif name == "generate":
                step_funcs.append(
                    lambda d, llm=state.llm, tr=state.tool_registry, _f=func: _f(
                        d, llm=llm, tool_registry=tr
                    )
                )
            else:
                step_funcs.append(func)

        state.pipeline = RAGPipeline(step_funcs)
        _state = state
        _init_event.set()
        return state
    finally:
        _initializing = False

def get_state(request: Any = None) -> AppState:
    """Get initialized app state."""
    if request is not None and hasattr(request.app.state, "app_state"):
        return request.app.state.app_state
    if not _init_event.is_set() or _state is None:
        raise RuntimeError("State not initialized. Call init_adapters() first.")
    return _state

class MetricsMiddleware(BaseHTTPMiddleware):
    """Record request latency and token metrics."""

    async def dispatch(self, request, call_next):
        import time

        from core.metrics import get_current_metrics

        start = time.time()
        response = await call_next(request)
        latency_ms = int((time.time() - start) * 1000)
        metrics = get_current_metrics()
        metrics["endpoint"] = request.url.path
        metrics["status_code"] = response.status_code
        metrics["latency_ms"] = latency_ms
        get_metrics_logger().log(metrics)
        return response

def get_current_metrics() -> dict[str, Any]:
    """Get metrics collected for the current request."""
    from core.metrics import get_current_metrics as _get_metrics

    return _get_metrics()
```

#### `api/lifespan.py`

```py
"""Application lifespan — startup/shutdown with graceful cleanup."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.deps import init_adapters
from core.config import AppConfig, load_config
from core.logger import get_logger
from core.metrics import get_metrics_logger
from core.registry import create as registry_create  # noqa: F401 — для тестируемости

logger = get_logger("lifespan")

def _load_config() -> AppConfig:
    """Load config from YAML, fallback to env defaults."""
    config_path = os.getenv("AI_CONFIG_PATH", "config.yaml")
    return load_config(config_path)

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage application lifecycle."""
    config = _load_config()
    get_metrics_logger().start()
    state = await init_adapters(config)
    # Сохраняем state в app для доступа через request.app.state
    app.state.app_state = state

    yield

    state = getattr(app.state, "app_state", state)

    await get_metrics_logger().stop()

    try:
        if state.llm and hasattr(state.llm, "shutdown"):
            try:
                await state.llm.shutdown()
            except Exception as e:
                logger.warning("LLM shutdown failed: %s", e)

        if state.embedder and hasattr(state.embedder, "shutdown"):
            try:
                await state.embedder.shutdown()
            except Exception as e:
                logger.warning("Embedder shutdown failed: %s", e)

        index_path = getattr(config.vector_store, "index_path", None)
        if index_path and state.vector_store:
            try:
                namespaces = await state.vector_store.list_namespaces(index_path)
                for ns in namespaces:
                    await state.vector_store.save(index_path, namespace=ns)
            except Exception:
                pass
    except RuntimeError:
        pass
```

#### `api/router.py`

```py
"""Auto-discovery router assembly."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from fastapi import APIRouter

from api import admin  # ← добавлено

logger = logging.getLogger("ai_assistant.router")

def assemble_routers() -> list[APIRouter]:
    """Auto-discover and collect routers from features/*/handlers.py + admin."""
    routers: list[APIRouter] = []

    # 1. Admin router (manual, not auto-discovered)
    routers.append(admin.router)

    # 2. Auto-discovered feature routers
    features_dir = Path(__file__).parent.parent / "features"
    if not features_dir.exists():
        return routers

    for feature_dir in features_dir.iterdir():
        if not feature_dir.is_dir() or feature_dir.name.startswith("_"):
            continue
        handlers_path = feature_dir / "handlers.py"
        if not handlers_path.exists():
            continue
        try:
            module = importlib.import_module(f"features.{feature_dir.name}.handlers")
            router = getattr(module, "router", None)
            if isinstance(router, APIRouter):
                routers.append(router)
                logger.debug(f"Loaded router from features.{feature_dir.name}.handlers")
            else:
                logger.warning(
                    f"No 'router' found in features.{feature_dir.name}.handlers"
                )
        except Exception as e:
            logger.error(f"Failed to load features.{feature_dir.name}.handlers: {e}")
            continue

    return routers
```

#### `api/security.py`

```py
from __future__ import annotations

import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

CONFIG_PATH = Path("config.yaml")
SECURITY_MAX_BODY = 10_485_760
bearer_scheme = HTTPBearer(auto_error=False)

def _load_security_cfg() -> dict[str, Any]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}).get("security", {})
    return {}

class SecurityLimiter:
    def __init__(self) -> None:
        self.requests: dict[str, list[float]] = defaultdict(list)
        cfg = _load_security_cfg()
        rate_str = cfg.get("rate_limit", "100/minute")
        try:
            self.max_req, period = int(rate_str.split("/")[0]), rate_str.split("/")[1]
            self.window = 60.0 if period == "minute" else 1.0
        except Exception:
            self.max_req, self.window = 100, 60.0

    def is_allowed(self, ip: str) -> bool:
        now = time.time()
        self.requests[ip] = [t for t in self.requests[ip] if t > now - self.window]
        if len(self.requests[ip]) >= self.max_req:
            return False
        self.requests[ip].append(now)
        return True

limiter = SecurityLimiter()

def get_expected_api_key() -> str | None:
    cfg = _load_security_cfg()
    return cfg.get("api_key") or os.getenv("AI_API_KEY")

class LimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Any) -> Response:
        ip = request.client.host if request.client else "unknown"
        if not limiter.is_allowed(ip):
            return Response(
                "Rate limit exceeded", status_code=429, media_type="text/plain"
            )
        return await call_next(request)

async def check_request_size(request: Request) -> None:
    cl = request.headers.get("content-length")
    max_sz = _load_security_cfg().get("max_body_size", SECURITY_MAX_BODY)
    if cl and int(cl) > int(max_sz):
        raise HTTPException(status_code=413, detail="Payload too large")

async def require_api_key(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> None:
    expected = get_expected_api_key()
    if not expected:
        return
    if not credentials:
        raise HTTPException(status_code=401, detail="Missing API key")
    if credentials.credentials != expected:
        raise HTTPException(status_code=401, detail="Invalid API key")

async def apply_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not limiter.is_allowed(ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

### `core/`

#### `core/__init__.py`

```py
"""Sacred core — immutable interfaces and domain."""

from . import config, domain, io_utils, pipeline, ports, prompts, registry, retry, utils

__all__ = [
    "domain",
    "ports",
    "prompts",
    "registry",
    "config",
    "pipeline",
    "retry",
    "io_utils",
    "utils",
]
```

#### `core/config.py`

```py
"""Application configuration — Pydantic + env-prefix AI__."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class CORSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CORS_", extra="allow")
    allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    allow_credentials: bool = True
    allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    allow_headers: list[str] = Field(default_factory=lambda: ["*"])

class UIConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_UI_", extra="allow")
    static_path: str = "./ui"

class ChatConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CHAT_", extra="allow")
    history_limit: int = 10
    max_context_tokens: int | None = None
    tokenizer_model: str = "gpt-4o"
    tokenizer_local_dir: str = "./data/tokenizers"

class ChunkerConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_CHUNKER_", extra="allow")
    provider: str = "simple"
    chunk_size: int = 512
    chunk_overlap: int = 50

class EmbedderConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_EMBEDDER_", extra="allow")
    provider: str = "mock"
    model: str = "text-embedding-3-small"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    dim: int = 384
    timeout: float = 60.0
    server_startup_delay: int = 3
    server_shutdown_timeout: int = 5
    # === GPU/CPU offload ===
    n_gpu_layers: int = Field(default=0, ge=-1, le=999)
    n_batch: int = Field(default=512, ge=1)
    n_ubatch: int = Field(default=64, ge=1)
    mmap: bool = True
    mlock: bool = False

class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_LLM_", extra="allow")
    provider: str = "mock"
    model: str = "gpt-4o-mini"
    api_base: str = "https://api.openai.com/v1"
    api_key: str | None = None
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout: float = 300.0
    server_startup_delay: int = 3
    server_shutdown_timeout: int = 5
    server_context_size: int = 4096
    stop_sequences: list[str] = Field(default_factory=list)
    # === Sampling ===
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    top_k: int = Field(default=40, ge=-1)
    min_p: float = Field(default=0.05, ge=0.0, le=1.0)
    repeat_penalty: float = Field(default=1.1, ge=0.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)

    # === Context ===
    n_batch: int = Field(default=512, ge=1)
    n_ubatch: int = Field(default=64, ge=1)
    cache_type_k: Literal["f16", "q8_0", "q4_0", "q4_1"] = "f16"
    cache_type_v: Literal["f16", "q8_0", "q4_0", "q4_1"] = "f16"

    # === GPU/CPU ===
    n_gpu_layers: int = Field(default=-1, ge=-1, le=999)
    split_mode: Literal["layer", "row", "none"] = "layer"
    main_gpu: int = Field(default=0, ge=0)
    tensor_split: list[float] = Field(default_factory=list)

    # === Performance ===
    num_threads: int = Field(default=0, ge=0)
    flash_attn: bool = False
    mmap: bool = True
    mlock: bool = False

    # === RoPE/YaRN ===
    rope_scaling: float = Field(default=1.0, gt=0.0)
    yarn_ext_factor: float = -1.0
    yarn_attn_factor: float = 1.0

    # === Speculative decoding ===
    draft_model: str | None = None
    draft_n_predict: int = Field(default=16, ge=1)

class VectorStoreConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_VECTOR_STORE_", extra="allow")
    provider: str = "memory"
    index_path: str = "./data/indices/default"
    metric: str = "l2"
    dim: int = 384

class StorageConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_STORAGE_", extra="allow")
    provider: str = "sqlite"
    db_path: str = "./data/storage.db"

class VoiceConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_VOICE_", extra="allow")
    enabled: bool = False
    recognizer_provider: str = "whisper_local"
    synthesizer_provider: str = "piper"

class VisionConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_VISION_", extra="allow")
    enabled: bool = False
    provider: str = "clip_local"

class RerankerConfig(BaseSettings):
    """Reranker configuration — optional, backward compatible."""

    model_config = SettingsConfigDict(env_prefix="AI_RERANKER_", extra="allow")
    provider: str = "dummy"  # "dummy" | "api"
    model: str = "rerank-multilingual-v3.0"
    api_base: str = "https://api.cohere.com"
    api_key: str | None = None
    timeout: float = 30.0
    threshold: float = 0.3

class RAGConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_RAG_", extra="allow")
    steps: list[str] = Field(
        default_factory=lambda: [
            "embed_query",
            "retrieve",
            "rerank",
            "build_context",
            "generate",
        ]
    )
    prompt_version: str = "v1"
    prompt_name: str = "rag_strict"
    top_k: int = 5
    default_namespace: str = "default"
    relevance_threshold: float = 0.3

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        extra="ignore",
    )
    app_name: str = "ai-assistant"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000
    config_version: str = "1.0.0"
    cors: CORSConfig = Field(default_factory=CORSConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    chat: ChatConfig = Field(default_factory=ChatConfig)
    chunker: ChunkerConfig = Field(default_factory=ChunkerConfig)
    embedder: EmbedderConfig = Field(default_factory=EmbedderConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    vision: VisionConfig = Field(default_factory=VisionConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    reranker: RerankerConfig = Field(default_factory=RerankerConfig)

    @field_validator("rag", mode="before")
    @classmethod
    def _load_rag_steps(cls, v: Any) -> Any:
        if isinstance(v, dict) and "steps" in v and isinstance(v["steps"], str):
            v["steps"] = v["steps"].split(",")
        return v

def load_config(path: str = "config.yaml") -> AppConfig:
    """Load config from YAML, fallback to env defaults."""
    config_path = Path(path)
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return AppConfig(**data)
    return AppConfig()
```

#### `core/io_utils.py`

```py
"""Atomic file operations."""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

async def atomic_write(path: str | Path, content: str | bytes, mode: str = "w") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        if "b" in mode:
            os.write(fd, content if isinstance(content, bytes) else content.encode())
        else:
            os.write(fd, content.encode() if isinstance(content, str) else content)
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        if await asyncio.to_thread(os.path.exists, tmp):
            await asyncio.to_thread(os.unlink, tmp)
        raise
```

#### `core/logger.py`

```py
# core/logger.py
"""Simple structured logging."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

def setup_logging(
    level: str = "INFO", log_file: str | None = "./data/app.log"
) -> logging.Logger:
    """Configure application logging."""
    logger = logging.getLogger("ai_assistant")
    logger.setLevel(getattr(logging, level.upper()))

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

def get_logger(name: str) -> logging.Logger:
    """Get child logger."""
    return logging.getLogger(f"ai_assistant.{name}")
```

#### `core/metrics.py`

```py
"""Async JSONL metrics logging."""

from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar
from pathlib import Path
from typing import Any

class MetricsLogger:
    """Non-blocking JSONL metrics logger using asyncio queue + background task."""

    def __init__(self, path: str = "./data/metrics.jsonl") -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._queue: asyncio.Queue[dict[str, Any] | None] | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start background writer task."""
        if self._task is None or self._task.done():
            self._queue = asyncio.Queue(maxsize=1000)
            self._task = asyncio.create_task(self._worker())

    def _append_line(self, line: str) -> None:
        """Synchronous file append."""
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(line)

    async def _worker(self) -> None:
        """Consume queue and append JSON lines."""
        if self._queue is None:
            return
        while True:
            item = await self._queue.get()
            if item is None:
                break
            try:
                line = json.dumps(item, ensure_ascii=False, default=str) + "\n"
                await asyncio.to_thread(self._append_line, line)
            except Exception:
                pass

    def log(self, data: dict[str, Any]) -> None:
        """Enqueue metric record (non-blocking)."""
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(data)
        except asyncio.QueueFull:
            pass

    async def stop(self) -> None:
        """Signal shutdown and await worker completion."""
        if self._queue is None:
            return
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except Exception:
                pass
        self._queue = None
        self._task = None

_metrics_logger: MetricsLogger | None = None

def get_metrics_logger() -> MetricsLogger:
    """Singleton accessor."""
    global _metrics_logger
    if _metrics_logger is None:
        _metrics_logger = MetricsLogger()
    return _metrics_logger

_request_metrics: ContextVar[dict[str, Any]] = ContextVar("request_metrics", default={})

def record_metric(key: str, value: Any) -> None:
    """Record a metric for the current request context."""
    try:
        metrics = _request_metrics.get()
    except LookupError:
        metrics = {}
    metrics[key] = value
    _request_metrics.set(metrics)

def get_current_metrics() -> dict[str, Any]:
    """Get metrics collected for the current request."""
    try:
        return _request_metrics.get().copy()
    except LookupError:
        return {}
```

#### `core/pipeline.py`

```py
"""RAGPipeline executor — sacred, immutable."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.domain.pipeline import PipelineData

class RAGPipeline:
    """Sequential step runner."""

    def __init__(
        self, steps: list[Callable[[PipelineData], Awaitable[PipelineData]]]
    ) -> None:
        self.steps = steps

    async def run(self, data: PipelineData) -> PipelineData:
        """Execute steps sequentially, passing PipelineData through."""
        for step in self.steps:
            data = await step(data)
        return data
```

#### `core/registry.py`

```py
"""Adapter registry — sacred, immutable."""

from collections.abc import Callable
from typing import Any

_registry: dict[str, dict[str, Callable[..., Any]]] = {}

def register(port: str, name: str) -> Callable[[type], type]:
    """Decorator to register an adapter implementation.

    Args:
        port: Port category (e.g., "llm", "embedder").
        name: Adapter identifier (e.g., "openai_compatible").

    Returns:
        Decorator function.
    """

    def decorator(cls: type) -> type:
        _registry.setdefault(port, {})[name] = cls
        return cls

    return decorator

def create(port: str, name: str, config: Any) -> Any:
    """Instantiate a registered adapter.

    Args:
        port: Port category.
        name: Registered adapter name.
        config: Configuration object passed to adapter __init__.

    Returns:
        Adapter instance.

    Raises:
        ValueError: If port/name not found.
    """
    if port not in _registry or name not in _registry[port]:
        raise ValueError(f"No adapter registered for {port}/{name}")
    return _registry[port][name](config)

def list_adapters(port: str | None = None) -> dict[str, list[str]] | list[str]:
    """List registered adapters."""
    if port is None:
        return {p: list(adapters.keys()) for p, adapters in _registry.items()}
    if port in _registry:
        return list(_registry[port].keys())
    return []
```

#### `core/retry.py`

```py
"""Retry decorator."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# Permanent errors that should NOT be retried
_PERMANENT_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    ImportError,
    ModuleNotFoundError,
)

def with_retry(
    max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0
) -> Callable[[F], F]:
    """Decorator adding exponential backoff retry.

    Does NOT retry exceptions in _PERMANENT_ERRORS.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except _PERMANENT_ERRORS:
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            raise last_exception if last_exception else RuntimeError("Retry exhausted")

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            current_delay = delay
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except _PERMANENT_ERRORS:
                    raise
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        import time

                        time.sleep(current_delay)
                        current_delay *= backoff
            raise last_exception if last_exception else RuntimeError("Retry exhausted")

        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return sync_wrapper  # type: ignore[return-value]

    return decorator
```

#### `core/tool_registry.py`

```py
"""Tool registry — manages available tools for LLM."""

from __future__ import annotations

from core.ports.tools import ITool, IToolRegistry, ToolCall, ToolResult, ToolSpec

class ToolRegistry(IToolRegistry):
    """Concrete tool registry using in-memory dict storage."""

    def __init__(self) -> None:
        self._tools: dict[str, ITool] = {}

    def register(self, tool: ITool) -> None:
        """Add a tool to registry."""
        self._tools[tool.spec.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool from registry."""
        self._tools.pop(name, None)

    def list_tools(self) -> list[ToolSpec]:
        """Return schemas of all registered tools."""
        return [t.spec for t in self._tools.values()]

    def get_tool(self, name: str) -> ITool | None:
        """Get tool by name."""
        return self._tools.get(name)

    async def dispatch(self, call: ToolCall) -> ToolResult:
        """Execute a tool call."""
        tool = self._tools.get(call.tool_name)
        if tool is None:
            return ToolResult(
                call_id=call.call_id,
                output="",
                error=f"Tool '{call.tool_name}' not found",
                is_error=True,
            )
        try:
            return await tool.execute(call.arguments)
        except Exception as e:
            return ToolResult(
                call_id=call.call_id,
                output="",
                error=str(e),
                is_error=True,
            )
```

#### `core/utils.py`

```py
"""Utility functions."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]

try:
    import tokenizers
except ImportError:
    tokenizers = None  # type: ignore[assignment]

# Маппинг: имя модели в config.yaml → папка в data/tokenizers/
_MODEL_TO_TOKENIZER: dict[str, str] = {
    "qwen2.5": "qwen2.5",
    "qwen2.5-7b-instruct": "qwen2.5",
    "qwen2.5-14b-instruct": "qwen2.5",
    "llama-3.2": "llama-3.2",
    "llama-3.2-3b-instruct": "llama-3.2",
    "llama-3.1": "llama-3.2",
    "gemma-3": "gemma-3",
    "gemma-3-4b-it": "gemma-3",
    "gemma-3-27b-it": "gemma-3",
}

def resolve_api_key(config_value: str | None, env_var: str = "OPENAI_API_KEY") -> str:
    """Resolve API key from config or environment."""
    if config_value:
        return config_value
    key = os.getenv(env_var)
    if key:
        return key
    raise ValueError(f"API key not found in config or env var {env_var}")

def _resolve_tokenizer_dir(model: str, local_dir: str) -> Path | None:
    """Map model name to local tokenizer directory."""
    base = Path(local_dir)
    if (base / model / "tokenizer.json").exists():
        return base / model
    family = _MODEL_TO_TOKENIZER.get(model.lower())
    if family and (base / family / "tokenizer.json").exists():
        return base / family
    for key, val in _MODEL_TO_TOKENIZER.items():
        if key in model.lower() and (base / val / "tokenizer.json").exists():
            return base / val
    return None

def get_tokenizer(
    model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> Any | None:
    """Get tokenizer: tiktoken first (OpenAI), then local HF, then None."""
    if tiktoken is not None:
        try:
            return tiktoken.encoding_for_model(model)
        except Exception:
            try:
                return tiktoken.get_encoding("cl100k_base")
            except Exception:
                pass
    if tokenizers is not None:
        tok_dir = _resolve_tokenizer_dir(model, local_dir)
        if tok_dir is not None:
            try:
                return tokenizers.Tokenizer.from_file(str(tok_dir / "tokenizer.json"))
            except Exception:
                pass
    return None

def count_tokens(
    text: str, model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> int:
    """Count tokens. Fallback to char//4 if no tokenizer available."""
    if not text:
        return 0
    enc = get_tokenizer(model, local_dir=local_dir)
    if enc is None:
        return len(text) // 4
    try:
        if hasattr(enc, "encode_batch"):
            return len(enc.encode(text).tokens)
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4

def get_context_limit(llm: Any) -> int | None:
    """Extract context window size from LLM adapter config."""
    cfg = getattr(llm, "config", None)
    if cfg is None:
        return None
    limit = getattr(cfg, "server_context_size", None)
    if limit is None:
        limit = getattr(cfg, "context_size", None)
    if limit is None:
        limit = getattr(cfg, "max_tokens", None)
    if isinstance(limit, (int, float)) and limit > 0:
        return int(limit)
    return None
```

### `core/domain/`

#### `core/domain/__init__.py`

```py
"""Domain models — pure, no external dependencies."""

from .documents import Chunk, ChunkMetadata, Document
from .errors import AdapterError, ConfigurationError, VersionMismatchError
from .messages import (
    AssistantMessage,
    ImagePayload,
    TextPayload,
    UserMessage,
    VoicePayload,
)
from .pipeline import PipelineData

__all__ = [
    "UserMessage",
    "AssistantMessage",
    "TextPayload",
    "ImagePayload",
    "VoicePayload",
    "Document",
    "Chunk",
    "ChunkMetadata",
    "PipelineData",
    "ConfigurationError",
    "AdapterError",
    "VersionMismatchError",
]
```

#### `core/domain/documents.py`

```py
"""Document and chunk models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

@dataclass(frozen=True)
class ChunkMetadata:
    source: str
    index: int
    total_chunks: int
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    custom: dict[str, Any] = field(default_factory=dict)

@dataclass
class Chunk:
    id: str
    text: str
    embedding: list[float] | None = None
    metadata: ChunkMetadata | None = None

@dataclass
class Document:
    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    chunks: list[Chunk] = field(default_factory=list)
```

#### `core/domain/errors.py`

```py
"""Domain exceptions."""

class ConfigurationError(Exception):
    """Invalid configuration."""

    pass

class AdapterError(Exception):
    """Adapter operation failed."""

    pass

class VersionMismatchError(Exception):
    """Index/model version mismatch."""

    pass
```

#### `core/domain/messages.py`

```py
"""Message domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

@dataclass(frozen=True)
class TextPayload:
    content: str

@dataclass(frozen=True)
class ImagePayload:
    url: str | None = None
    base64_data: str | None = None
    mime_type: str = "image/png"

@dataclass(frozen=True)
class VoicePayload:
    audio_base64: str
    mime_type: str = "audio/wav"
    duration_ms: int | None = None

@dataclass(frozen=True)
class UserMessage:
    role: MessageRole = field(default=MessageRole.USER, init=False)
    text: str | None = None
    image: ImagePayload | None = None
    voice: VoicePayload | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.text is None and self.image is None and self.voice is None:
            raise ValueError("UserMessage must contain at least one payload")

@dataclass(frozen=True)
class AssistantMessage:
    role: MessageRole = field(default=MessageRole.ASSISTANT, init=False)
    text: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

#### `core/domain/pipeline.py`

```py
"""Pipeline data carrier."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .documents import Chunk
from .messages import AssistantMessage, UserMessage

@dataclass
class PipelineData:
    query: UserMessage | None = None
    chunks: list[Chunk] = field(default_factory=list)
    context: str = ""
    response: AssistantMessage | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
```

### `core/ports/`

#### `core/ports/__init__.py`

```py
"""Core ports (interfaces). Immutable."""

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

__all__ = [
    "IChunker",
    "IEmbedder",
    "ILLM",
    "IVectorStore",
    "IVoiceRecognizer",
    "IVoiceSynthesizer",
    "IVisionProcessor",
    "ITransport",
    "ILongTermMemory",
    "IChatStorage",
    "ISettingsStorage",
    "IReranker",
    "RerankResult",
]
```

#### `core/ports/chunker.py`

```py
"""Chunker port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.domain.documents import Chunk, Document

class IChunker(ABC):
    """Split documents into chunks."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def chunk(self, document: Document) -> list[Chunk]:
        """Split document into chunks."""
        ...
```

#### `core/ports/embedder.py`

```py
"""Embedder port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

class IEmbedder(ABC):
    """Text embedding interface."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Embedding vector dimension."""
        ...

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed list of texts."""
        ...
```

#### `core/ports/events.py`

```py
"""Event bus port — placeholder for future extension."""

from __future__ import annotations
```

#### `core/ports/llm.py`

```py
"""LLM port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from core.domain.messages import AssistantMessage, UserMessage

class ILLM(ABC):
    """Language model interface."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def complete(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AssistantMessage:
        """Non-streaming completion."""
        ...

    @abstractmethod
    def stream(
        self, messages: list[UserMessage | AssistantMessage], **kwargs: Any
    ) -> AsyncIterator[str]: ...
```

#### `core/ports/memory.py`

```py
"""Long-term memory port — persistent conversation and agent memory.

Extends beyond IChatStorage (which is request-scoped history) to:
- Cross-session facts (user preferences, learned information)
- Episodic memory (summarized past conversations)
- Semantic memory (knowledge graph, embeddings of facts)

This is the foundation for agents that remember you across months.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

@dataclass
class MemoryEntry:
    """Single fact or episode in long-term memory."""

    id: str = ""  # Database-assigned ID
    content: str = ""
    source: str = "conversation"  # "conversation", "explicit", "inferred"
    importance: float = 1.0  # 0.0-1.0, for retention priority
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

class ILongTermMemory(ABC):
    """Persistent memory that survives individual sessions."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def add(self, user_id: str, entry: MemoryEntry) -> None:
        """Store a new memory entry for a user."""
        ...

    @abstractmethod
    async def get(
        self, user_id: str, query: str | None = None, limit: int = 20
    ) -> list[MemoryEntry]:
        """Retrieve relevant memories. If query provided, use semantic search."""
        ...

    @abstractmethod
    async def forget(self, user_id: str, entry_id: str) -> bool:
        """Remove a specific memory entry."""
        ...

    @abstractmethod
    async def consolidate(self, user_id: str) -> None:
        """Compress and summarize old memories (run periodically)."""
        ...
```

#### `core/ports/modality.py`

```py
"""Generic modality processor port — placeholder for future extension."""

from __future__ import annotations
```

#### `core/ports/reranker.py`

```py
"""Reranker port — post-retrieval relevance scoring."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from core.domain.documents import Chunk

@dataclass
class RerankResult:
    """Single rerank result with relevance score."""

    chunk: Chunk
    score: float  # 0.0 to 1.0, higher = more relevant

class IReranker(ABC):
    """Re-rank retrieved chunks by relevance to query.

    Used after vector store retrieval to filter out false positives
    and improve context quality for generation.
    """

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def rerank(
        self, query: str, chunks: list[Chunk], top_k: int | None = None
    ) -> list[RerankResult]:
        """Rerank chunks by relevance to query.

        Args:
            query: Original user query.
            chunks: Chunks from vector store retrieval.
            top_k: Max results to return. None = return all scored.

        Returns:
            List of RerankResult sorted by score descending.
        """
        ...
```

#### `core/ports/storage.py`

```py
"""Storage ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

class IChatStorage(ABC):
    """Chat history persistence."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def save_message(
        self, conversation_id: str, message: dict[str, Any]
    ) -> None: ...

    @abstractmethod
    async def get_history(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]: ...

class ISettingsStorage(ABC):
    """Settings persistence."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def get(self, key: str, default: Any = None) -> Any: ...

    @abstractmethod
    async def set(self, key: str, value: Any) -> None: ...
```

#### `core/ports/tools.py`

```py
"""Tool port — external capabilities (calculator, search, APIs, code execution).

This enables the LLM to call external tools, similar to OpenAI function calling
but framework-agnostic. ToolRegistry manages available tools; ITool is the
interface for individual tool implementations.

Future directions:
- MCP (Model Context Protocol) adapter
- Local code execution sandbox
- Hardware control (robotics, IoT)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class ToolSpec:
    """Schema describing a tool for LLM consumption.

    Mirrors OpenAI function schema but framework-agnostic.
    """

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema object
    required: list[str] = field(default_factory=list)

@dataclass
class ToolCall:
    """A request from LLM to invoke a tool."""

    tool_name: str
    arguments: dict[str, Any]
    call_id: str = ""  # For matching response to request

@dataclass
class ToolResult:
    """Result of a tool invocation."""

    call_id: str
    output: str | dict[str, Any]
    error: str | None = None
    is_error: bool = False

class ITool(ABC):
    """Single tool implementation."""

    @property
    @abstractmethod
    def spec(self) -> ToolSpec:
        """Return the schema for this tool."""
        ...

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Execute the tool with given arguments."""
        ...

class IToolRegistry(ABC):
    """Pure interface for tool registry — implementations provide storage strategy."""

    @abstractmethod
    def register(self, tool: ITool) -> None:
        """Add a tool to registry."""
        ...

    @abstractmethod
    def unregister(self, name: str) -> None:
        """Remove a tool from registry."""
        ...

    @abstractmethod
    def list_tools(self) -> list[ToolSpec]:
        """Return schemas of all registered tools."""
        ...

    @abstractmethod
    def get_tool(self, name: str) -> ITool | None:
        """Get tool by name."""
        ...

    @abstractmethod
    async def dispatch(self, call: ToolCall) -> ToolResult:
        """Execute a tool call by dispatching to the registered tool."""
        ...
```

#### `core/ports/transport.py`

```py
"""Transport port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

class ITransport(ABC):
    """HTTP/WS server abstraction."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...
```

#### `core/ports/vector_store.py`

```py
"""Vector store port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from core.domain.documents import Chunk

class IVectorStore(ABC):
    """Vector storage with FAISS-like semantics."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def add(self, chunks: list[Chunk], namespace: str = "default") -> None:
        """Add chunks with embeddings to a namespace."""
        ...

    @abstractmethod
    async def search(
        self, query_embedding: list[float], top_k: int = 5, namespace: str = "default"
    ) -> list[Chunk]:
        """Search by embedding in a namespace."""
        ...

    @abstractmethod
    async def delete(self, chunk_ids: list[str], namespace: str = "default") -> None:
        """Delete chunks by ID from a namespace."""
        ...

    @abstractmethod
    async def save(self, path: str, namespace: str = "default") -> None:
        """Persist namespace index + metadata."""
        ...

    @abstractmethod
    async def load(self, path: str, namespace: str = "default") -> None:
        """Load namespace index + metadata. Validate version."""
        ...

    @abstractmethod
    async def list_by_filter(
        self, filter: dict[str, Any], namespace: str = "default"
    ) -> list[tuple[str, dict[str, Any]]]:
        """Return (chunk_id, metadata) matching ALL filter key-values in namespace."""
        ...

    @abstractmethod
    async def list_namespaces(self, path: str) -> list[str]:
        """Return list of available namespace names."""
        ...
```

#### `core/ports/vision.py`

```py
"""Vision port."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

class IVisionProcessor(ABC):
    """Image understanding."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def describe(self, image_base64: str, prompt: str | None = None) -> str: ...
```

#### `core/ports/voice.py`

```py
"""Voice ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

class IVoiceRecognizer(ABC):
    """Speech-to-text."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def transcribe(
        self, audio_bytes: bytes, mime_type: str = "audio/wav"
    ) -> str: ...

class IVoiceSynthesizer(ABC):
    """Text-to-speech."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> bytes: ...
```

### `core/prompts/`

#### `core/prompts/__init__.py`

```py
"""Versioned prompt loader."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

def get_prompt(name: str, version: str = "v1", **kwargs: str) -> str:
    """Load and render a Jinja2 prompt template.

    Args:
        name: Template filename without .j2 extension.
        version: Prompt version directory (e.g., "v1", "v2").
        **kwargs: Template variables.

    Returns:
        Rendered prompt string.
    """
    base = Path(__file__).parent / version
    if not base.exists():
        raise ValueError(f"Prompt version directory not found: {base}")
    env = Environment(
        loader=FileSystemLoader(str(base)),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template(f"{name}.j2").render(**kwargs)
```

### `core/prompts/v1/`

#### `core/prompts/v1/rag_creative.j2`

```j2
You are a creative AI assistant. Use the retrieved context as inspiration.

Context:
{% for chunk in chunks %}
[{{ loop.index }}] {{ chunk.text }}
{% endfor %}

Question: {{ query }}

Provide an imaginative, engaging response. Feel free to expand beyond the context when appropriate.
```

#### `core/prompts/v1/rag_default.j2`

```j2
You are a helpful AI assistant. Use the following retrieved context to answer the user's question.

Context:
{% for chunk in chunks %}
[{{ loop.index }}] {{ chunk.text }}
{% endfor %}

Question: {{ query }}

Answer concisely and accurately. If the context doesn't contain the answer, say "I don't have enough information."
```

#### `core/prompts/v1/rag_strict.j2`

```j2
You are a precise AI assistant. Answer STRICTLY based on the provided context.
Use citations [1], [2], etc. to reference specific chunks.

Rules:
1. If the answer is NOT in the context, say exactly: "У меня недостаточно информации."
2. NEVER invent facts not present in the context.
3. Use citations [N] after each factual claim.
4. Be concise and accurate.

Context:
{% for chunk in chunks %}
[{{ loop.index }}] {{ chunk.text }}
{% endfor %}

Question: {{ query }}

Answer (with citations):
```

#### `core/prompts/v1/summarize.j2`

```j2
Summarize the following text in {{ max_sentences }} sentences:

{{ text }}

Summary:
```

#### `core/prompts/v1/voice_transcribe.j2`

```j2
The following is a voice transcription. Clean up any obvious errors and format it nicely:

"{{ transcript }}"

Cleaned text:
```

### `features/`

#### `features/__init__.py`

```py
"""Features package — each feature is isolated."""
```

### `features/chat/`

#### `features/chat/__init__.py`

```py
"""Chat feature — universal chat router."""
```

#### `features/chat/handlers.py`

```py
# features/chat/handlers.py
"""Chat feature HTTP handlers."""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import AppState, get_state
from api.security import require_api_key
from features.chat.manager import ChatManager
from features.chat.schemas import (
    ChatRequest,
    ChatResponse,
    OAIChatCompletion,
    OAIChatCompletionRequest,
    OAIChatMessage,
    OAIChoice,
    OAIDeltaChunk,
    OAIModel,
    OAIModelList,
)

router = APIRouter(tags=["chat"])

def _get_chat_manager(state: AppState = Depends(get_state)) -> ChatManager:
    return ChatManager(
        llm=state.llm,
        voice_recognizer=state.voice_recognizer,
        vision=state.vision,
        storage=getattr(state, "storage", None),
        history_limit=state.config.chat.history_limit,
        max_context_tokens=getattr(state.config.chat, "max_context_tokens", None),
        tokenizer_model=getattr(state.config.chat, "tokenizer_model", "gpt-4o"),
        tool_registry=getattr(state, "tool_registry", None),
        embedder=getattr(state, "embedder", None),
        vector_store=getattr(state, "vector_store", None),
        reranker=getattr(state, "reranker", None),
    )

# --- Legacy endpoints (backward compatible) ---

@router.post(
    "/chat", response_model=ChatResponse, dependencies=[Depends(require_api_key)]
)
async def chat(
    req: ChatRequest,
    manager: ChatManager = Depends(_get_chat_manager),
) -> ChatResponse:
    conv_id = req.conversation_id or str(uuid.uuid4())
    try:
        response = await manager.chat(
            message=req.message,
            conversation_id=conv_id,
            image_url=req.image_url,
            image_base64=req.image_base64,
            voice_base64=req.voice_base64,
            metadata=req.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return ChatResponse(
        message=response.text or "",
        conversation_id=conv_id,
        metadata=response.metadata,
    )

@router.post(
    "/chat/stream", response_model=None, dependencies=[Depends(require_api_key)]
)
async def chat_stream(
    req: ChatRequest,
    manager: ChatManager = Depends(_get_chat_manager),
) -> StreamingResponse:
    conv_id = req.conversation_id or str(uuid.uuid4())

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for chunk in manager.stream_chat(
                message=req.message,
                conversation_id=conv_id,
                image_url=req.image_url,
                image_base64=req.image_base64,
                voice_base64=req.voice_base64,
                metadata=req.metadata,
            ):
                yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: ERROR: {e}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# --- OpenAI-compatible endpoints ---

@router.get("/v1/models", response_model=OAIModelList)
async def list_models(state: AppState = Depends(get_state)) -> OAIModelList:
    models = getattr(state.config.llm, "available_models", [])
    if not models:
        models = [state.config.llm.model]
    return OAIModelList(data=[OAIModel(id=m) for m in models])

@router.post(
    "/v1/chat/completions", response_model=None, dependencies=[Depends(require_api_key)]
)
async def openai_chat_completions(
    req: OAIChatCompletionRequest,
    manager: ChatManager = Depends(_get_chat_manager),
) -> OAIChatCompletion | StreamingResponse:
    # Extract last user message as our "message"
    last_user_msg = ""
    for m in reversed(req.messages):
        if m.role == "user" and m.content:
            last_user_msg = m.content
            break

    conv_id = str(uuid.uuid4())

    if req.stream:

        async def event_generator() -> AsyncIterator[str]:
            try:
                async for chunk in manager.stream_chat(
                    message=last_user_msg,
                    conversation_id=conv_id,
                ):
                    delta = OAIDeltaChunk(
                        choices=[
                            OAIChoice(
                                index=0,
                                delta=OAIChatMessage(role="assistant", content=chunk),
                                finish_reason=None,
                            )
                        ]
                    )
                    yield f"data: {delta.model_dump_json()}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as e:
                yield f'data: {{"error": "{e}"}}\n\n'

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    try:
        response = await manager.chat(
            message=last_user_msg,
            conversation_id=conv_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return OAIChatCompletion(
        created=int(time.time()),
        choices=[
            OAIChoice(
                index=0,
                message=OAIChatMessage(role="assistant", content=response.text or ""),
                finish_reason="stop",
            )
        ],
    )
```

#### `features/chat/manager.py`

```py
"""Chat manager — routes Text/Voice/Image to LLM."""

from __future__ import annotations

import base64
import json
import re
from collections.abc import AsyncIterator
from typing import Any

from core.domain.errors import AdapterError
from core.domain.messages import AssistantMessage, ImagePayload, UserMessage
from core.domain.pipeline import PipelineData
from core.logger import get_logger
from core.metrics import record_metric
from core.ports.tools import ToolCall
from core.prompts import get_prompt
from core.utils import count_tokens, get_context_limit
from pipeline.steps import build_context, embed_query, rerank, retrieve

logger = get_logger("chat")

_NS_MAP = {"p": "personal", "w": "work", "o": "other"}
_PREFIX_RE = re.compile(r"^\[(p|w|o)\]\s*(.*)", re.IGNORECASE)

class ChatManager:
    """Universal chat router."""

    def __init__(
        self,
        llm: Any,
        voice_recognizer: Any | None = None,
        vision: Any | None = None,
        storage: Any | None = None,
        history_limit: int = 10,
        max_context_tokens: int | None = None,
        tokenizer_model: str = "gpt-4o",
        tool_registry: Any | None = None,
        embedder: Any | None = None,
        vector_store: Any | None = None,
        reranker: Any | None = None,
    ) -> None:
        self.llm = llm
        self.voice_recognizer = voice_recognizer
        self.vision = vision
        self.storage = storage
        self.history_limit = history_limit
        self.max_context_tokens = max_context_tokens
        self.tokenizer_model = tokenizer_model
        self.tool_registry = tool_registry
        self.embedder = embedder
        self.vector_store = vector_store
        self.reranker = reranker

    def _count_tokens(self, text: str) -> int:
        return count_tokens(text, self.tokenizer_model)

    def _trim_history(
        self,
        history: list[dict[str, Any]],
        user_msg: UserMessage,
    ) -> list[dict[str, Any]]:
        """Trim oldest messages so system + history + user_msg fit token budget.

        Keeps the most recent messages that fit within the token budget.
        """
        budget = self.max_context_tokens
        if isinstance(budget, (int, float)) and budget > 0:
            pass
        else:
            budget = get_context_limit(self.llm)
        if not isinstance(budget, (int, float)) or budget <= 0:
            # No tokenizer available — simple count-based fallback
            return (
                history[-self.history_limit :]
                if len(history) > self.history_limit
                else history
            )

        user_tokens = self._count_tokens(user_msg.text or "")
        system_msg = getattr(self.llm, "system_message", None)
        system_tokens = self._count_tokens(str(system_msg) if system_msg else "")
        overhead = 50
        reserved = user_tokens + system_tokens + overhead

        available = budget - reserved
        if available <= 0:
            return []

        # Walk from newest to oldest, accumulating until budget exhausted
        total = 0
        keep: list[dict[str, Any]] = []
        for h in reversed(history):
            text = h.get("content", "")
            tokens = self._count_tokens(text)
            if total + tokens > available:
                break
            total += tokens
            keep.append(h)

        # Reverse to restore chronological order (oldest first)
        keep.reverse()
        return keep

    async def _maybe_rag(self, message: str) -> tuple[str, int]:
        if not self.embedder or not self.vector_store:
            return message, 0

        m = _PREFIX_RE.match(message)
        if not m:
            return message, 0  # Без префикса → RAG НЕ запускается

        ns_short = m.group(1).lower()
        query_text = m.group(2)
        namespace = _NS_MAP.get(ns_short, "default")

        data = PipelineData(
            query=UserMessage(text=query_text),
            metadata={
                "top_k": 5,
                "prompt_name": "rag_strict",
                "prompt_version": "v1",
                "namespace": namespace,
                "relevance_threshold": 0.3,
            },
        )

        data = await embed_query(data, embedder=self.embedder)
        if not data.errors:
            data = await retrieve(data, vector_store=self.vector_store)
        if self.reranker and not data.errors:
            data = await rerank(data, reranker=self.reranker)
        data = await build_context(data)

        if not data.context:
            logger.debug(f"RAG skipped: no relevant chunks in {namespace}")
            return query_text, 0

        chunks_for_prompt = [{"text": c.text or " "} for c in data.chunks]
        rag_prompt = get_prompt(
            "rag_strict",
            version="v1",
            query=query_text,
            chunks=json.dumps(chunks_for_prompt, ensure_ascii=False),
            context=data.context,
        )
        return rag_prompt, len(data.chunks)

    async def chat(
        self,
        message: str,
        conversation_id: str,
        image_url: str | None = None,
        image_base64: str | None = None,
        voice_base64: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssistantMessage:
        """Process a chat message (text, image, or voice)."""
        meta = metadata or {}
        logger.info(f"Chat request: conv={conversation_id}, msg_len={len(message)}")

        if voice_base64:
            if self.voice_recognizer is None:
                raise AdapterError("Voice recognizer not configured")
            audio_bytes = base64.b64decode(voice_base64)
            transcribed = await self.voice_recognizer.transcribe(audio_bytes)
            message = transcribed

        image_payload = None
        if image_url:
            image_payload = ImagePayload(url=image_url)
        elif image_base64:
            image_payload = ImagePayload(base64_data=image_base64)

        # --- RAG injection ---
        message, rag_chunks = await self._maybe_rag(message)
        record_metric("rag_chunks", rag_chunks)
        # ---------------------

        user_msg = UserMessage(
            text=message,
            image=image_payload,
            metadata=meta,
        )

        messages: list[Any] = [user_msg]
        input_tokens = self._count_tokens(message or "")

        history: list[dict[str, Any]] = []
        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id, limit=self.history_limit
                )
                try:
                    history = self._trim_history(history, user_msg)
                except Exception as e:
                    logger.warning(
                        "Token-based trim failed (%s), falling back to count-based", e
                    )
                    history = (
                        history[: -self.history_limit]
                        if len(history) > self.history_limit
                        else history
                    )
                for h in history:
                    role = h.get("role", "")
                    content = h.get("content", "")
                    if role == "user":
                        messages.insert(-1, UserMessage(text=content))
                    elif role == "assistant":
                        messages.insert(-1, AssistantMessage(text=content))
                    input_tokens += self._count_tokens(content)
            except Exception:
                pass

        response: AssistantMessage | None = None
        for _ in range(3):
            try:
                response = await self.llm.complete(messages)
            except Exception as e:
                logger.error(f"Chat failed: conv={conversation_id}, error={e}")
                raise

            if not response.tool_calls:
                break

            messages.append(response)

            if self.tool_registry:
                for call in response.tool_calls:
                    try:
                        func = call.get("function", {})
                        tool_name = func.get("name", "")
                        arguments = json.loads(func.get("arguments", "{}"))
                        tc = ToolCall(
                            tool_name=tool_name,
                            arguments=arguments,
                            call_id=call.get("id", ""),
                        )
                        result = await self.tool_registry.execute(tc)
                        content = (
                            result.output
                            if not result.is_error
                            else f"Error: {result.error}"
                        )
                    except Exception as e:
                        content = f"Error: {e}"

                    messages.append(
                        {
                            "role": "tool",
                            "content": str(content),
                            "tool_call_id": call.get("id", ""),
                        }
                    )
            else:
                break

        if response is None:
            response = AssistantMessage(text="Error: no response generated")

        output_tokens = self._count_tokens(response.text or "")
        tools_used = sum(
            len(m.tool_calls)
            for m in messages
            if isinstance(m, AssistantMessage) and m.tool_calls
        )

        record_metric("input_tokens", input_tokens)
        record_metric("output_tokens", output_tokens)
        record_metric("tools_used", tools_used)

        logger.info(
            f"Chat response: conv={conversation_id}, "
            f"resp_len={len(response.text or '')}"
        )

        if self.storage:
            try:
                await self.storage.save_message(
                    conversation_id,
                    {"role": "user", "content": message, "metadata": meta},
                )
                await self.storage.save_message(
                    conversation_id,
                    {
                        "role": "assistant",
                        "content": response.text or "",
                        "metadata": {},
                    },
                )
            except Exception:
                pass

        return response

    async def stream_chat(
        self,
        message: str,
        conversation_id: str,
        image_url: str | None = None,
        image_base64: str | None = None,
        voice_base64: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream chat response."""
        meta = metadata or {}

        if voice_base64:
            if self.voice_recognizer is None:
                raise AdapterError("Voice recognizer not configured")
            audio_bytes = base64.b64decode(voice_base64)
            transcribed = await self.voice_recognizer.transcribe(audio_bytes)
            message = transcribed

        image_payload = None
        if image_url:
            image_payload = ImagePayload(url=image_url)
        elif image_base64:
            image_payload = ImagePayload(base64_data=image_base64)

        # --- RAG injection ---
        message, rag_chunks = await self._maybe_rag(message)
        record_metric("rag_chunks", rag_chunks)
        # ---------------------

        user_msg = UserMessage(
            text=message,
            image=image_payload,
            metadata=meta,
        )

        messages: list[Any] = [user_msg]
        input_tokens = self._count_tokens(message or "")

        if self.storage:
            try:
                history = await self.storage.get_history(
                    conversation_id, limit=self.history_limit
                )
                try:
                    history = self._trim_history(history, user_msg)
                except Exception:
                    history = (
                        history[-self.history_limit :]
                        if len(history) > self.history_limit
                        else history
                    )
                for h in history:
                    role = h.get("role", "")
                    content = h.get("content", "")
                    if role == "user":
                        messages.insert(-1, UserMessage(text=content))
                    elif role == "assistant":
                        messages.insert(-1, AssistantMessage(text=content))
                    input_tokens += self._count_tokens(content)
            except Exception:
                pass

        output_text = ""
        async for chunk in self.llm.stream(messages):
            output_text += chunk
            yield chunk

        record_metric("input_tokens", input_tokens)
        record_metric("output_tokens", self._count_tokens(output_text))
        record_metric("tools_used", 0)
```

#### `features/chat/schemas.py`

```py
# features/chat/schemas.py
"""Chat feature Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

class ChatRequest(BaseModel):
    """Universal chat request."""

    message: str
    conversation_id: str | None = Field(
        default=None, description="Thread ID for continuity"
    )
    image_url: str | None = None
    image_base64: str | None = None
    voice_base64: str | None = None
    stream: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

class ChatResponse(BaseModel):
    """Chat response."""

    message: str
    conversation_id: str
    role: str = "assistant"
    metadata: dict[str, Any] = Field(default_factory=dict)

class ChatStreamChunk(BaseModel):
    """SSE stream chunk."""

    delta: str
    conversation_id: str
    finished: bool = False

# --- OpenAI-compatible schemas ---

class OAIChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    content: str | None = None
    name: str | None = None

class OAIChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    model: str | None = None
    messages: list[OAIChatMessage]
    stream: bool = False
    max_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: list[str] | str | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    user: str | None = None

class OAIChoice(BaseModel):
    index: int = 0
    message: OAIChatMessage | None = None
    delta: OAIChatMessage | None = None
    finish_reason: str | None = None

class OAIChatCompletion(BaseModel):
    id: str = "chatcmpl-local"
    object: str = "chat.completion"
    created: int = 0
    model: str = "local"
    choices: list[OAIChoice]

class OAIDeltaChunk(BaseModel):
    id: str = "chatcmpl-local"
    object: str = "chat.completion.chunk"
    created: int = 0
    model: str = "local"
    choices: list[OAIChoice]

class OAIModel(BaseModel):
    id: str
    object: str = "model"
    created: int = 1677610602
    owned_by: str = "local"

class OAIModelList(BaseModel):
    object: str = "list"
    data: list[OAIModel]
```

### `features/image_analysis/`

#### `features/image_analysis/__init__.py`

```py
"""Image analysis feature."""
```

#### `features/image_analysis/handlers.py`

```py
"""Image analysis feature handlers."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import AppState, get_state
from features.image_analysis.manager import ImageAnalysisManager
from features.image_analysis.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter(prefix="/image", tags=["image"])

def _get_manager(state: AppState = Depends(get_state)) -> ImageAnalysisManager:
    return ImageAnalysisManager(
        vision=state.vision,
        llm=state.llm,
    )

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_image(
    req: AnalyzeRequest,
    manager: ImageAnalysisManager = Depends(_get_manager),
) -> AnalyzeResponse:
    if not req.image_base64 and not req.image_url:
        raise HTTPException(status_code=400, detail="Provide image_base64 or image_url")
    try:
        result = await manager.analyze(
            image_base64=req.image_base64,
            image_url=req.image_url,
            prompt=req.prompt,
        )
        source = "llm" if manager.use_llm_vision else "vision"
        return AnalyzeResponse(
            description=result.text or "",
            source=source,
            metadata=req.metadata,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

#### `features/image_analysis/manager.py`

```py
"""Image analysis manager."""

from __future__ import annotations

from typing import Any

from core.domain.messages import AssistantMessage, ImagePayload, UserMessage

class ImageAnalysisManager:
    """Routes image analysis to vision processor or multimodal LLM."""

    def __init__(
        self,
        vision: Any | None = None,
        llm: Any | None = None,
    ) -> None:
        self.vision = vision
        self.llm = llm

    @property
    def use_llm_vision(self) -> bool:
        return self.vision is None and self.llm is not None

    async def analyze(
        self,
        image_base64: str | None = None,
        image_url: str | None = None,
        prompt: str = "Describe this image.",
    ) -> AssistantMessage:
        """Analyze image via vision processor with LLM fallback."""
        image = None
        if image_base64:
            image = ImagePayload(base64_data=image_base64, mime_type="image/png")
        elif image_url:
            image = ImagePayload(url=image_url)

        if self.vision:
            img_input = image_base64 or image_url or ""
            result = await self.vision.describe(img_input, prompt=prompt)
            if result and result.strip():
                return AssistantMessage(text=result)

        if self.llm and image:
            user_msg = UserMessage(text=prompt, image=image)
            return await self.llm.complete([user_msg])

        return AssistantMessage(
            text=(
                "Vision analysis not available. "
                "Enable vision in config or use a multimodal LLM."
            )
        )
```

#### `features/image_analysis/schemas.py`

```py
"""Image analysis schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

class AnalyzeRequest(BaseModel):
    image_base64: str | None = None
    image_url: str | None = None
    prompt: str = "Describe this image."
    metadata: dict[str, Any] = Field(default_factory=dict)

class AnalyzeResponse(BaseModel):
    description: str
    source: str = "vision"
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### `features/rag/`

#### `features/rag/__init__.py`

```py
"""RAG feature — text retrieval-augmented generation."""
```

#### `features/rag/handlers.py`

```py
"""RAG feature HTTP handlers with namespace and reranker support."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.deps import AppState, get_state
from api.security import require_api_key
from features.rag.manager import IndexingManager, RAGManager
from features.rag.schemas import (
    DeleteRequest,
    DeleteResponse,
    HealthResponse,
    IndexRequest,
    IndexResponse,
    NamespaceListResponse,
    QueryRequest,
    QueryResponse,
)

router = APIRouter(prefix="/rag", tags=["rag"])

DOCUMENTS_ROOT = Path("documents")

def _get_indexing_manager(state: AppState = Depends(get_state)) -> IndexingManager:
    return IndexingManager(
        chunker=state.chunker,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )

def _get_rag_manager(state: AppState = Depends(get_state)) -> RAGManager:
    if state.pipeline is None:
        raise HTTPException(status_code=500, detail="RAG pipeline not initialized")
    return RAGManager(
        pipeline=state.pipeline,
        llm=state.llm,
        vector_store=state.vector_store,
        embedder=state.embedder,
        reranker=state.reranker,
    )

@router.post(
    "/index", response_model=IndexResponse, dependencies=[Depends(require_api_key)]
)
async def index_documents(
    req: IndexRequest,
    manager: IndexingManager = Depends(_get_indexing_manager),
    state: AppState = Depends(get_state),
) -> IndexResponse:
    namespace = req.namespace or state.config.rag.default_namespace
    result = await manager.index_documents(req.documents, namespace=namespace)
    # Auto-save after indexing
    index_path = getattr(state.config.vector_store, "index_path", None)
    if index_path:
        try:
            await manager.save_index(index_path, namespace=namespace)
        except Exception as e:
            result["errors"].append(f"Auto-save failed: {e}")
    return IndexResponse(**result, namespace=namespace)

@router.post(
    "/query", response_model=QueryResponse, dependencies=[Depends(require_api_key)]
)
async def query_rag(
    req: QueryRequest,
    manager: RAGManager = Depends(_get_rag_manager),
    state: AppState = Depends(get_state),
) -> QueryResponse:
    cfg = state.config.rag
    # Use strict prompt by default
    prompt_name = req.prompt_name or cfg.prompt_name or "rag_strict"

    # Get relevance threshold from config or request
    relevance_threshold = getattr(cfg, "relevance_threshold", 0.3)

    result = await manager.query(
        query_text=req.query,
        top_k=req.top_k or cfg.top_k,
        prompt_name=prompt_name,
        prompt_version=req.prompt_version or cfg.prompt_version,
        namespace=req.namespace or cfg.default_namespace,
        relevance_threshold=relevance_threshold,
    )
    return QueryResponse(**result)

@router.post(
    "/delete", response_model=DeleteResponse, dependencies=[Depends(require_api_key)]
)
async def delete_chunks(
    req: DeleteRequest,
    state: AppState = Depends(get_state),
) -> DeleteResponse:
    namespace = req.namespace or state.config.rag.default_namespace
    errors: list[str] = []
    deleted = 0
    try:
        if req.chunk_ids:
            await state.vector_store.delete(req.chunk_ids, namespace=namespace)
            deleted += len(req.chunk_ids)
        elif req.document_ids:
            all_chunks = await state.vector_store.list_by_filter(
                {}, namespace=namespace
            )
            to_delete = []
            for chunk_id, meta in all_chunks:
                if meta.get("source") in req.document_ids:
                    to_delete.append(chunk_id)
            if to_delete:
                await state.vector_store.delete(to_delete, namespace=namespace)
                deleted += len(to_delete)
    except Exception as e:
        errors.append(str(e))
    return DeleteResponse(deleted_chunks=deleted, errors=errors)

@router.get("/health", response_model=HealthResponse)
async def rag_health(
    manager: RAGManager = Depends(_get_rag_manager),
    state: AppState = Depends(get_state),
) -> HealthResponse:
    health = await manager.health()
    return HealthResponse(
        status=health["status"],
        index_loaded=health["index_loaded"],
        chunk_count=health["chunk_count"],
        embedder_dim=getattr(state.embedder, "dimension", None),
    )

@router.get("/namespaces", response_model=NamespaceListResponse)
async def list_namespaces(
    state: AppState = Depends(get_state),
) -> NamespaceListResponse:
    index_path = getattr(state.config.vector_store, "index_path", None)
    namespaces: list[str] = []
    if index_path:
        try:
            namespaces = await state.vector_store.list_namespaces(index_path)
        except Exception:
            pass
    if not namespaces:
        namespaces = ["default"]
    return NamespaceListResponse(namespaces=namespaces)

@router.post("/save-chat", response_model=None, dependencies=[Depends(require_api_key)])
async def save_chat(
    req: dict[str, Any],
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Save chat content to documents folder and index it."""
    namespace = req.get("namespace", "personal")
    filename = req.get("filename", "chat.md")
    content = req.get("content", "")

    # Validate namespace
    if namespace not in ("personal", "work", "other"):
        raise HTTPException(
            status_code=400, detail="Invalid namespace. Use: personal, work, other"
        )

    # Save to documents folder
    folder = DOCUMENTS_ROOT / namespace
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / filename

    try:
        file_path.write_text(content, encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}")

    # Index the saved chat
    try:
        manager = IndexingManager(
            chunker=state.chunker,
            embedder=state.embedder,
            vector_store=state.vector_store,
        )
        result = await manager.index_documents(
            [
                {
                    "id": file_path.stem,
                    "content": content,
                    "metadata": {
                        "source": str(file_path),
                        "folder": namespace,
                        "type": "chat_export",
                    },
                }
            ],
            namespace=namespace,
        )

        # Auto-save index
        index_path = getattr(state.config.vector_store, "index_path", None)
        if index_path:
            await manager.save_index(index_path, namespace=namespace)

        return {
            "saved": True,
            "path": str(file_path),
            "namespace": namespace,
            "indexed_count": result.get("indexed_count", 0),
            "chunk_count": result.get("chunk_count", 0),
        }
    except Exception as e:
        # File saved but indexing failed
        return {
            "saved": True,
            "path": str(file_path),
            "namespace": namespace,
            "indexed": False,
            "error": str(e),
        }

@router.post("/reindex", response_model=None, dependencies=[Depends(require_api_key)])
async def reindex_documents(
    req: dict[str, Any],
    state: AppState = Depends(get_state),
) -> dict[str, Any]:
    """Reindex documents from folders. Called from UI button."""
    folder = req.get("folder")
    clear = req.get("clear", False)

    # Run index_documents.py script
    script_path = Path(__file__).parent.parent.parent / "scripts" / "index_documents.py"
    if not script_path.exists():
        raise HTTPException(status_code=500, detail="index_documents.py not found")

    cmd = [sys.executable, str(script_path)]
    if folder:
        cmd.extend(["--folder", folder])
    if clear:
        cmd.append("--clear")

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=300
        )
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        # Parse output
        output = stdout
        errors: list[str] = []
        results: dict[str, Any] = {}

        if proc.returncode != 0:
            errors.append(stderr or "Unknown error")

        # Parse simple output format: "[namespace] X docs, Y chunks"
        for line in output.split("\n"):
            if "Done:" in line:
                parts = line.strip().split()
                if len(parts) >= 4:
                    ns = parts[0].strip("[]")
                    try:
                        idx = parts.index("docs,")
                        docs = int(parts[idx - 1])
                        chunks = int(parts[idx + 1])
                        results[ns] = {"indexed": docs, "chunks": chunks}
                    except (ValueError, IndexError):
                        pass

        return {
            "success": proc.returncode == 0,
            "results": results,
            "errors": errors,
            "output": output,
        }

    except TimeoutError:
        raise HTTPException(status_code=504, detail="Indexing timeout")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")
```

#### `features/rag/manager.py`

```py
"""RAG managers — indexing and querying with namespace and reranker support."""

from __future__ import annotations

import uuid
from typing import Any

from core.domain.documents import Chunk, Document
from core.domain.messages import UserMessage
from core.domain.pipeline import PipelineData
from core.pipeline import RAGPipeline

NO_INFO_PHRASES = [
    "не достаточно",
    "недостаточно",
    "не имею",
    "не знаю",
    "not enough",
    "don't have",
    "no information",
    "не найдено",
    "not found",
    "i don't have",
    "i do not have",
    "don't know",
    "do not know",
    "у меня недостаточно",
    "у меня нет",
]

class IndexingManager:
    """Handles document ingestion: chunk + embed + store per namespace."""

    def __init__(
        self,
        chunker: Any,
        embedder: Any,
        vector_store: Any,
    ) -> None:
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store

    async def index_documents(
        self, documents: list[dict[str, Any]], namespace: str = "default"
    ) -> dict[str, Any]:
        all_chunks: list[Chunk] = []
        errors: list[str] = []
        indexed = 0

        for raw in documents:
            doc_id = raw.get("id") or str(uuid.uuid4())
            doc = Document(
                id=doc_id,
                content=raw.get("content", ""),
                metadata=raw.get("metadata", {}),
            )
            if not doc.content.strip():
                errors.append(f"Document {doc_id} has empty content")
                continue

            try:
                chunks = await self.chunker.chunk(doc)
            except Exception as e:
                errors.append(f"Chunking failed for {doc_id}: {e}")
                continue

            if not chunks:
                errors.append(f"No chunks produced for {doc_id}")
                continue

            texts = [c.text for c in chunks if c.text]
            try:
                embeddings = await self.embedder.embed(texts)
            except Exception as e:
                errors.append(f"Embedding failed for {doc_id}: {e}")
                continue

            embedded_chunks = []
            for i, chunk in enumerate(chunks):
                if i < len(embeddings):
                    embedded_chunks.append(
                        Chunk(
                            id=chunk.id,
                            text=chunk.text,
                            embedding=embeddings[i],
                            metadata=chunk.metadata,
                        )
                    )

            all_chunks.extend(embedded_chunks)
            indexed += 1

        if all_chunks:
            try:
                await self.vector_store.add(all_chunks, namespace=namespace)
            except Exception as e:
                errors.append(f"Vector store add failed: {e}")

        return {
            "indexed_count": indexed,
            "chunk_count": len(all_chunks),
            "errors": errors,
        }

    async def save_index(self, path: str, namespace: str = "default") -> None:
        await self.vector_store.save(path, namespace=namespace)

class RAGManager:
    """Handles RAG queries using the pipeline per namespace."""

    def __init__(
        self,
        pipeline: RAGPipeline,
        llm: Any,
        vector_store: Any,
        embedder: Any | None = None,
        reranker: Any | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.llm = llm
        self.vector_store = vector_store
        self.embedder = embedder
        self.reranker = reranker

    def _is_no_info_answer(self, answer: str | None) -> bool:
        """Check if answer indicates insufficient information."""
        if answer is None:
            return True
        answer_lower = answer.lower()
        return any(phrase in answer_lower for phrase in NO_INFO_PHRASES)

    async def query(
        self,
        query_text: str,
        top_k: int,
        prompt_name: str,
        prompt_version: str,
        namespace: str | None,
        relevance_threshold: float = 0.3,
    ) -> dict[str, Any]:
        if not namespace:
            namespace = "default"

        # Single namespace query — use pipeline
        data = PipelineData(
            query=UserMessage(text=query_text),
            metadata={
                "top_k": top_k,
                "prompt_name": prompt_name,
                "prompt_version": prompt_version,
                "namespace": namespace,
                "relevance_threshold": relevance_threshold,
            },
        )
        result = await self.pipeline.run(data)

        answer = result.response.text if result.response else ""

        # Only show sources if answer actually uses context
        sources = []
        if result.chunks and not self._is_no_info_answer(answer):
            for c in result.chunks:
                meta = c.metadata.custom if c.metadata and c.metadata.custom else {}
                sources.append(
                    {
                        "chunk_id": c.id,
                        "text_preview": c.text[:200] if c.text else "",
                        "metadata": meta,
                    }
                )

        return {
            "answer": answer,
            "sources": sources,
            "chunks_used": len(result.chunks),
            "errors": result.errors,
        }

    async def health(self) -> dict[str, Any]:
        # Count chunks across ALL namespaces
        total_chunks = 0
        try:
            index_path = getattr(
                self.vector_store.config, "index_path", "./data/indices"
            )
            namespaces = await self.vector_store.list_namespaces(index_path)
            for ns in namespaces:
                chunks = await self.vector_store.list_by_filter({}, namespace=ns)
                total_chunks += len(chunks)
        except Exception:
            pass

        return {
            "status": "ok",
            "index_loaded": total_chunks > 0,
            "chunk_count": total_chunks,
        }
```

#### `features/rag/schemas.py`

```py
"""RAG feature Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

class IndexRequest(BaseModel):
    """Request to index documents."""

    documents: list[dict[str, Any]] = Field(
        ..., description="List of {id, content, metadata} objects"
    )
    namespace: str | None = Field(
        default=None, description="Index namespace (default, personal, work, etc.)"
    )

class IndexResponse(BaseModel):
    """Response after indexing."""

    indexed_count: int
    chunk_count: int
    namespace: str | None = None
    errors: list[str] = Field(default_factory=list)

class QueryRequest(BaseModel):
    """RAG query request."""

    query: str
    top_k: int | None = Field(default=None, ge=1, le=50)
    prompt_name: str | None = None
    prompt_version: str | None = None
    namespace: str | None = Field(default=None, description="Query namespace")

class QueryResponse(BaseModel):
    """RAG query response."""

    answer: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    chunks_used: int
    errors: list[str] = Field(default_factory=list)

class DeleteRequest(BaseModel):
    """Delete documents/chunks request."""

    document_ids: list[str] | None = None
    chunk_ids: list[str] | None = None
    namespace: str | None = Field(default=None, description="Target namespace")

class DeleteResponse(BaseModel):
    """Delete response."""

    deleted_chunks: int
    errors: list[str] = Field(default_factory=list)

class HealthResponse(BaseModel):
    """RAG health check."""

    status: str
    index_loaded: bool
    chunk_count: int
    embedder_dim: int | None = None

class NamespaceListResponse(BaseModel):
    """Available RAG namespaces."""

    namespaces: list[str]
```

### `pipeline/`

#### `pipeline/__init__.py`

```py
"""Pipeline steps and decorators."""

from .decorators import get_step, step
from .steps import build_context, embed_query, generate, retrieve

__all__ = ["step", "get_step", "embed_query", "retrieve", "build_context", "generate"]
```

#### `pipeline/decorators.py`

```py
"""Pipeline step registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

_step_registry: dict[str, Callable[..., Awaitable[Any]]] = {}

def step(
    name: str,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Register a pipeline step by name.

    Args:
        name: Unique step identifier.

    Returns:
        Decorator that registers the function.
    """

    def decorator(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        _step_registry[name] = fn
        return fn

    return decorator

def get_step(name: str) -> Callable[..., Awaitable[Any]]:
    """Retrieve a registered step.

    Args:
        name: Step identifier.

    Returns:
        Registered step function.

    Raises:
        ValueError: If step not found.
    """
    if name not in _step_registry:
        raise ValueError(f"Unknown step: {name}")
    return _step_registry[name]
```

#### `pipeline/steps.py`

```py
# pipeline/steps.py
"""RAG pipeline steps with namespace and rerank support."""

from __future__ import annotations

import json
from typing import Any

from core.domain.messages import AssistantMessage, UserMessage
from core.domain.pipeline import PipelineData
from core.metrics import record_metric
from core.ports.tools import ToolCall
from core.prompts import get_prompt
from core.utils import count_tokens, get_context_limit
from pipeline.decorators import step

def _estimate_tokens(text: str, model: str = "gpt-4o") -> int:
    return count_tokens(text, model)

def _get_llm_context_limit(llm: Any) -> int | None:
    return get_context_limit(llm)

@step("embed_query")
async def embed_query(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Embed the user query text."""
    embedder = kwargs.get("embedder")
    if embedder is None:
        data.errors.append("embed_query: embedder not provided")
        return data
    if data.query is None or not data.query.text:
        data.errors.append("embed_query: no query text")
        return data
    try:
        embeddings = await embedder.embed([data.query.text])
        data.metadata["query_embedding"] = embeddings[0]
    except Exception as e:
        data.errors.append(f"embed_query failed: {e}")
    return data

@step("retrieve")
async def retrieve(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Retrieve relevant chunks from vector store (namespace-aware)."""
    vector_store = kwargs.get("vector_store")
    if vector_store is None:
        data.errors.append("retrieve: vector_store not provided")
        return data
    embedding = data.metadata.get("query_embedding")
    if embedding is None:
        data.errors.append("retrieve: no query embedding")
        return data
    try:
        top_k = data.metadata["top_k"]
        namespace = data.metadata.get("namespace") or "default"
        chunks = await vector_store.search(embedding, top_k=top_k, namespace=namespace)
        data.chunks = chunks
        record_metric("rag_chunks", len(chunks))
    except Exception as e:
        data.errors.append(f"retrieve failed: {e}")
    return data

@step("rerank")
async def rerank(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Rerank retrieved chunks by relevance and filter by threshold.

    If reranker is not configured (None), acts as transparent pass-through.
    """
    if not data.chunks:
        return data

    reranker = kwargs.get("reranker")
    if reranker is None:
        return data

    try:
        query = data.query.text if data.query else ""
        top_k = data.metadata.get("top_k", 5)
        threshold = data.metadata.get("relevance_threshold", 0.3)

        results = await reranker.rerank(query, data.chunks, top_k=top_k)

        filtered = [r for r in results if r.score >= threshold]

        if not filtered:
            data.chunks = []
            data.metadata["rerank_filtered_out"] = True
        else:
            data.chunks = [r.chunk for r in filtered]
            data.metadata["rerank_scores"] = [r.score for r in filtered]

    except Exception as e:
        data.errors.append(f"rerank failed: {e}")

    return data

@step("build_context")
async def build_context(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Build context string from retrieved (and reranked) chunks."""
    if not data.chunks:
        data.context = ""
        return data
    lines = [chunk.text for chunk in data.chunks if chunk.text]
    data.context = "\n\n".join(lines)
    return data

@step("generate")
async def generate(data: PipelineData, **kwargs: Any) -> PipelineData:
    """Generate response using LLM with context."""
    llm = kwargs.get("llm")
    tool_registry = kwargs.get("tool_registry")
    if llm is None:
        data.errors.append("generate: llm not provided")
        return data
    if data.query is None:
        data.errors.append("generate: no query")
        return data

    prompt_version = data.metadata["prompt_version"]
    prompt_name = data.metadata["prompt_name"]

    try:
        prompt = get_prompt(
            prompt_name,
            version=prompt_version,
            query=data.query.text or "",
            context=data.context,
        )
    except Exception:
        chunks_text = "\n".join(
            [f"[{i + 1}] {c.text}" for i, c in enumerate(data.chunks)]
        )
        prompt = (
            f"Context:\n{chunks_text}\n\nQuestion: {data.query.text or ''}\nAnswer:"
        )

    record_metric("input_tokens", _estimate_tokens(prompt))

    max_ctx = _get_llm_context_limit(llm)
    if isinstance(max_ctx, int) and max_ctx > 0:
        prompt_tokens = _estimate_tokens(prompt)
        margin = max(256, int(max_ctx * 0.1))
        limit = max_ctx - margin
        if prompt_tokens > limit:
            while data.chunks and prompt_tokens > limit:
                data.chunks = data.chunks[:-1]
                if not data.chunks:
                    break
                try:
                    prompt = get_prompt(
                        prompt_name,
                        version=prompt_version,
                        query=data.query.text or "",
                        context=data.context,
                    )
                except Exception:
                    chunks_text = "\n".join(
                        [f"[{i + 1}] {c.text}" for i, c in enumerate(data.chunks)]
                    )
                    prompt = (
                        f"Context:\n{chunks_text}\n\n"
                        f"Question: {data.query.text or ''}\nAnswer:"
                    )
                prompt_tokens = _estimate_tokens(prompt)
            if prompt_tokens > limit:
                data.errors.append(
                    f"generate: prompt too long ({prompt_tokens} tokens) "
                    f"exceeds limit ({limit})"
                )
                data.response = AssistantMessage(
                    text="Sorry, the retrieved context is too large to process. "
                    "Please narrow your query."
                )
                return data

    original_image = data.query.image if data.query else None

    messages: list[Any] = [UserMessage(text=prompt, image=original_image)]
    response: AssistantMessage | None = None

    for _ in range(3):
        try:
            response = await llm.complete(messages)
        except Exception as e:
            data.errors.append(f"generate failed: {e}")
            data.response = AssistantMessage(
                text="Sorry, I encountered an error generating the response."
            )
            return data

        if not response.tool_calls:
            break

        messages.append(response)

        if tool_registry:
            for call in response.tool_calls:
                try:
                    func = call.get("function", {})
                    tool_name = func.get("name", "")
                    arguments = json.loads(func.get("arguments", "{}"))
                    tc = ToolCall(
                        tool_name=tool_name,
                        arguments=arguments,
                        call_id=call.get("id", ""),
                    )
                    result = await tool_registry.execute(tc)
                    content = (
                        result.output
                        if not result.is_error
                        else f"Error: {result.error}"
                    )
                except Exception as e:
                    content = f"Error: {e}"

                messages.append(
                    {
                        "role": "tool",
                        "content": str(content),
                        "tool_call_id": call.get("id", ""),
                    }
                )
        else:
            break

    data.response = (
        response
        if response
        else AssistantMessage(text="Sorry, tool call loop exhausted.")
    )
    record_metric("output_tokens", _estimate_tokens(data.response.text or ""))
    return data
```
