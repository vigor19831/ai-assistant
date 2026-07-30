# AI Assistant

Local AI assistant framework. FastAPI + RAG with namespaces.
Offline-first, OpenAI-compatible LLM/embedder adapters.

**Solo-maintained.** Published as-is — no contributions accepted.

![Chat - example](docs/screenshot.png)

## What is this

- **LLM**: any OpenAI-compatible server (llama.cpp, Ollama, vLLM, etc.)
- **Embedder**: any OpenAI-compatible server (nomic-embed-text, etc.)
- **Reranker**: optional API-based reranking (set `provider: null` to disable)
- **Vector store**: FAISS (persistent) or memory (ephemeral)
- **Storage**: SQLite
- **API**: OpenAI-compatible HTTP API (`/v1/chat/completions`, `/v1/models`) + native endpoints

## Requirements

- Python 3.11+
- LLM server running
- Embedder server running

## Quick Start

```bash
# 1. Install
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install .
# Optional: FAISS for persistent vector store
pip install .[faiss]

# 2. Configure
cp config.example.yaml config.yaml
# Edit config.yaml: set llm.api_base, embedder.api_base, rag.sources

# 3. Download tokenizers (local models only)
python scripts/download_tokenizers.py

# 4. Start
python -m uvicorn ai_assistant.main:create_app --reload
# Or use run_servers.py for local llama.cpp setup

# 5. Verify
python scripts/check_llm.py
python scripts/check_rag.py
```

Open http://localhost:8000/ui.

## Configuration

Key sections in `config.yaml`:

| Section | Purpose |
|---------|---------|
| `llm` | Model, API endpoint, sampling |
| `embedder` | Embedding model, dimension (must match `vector_store.dim`) |
| `reranker` | Optional reranking API |
| `vector_store` | FAISS or memory, index path, dimension |
| `rag` | Pipeline steps, top_k, document `sources` |
| `namespaces` | Per-namespace prefix, chunk size, prompt |
| `security` | API key, admin endpoints, body size limits |

`config.yaml` is git-ignored. `config.example.yaml` is the template in repo.

## Usage

### RAG Namespaces

RAG is opt-in. Start a message with a namespace prefix to search documents:

```
[m] what is the architecture?
```

Configure prefixes per namespace in `config.yaml`:

```yaml
namespaces:
  mydocs:
    prefix: m
    chunk_size: 512
    prompt: rag_strict
```

### Index Documents

After editing `rag.sources`, open the web UI at `http://localhost:8000/ui` and click the **Index** button, or use the API.

### API Examples

**OpenAI-compatible chat:**
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"your-model-name","messages":[{"role":"user","content":"[m] what is this?"}]}'
```

**Native RAG query:**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query":"[m] what is this?", "namespace":"mydocs"}'
```

## RAG Quality

`scripts/check_rag.py` is the single source of truth for RAG correctness.
Do not edit it to make tests pass — fix the pipeline (embedder, reranker, prompt, or LLM) instead.

```bash
python scripts/check_rag.py        # Full run (re-index + test)
python scripts/check_rag.py --skip-index   # Test only, reuse indices
```

## RAG LLM Model Requirements

RAG quality is bottlenecked by the **LLM**, not the retriever. Small models (3–5B) handle simple Q&A but struggle with multi-hop reasoning, conflict resolution, and long-context fidelity.

| Use Case | Minimum | Good | Excellent |
|----------|---------|------|-----------|
| Simple Q&A | 4B | 7B | 14B+ |
| Multi-hop / logic | 7B | 14B | 32B+ |
| Multi-language | 7B | 14B | 32B+ |

VRAM (Q4_K_M): 4B ~3–4 GB, 7–8B ~5–6 GB, 14B ~9–10 GB, 32B ~20 GB.

If retrieval is correct but answers are wrong, the model is likely too small for the task.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'faiss'` | `pip install faiss-cpu` |
| `embedder.dim != vector_store.dim` | Set both `dim` values to the same number in `config.yaml` |
| "I do not have enough information" | Check namespaces exist (`/api/v1/rag/namespaces`), verify prefix matches, re-index |
| `401 Unauthorized` on `/api/v1/*` | Legacy endpoints need `Authorization: Bearer <key>`; OpenAI-compatible `/v1/*` does not |
| RAG answers wrong despite correct retrieval | Model too small, or reduce `chunk_size` to 256–384 and `temperature` to 0.05–0.1 |

## Documentation

- `docs/ai_rules.md` — AI development constraints
- `docs/architecture.md` — architectural strategy and RAG philosophy
- `docs/drift.md` — known architectural drift log

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
