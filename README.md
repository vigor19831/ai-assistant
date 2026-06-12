# AI Assistant

Модульный фреймворк для локальных LLM. Работает offline, поддерживает RAG, совместим с OpenAI API.

## Возможности

- 💬 Чат с памятью и контекстом
- 📚 RAG: поиск по документам с namespace'ами (`[p]ersonal`, `[w]ork`, `[o]ther`, `[c]ode`, `[b]ooks`)
- 🔌 Поддержка любых OpenAI-compatible серверов (llama.cpp, Ollama, vLLM)
- 🧠 Работает полностью offline (mock-режим)

## Быстрый старт

```
# 1. Установка
pip install -e ".[faiss]"

# 2. Настройка LLM-сервера
# Варианты:
# • llama-server: llama-server.exe -m model.gguf --port 8080
# • Ollama: ollama serve
# • vLLM: python -m vllm.entrypoints.openai.api_server --model ...

# 3. Конфиг
# Отредактируй config.yaml:
# llm.api_base: http://127.0.0.1:8080/v1
# llm.model: имя-модели-на-сервере

# 4. Запуск (из корня проекта, .venv активируется автоматически)
python start.py              # запуск LLM + embedder + uvicorn
python stop.py               # остановка всех серверов

# Или вручную:
python scripts/start.py
python main.py
uvicorn ai_assistant.main:app --host 0.0.0.0 --port 8000

# 5. UI
# Подключи любой OpenAI-compatible клиент к http://localhost:8000
# Рекомендуется: Page Assist (браузерное расширение)
```

## RAG — поиск по документам

```bash
# Индексация документов
python scripts/index_documents.py
```

В чате используй префиксы:

| Префикс | Namespace |
|---------|-----------|
| `[p]` | personal |
| `[w]` | work |
| `[o]` | other |
| `[c]` | code |
| `[b]` | books |

## Рекомендуемые модели

**LLM:**

- `gemma-3-4b-it` — быстрая, качественная, мультиязычная
- `qwen2.5-7b-instruct` — хороший баланс скорость/качество
- `llama-3.2-3b-instruct` — компактная, для слабых GPU

**Embedder:**

- `nomic-embed-text-v1.5` — размерность 768
- `mxbai-embed-large-v1` — размерность 1024

> ⚠️ **Важно:** `embedder.dim` в `config.yaml` **должен** совпадать с `vector_store.dim`.

## Требования

- Python 3.13+
- 8+ GB RAM (для CPU-режима)
- GPU опционально (CUDA/Metal/Vulkan)

---

All rights reserved. For personal use only.
