# AI Assistant

Production-grade offline RAG framework for solo maintainers.

- **Offline-first**: works without cloud, your data never leaves your machine
- **Namespace isolation**: separate knowledge bases that never cross-contaminate
- **Measured quality**: 17/17 contract tests pass on 4GB VRAM hardware
- **10-year maintainability**: boring code, explicit architecture, no magic

**Solo-maintained. Published as-is.**
**Created with AI assistance by a non-professional programmer.**

---

## RAG Capabilities

### Retrieval

- **Multi-query retrieval**: generates 2 query variations via LLM, retrieves for each, deduplicates — better recall for synonyms and rephrasings.
- **HyDE (Hypothetical Document Embedding)**: generates hypothetical answer, embeds it, retrieves by that embedding.
- **Recursive chunking**: splits by paragraphs → sentences → words, preserves context boundaries.
- **Namespace isolation**: each namespace is a separate knowledge base, no cross-contamination.

### Ranking

- **Cross-encoder reranking**: `bge-reranker-v2-m3` reorders candidates by relevance (rank-only, no threshold filtering).
- **Top-k selection**: configurable number of chunks to include in context.

### Generation

- **Condense question**: rewrites follow-up questions using chat history for multi-turn conversations.
- **Token budget management**: adaptive margin based on context window size.
- **Source citation**: every answer includes `[Document N]` references.
- **Conflict detection**: reports contradictions instead of silently choosing one.

### Quality Assurance

- **43 automated tests** via `check_rag.py` — single source of truth for RAG quality.
- **17 contract tests** (must pass on any hardware).
- **26 future capability tests** (quality depends on LLM size).
- **Hardware Ceiling Log**: honest documentation of what works on your GPU.

---

## Quality Assurance

Every release is validated against `check_rag.py` — a 43-test benchmark covering retrieval, ranking, generation, and edge cases.

### Current Results (Qwen2.5-7B-Instruct IQ4_XS, 4GB VRAM)

```
CONTRACT: 17/17 passed
CHAT PREFIX E2E: 7/9 passed
  CHAT CONTRACT: 2/2 passed
  CHAT FUTURE: 5/7 passed
KNOWN LIMITATIONS TRIGGERED: 9
FUTURE CAPABILITIES: 17/26 passed
```

### What Contract Tests Verify

- Direct retrieval with source citation.
- Cross-namespace isolation (no data leakage).
- Semantic synonym retrieval ("hue" → "color").
- Multi-hop reasoning (favorite color → programming language).
- Conflict detection (contradictory documents).
- Cross-lingual retrieval (English query → Russian document).
- Prompt injection resistance.
- Token budget truncation.
- Empty query and invalid namespace handling.

### Known Limitations (Hardware-Dependent)

9 tests fail on 4GB VRAM due to LLM size, not code quality:

- Noise rejection (weak models include irrelevant chunks).
- Multi-turn follow-up resolution (requires better context understanding).
- Open synthesis from multiple chunks (requires larger context window).

**Expected fix**: LLM upgrade to Qwen2.5-14B or DeepSeek-R1-Distill-Qwen-7B. No pipeline changes required.

---

## Hardware Requirements

### Minimum (4GB VRAM)

| Component | Value |
|-----------|-------|
| GPU | GTX 1650 or equivalent (4GB VRAM) |
| RAM | 16GB |
| LLM | Qwen2.5-7B-Instruct IQ4_XS (~4.5GB, partial GPU offload) |
| Embedder | bge-m3 (CPU or GPU) |
| Reranker | bge-reranker-v2-m3 (CPU) |
| Performance | 5–10 tok/s, 3–6 seconds per query |

### Recommended (8GB+ VRAM)

| Component | Value |
|-----------|-------|
| GPU | RTX 3060 or better (8GB+ VRAM) |
| LLM | Qwen2.5-14B-Instruct Q4_K_M (~9GB, full GPU offload) |
| Performance | 20–30 tok/s, 1–2 seconds per query |

### Hardware Ceiling Log

| Date | Hardware | LLM | Result | Limitation |
|------|----------|-----|--------|------------|
| 2026-08-14 | GTX 1650 4GB | Qwen2.5-7B IQ4_XS | 17/17 PASS + 9 known limitations | multihop, noise rejection require ≥8B params |
| 2026-08-12 | GTX 1650 4GB | Qwen3-4B Q5_K_M | 13/17 PASS + 12 known limitations | 4B weaker than 7B on RAG tasks |
| 2026-07-13 | GTX 1650 4GB | gemma-4-e2b-it | 6/13 PASS | multihop, noise rejection, open synthesis require ≥8B params |

**Key insight**: RAG quality is bottlenecked by LLM instruction discipline, not retrieval quality. A 7–8B model scores 16/17 where a 4B model scores 13/17 on the same retrieval.

---

## Quick Start

**Prerequisites**: Python 3.11+, `llama-server` (see [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases)), GGUF models.

