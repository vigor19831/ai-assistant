#!/usr/bin/env python3
"""Check LLM server — universal, works with any OpenAI-compatible API."""

from __future__ import annotations

import os
from pathlib import Path

import httpx

root = Path(__file__).parent.parent
cfg_path = root.parent / "config.yaml"

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

# Priority: env var → config → localhost default
api_base = os.getenv(
    "AI_LLM_API_BASE", llm.get("api_base", "http://127.0.0.1:8080/v1")
).rstrip("/")
model = llm.get("model", "unknown")

print(f"\nChecking LLM API at {api_base}...")

# 1. Check /v1/models
try:
    resp = httpx.get(f"{api_base}/models", timeout=5.0)
    reachable = resp.status_code < 500
    print(f"API reachable: {reachable} (status {resp.status_code})")
except Exception as e:
    print(f"API not reachable: {e}")
    reachable = False

# 2. Check model response via /v1/chat/completions
if reachable:
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
        ok = resp.status_code == 200
        print(f"Model '{model}' responds: {ok}")
        if not ok:
            print(f"Response: {resp.text[:200]}")
    except Exception as e:
        print(f"Model check failed: {e}")
else:
    print("Skipping model check — API not reachable")

print("\nTroubleshooting:")
print("  1. Ensure your LLM server is running")
print("  2. Check config.yaml -> llm.api_base or set AI_LLM_API_BASE env var")
print("  3. Verify the model name matches what the server expects")
print("  4. Check server logs for errors")
