# AI Assistant

Production-grade offline RAG framework for solo maintainers.

- **Offline-first**: works without cloud; your data never leaves your machine
- **Multilingual**: bge-m3 embedder; quality measured on Russian and English corpora — other scripts not yet measured
- **Namespace isolation**: separate knowledge bases that never cross-contaminate
- **Measured quality**: 17/17 contract + 9/9 chat e2e + 31/34 capability tests on 4GB VRAM (Qwen2.5-7B); full log: `docs/architecture.md` §14
- **Deterministic**: temperature 0.0 by default — verdicts reproduce byte-identically (one known 7B chat flake, see docs)
- **10-year maintainability**: boring code, explicit architecture, no magic

**Solo-maintained. Published as-is.**
**Created with AI assistance by a non-professional programmer.**

---

## Pipeline & Quality

Pipeline: retrieve (multi-query — the LLM generates 2 query variations; optional HyDE) → cross-encoder rerank (rank-only, never filters) → build context (token-budget aware) → generate (strict RAG: `[Document N]` citations, conflict reporting, "I don't know" when evidence is absent). Chunking is recursive (paragraphs → sentences → words); question condensation handles multi-turn.

Quality is measured, not assumed: `scripts/check_rag.py` — 51 cases (17 contract tests that must pass on any hardware, 34 capability tests whose quality depends on LLM size, chat e2e). The benchmark is the single source of truth for RAG quality; results, canon and the full hardware campaign live in `docs/architecture.md` §14; known limitations (open-synthesis recall, date honesty on undated atoms, 7B list formatting, the multi-turn-1 flake) in `docs/architecture.md` §14 and `docs/drift.md`.

---

## Hardware

Measured minimum: GTX 1650 (4GB VRAM) / 16GB RAM — Qwen2.5-7B-Instruct IQ4_XS, partial GPU offload (20 layers), 5–10 tok/s, 3–6 seconds per query; bge-m3 embedder and bge-reranker-v2-m3 on CPU. The 14B class requires 12GB+ VRAM (measured verdict, see the Hardware Ceiling Log). Full campaign history: `docs/architecture.md` §14.

---

## Quick Start

**Prerequisites**: Python 3.11+, `llama-server` (see [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases)), GGUF models.

```bash
git clone <repo-url> ai-assistant && cd ai-assistant
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -e ".[faiss]"        # runtime only
pip install -e ".[dev,faiss]"    # if you will run tests/lint (check_all)
cp config.example.yaml config.yaml
# Edit config.yaml: set llm.model, embedder.model, reranker.model, n_gpu_layers
python scripts/download_tokenizers.py
python run_servers.py
```

Always start and stop the stack via `run_servers.py`: it pins the working directory to the project folder. Launching uvicorn manually from another directory silently creates a new empty `data/` there.

**Documents**: place originals in `data/raw_documents/` — root is the default namespace, level-1 subfolders are namespaces, an `_atomize/` folder marks atomization intent; one home per file, no copies. Run `python scripts/prepare_docs.py` (or script-runner mode [1]) — parts land in `data/documents/` (files >150 KB split into ~30 KB parts, smaller pass as-is) and auto-index within 60 s. For faster indexing see the GPU embedding profile in `config.example.yaml`. Never edit `data/documents/` by hand: it is a mirror, and the reconcile treats hand-placed files as leftovers of vanished sources.

