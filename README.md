# AI Assistant

Production-grade offline RAG framework for solo maintainers.

- **Offline-first**: works without cloud, your data never leaves your machine
- **Language coverage**: multilingual by design (bge-m3 embedder); quality measured on Russian and English corpora — other scripts not yet measured
- **Namespace isolation**: separate knowledge bases that never cross-contaminate
- **Measured quality**: 17/17 contract tests + 30–31/34 capability tests + 8–9/9 chat e2e on 4GB VRAM hardware (Qwen2.5-7B, llama.cpp build of 2026-09-07)
- **Deterministic**: temperature 0.0 by default — verdicts reproduce byte-identically (one known 7B chat flake, see docs)
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

- **51 test cases** via `check_rag.py` — single source of truth for RAG quality.
- **17 contract tests** (must pass on any hardware).
- **34 future capability tests** (quality depends on LLM size).
- **Chat e2e tests** (prefix conversation, contract).
- **Hardware Ceiling Log**: honest documentation of what works on your GPU.

---

## Quality Assurance

Every release is validated against `check_rag.py` — a 51-case benchmark covering retrieval, ranking, generation, and edge cases.

### Current Results (Qwen2.5-7B-Instruct IQ4_XS, 20 GPU layers, 4GB VRAM)

Measured on the llama.cpp build of 2026-09-07. The engine was updated
2026-09-10; only the 4B profile is re-baselined on the new build so far
(16/17 + 7/9 + 28/34, ×2 stable — see `docs/drift.md`). The 7B canon
moves to the new build after the next re-baseline ×2.

Config: context window 8192, `max_context_tokens` 4800,
`history_limit` 6, token margin 0.10 (see `docs/drift.md` #68 —
the window-math method; values rebalanced 2026-09-03, verified
on check_rag both 7B and 4B profiles).

