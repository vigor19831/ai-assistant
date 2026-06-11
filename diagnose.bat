@echo off
echo === AI Assistant Diagnostic ===

echo.
echo [1] Python version:
python --version

echo.
echo [2] Config check:
python -c "from ai_assistant.core.config import load_config; c=load_config(); print('LLM:', c.llm.provider, c.llm.model); print('Embedder:', c.embedder.provider, c.embedder.model); print('Dims match:', c.embedder.dim == c.vector_store.dim)"

echo.
echo [3] Server check:
curl -s http://127.0.0.1:8080/v1/models >nul 2>&1 && echo LLM server: OK || echo LLM server: FAILED
curl -s http://127.0.0.1:8081/v1/models >nul 2>&1 && echo Embedder server: OK || echo Embedder server: FAILED

echo.
echo [4] Index files:
dir /s /b data\indices 2>nul || echo No indices found

echo.
echo [5] Smoke test:
python scripts\check_smoke.py

echo.
echo === Done ===
pause