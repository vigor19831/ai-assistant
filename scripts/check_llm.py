#!/usr/bin/env python3
"""Check LLM server — uses project's real adapter, not raw HTTP.

Returns 0 if LLM adapter initializes and responds to chat completions.
Returns 1 on internal error or if the server is unreachable.
"""

import asyncio
import os
import sys

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.core.config import load_config
from ai_assistant.core.domain.configs import LLMConfigData
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.logger import get_logger

_logger = get_logger("check_llm")


async def check_llm() -> int:
    """Check LLM connectivity via real project adapter."""
    config_path = os.getenv("AI_CONFIG_PATH", "config.yaml")
    try:
        cfg = load_config(config_path)
    except Exception as exc:
        print(f"Config error: {exc}")
        return 1

    print(f"Provider: {cfg.llm.provider}")
    print(f"API base: {cfg.llm.api_base}")
    print(f"Model: {cfg.llm.model}")

    llm_data = LLMConfigData(
        model=cfg.llm.model,
        api_base=cfg.llm.api_base,
        api_key=cfg.llm.api_key,
        max_tokens=cfg.llm.max_tokens,
        temperature=cfg.llm.temperature,
        timeout=cfg.llm.timeout,
        connect_timeout=cfg.llm.connect_timeout,
        server_context_size=cfg.llm.server_context_size,
        top_p=cfg.llm.top_p,
        top_k=cfg.llm.top_k,
        min_p=cfg.llm.min_p,
        repeat_penalty=cfg.llm.repeat_penalty,
        presence_penalty=cfg.llm.presence_penalty,
        frequency_penalty=cfg.llm.frequency_penalty,
        stop_sequences=tuple(cfg.llm.stop_sequences),
        system_message=cfg.llm.system_message,
        available_models=tuple(cfg.llm.available_models),
        n_gpu_layers=cfg.llm.n_gpu_layers,
        n_batch=cfg.llm.n_batch,
        n_ubatch=cfg.llm.n_ubatch,
        mmap=cfg.llm.mmap,
        mlock=cfg.llm.mlock,
    )

    print("Initializing LLM adapter...")
    try:
        llm = create_adapter("llm", cfg.llm.provider, llm_data)
    except Exception as exc:
        print(f"Adapter init failed: {exc}")
        return 1

    # Verify context limit is available
    ctx_limit = llm.get_context_limit()
    print(f"Context limit: {ctx_limit}")

    print("Checking chat completion...")
    try:
        response = await llm.complete([UserMessage(text="Hi")])
    except Exception as exc:
        print(f"\nStatus: LLM server is not running or not responding")
        print(f"Error: {exc}")
        print("\nTo start the server:")
        print("  1. llama-server.exe -m model.gguf --port 8080")
        print("  2. ollama serve")
        print("  3. Or check config.yaml -> llm.api_base")
        print("\nTroubleshooting:")
        print("  - Verify the model name matches what the server expects")
        print("  - Check server logs for errors")
        return 1
    finally:
        # Adapter owns its client — unconditional cleanup per §3.1
        await llm.shutdown()

    print(f"Response: {response.text[:200]!r}")
    print("\nStatus: LLM server is healthy")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(check_llm()))
