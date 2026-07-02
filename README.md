# AI Assistant

**Solo-maintained. No contributions accepted.**
This project is developed for personal use by a non-programmer. AI writes the code; I set the direction.

This repository is published as-is.
I do not review issues, discussions, or pull requests.

---

## What is this

Local AI assistant framework. FastAPI + RAG with namespaces.
Offline-first, OpenAI-compatible LLM/embedder adapters.

- **LLM**: any OpenAI-compatible server (llama.cpp, Ollama, vLLM, etc.)
- **Embedder**: any OpenAI-compatible server (nomic-embed-text, etc.)
- **Vector store**: FAISS (persistent) or memory (ephemeral)
- **Storage**: SQLite
- **API**: OpenAI-compatible HTTP API (`/v1/chat/completions`, `/v1/models`) + native endpoints

---
### 1. First Time Setup

1. **Download:** Click the green **"Code"** button on GitHub → **"Download ZIP"** → extract the ZIP

2. **Open a terminal** in the project folder:
   - **Windows:** Click the folder's address bar, type `cmd`, press Enter
   - **macOS:** Right-click folder → "New Terminal at Folder"
   - **Linux:** Right-click folder → "Open in Terminal"

3. **Run the setup script:**
   - **Windows:**
     ```
     python scripts/setup.py
     ```
   - **macOS / Linux:**
     ```
     python3 scripts/setup.py
     ```
> **Note:** If you move the project folder after setup, run `setup.py` again to fix paths.

The script will:
- Check your Python version (3.11+ required)
- Create a virtual environment (`.venv/`)
- Install all dependencies
- Create `config.local.yaml` from a template. Add your API keys and local paths there. Do not put secrets in `config.yaml`.
- Create required data folder (`data/`). Document sources are configured in `config.yaml` via `rag.sources`, or overridden per-machine in `config.local.yaml`.

If Python is not installed, the script will open the download page in your browser.

