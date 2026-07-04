# AI Assistant

**Solo-maintained. No contributions accepted.**
This project is developed for personal use by a non-programmer. AI writes the code; I set the direction.

This repository is published as-is.
I do not review issues, discussions, or pull requests.

## What is this

Local AI assistant framework. FastAPI + RAG with namespaces.
Offline-first, OpenAI-compatible LLM/embedder adapters.

- **LLM**: any OpenAI-compatible server (llama.cpp, Ollama, vLLM, etc.)
- **Embedder**: any OpenAI-compatible server (nomic-embed-text, etc.)
- **Reranker**: optional API-based reranking (set `provider: null` to disable)
- **Vector store**: FAISS (persistent) or memory (ephemeral)
- **Storage**: SQLite
- **API**: OpenAI-compatible HTTP API (`/v1/chat/completions`, `/v1/models`) + native endpoints

## Requirements

- Python 3.11+
- LLM server: llama.cpp (local GGUF), Ollama, vLLM, or any OpenAI-compatible endpoint
- Embedder server: any OpenAI-compatible endpoint

## Quick Start

### 1. Install

```bash
# Create virtual environment
python -m venv .venv

# Activate
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

# Install dependencies
pip install .

# Optional: FAISS for persistent vector store
pip install .[faiss]
```

### 2. Configure

```bash
# Copy example config
cp config.example.yaml config.yaml

# Edit config.yaml with your model names, API keys, and paths
```

### 3. Download Tokenizers (local models only)

```bash
python run_scripts.py  # select download_tokenizers.py
```

Required for local models (Llama, Qwen, Gemma, Phi, etc.). Skip for cloud OpenAI models.

### 4. Download Engine and Models (local llama.cpp only)

**Engine:** Download `llama-server` from [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases) and place in `vendor/llama/` (or use Ollama, vLLM, etc.)

**Models:** Place GGUF models in `vendor/models/`. Download from [HuggingFace](https://huggingface.co/models).

### 5. Start

```bash
# If using local llama.cpp models, start servers first:
python run_servers.py

# Or start only the API (if using external servers):
python -m uvicorn ai_assistant.main:create_app --reload
```

Open http://localhost:8000/ui in your browser.

## Configuration

Edit `config.yaml` (copied from `config.example.yaml`). Key sections:

- `llm` -- model, API endpoint, sampling parameters
- `embedder` -- embedding model, dimension (must match `vector_store.dim`)
- `reranker` -- optional reranking API config (set `provider: null` to disable)
- `vector_store` -- FAISS or memory, index path, dimension
- `chunker` -- document splitting strategy
- `chat` -- history limit, max context tokens
- `rag` -- pipeline steps, top_k, thresholds, document `sources`
- `namespaces` -- per-namespace prefix, chunk size, threshold, prompt override
- `storage` -- SQLite database path
- `security` -- API key, `admin_enabled`, body size limits
- `logging` -- level, format (text/json), rotation
- `cors` / `ui` -- cross-origin and static file settings

`config.yaml` is git-ignored. `config.example.yaml` is the template in repo.

## Daily Use

**RAG Namespaces:** RAG is opt-in. Start a message with a namespace prefix (e.g., `[d] what is...`) to search documents. Messages without a prefix go directly to LLM. Configure prefixes per namespace in `config.yaml` under `namespaces.<name>.prefix`.

**Chat Exports:** Save and index chat history via `/api/v1/rag/save-chat`. Toggle in `config.yaml` via `rag.index_chat_exports`.

**Admin Endpoints:** Disabled by default. Set `security.admin_enabled: true` to expose `/api/v1/admin/*`.

**Helper scripts** (run via `run_scripts.py`):

| Script | When to run |
|--------|-------------|
| `index_documents.py` | After updating `rag.sources` in `config.yaml` (requires running servers) |
| `download_tokenizers.py` | After adding a new model (HF only) |
| `kill.py` | Emergency shutdown -- stops all running servers |
| `check_llm.py` | [dev] Verifies LLM connection and basic generation |
| `check_rag.py` | [dev] Tests the full RAG pipeline |
| `check_all.py` | [dev] Runs all checks |
| `clean_cache.py` | [dev] Remove temporary / cache files |
| `context_build.py` | [dev] Build project context for AI assistance |
| `open_shell.py` | [dev] Open interactive shell with project imports |
| `structure.py` | [dev] Print project file structure |

**Background Reindex:** `POST /api/v1/rag/reindex` returns immediately, runs in background. Check status with `GET /api/v1/rag/reindex/status/{task_id}`. Tasks time out after 4 hours. Only one reindex runs at a time.

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
