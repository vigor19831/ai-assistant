## TODO ##
---
[ ] <Specific Action/Title> | <Reason/Why this is a problem> | <Affected Files> | <How to verify/Test criteria>
---

[ ] Unpin numpy <2.0.0 | numpy 2.0+ released, missing security patches and performance improvements | pyproject.toml | Test: pytest suite passes with numpy>=2.0.0; FAISS index operations correct
[ ] Extract HTTP client base to adapters/_http_base.py | 3rd HTTP adapter (MCP/A2A) will duplicate httpx setup, error-prone | adapters/_http_base.py (new), adapters/embedder_openai_compatible.py, adapters/llm_openai_compatible.py | Test: OpenAICompatibleEmbedder still works; no behavior change; _http_base covered by unit test
[ ] Move adapter imports from factory.py to __init__.py | Adding new adapter requires editing factory.py despite @register decorator; violates "explicit but scalable" | adapters/__init__.py, adapters/factory.py | Test: create_adapter works for all existing adapters; new adapter can be added by import only