4. **Download models:** Place your GGUF models in `vendor/models/`. Download from [HuggingFace](https://huggingface.co/models) or other sources. Ensure filenames match your `config.yaml` settings.

5. **Edit configuration:**
   - Open `config.yaml` for shared settings (model names, endpoints, thresholds).
   - Open `config.local.yaml` for secrets (API keys) and local paths (document folders).
   - In `config.local.yaml`, only include fields you want to override -- all others are inherited from `config.yaml`.

   **Model selection:** Set `model` to the exact name of the model loaded on your server. For `run_servers.py` with llama.cpp, use the GGUF filename *without* the `.gguf` extension. List all available models in `available_models` (first entry is treated as active for `/v1/models`):

   ```yaml
   llm:
     model: your-model-name-1
     available_models:
       - "your-model-name-1"
       - "your-model-name-2"
       - "your-model-name-3"
   ```

6. **Download tokenizers:** Run `download_tokenizers.py` via `run_scripts.py` to download tokenizer files for your local models.
   - **Windows:** double-click `run_scripts.py` (in the project root), select `download_tokenizers.py`
   - **macOS / Linux:** `python3 run_scripts.py`, select `download_tokenizers.py`

   *Note: This is required for local models (Llama, Qwen, Gemma, Phi, etc.). You can skip this step only if you use cloud OpenAI models (like `gpt-4o`).*

### 2. Start the Server

**If using llama.cpp (local GGUF models):**

> **Windows first-time users:** After downloading llama.cpp, Windows may show a security warning ("Unknown publisher") when first running `llama-server.exe`. You must run `llama-server.exe` manually once and click "Run anyway" before using `run_servers.py`. Otherwise `run_servers.py` will hang silently because the security dialog cannot appear for subprocesses.

- **Windows:** double-click `run_servers.py`
- **macOS / Linux:** `.venv/bin/python run_servers.py`

**If using Ollama, vLLM, or other external server:**
Start the server separately according to its documentation, then verify `api_base` in `config.yaml` matches its endpoint.

Then open http://localhost:8000 in your browser.

---
### 3. Daily Use

**RAG Namespaces:** RAG is opt-in. To search your documents, start a message with a namespace prefix configured in `config.yaml` (e.g., `[p]` for personal, `[w]` for work). Messages without a prefix go directly to the LLM with no document search. Prefixes are defined per-namespace via the `prefix` field -- remove or change them in `config.yaml` as needed. Local paths to document folders go in `config.local.yaml`.

**Chat Exports:** Save and index chat history via the `/api/v1/rag/save-chat` endpoint (toggle in `config.yaml` via `rag.index_chat_exports`).

**API Endpoints:**

The server exposes two API families:

1. **Native API** (`/api/v1/*`) — requires API key if configured:
   - `POST /api/v1/chat` — chat with RAG
   - `POST /api/v1/chat/stream` — streaming chat (SSE)
   - `POST /api/v1/rag/query` — RAG query only
   - `POST /api/v1/rag/index` — index documents
   - `POST /api/v1/rag/reindex` — background reindex from disk
   - `GET /api/v1/rag/reindex/status/{task_id}` — check reindex progress
   - `GET /api/v1/rag/health` — RAG health check
   - `GET /api/v1/rag/namespaces` — list namespaces
   - `POST /api/v1/rag/delete` — delete chunks/documents
   - `POST /api/v1/rag/save-chat` — save chat export

2. **OpenAI-compatible API** (`/v1/*`) — stays at root, optional auth via `security.openai_routes_require_auth`:
   - `GET /v1/models` — list available models
   - `POST /v1/chat/completions` — OpenAI-compatible chat (supports streaming)

   Use this to connect existing tools (continue.dev, OpenWebUI, etc.) that expect an OpenAI endpoint.

**Admin endpoints** (`/admin/*`, dev-only):
   - `GET /admin/current-model` — show active model
   - `POST /admin/api-key` — rotate API key at runtime (process-local only)

   Disabled unless `security.admin_enabled: true`.

**Servers:**

`run_servers.py` — starts local llama.cpp LLM and embedder servers. Must be running before using the app (if you use local models).

- **Start:** double-click `run_servers.py` (Windows) or `.venv/bin/python run_servers.py` (macOS/Linux)
- **Stop:** press `Ctrl+C` in the terminal window. The app performs graceful shutdown: finishes active requests, persists indices, closes connections.

If using Ollama, vLLM, or other external servers — start them separately.

**Helper scripts** (run via `run_scripts.py` from the project root):

| Script | When to run |
|--------|-------------|
| `index_documents.py` | After updating `rag.sources` in `config.yaml` |
| `download_tokenizers.py` | After adding a new model (HF only) |
| `kill.py` | Emergency shutdown — stops all running servers |
| `check_llm.py` | [dev] Verifies LLM connection and basic generation |
| `check_rag.py` | [dev] Tests the full RAG pipeline (retrieval + generation) |

**Background Reindex:**
The `/api/v1/rag/reindex` endpoint returns immediately and runs in the background. Check status with `/api/v1/rag/reindex/status/{task_id}`. Tasks time out after 4 hours. Only one reindex runs at a time (semaphore-protected).

---

## ⚠️ Security & Production Deployment
The default `config.yaml` is optimized for local development and includes `debug: true` and `security.admin_enabled: true`.
**Before deploying to production:**
- Set `debug: false`
- Set `security.admin_enabled: false`
- Set `security.openai_routes_require_auth: true` if you expose `/v1/*` externally
- Set `security.api_key` in `config.local.yaml` or `AI_SECURITY_API_KEY` env var
- Review `security.allowed_hosts`

---

## Requirements

- Python 3.11+
- LLM server: llama.cpp (local GGUF), Ollama, vLLM, or any OpenAI-compatible endpoint
- Embedder server: any OpenAI-compatible endpoint

## Configuration

Edit `config.yaml` to point to your LLM and embedder endpoints. All available options are documented inline with comments.

Key sections:
- `llm` -- model, API endpoint, sampling parameters
- `embedder` -- embedding model, dimension (must match `vector_store.dim`)
- `vector_store` -- FAISS or memory, index path, dimension
- `rag` -- pipeline steps (`embed_query`, `retrieve`, `rerank`, `build_context`, `generate`, optional `hyde_query`), top_k, thresholds
- `namespaces` -- per-namespace chunk size, threshold, prompt overrides
- `security` -- API key, admin endpoints, body size limits
- `logging` -- level, format (text/json), rotation

**Local overrides:** Put secrets (API keys) and machine-specific paths in `config.local.yaml`. It is git-ignored and merged with `config.yaml` at startup. Only include fields you want to override -- all others are inherited from `config.yaml`.

## Project Structure

```
ai-assistant/                          # Project root
├── .venv/                             # Virtual environment
├── data/                              # Runtime data
│   ├── tokenizers/                    # Local HuggingFace tokenizers
│   ├── indices/                       # FAISS vector indices
│   ├── storage.db                     # SQLite database
│   ├── app.log                        # Application logs
│   └── .run_history.json              # Script run history
│
├── docs/                              # Documentation
│   ├── ai_rules.md                    # AI development rules
│   ├── architectural_strategy.md      # Architecture decisions
│   └── drift.md                       # Known drift log
│
├── scripts/                           # Helper scripts
│   ├── setup.py                       # Project setup (one-time)
│   ├── check_all.py                   # [dev] Code check
│   ├── check_llm.py                   # [dev] LLM connection check
│   ├── check_rag.py                   # [dev] RAG pipeline check
│   ├── clean_cache.py                 # Cache cleanup
│   ├── context_build.py               # [dev] AI context build
│   ├── download_tokenizers.py         # Download tokenizers
│   ├── index_documents.py             # Document indexing
│   ├── kill.py                        # Emergency shutdown
│   ├── open_shell.py                  # [dev] Open shell with venv
│   └── structure.py                   # [dev] Structure generation
│
│
├── src/ai_assistant/                  # Application source code
│   ├── core/                          # Domain, ports, pipeline (immutable)
│   ├── adapters/                      # Adapter implementations
│   ├── api/                           # HTTP handlers, DI, lifespan
│   └── features/                      # Chat and RAG features
│
├── tests/                             # Tests
│
├── ui/                                # Web interface
│   └── index.html
│
├── vendor/                            # External models (not in git)
│   ├── models/
│   └── llama/
│
├── config.yaml                        # Shared config (in repo)
├── config.local.yaml                  # Local overrides (git-ignored)
├── LICENSE
├── NOTICE
├── pyproject.toml                     # Dependencies, settings
├── README.md                          # This file
├── run_scripts.py                     # Script runner (project root)
└── run_servers.py                     # Server orchestrator
```

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
```
