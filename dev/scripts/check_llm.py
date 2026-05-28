#!/usr/bin/env python3
"""Check LLM server — universal, works with any OpenAI-compatible API."""

import os
import sys
from pathlib import Path

import httpx

from ai_assistant.core.config import load_config


def check_llm() -> int:
    """Check LLM connectivity. Returns 0 if check completed, 1 on internal error."""
    config_path = os.getenv("AI_CONFIG_PATH", "config.yaml")
    try:
        cfg = load_config(config_path)
    except Exception as e:
        print(f"Config error: {e}")
        return 1

    api_base = cfg.llm.api_base.rstrip("/")
    model = cfg.llm.model

    print(f"Provider: {cfg.llm.provider}")
    print(f"API base: {api_base}")
    print(f"Model: {model}\n")
    print(f"Checking LLM API at {api_base}...")

    # 1. Check /v1/models
    try:
        resp = httpx.get(f"{api_base}/models", timeout=5.0)
        reachable = resp.status_code == 200
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
            ok = False
    else:
        print("Skipping model check — API not reachable")
        ok = False

    if not ok:
        print("\nStatus: LLM server is not running or not responding")
        print("\nTo start the server:")
        print("  1. llama-server.exe -m model.gguf --port 8080")
        print("  2. ollama serve")
        print("  3. Or check config.yaml -> llm.api_base")
        print("\nTroubleshooting:")
        print("  - Verify the model name matches what the server expects")
        print("  - Check server logs for errors")

    return 0  # Скрипт отработал, статус сервера определён


if __name__ == "__main__":
    sys.exit(check_llm())