**Chat exports** (AI conversations, decision-heavy dialogs): MOVE the file into an `_atomize/` folder and run mode [2] (`python scripts/prepare_docs.py --full`) — the archivist LLM distills status-disciplined atoms (fact / decision with the exact user quote / recommendation / hypothesis), guarding against advice being read as a decision a year later (drift #67). Audit with mode [3] (`--validate`, read-only V1–V6); the producer itself reports only a run-total. Known 4B residuals: invented dates, run-to-run language flips (drift #87).

**Queries**: `[prefix] question` routes to a namespace (`[d]` = default; prefixes are configured in `namespaces:`). Without a prefix the chat is plain conversation — RAG is strictly opt-in.

Open http://localhost:8000/ui.

For GPU support and build-from-source instructions, see the [llama.cpp documentation](https://github.com/ggml-org/llama.cpp#build).

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
| `archivist` | Atom-extraction LLM profile for prepare_docs --full |
| `vector_store` | FAISS or memory, index path, dimension |
| `rag` | Pipeline steps, top_k, sources, token margin |
| `namespaces` | Per-namespace prefix, chunk size, prompt template |
| `security` | API key, admin endpoints, body size limits |
| `tokenizer` | Provider (`huggingface`, `tiktoken`) and model path |

Full reference in `config.example.yaml`.

---

## Running Tests

```bash
# Full check (ruff + mypy + tests + coverage + audits) — every
# Python file in the repo (src/, scripts/, tests/, launchers)
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
| `check_rag.py` results differ between runs | Usually environment changed: benchmark is deterministic (temp 0.0) — check config, model, or index state. One documented exception: multi-turn-1 on 7B is nondeterministic (see Known Limitations); re-run any other surprising red before classifying it. |
| Indexing never completes ("Auto-reindex timed out" loop) | Corpus exceeds the 600 s watcher window on the CPU embedder (~4 chunks/s). Split files via `scripts/prepare_docs.py` (parts ~30 KB) or switch to the indexing profile (GPU embedder, LLM at 10 layers — see config.yaml comments). |
| `HTTP request failed` at reindex start | Embedder server not up yet (startup race) or dead. Check `curl http://127.0.0.1:8081/health`; restart the stack. |
| "GPU indexing" seems slow / crashes | Verify the embedder actually launched on GPU: `ps aux \| grep bge-m3` must show exactly ONE `-ngl` flag, its value from config.yaml (drift #60: dual -ngl flags run the server in an unpredictable mode). |

---

## Project Structure

```
ai-assistant/
├── config.yaml            ← your configuration (git-ignored)
├── config.example.yaml    ← configuration template
├── pyproject.toml         ← dependencies and tooling
├── run_servers.py         ← starts LLM, embedder, reranker, API servers
├── run_servers.yaml       ← server launch configuration
├── run_scripts.py         ← interactive script runner (check_rag, prepare_docs, …)
├── src/ai_assistant/      ← core/ (domain, ports, prompts, pipeline), adapters/, features/, api/, ui/
├── tests/                 ← ~1000 tests (contracts, edge cases, integration, e2e)
├── scripts/               ← check_all, check_rag, check_llm, prepare_docs, download_tokenizers, …
├── docs/                  ← ai_rules.md, architecture.md, drift.md
├── data/                  ← runtime, git-ignored: raw_documents/, documents/ (mirror), indices/, storage.db, tokenizers/, app.log
└── vendor/                ← llama-server binary + GGUF models (git-ignored)
```

**You provide** (everything else is auto-created on first run):

1. `config.yaml` — copy from `config.example.yaml`; set model names, API endpoints, `n_gpu_layers` (0 = CPU, exact counts for partial offload — 20 for Qwen2.5-7B on 4GB VRAM, 99 = all layers), `rag.sources`.
2. `vendor/llama/llama-server` — from [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases).
3. `vendor/models/*.gguf` — LLM (Qwen2.5-7B IQ4_XS ~4.5GB), embedder (bge-m3 ~1.2GB), reranker (bge-reranker-v2-m3 ~0.5GB).
4. `data/raw_documents/` — your `.md` / `.txt` files (see Quick Start).

**Backups**: the git repo stores only code. Your data — `data/` (chat history, indices, documents) and `config.yaml` — is not in it. Copy both regularly; a dead disk is the one failure this project cannot recover from.

---

## Documentation

- `docs/ai_rules.md` — AI development constraints
- `docs/architecture.md` — architectural strategy, RAG philosophy, Hardware Ceiling Log
- `docs/drift.md` — drift log + FUTURE RISKS

---

## License

Apache License 2.0. See [LICENSE](LICENSE).
