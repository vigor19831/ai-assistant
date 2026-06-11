# diagnose.ps1
$ErrorActionPreference = "Stop"

Write-Host "=== AI Assistant Diagnostic ===" -ForegroundColor Green

# 1. Python версия
Write-Host "`n[1] Python check..." -ForegroundColor Cyan
python --version
if ($LASTEXITCODE -ne 0) { Write-Host "Python не найден!" -ForegroundColor Red; exit 1 }

# 2. Зависимости
Write-Host "`n[2] Dependencies check..." -ForegroundColor Cyan
python -c "import fastapi; print('fastapi:', fastapi.__version__)"
python -c "import httpx; print('httpx: OK')"
python -c "import uvicorn; print('uvicorn: OK')"
python -c "import faiss; print('faiss: OK')" 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "faiss НЕ установлен (опционально)" -ForegroundColor Yellow }

# 3. Конфигурация
Write-Host "`n[3] Config check..." -ForegroundColor Cyan
python -c @"
from ai_assistant.core.config import load_config
c = load_config()
print(f'LLM provider: {c.llm.provider}')
print(f'LLM model: {c.llm.model}')
print(f'LLM api_base: {c.llm.api_base}')
print(f'Embedder provider: {c.embedder.provider}')
print(f'Embedder model: {c.embedder.model}')
print(f'Embedder api_base: {c.embedder.api_base}')
print(f'Embedder dim: {c.embedder.dim}')
print(f'VectorStore dim: {c.vector_store.dim}')
print(f'VectorStore provider: {c.vector_store.provider}')
if c.embedder.dim != c.vector_store.dim:
    print('ERROR: embedder.dim != vector_store.dim!')
"@

# 4. Проверка серверов
Write-Host "`n[4] Server connectivity..." -ForegroundColor Cyan
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8080/v1/models" -TimeoutSec 5
    Write-Host "LLM server (8080): OK" -ForegroundColor Green
    $r.Content | ConvertFrom-Json | Select-Object -First 3
} catch {
    Write-Host "LLM server (8080): FAILED - $($_.Exception.Message)" -ForegroundColor Red
}

try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8081/v1/models" -TimeoutSec 5
    Write-Host "Embedder server (8081): OK" -ForegroundColor Green
    $r.Content | ConvertFrom-Json | Select-Object -First 3
} catch {
    Write-Host "Embedder server (8081): FAILED - $($_.Exception.Message)" -ForegroundColor Red
}

# 5. Проверка индексов
Write-Host "`n[5] Index files..." -ForegroundColor Cyan
if (Test-Path .\data\indices) {
    Get-ChildItem .\data\indices -Recurse | Select-Object Name, Length
} else {
    Write-Host "No indices found" -ForegroundColor Yellow
}

# 6. Smoke test
Write-Host "`n[6] Running smoke test..." -ForegroundColor Cyan
python scripts\check_smoke.py

Write-Host "`n=== Diagnostic complete ===" -ForegroundColor Green