# AI Assistant — Local AI on Your Machine

> **Chat with AI on your own computer.** No internet needed, no subscriptions, no data leaving your device. Your conversations and documents stay private.

---

## What Is This

**AI Assistant** lets you chat with AI and search your own documents (PDFs, notes, books) for answers — all running locally, no cloud involved.

### What Is RAG?

**RAG** (Retrieval-Augmented Generation) means the AI **first searches your documents**, then answers based on what it found. It doesn't make things up — it quotes your files.

**Example:** you upload 50 tax PDFs and ask "What deductions apply in 2024?" The AI finds the relevant pages and gives a precise answer with citations.

---

## Why Run It Locally

| Cloud AI (ChatGPT, Claude) | This Project |
|---|---|
| Data goes to someone else's servers | Everything stays on your computer |
| Monthly subscription | Free — download models once |
| Needs internet | Works offline |
| Doesn't know your documents | Searches your files directly |
| Can "hallucinate" made-up facts | Answers only from your documents |

---

## Installation

### 1. Check Python

You need **Python 3.11 or newer**:

```bash
python3 --version
# or
python --version
```

If the version is too old, [download a newer Python](https://www.python.org/downloads/).

### 2. Create a Virtual Environment

This is an isolated folder for project libraries so they don't clutter your system.

**Linux / macOS:**
```bash
cd project-folder
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
cd project-folder
python -m venv .venv
.venv\Scripts\activate
```

When you see `(.venv)` at the start of your terminal line, you're good to go.

### 3. Install the Project

```bash
pip install -e ".[faiss]"
```

### 4. Copy the Config File

```bash
cp config.example.yaml config.yaml
```

Open `config.yaml` in any text editor and adjust it to your setup.

---

## Running the Servers

The project needs two servers: an **LLM server** (the AI itself) and an **API server** (this project). You don't need to start them manually — use `run_servers.py`.

```bash
python run_servers.py start
```

This starts everything automatically. Verify it's working:

```bash
curl http://localhost:8000/v1/models
```

You should see a list of available models.

### Stop

```bash
python run_servers.py stop
```

### Other Commands

```bash
python run_servers.py kill     # Force-kill all processes
python run_servers.py --help   # Show help
```

---

## Using the Scripts Menu

`run_scripts.py` provides a convenient menu for running useful utilities.

```bash
python run_scripts.py
```

This opens a menu with available scripts. The main ones:

| Script | What It Does |
|---|---|
| `index_documents.py` | Indexes documents from `sources/` for search |
| `check_llm.py` | Checks if the LLM server responds |
| `check_rag.py` | Checks if document search works |
| `clean_cache.py` | Cleans temporary files |
| `context_build.py` | Builds context for the AI assistant |

**Example:** index your documents
```bash
python run_scripts.py
# Select: index_documents.py from the menu
```

Or run directly:
```bash
python scripts/index_documents.py
```

---

## Quick Start: Your First Chat

1. Start the servers: `python run_servers.py start`
2. Open in browser: `http://localhost:8000/ui`
3. Or via API:
   ```bash
   curl http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model": "llama3.2", "messages": [{"role": "user", "content": "Hello!"}]}'
   ```

---

## Project Layout

```
ai-assistant/
├── config.yaml          ← your config (edit this)
├── config.example.yaml  ← example config
├── run_servers.py       ← start/stop servers
├── run_scripts.py       ← scripts menu
├── scripts/             ← utility scripts
├── src/                 ← source code
├── data/                ← your data (indices, chats, logs)
│   ├── indices/         ← search indexes
│   ├── storage.db       ← chat history
│   └── app.log          ← logs
└── sources/             ← put documents here for RAG
    ├── personal/
    └── work/
```

---

## License

Apache License 2.0. See [LICENSE](LICENSE).

## Solo maintenance note

This project is developed by a solo creator with extensive use of AI-assisted programming tools. The author defines the product vision, architecture, requirements, testing strategy, and development roadmap, while AI tools are used to accelerate implementation, refactoring, documentation, and experimentation. All design decisions, feature prioritization, and project direction remain under human supervision.
