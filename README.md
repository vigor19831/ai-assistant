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

### 3. Install dependencies

```bash
pip install -e ".[dev,faiss]"
pip install pytest-cov
```

### 4. Install llama.cpp

**Option A: Pre-built binaries (recommended)**

| OS | Command |
|----|---------|
| **Ubuntu/Debian** | `wget https://github.com/ggerganov/llama.cpp/releases/latest/download/llama.cpp-ubuntu-x64.deb && sudo dpkg -i llama.cpp-ubuntu-x64.deb` |
| **Arch/EndeavourOS** | `yay -S llama.cpp` |
| **Fedora** | `sudo dnf install llama.cpp` |
| **macOS** | `brew install llama.cpp` |
| **Windows** | Download `llama.cpp-win-x64.zip` from [GitHub Releases](https://github.com/ggerganov/llama.cpp/releases) |

Then copy binaries to the project:
```bash
mkdir -p vendor/llama
cp $(which llama-server) vendor/llama/ 2>/dev/null
cp $(which llama-cli) vendor/llama/ 2>/dev/null
# Windows: extract zip to vendor/llama/
```

**Option B: Build from source (GPU support, latest features)**

*Linux/macOS:*
```bash
mkdir -p vendor && cd vendor
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git llama_source
cd llama_source && mkdir build && cd build
cmake .. -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=OFF
cmake --build . -j8 --config Release
mkdir -p ../../llama
cp bin/llama-server bin/llama-cli ../../llama/
cd ../.. && rm -rf llama_source
```

*Windows (PowerShell):*
```powershell
mkdir -p vendor; cd vendor
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git llama_source
cd llama_source; mkdir build; cd build
cmake .. -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=OFF
cmake --build . -j8 --config Release
mkdir -p ../../llama
cp bin/Release/llama-server.exe bin/Release/llama-cli.exe ../../llama/
cd ../..; rm -rf llama_source
```

> **GPU support:** change `-DGGML_CUDA=OFF` to `ON`. Requires CUDA Toolkit (`sudo pacman -S cuda` on Arch, `sudo apt install nvidia-cuda-toolkit` on Ubuntu).

### 5. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:
- Set `llm.model` to your GGUF filename (e.g., `Qwen3-4B-Instruct-IQ4_XS`)
- Set `embedder.model` to your embedding GGUF filename
- Adjust `n_gpu_layers` for your hardware (0 = CPU only, 20-30 = partial GPU offload, 999 = all layers on GPU)

### 6. Download models

Place `.gguf` files in `vendor/models/`.

Recommended starter: **Qwen3-4B-Instruct** (IQ4_XS, ~2.5 GB, passes 11/16 RAG tests on 4 GB VRAM).

### 7. Download tokenizers

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

## Updating llama.cpp

**Pre-built:** repeat the install command for your OS, then copy new binaries to `vendor/llama/`.

**From source:**
```bash
cd vendor
git clone --depth 1 https://github.com/ggerganov/llama.cpp.git llama_source
cd llama_source && mkdir build && cd build
cmake .. -DBUILD_SHARED_LIBS=OFF -DGGML_CUDA=OFF
cmake --build . -j8 --config Release
cp bin/llama-server bin/llama-cli ../../llama/
cd ../.. && rm -rf llama_source
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
├── tests/                # 870+ tests
├── scripts/              # check_all.py, check_rag.py, etc.
├── vendor/               # External binaries and models
│   ├── llama/            # llama.cpp binaries
│   └── models/           # GGUF model files
├── config.yaml           # Your personal config (git-ignored)
├── config.example.yaml   # Template in repo
└── pyproject.toml        # Dependencies and tool settings
```

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
| `llm` | Model, API endpoint, sampling, GPU layers, context size |
| `embedder` | Embedding model, dimension, GPU layers |
| `reranker` | Reranker model and provider (`local` or `api`) |
| `vector_store` | FAISS or memory, index path, dimension |
| `rag` | Pipeline steps, top_k, sources, token margin |
| `namespaces` | Per-namespace prefix, chunk size, prompt template |
| `security` | API key, admin endpoints, body size limits |
| `tokenizer` | Provider (`huggingface`, `tiktoken`) and model path |

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

## RAG LLM Model Requirements

RAG quality is bottlenecked by the **LLM**, not the retriever. Small models (3–5B) handle simple Q&A but struggle with multi-hop reasoning, conflict resolution, and noise rejection.

**Key insight:** larger models follow instructions better and reject noise more reliably. For the same retrieval quality, a 7-8B model can score 14-16/16 on RAG tests where a 4B model scores 8-11/16. The difference is not in "knowledge" — it's in **instruction discipline**.

| Use Case | 4B (Qwen3) | 7-8B (Qwen3) | 14-32B |
|----------|-----------|-------------|--------|
| Simple Q&A | ✓ Good | ✓ Excellent | ✓ Excellent |
| Multi-hop reasoning | ✗ Unreliable | ✓ Good | ✓ Excellent |
| Noise rejection | ✗ Weak | ✓ Good | ✓ Excellent |
| Conflict resolution | ✗ Unreliable | ✓ Good | ✓ Excellent |
| Cross-lingual retrieval | △ Mixed | ✓ Good | ✓ Excellent |
| RAG test score (typical) | 11/16 | 14-16/16 | 16/16 |

VRAM (Q4_K_M): 4B ~3–4 GB, 7–8B ~5–6 GB, 14B ~9–10 GB, 32B ~20 GB.

**For 4 GB VRAM GPUs:** a 7-8B model with partial GPU offload (n_gpu_layers=15-20) will be slower (5-10 tok/s) but dramatically better at RAG than any 4B model running fully on GPU.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `libllama-server-impl.so: not found` | Use pre-built binary or rebuild with `-DBUILD_SHARED_LIBS=OFF` |
| mypy fails on Python 3.14+ | Use Python 3.11–3.13, or wait for mypy update |
| `faiss-cpu not installed` | `pip install faiss-cpu` |
| Servers not responding | Check `data/llama.log`; ensure `llama-server` is installed |
| RAG answers wrong despite correct retrieval | Try larger model or reduce `chunk_size` / `temperature` |
| `401 Unauthorized` on native endpoints | Add `Authorization: Bearer <key>` header |

---

## Documentation

- `docs/ai_rules.md` — AI development constraints
- `docs/architecture.md` — architectural strategy and RAG philosophy
- `docs/drift.md` — known architectural drift log

## License

Apache License 2.0. See [LICENSE](LICENSE).
