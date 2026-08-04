# AI Assistant

Local AI assistant framework. FastAPI + RAG with namespaces.
Offline-first, OpenAI-compatible LLM/embedder adapters.

**Solo-maintained. Published as-is.**

---

## Requirements

- Python 3.11+
- llama.cpp server or any OpenAI-compatible API
- GGUF models (LLM required; embedder and reranker optional)

---

## Quick Start

### 1. Clone and enter project

```bash
git clone <repo-url> ai-assistant
cd ai-assistant
```

### 2. Create virtual environment

**Linux/macOS:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows:**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install

```bash
pip install -e ".[dev,faiss]"
pip install pytest-cov
```

### 4. Build llama.cpp (static, no shared library dependencies)

**Linux/macOS:**
```bash
mkdir -p vendor
cd vendor
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git llama_source
cd llama_source
mkdir build && cd build
cmake .. -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=OFF
cmake --build . -j8 --config Release
mkdir -p ../../llama
cp bin/llama-server bin/llama-cli ../../llama/
cd ../..
rm -rf llama_source
```

**Windows (PowerShell):**
```powershell
mkdir -p vendor
cd vendor
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git llama_source
cd llama_source
mkdir build && cd build
cmake .. -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=OFF
cmake --build . -j8 --config Release
mkdir -p ../../llama
cp bin/Release/llama-server.exe bin/Release/llama-cli.exe ../../llama/
cd ../..
rm -rf llama_source
```

> **GPU support:** change `OFF` to `ON` for `-DGGML_CUDA`. Requires CUDA Toolkit installed.

### 5. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:
- Set `llm.model` to your GGUF filename
- Set `embedder.model` to your embedding GGUF filename
- Adjust `n_gpu_layers` for your hardware (0 = CPU only)

### 6. Download models

Place `.gguf` files in `vendor/models/`.

### 7. Download tokenizers (for tiktoken)

```bash
python scripts/download_tokenizers.py
```

### 8. Start servers

```bash
python run_servers.py
```

Open http://localhost:8000/ui.

### 9. Verify

```bash
python scripts/check_all.py
```

---

## Project Structure

```
.
├── src/ai_assistant/     # Application code
│   ├── core/             # Domain, ports, config
│   ├── adapters/         # LLM, embedder, reranker, vector store
│   ├── features/         # Chat, RAG
│   └── api/              # FastAPI routes, middleware
├── tests/                # 862 tests
├── scripts/              # check_all.py, check_rag.py, etc.
├── vendor/               # External binaries and models
│   ├── llama/            # llama.cpp static binaries
│   └── models/           # GGUF model files
├── config.yaml           # Your personal config (git-ignored)
├── config.example.yaml   # Template in repo
└── pyproject.toml        # Dependencies and tool settings
```

---

## Updating llama.cpp

**Linux/macOS:**
```bash
cd vendor
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git llama_source
cd llama_source && mkdir build && cd build
cmake .. -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=OFF
cmake --build . -j8 --config Release
cp bin/llama-server bin/llama-cli ../../llama/
cd ../.. && rm -rf llama_source
```

**Windows:** same, but copy from `bin/Release/`.

---

## Running Tests

```bash
# Full check (ruff + mypy + tests + coverage)
python scripts/check_all.py

# Tests only
python -m pytest tests/ -x -q

# RAG quality
python scripts/check_rag.py
```

---

## Configuration Reference

| Section | Purpose |
|---------|---------|
| `llm` | Model, API endpoint, sampling, GPU layers |
| `embedder` | Embedding model, dimension, GPU layers |
| `reranker` | Reranker model and provider |
| `vector_store` | FAISS or memory, index path, dimension |
| `rag` | Pipeline steps, sources |
| `namespaces` | Per-namespace prefix, chunk size, prompt |
| `security` | API key, admin endpoints |

---

## API Examples

**OpenAI-compatible chat:**
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Hello"}]}'
```

**RAG query (native):**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query":"[m] what is the architecture?", "namespace":"main"}'
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `libllama-server-impl.so: not found` | Rebuild with `-DBUILD_SHARED_LIBS=OFF` |
| mypy fails on Python 3.14+ | Use Python 3.11–3.13, or wait for mypy update |
| `faiss-cpu not installed` | `pip install faiss-cpu` |
| Servers not responding | Check `data/llama.log` |
| RAG answers wrong | Try larger model or reduce `chunk_size` / `temperature` |

---

## Documentation

- `docs/ai_rules.md` — AI development constraints
- `docs/architecture.md` — architectural strategy and RAG philosophy
- `docs/drift.md` — known architectural drift log

## License

Apache License 2.0. See [LICENSE](LICENSE).
