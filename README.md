# AI Assistant

Chat with AI models on your own computer. No internet required, no cloud, no subscriptions. Your data stays with you.

**What it does:**
- Chat with AI (like ChatGPT, but locally)
- Search your documents (Word, PDF, notes, books) for answers
- Works with any model that speaks the OpenAI format

---

## Why use this?

| Scenario | How it works |
|----------|--------------|
| Ask AI a question | Type in chat, get an answer |
| Find info in 100 PDFs | Upload PDFs, ask "what about taxes in 2024" |
| Save an important conversation | Export chat as a document, search it later |
| Work offline | Everything runs on your computer |

---

## What is what

**Simple explanations:**

- **LLM** — Large Language Model, the AI that writes text. Like ChatGPT, but on your machine.
- **Embedder** — A model that turns text into numbers (vectors) to find similar pieces.
- **RAG** — The AI first searches your documents, then answers based on what it found.
- **Namespace** — A folder for documents. `[p]` = personal, `[w]` = work, `[c]` = code.
- **Chunk** — A piece of text. Big documents are cut into ~512 character chunks for faster search.
- **FAISS** — A database for finding similar texts. Fast even with 100,000 documents.

---

## Step-by-step installation

### Step 0. Check Python

You need Python 3.11 or newer. Check:

```bash
python3 --version
# or
python --version
```

