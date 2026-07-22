#!/usr/bin/env python3
"""Check LLM server — uses project's real adapter, not raw HTTP.

Returns 0 if LLM adapter initializes and responds to chat completions.
Returns 1 on internal error or if the server is unreachable.
"""

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.core.config import load_config
from ai_assistant.core.domain.configs import LLMConfigData
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.ports.llm import ILLM

# ── Constants ───────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent.resolve()
_ROOT = _SCRIPT_DIR.parent
_CONFIG_DEFAULT = _ROOT / "config.yaml"
_SEP = "─" * 50

# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_config_path() -> Path:
    """Return explicit config path from env, or default beside this script."""
    env = os.getenv("AI_CONFIG_PATH")
    if not env or not env.strip():
        return _CONFIG_DEFAULT
    return Path(env.strip()).expanduser()


def _to_tuple(value: list[str] | tuple[str, ...] | str | None) -> tuple[str, ...]:
    """Safely convert a config sequence to a tuple.

    Guards against:
      - None → ()
      - plain str → (str,)      # prevents tuple("abc") → ('a','b','c')
      - list / tuple → tuple(...)
    """
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _print_troubleshooting(provider: str, api_base: str, exc: Exception) -> None:
    """Print structured troubleshooting block."""
    print()
    print(_SEP)
    print("  STATUS: LLM server is not running or not responding")
    print(_SEP)
    print(f"  Provider: {provider}")
    print(f"  API base: {api_base}")
    print(f"  Error: {exc}")
    print()
    print("  To start the server:")
    print("    1. llama-server.exe -m model.gguf --port 8080")
    print("    2. ollama serve")
    print("    3. Or check config.yaml -> llm.api_base")
    print()
    print("  Troubleshooting:")
    print("    - Verify the model name matches what the server expects")
    print("    - Check server logs for errors")
    print(_SEP)
    print()


async def _check_llm() -> int:
    """Check LLM connectivity via real project adapter."""
    config_path = _get_config_path()
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return 1

    try:
        cfg = load_config(str(config_path))
    except Exception as exc:
        print(f"Config error: {exc}")
        return 1

    try:
        llm_cfg = cfg.llm
    except AttributeError:
        print("Config error: missing 'llm' section")
        return 1

    provider: str = llm_cfg.provider
    api_base: str = llm_cfg.api_base
    model: str = llm_cfg.model

    print()
    print(_SEP)
    print(f"  LLM HEALTH CHECK          {time.strftime('%H:%M:%S')}")
    print(_SEP)
    print(f"  Provider: {provider}")
    print(f"  API base: {api_base}")
    print(f"  Model:    {model}")
    print()

    # Build adapter config defensively — schema changes must not crash the CLI
    try:
        llm_data = LLMConfigData(
            model=model,
            api_base=api_base,
            api_key=llm_cfg.api_key,
            max_tokens=llm_cfg.max_tokens,
            temperature=llm_cfg.temperature,
            timeout=llm_cfg.timeout,
            connect_timeout=llm_cfg.connect_timeout,
            server_context_size=llm_cfg.server_context_size,
            top_p=llm_cfg.top_p,
            top_k=llm_cfg.top_k,
            min_p=llm_cfg.min_p,
            repeat_penalty=llm_cfg.repeat_penalty,
            presence_penalty=llm_cfg.presence_penalty,
            frequency_penalty=llm_cfg.frequency_penalty,
            stop_sequences=_to_tuple(llm_cfg.stop_sequences),
            system_message=llm_cfg.system_message,
            available_models=_to_tuple(llm_cfg.available_models),
            n_gpu_layers=llm_cfg.n_gpu_layers,
            n_batch=llm_cfg.n_batch,
            n_ubatch=llm_cfg.n_ubatch,
            mmap=llm_cfg.mmap,
            mlock=llm_cfg.mlock,
        )
    except AttributeError as exc:
        print(f"Config schema error: {exc}")
        return 1

    print("  Initializing LLM adapter...")
    llm: ILLM | None = None
    try:
        llm = create_adapter("llm", provider, llm_data)
    except Exception as exc:
        print(f"Adapter init failed: {exc}")
        return 1

    try:
        ctx_limit: int | None = llm.get_context_limit()
        print(f"  Context limit: {ctx_limit}")
        print()

        print("  Checking chat completion...")
        response = await llm.complete([UserMessage(text="Hi")])
    except Exception as exc:
        _print_troubleshooting(provider, api_base, exc)
        return 1
    finally:
        if llm is not None:
            try:
                await llm.shutdown()
            except Exception as shutdown_exc:
                # Never let cleanup mask the original error reason
                print(f"  ! Shutdown warning: {shutdown_exc}")
    # finally completes before the return in the except block above

    text = response.text
    snippet = (text or "")[:200]
    print(f"  Response: {snippet!r}")
    print()
    print(_SEP)
    print("  STATUS: LLM server is healthy")
    print(_SEP)
    print()
    return 0


# ── Main ──────────────────────────────────────────────────────────────────────
def main() -> int:
    """Entry point with graceful signal handling."""
    def _on_sigint(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)

    try:
        return asyncio.run(_check_llm())
    except KeyboardInterrupt:
        print("\n  ! Interrupted by user. Exiting.")
        return 0
    except Exception as exc:
        print(f"\n  ! Unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