```
CONTRACT: 17/17 passed
CHAT PREFIX E2E: 8–9/9 passed (multi-turn-1 nondeterministic — see docs)
CHAT CONTRACT: 2/2 passed
CHAT FUTURE: 6–7/7 passed
KNOWN LIMITATIONS TRIGGERED: 3–4
FUTURE CAPABILITIES: 30–31/34 passed
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

### Known Limitations (class-level; the benchmark counts 3–4 triggered tests on 7B)

- Open-synthesis recall ("What do I like?"-class queries): top_k
  retrieval cannot surface every expected fact from a large namespace —
  retrieval-side, model-independent (drift #84).
- Date honesty on undated atoms: asked "when" over atoms with no date,
  the 4B answers "what" instead, the 7B merges unrelated facts into a
  temporal answer (drift #84/#85; cure documented — stronger model or
  generation-side guard, not another prompt iteration).
- Strict formatting on open synthesis: the 7B trims the requested list
  format ("list my hobbies"-class) — model format quirk.
- 4B-specific: typo bridging ("Pithon") and option prioritization are
  parameter-bound; the 7B passes both (measured).
- multi-turn-1 on the benchmark prefix: nondeterministic on 7B — the
  one known exception to verdict determinism; live multi-turn is green
  (see `docs/architecture.md` §14).

Question condensation was fixed by a prompt contract (drift #58);
conversation recall passes. The two-tier fallback documented in
`docs/architecture.md` §14 (7B primary / Qwen3.5-4B RAG-heir /
Phi-4-mini chat-fallback) covers the residual gaps.

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

### Recommended (12GB+ VRAM)

| Component | Value |
|-----------|-------|
| GPU | 12GB+ VRAM (e.g. RTX 3060 12GB) |
| LLM | Qwen2.5-14B-Instruct Q4_K_M (~9GB, full GPU offload; the 14B class needs 12GB+ VRAM — measured verdict, see Hardware Ceiling Log) |
| Performance | 20–30 tok/s, 1–2 seconds per query (estimate; measured on the 4GB minimum: 5–10 tok/s) |

Full campaign history, verdicts (King / Heir / Rejected), per-run
details and the throne decision: `docs/architecture.md` §14.

---

## Quick Start

**Prerequisites**: Python 3.11+, `llama-server` (see [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases)), GGUF models.

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
Always start and stop the stack via `run_servers.py`: it pins the
working directory to the project folder. Launching uvicorn manually
from another directory silently creates a new empty `data/` there.

Large corpus (>150 KB files): split first via scripts/prepare_docs.py
(data/raw_documents/ -> data/documents/). For faster indexing see the
GPU embedding profile in config.example.yaml (embedder section).

Chat exports (AI conversations, decision-heavy dialogs): MOVE the
file into an `_atomize/` folder (raw_documents/ root, or inside a
namespace folder) and run mode [2] in the
script runner (same as `python scripts/prepare_docs.py --full`) —
the archivist LLM distills status-disciplined atoms (fact / decision
with exact user quote / recommendation / hypothesis). Atoms guard
against advice being read as a decision a year later (measured
cross-model, drift #67). Location is the intent: raw_documents/ root
files are split-only, a level-1 subfolder is a namespace (mirrors
into documents/{ns}/), an _atomize/ folder marks atomization; one
home per file, no copies (drift #108-#110). Queries reach a namespace
by prefix: `[w] question` (namespaces: in config.yaml). Then audit
them: `python
scripts/prepare_docs.py --validate` — a read-only V1–V6 contract
check (drift #87); the producer itself prints only a run-total error
count pointing to the audit. Known 4B residuals: stable invented
dates and run-to-run language flips (drift #87).

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
| Indexing never completes ("Auto-reindex timed out" loop) | Corpus exceeds the 600 s watcher window on the CPU embedder (~4 chunks/s). Split files via `scripts/prepare_docs.py` (parts ~12 KB) or switch to the indexing profile (GPU embedder, LLM at 10 layers — see config.yaml comments). |
| `HTTP request failed` at reindex start | Embedder server not up yet (startup race) or dead. Check `curl http://127.0.0.1:8081/health`; restart the stack. |
| "GPU indexing" seems slow / crashes | Verify the embedder actually launched on GPU: `ps aux \| grep bge-m3` must show exactly ONE `-ngl` flag, its value from config.yaml (drift #60: dual -ngl flags run the server in an unpredictable mode). |

---

## Project Structure

```
ai-assistant/
├── config.yaml ← Your personal configuration (git-ignored)
├── config.example.yaml ← Configuration template
├── pyproject.toml ← Dependencies and tooling
├── run_servers.py ← Starts LLM, embedder, reranker, API servers
├── run_servers.yaml ← Server launch configuration
├── run_scripts.py ← Interactive script runner (check_rag, prepare_docs, etc.)
├── src/ ← Application source code (core: domain, ports, prompts; adapters; features; api; ui)
├── tests/ ← ~1000 tests
├── scripts/ ← Utility scripts
├── docs/ ← Architecture and rules documentation
├── data/ ← Runtime data (git-ignored, auto-created)
└── vendor/ ← External binaries and models (git-ignored)
```

### Directory Descriptions

| Directory | Purpose | Auto-created? |
|-----------|---------|---------------|
| `src/ai_assistant/` | Application code: `core/` (domain, ports, prompts, pipeline), `adapters/` (LLM, embedder, reranker, vector store), `features/` (chat, RAG), `api/` (FastAPI routes), `ui/` (static web interface) | No |
| `tests/` | ~1000 tests covering contracts, edge cases, integration, e2e | No |
| `scripts/` | Utility scripts: `check_all.py` (full check), `check_rag.py` (RAG quality benchmark), `check_llm.py` (LLM connectivity), `download_tokenizers.py` (tokenizer files), `prepare_docs.py` (split large files; --atoms extracts status-disciplined knowledge atoms; --validate audits the atom contract V1–V6) | No |
| `docs/` | `ai_rules.md` (AI constraints), `architecture.md` (strategy + RAG philosophy), `drift.md` (known compromises) | No |
| `data/` | Runtime data: `indices/` (FAISS vector indices per namespace), `storage.db` (SQLite chat history), `documents/` (your docs for RAG), `tokenizers/` (downloaded tokenizer files), `app.log` (application log) | Yes (on first run) |
| `data/documents/` | Your `.md` / `.txt` files for RAG. Auto-indexed every 60s when server is running | You create it |
| `data/indices/` | FAISS vector indices. One subdirectory per namespace | Yes (on first index) |
| `data/tokenizers/` | Downloaded tokenizer files. Run `scripts/download_tokenizers.py` to populate | Yes (via script) |
| `vendor/llama/` | `llama-server` binary. Download from [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases) | You provide it |
| `vendor/models/` | GGUF model files: LLM (~4.5GB), embedder (~1.2GB), reranker (~0.5GB) | You provide it |
| `config.yaml` | Your personal settings: models, API endpoints, GPU layers. Copy from `config.example.yaml` and edit | You create it |

### What You Must Provide

After cloning the repo:

1. **`config.yaml`** — `cp config.example.yaml config.yaml`, then edit:
   - `llm.model`, `embedder.model`, `reranker.model` — your GGUF filenames
   - `llm.api_base`, `embedder.api_base`, `reranker.api_base` — server URLs
   - `llm.n_gpu_layers` — layer count placed on GPU. 0 = CPU, exact counts for
     partial offload (e.g. 20 for Qwen2.5-7B on 4GB VRAM — see Hardware Ceiling
     Log), 99 = all layers (8GB+ VRAM)
   - `rag.sources` — path to your documents folder

2. **`vendor/llama/llama-server`** — download from [llama.cpp releases](https://github.com/ggerganov/llama.cpp/releases) or build from source.

3. **`vendor/models/*.gguf`** — download GGUF models:
   - LLM: Qwen2.5-7B-Instruct IQ4_XS (~4.5GB) or larger
   - Embedder: bge-m3 (~1.2GB)
   - Reranker: bge-reranker-v2-m3 (~0.5GB)

4. **`data/documents/`** — create this folder and put your `.md` / `.txt` files here. They auto-index when the server starts. Files >150 KB: place originals in `data/raw_documents/` and run `python scripts/prepare_docs.py` — large single files exceed the indexing window and never complete.

Everything else (`data/indices/`, `data/storage.db`, `data/tokenizers/`) is created automatically on first run.

**Backups**: the git repo stores only code. Your data — `data/` (chat
history, indices, documents) and `config.yaml` — is not in it. Copy
both regularly; a dead disk is the one failure this project cannot
recover from.

---

## Documentation

- `docs/ai_rules.md` — AI development constraints
- `docs/architecture.md` — architectural strategy and RAG philosophy
- `docs/drift.md` — known architectural drift log

---

## License

Apache License 2.0. See [LICENSE](LICENSE).