If the version is below 3.11 — [download new Python](https://www.python.org/downloads/).

### Step 1. Create a virtual environment

This is an isolated folder with libraries, so you don't mess up your system Python.

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

After activation you will see `(.venv)` at the start of the line — that's good.

**To exit the environment:**
```bash
deactivate
```

### Step 2. Install the program

```bash
pip install -e ".[faiss]"
```

If you want to develop (tests, code checks):
```bash
pip install -e ".[faiss,dev]"
```

Installation takes 2-5 minutes. If you see errors — check the [Troubleshooting](#troubleshooting) section.

### Step 3. Create config

```bash
cp config.example.yaml config.yaml
```

Open `config.yaml` in any text editor (VS Code, Notepad++, nano).

### Step 4. Download a model

**Option A — Ollama (easiest):**

```bash
# Install Ollama: https://ollama.com

# Download a model (~4 GB)
ollama pull llama3.2

# Start the server
ollama serve
```

**Option B — llama.cpp (for advanced users):**

Download a GGUF model from [HuggingFace](https://huggingface.co/models?sort=trending&search=gguf), for example:
- `bartowski/Llama-3.2-3B-Instruct-GGUF` — light, fast
- `bartowski/Mistral-7B-Instruct-v0.3-GGUF` — smarter, but needs 8 GB RAM

```bash
llama-server -m model.gguf --port 8080
```

**Option C — OpenAI (cloud, needs internet):**

Get an API key at [platform.openai.com](https://platform.openai.com), paste it into `config.yaml`.

### Step 5. Set up config.yaml

Here is a minimal working config for Ollama (you can leave everything else as is):

```yaml
app_name: ai-assistant
debug: false
host: 0.0.0.0
port: 8000
config_version: "1.5.0"

cors:
  allow_origins: ["http://localhost", "http://127.0.0.1"]
  allow_credentials: true
  allow_methods: ["*"]
  allow_headers: ["*"]

chat:
  history_limit: 10
  max_context_tokens: 4096
  tokenizer_model: "gpt-4o"
  tokenizer_local_dir: "./data/tokenizers"

chunker:
  provider: simple
  chunk_size: 512
  chunk_overlap: 50

embedder:
  provider: openai_compatible
  api_base: http://127.0.0.1:11434/v1   # Ollama
  api_key: sk-local-api-key
  model: nomic-embed-text                 # Light model for embeddings
  dim: 768
  timeout: 60.0
  connect_timeout: 5.0

llm:
  provider: openai_compatible
  api_base: http://127.0.0.1:11434/v1   # Ollama
  api_key: sk-local-api-key
  model: llama3.2
  max_tokens: 4096
  temperature: 0.7
  timeout: 300.0
  connect_timeout: 5.0

vector_store:
  provider: faiss
  index_path: ./data/indices
  metric: l2
  dim: 768
  max_chunks: 100000
  max_document_size: 10485760

storage:
  provider: sqlite
  db_path: ./data/storage.db

reranker:
  provider: null

rag:
  steps: [embed_query, retrieve, rerank, build_context, generate]
  prompt_version: v1
  prompt_name: rag_strict
  top_k: 5
  default_namespace: "default"
  relevance_threshold: 0.1
  chat_exports_root: "data/chat_exports"
  index_chat_exports: false

namespaces:
  personal: {threshold: 0.1, chunk_size: 512, prompt: rag_strict}
  work: {threshold: 0.3, chunk_size: 1024, prompt: rag_creative}
  other: {threshold: 0.1, chunk_size: 512, prompt: rag_strict}
  code: {threshold: 0.1, chunk_size: 512, prompt: rag_strict}
  books: {threshold: 0.1, chunk_size: 512, prompt: rag_strict}

security:
  api_key: sk-local-api-key
  max_body_size: 10485760
  allowed_hosts: ["localhost", "127.0.0.1"]

logging:
  level: "INFO"
  file: "./data/app.log"
  format: "text"
  max_bytes: 10485760
  backup_count: 2

ui:
  static_path: "../../ui"
```

### Step 6. Start the server

```bash
python -m ai_assistant.main
```

If everything is OK, you will see:
```
INFO:     Started server process [12345]
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 7. Check that it works

**Check 1 — LLM responds:**
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "llama3.2", "messages": [{"role": "user", "content": "Hello!"}]}'
```

You should get a JSON with the model's answer.

**Check 2 — list of models:**
```bash
curl http://localhost:8000/v1/models
```

**Check 3 — via script:**
```bash
python scripts/check_llm.py
python scripts/check_rag.py
```

### Step 8. Connect a client

- **Page Assist** (browser extension) — easiest
  - Install the extension
  - API URL: `http://localhost:8000`
  - API key: `sk-local-api-key`
  - Model: `llama3.2`

- **Continue.dev** (VS Code extension)
- **OpenCode** (IDE with AI)

---

## How much memory you need

| Model | File size | RAM (CPU) | VRAM (GPU) | Speed |
|-------|-----------|-----------|------------|-------|
| Llama 3.2 3B (Q4) | ~2 GB | 4 GB | 3 GB | Very fast |
| Llama 3.1 8B (Q4) | ~5 GB | 8 GB | 6 GB | Fast |
| Mistral 7B (Q4) | ~4 GB | 8 GB | 6 GB | Fast |
| Llama 3.1 70B (Q4) | ~40 GB | 64 GB | 48 GB | Slow |
| Phi-4 Mini (Q4) | ~2.5 GB | 6 GB | 4 GB | Very fast |

**Rule:** You need about 1.5-2x the model size in RAM.

**For embeddings (document search):**
- `nomic-embed-text` — ~300 MB, works on any hardware

---

## Where to get models

| Source | What to download | Link |
|--------|-----------------|------|
| HuggingFace | GGUF files | [huggingface.co/models?search=gguf](https://huggingface.co/models?search=gguf) |
| Ollama Hub | Ready-to-use models | [ollama.com/library](https://ollama.com/library) |
| bartowski | Quality quantizations | [huggingface.co/bartowski](https://huggingface.co/bartowski) |

**Recommendations for beginners:**
- **Quick start:** `llama3.2` (Ollama) or `bartowski/Llama-3.2-3B-Instruct-GGUF`
- **Balance speed/quality:** `mistral` (Ollama) or `bartowski/Mistral-7B-Instruct-v0.3-GGUF`
- **For Russian:** `qwen2.5` or `saiga` models

---

## Working with documents (RAG)

### Upload documents

**Method 1 — folder (automatic):**

Create a folder `sources/personal/` and put `.txt`, `.md`, `.pdf` files there.

```bash
python scripts/index_documents.py
```

**Method 2 — via API:**
```bash
curl -X POST http://localhost:8000/api/v1/rag/index \
  -H "Authorization: Bearer sk-local-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "documents": [
      {"id": "doc1", "content": "Document text..."}
    ],
    "namespace": "work"
  }'
```

### Ask about documents

In chat, write with a prefix:
```
[p] What do my notes say?
[w] What were the Q3 numbers?
[c] How does auth work?
```

Without prefix — searches in the `default` namespace.

### Save a conversation

```bash
curl -X POST http://localhost:8000/api/v1/rag/save-chat \
  -H "Authorization: Bearer sk-local-api-key" \
  -d '{
    "content": "Important conversation with AI...",
    "namespace": "personal",
    "filename": "ideas.md"
  }'
```

To search saved conversations later, set in `config.yaml`:
```yaml
rag:
  index_chat_exports: true
```

---

## Updating

```bash
# Enter the environment (if you exited)
source .venv/bin/activate

# Download new code
git pull

# Update dependencies
pip install -e ".[faiss]"
```

**Your data won't be lost** — it's in the `data/` folder, which is not deleted on update.

---

## Complete removal / clean reinstall

```bash
# Stop the server (Ctrl+C)

# Delete the environment
deactivate
rm -rf .venv

# Delete data (warning — chats and indexes will be lost!)
rm -rf data/
rm -f config.yaml

# Start over from Step 2
```

---

## Troubleshooting

### "Port 8000 is already in use"

```bash
# Find the process
lsof -i :8000
# or
netstat -ano | findstr :8000

# Kill it
kill -9 <PID>
# or change port in config.yaml: port: 8001
```

### "FAISS won't install"

```bash
# For Windows — install Visual C++ Build Tools
# For Linux:
sudo apt-get install libopenblas-dev

# Or use memory instead of faiss:
# In config.yaml: provider: memory
```

### "Model doesn't respond / Connection refused"

1. Check that the LLM server is running:
   ```bash
   curl http://localhost:11434/v1/models  # Ollama
   ```
2. Check `api_base` in `config.yaml` — port must match
3. Check logs: `tail -f data/app.log`

### "Out of memory" / "Killed"

Your model is too big for your RAM. Pick a smaller one:
- Instead of 8B → 3B model
- Instead of Q8 → Q4 quantization

### "Invalid Content-Length" / 413

File is too big. Increase the limit in `config.yaml`:
```yaml
security:
  max_body_size: 52428800  # 50 MB
```

### "ModuleNotFoundError" after update

```bash
pip install -e ".[faiss]" --force-reinstall
```

---

## Project structure after installation

```
ai-assistant/
├── .venv/                  # Virtual environment (don't touch)
├── data/                   # Your data (don't delete!)
│   ├── indices/            # Search indexes (FAISS)
│   ├── storage.db          # Chat history (SQLite)
│   ├── app.log             # Program logs
│   ├── tokenizers/         # Tokenizer cache
│   └── chat_exports/       # Saved conversations
├── sources/                # Folder for documents (create yourself)
│   ├── personal/
│   └── work/
├── config.yaml             # Your configuration (edit this)
├── config.example.yaml     # Example config (don't touch)
├── src/                    # Source code
├── tests/                  # Tests
├── scripts/                # Useful scripts
└── README.md               # This file
```

---

## Development

### Run tests
```bash
pytest                          # All tests
pytest -m "not online"          # Skip server tests
pytest -m "smoke"               # Only quick tests
```

### Code checks
```bash
ruff check src/                  # Style check
mypy src/                        # Type check
```

---

## License

Apache License 2.0. See [LICENSE](LICENSE).

---

## Solo maintenance note

This project is developed by a solo creator with extensive use of AI-assisted programming tools. The author defines the product vision, architecture, requirements, testing strategy, and development roadmap, while AI tools are used to accelerate implementation, refactoring, documentation, and experimentation. All design decisions, feature prioritization, and project direction remain under human supervision.