```bash
git clone <repo-url> ai-assistant && cd ai-assistant
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[dev,faiss]"
cp config.example.yaml config.yaml
# Edit config.yaml: set llm.model, embedder.model, reranker.model, n_gpu_layers
python scripts/download_tokenizers.py
python run_servers.py
```

Open http://localhost:8000/ui.

For GPU support and build-from-source instructions, see the [llama.cpp documentation](https://github.com/ggerganov/llama.cpp#build).

---

## API Examples

### OpenAI-compatible chat

```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen","messages":[{"role":"user","content":"Hello"}]}'
```

### RAG query (native)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer local" \
  -d '{"query":"[d] what is the architecture?"}'
```

---

## Configuration

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

Full reference in `config.example.yaml`.

---

## Running Tests

```bash
# Full check (ruff + mypy + tests + coverage)
python scripts/check_all.py

# Tests only
python -m pytest tests/ -x -q

# RAG quality benchmark
python scripts/check_rag.py
```

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
| `check_rag.py` results fluctuate ±1 test | Normal GPU non-determinism. Run 3 times and take majority. |

---

## Project Structure

```
ai-assistant/
├── config.yaml ← Your personal configuration (git-ignored)
├── config.example.yaml ← Configuration template
├── pyproject.toml ← Dependencies and tooling
├── run_servers.py ← Starts LLM, embedder, reranker, API servers
├── run_servers.yaml ← Server launch configuration
├── src/ ← Application source code
├── tests/ ← 850+ tests
├── scripts/ ← Utility scripts
├── docs/ ← Architecture and rules documentation
├── data/ ← Runtime data (git-ignored, auto-created)
├── vendor/ ← External binaries and models (git-ignored)
└── ui/ ← Static web interface
```

### Directory Descriptions

| Directory | Purpose | Auto-created? |
|-----------|---------|---------------|
| `src/ai_assistant/` | Application code: `core/` (domain, ports), `adapters/` (LLM, embedder, reranker, vector store), `features/` (chat, RAG), `api/` (FastAPI routes) | No |
| `tests/` | 870+ tests covering contracts, edge cases, integration, e2e | No |
| `scripts/` | Utility scripts: `check_all.py` (full check), `check_rag.py` (RAG quality benchmark), `check_llm.py` (LLM connectivity), `download_tokenizers.py` (tokenizer files), `index_documents.py` (manual indexing) | No |
| `docs/` | `ai_rules.md` (AI constraints), `architecture.md` (strategy + RAG philosophy), `drift.md` (known compromises) | No |
| `data/` | Runtime data: `indices/` (FAISS vector indices per namespace), `storage.db` (SQLite chat history), `documents/` (your docs for RAG), `tokenizers/` (downloaded tokenizer files), `app.log` (application log) | Yes (on first run) |
| `data/documents/` | Your `.md` / `.txt` files for RAG. Auto-indexed every 60s when server is running | You create it |
| `data/indices/` | FAISS vector indices. One subdirectory per namespace | Yes (on first index) |
| `data/tokenizers/` | Downloaded tokenizer files. Run `scripts/download_tokenizers.py` to populate | Yes (via script) |
| `vendor/llama/` | `llama-server` binary. Download from [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases) | You provide it |
| `vendor/models/` | GGUF model files: LLM (~4.5GB), embedder (~1.2GB), reranker (~0.5GB) | You provide it |
| `ui/` | Static web interface served at `/ui` | No |
| `config.yaml` | Your personal settings: models, API endpoints, GPU layers. Copy from `config.example.yaml` and edit | You create it |

### What You Must Provide

After cloning the repo:

1. **`config.yaml`** — `cp config.example.yaml config.yaml`, then edit:
   - `llm.model`, `embedder.model`, `reranker.model` — your GGUF filenames
   - `llm.api_base`, `embedder.api_base`, `reranker.api_base` — server URLs
   - `llm.n_gpu_layers` — adjust for your VRAM (0 = CPU, 20-30 = partial GPU, 999 = full GPU)
   - `rag.sources` — path to your documents folder

2. **`vendor/llama/llama-server`** — download from [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases) or build from source.

3. **`vendor/models/*.gguf`** — download GGUF models:
   - LLM: Qwen2.5-7B-Instruct IQ4_XS (~4.5GB) or larger
   - Embedder: bge-m3 (~1.2GB)
   - Reranker: bge-reranker-v2-m3 (~0.5GB)

4. **`data/documents/`** — create this folder and put your `.md` / `.txt` files here. They auto-index when the server starts.

Everything else (`data/indices/`, `data/storage.db`, `data/tokenizers/`) is created automatically on first run.

---

## Documentation

- `docs/ai_rules.md` — AI development constraints
- `docs/architecture.md` — architectural strategy and RAG philosophy
- `docs/drift.md` — known architectural drift log

---

## License

Apache License 2.0. See [LICENSE](LICENSE).
