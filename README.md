# AI Assistant

Chat with local LLMs using any OpenAI-compatible server. Fully offline. RAG with document namespaces.

## Quick Start

### 1. Install

```bash
pip install -e ".[faiss]"
```

### 2. Start LLM Server

**Option A — llama.cpp:**
```bash
llama-server -m model.gguf --port 8080
```

**Option B — Ollama:**
```bash
ollama serve
```

**Option C — vLLM:**
```bash
python -m vllm.entrypoints.openai.api_server --model your-model-name
```

### 3. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:
```yaml
llm:
  api_base: http://127.0.0.1:8080/v1
  model: your-model-name

embedder:
  api_base: http://127.0.0.1:8081/v1
  model: your-embedder-model
  dim: 768

vector_store:
  dim: 768  # Must match embedder.dim
```

### 4. Run

```bash
python scripts/run.py
```

The API is available at `http://localhost:8000`.

### 5. Connect Client

Use any OpenAI-compatible client:

- **Page Assist** (browser extension) — recommended
- **Continue.dev** (VS Code)
- **OpenCode** (IDE)

Or call directly:
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "your-model", "messages": [{"role": "user", "content": "Hello"}]}'
```

## Document Search (RAG)

### Index Documents

```bash
python scripts/index_documents.py
```

Or via API:
```bash
curl -X POST http://localhost:8000/api/v1/rag/index \
  -H "Authorization: Bearer sk-local-api-key" \
  -H "Content-Type: application/json" \
  -d '{"documents": [{"id": "doc1", "content": "..."}], "namespace": "work"}'
```

### Query with Namespaces

In chat, use prefixes to search specific document collections:

| Prefix | Namespace | Example |
|--------|-----------|---------|
| `[p]` | personal | `[p] What did I write about...` |
| `[w]` | work | `[w] Q3 revenue numbers` |
| `[c]` | code | `[c] How does auth work` |
| `[b]` | books | `[b] Summary of chapter 3` |
| `[o]` | other | `[o] Recipe for pasta` |

No prefix = search default namespace.

## Requirements

- Python 3.13+
- 8+ GB RAM (CPU mode)
- GPU optional

## License

MIT
