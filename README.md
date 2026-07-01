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
- Copy `.env.example` to `.env` and add your API keys (or leave empty for local servers without auth)
- Create required data folders (`data/`, `sources/`)

If Python is not installed, the script will open the download page in your browser.

4. **Download models:** Place your GGUF models in `vendor/models/`. Download from [HuggingFace](https://huggingface.co/models) or other sources. Ensure filenames match your `config.yaml` settings.

5. **Edit configuration:** Open `config.yaml` and set:
   - LLM: `model` (filename for llama.cpp GGUF, or model name for Ollama/vLLM) and `api_base`
   - Embedder: `model` and `api_base`
   - Adjust other settings as needed

6. **Download tokenizers:** Run `download_tokenizers.py` via `run_scripts.py`:
   - **Windows:** double-click `run_scripts.py`, select `download_tokenizers.py`
   - **macOS / Linux:** `python3 run_scripts.py`, select `download_tokenizers.py`

   This downloads tokenizers to `data/tokenizers/` based on your `config.yaml` settings.

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

**Servers:**

`run_servers.py` — starts local llama.cpp LLM and embedder servers. Must be running before using the app (if you use local models).

- **Start:** double-click `run_servers.py` (Windows) or `.venv/bin/python run_servers.py` (macOS/Linux)
- **Stop:** press `Ctrl+C` or `Enter` in the terminal window

If using Ollama, vLLM, or other external servers — start them separately.

**Helper scripts** (run via `run_scripts.py`):

| Script | When to run |
|--------|-------------|
| `index_documents.py` | After adding files to `sources/` |
| `download_tokenizers.py` | After adding a new model |
| `kill.py` | Emergency shutdown — stops all running servers |

## Requirements

- Python 3.11+
- LLM server: llama.cpp (local GGUF), Ollama, vLLM, or any OpenAI-compatible endpoint
- Embedder server: any OpenAI-compatible endpoint

## Configuration

Edit `config.yaml` to point to your LLM and embedder endpoints. All available options are documented inline with comments.

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
├── sources/                           # Document sources for RAG
│   ├── books/
│   ├── code/
│   ├── other/
│   ├── personal/
│   └── work/
│
├── src/ai_assistant/                  # Application source code
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
├── .env.example                       # Secret template (copy to .env)
├── config.yaml                        # Active config
├── LICENSE
├── NOTICE
├── pyproject.toml                     # Dependencies, settings
├── README.md                          # This file
├── run_scripts.py                     # Script runner
└── run_servers.py                     # Server orchestrator
```

## License

Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
