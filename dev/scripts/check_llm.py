#!/usr/bin/env python3
"""Check LLM server — universal, works with any OpenAI-compatible API.

Returns 0 if LLM server is reachable and responds to chat completions.
Returns 1 on internal error or if the server is unreachable / non-responsive.
"""

import os
import sys

import httpx

from ai_assistant.core.config import load_config


def check_llm() -> int:
    """Check LLM connectivity."""
    config_path = os.getenv("AI_CONFIG_PATH", "config.yaml")
    try:
        cfg = load_config(config_path)
    except Exception as e:
        print(f"Config error: {e}")
        return 1

    api_base = cfg.llm.api_base.rstrip("/")
    model = cfg.llm.model
    api_key = getattr(cfg.llm, "api_key", None)

    print(f"Provider: {cfg.llm.provider}")
    print(f"API base: {api_base}")
    print(f"Model: {model}")
    print(f"Checking LLM API at {api_base}...")

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    with httpx.Client(headers=headers, follow_redirects=True) as client:
        # 1. Check /v1/models
        reachable = False
        try:
            resp = client.get(f"{api_base}/models", timeout=5.0)
            reachable = resp.status_code == 200
            print(f"API reachable: {reachable} (status {resp.status_code})")
            if reachable:
                try:
                    data = resp.json()
                    available = [m.get("id", m) for m in data.get("data", [])]
                    if model not in available:
                        print(f"⚠️  Model '{model}' not found in /models list.")
                        print(f"   Available: {available[:5]}...")
                except Exception:
                    pass  # Non-standard /models response — ignore
        except (httpx.HTTPError, OSError) as e:
            print(f"API not reachable: {e}")
        except Exception as e:
            print(f"Unexpected error during connectivity check: {e}")
            return 1

        # 2. Check model response via /v1/chat/completions
        ok = False
        if reachable:
            try:
                resp = client.post(
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
                    try:
                        err = resp.json()
                        print(f"Response: {err}")
                    except Exception:
                        print(f"Response: {resp.text[:500]}")
            except (httpx.HTTPError, OSError) as e:
                print(f"Model check failed: {e}")
            except Exception as e:
                print(f"Unexpected error during model check: {e}")
                return 1
        else:
            print("Skipping model check — API not reachable")

    if not ok:
        print("\nStatus: LLM server is not running or not responding")
        print("\nTo start the server:")
        print("  1. llama-server.exe -m model.gguf --port 8080")
        print("  2. ollama serve")
        print("  3. Or check config.yaml -> llm.api_base")
        print("\nTroubleshooting:")
        print("  - Verify the model name matches what the server expects")
        print("  - Check server logs for errors")
        return 1

    print("\nStatus: LLM server is healthy")
    return 0


if __name__ == "__main__":
    sys.exit(check_llm())
