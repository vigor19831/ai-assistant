from pathlib import Path

import httpx

root = Path(__file__).parent.parent
cfg_path = root / "config.yaml"

print(f"Config exists: {cfg_path.exists()}")

llm = {}

try:
    import yaml

    with open(cfg_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    llm = cfg.get("llm", {})
    print(f"Provider: {llm.get('provider')}")
    print(f"API base: {llm.get('api_base')}")
    print(f"Model: {llm.get('model')}")
except Exception as e:
    print(f"Config error: {e}")

api_base = llm.get("api_base", "http://127.0.0.1:11434/v1")
model = llm.get("model", "unknown")

# Проверяем доступность Ollama
print(f"\nChecking Ollama at {api_base}...")
try:
    resp = httpx.get(f"{api_base}/models", timeout=5.0)
    print(f"Ollama API reachable: {resp.status_code < 500}")
except Exception as e:
    print(f"Ollama not reachable: {e}")

# Проверяем конкретную модель
try:
    resp = httpx.post(
        f"{api_base}/chat/completions",
        json={
            "model": model,
            "messages": [{"role": "user", "content": "Hi"}],
            "max_tokens": 10,
        },
        timeout=30.0,
    )
    print(f"Model '{model}' responds: {resp.status_code == 200}")
    if resp.status_code != 200:
        print(f"Response: {resp.text[:200]}")
except Exception as e:
    print(f"Model check failed: {e}")

print("\nTroubleshooting:")
print("  1. Is 'ollama serve' running?")
print("  2. Did you run 'ollama pull {model}'?")
print("  3. Is AI_LLM_API_BASE env var set correctly?")
