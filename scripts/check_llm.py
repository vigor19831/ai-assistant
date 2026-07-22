#!/usr/bin/env python3
"""Check LLM, embedder, and reranker servers via real project adapters.

Returns 0 if all configured adapters initialize and respond.
Returns 1 on internal error or if any server is unreachable.
"""

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.core.config import load_config
from ai_assistant.core.domain.configs import (
    EmbedderConfigData,
    LLMConfigData,
    RerankerConfigData,
)
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.messages import UserMessage
from ai_assistant.core.ports.llm import ILLM

# ── Constants ───────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).parent.resolve()
_ROOT = _SCRIPT_DIR.parent
_CONFIG_DEFAULT = _ROOT / "config.yaml"
_SEP = "─" * 50


# ── Helpers ─────────────────────────────────────────────────────────────────
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


# ── LLM check ───────────────────────────────────────────────────────────────
async def _check_llm(cfg) -> int:
    """Check LLM connectivity via real project adapter."""
    llm_cfg = cfg.llm
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

    llm: ILLM | None = None
    try:
        llm = create_adapter("llm", provider, llm_data)
        ctx_limit: int | None = llm.get_context_limit()
        print(f"  Context limit: {ctx_limit}")
        print()

        print("  Checking chat completion...")
        response = await llm.complete([UserMessage(text="Hi")])
    except Exception as exc:
        _print_troubleshooting("LLM", provider, api_base, exc)
        return 1
    finally:
        if llm is not None:
            try:
                await llm.shutdown()
            except Exception as shutdown_exc:
                print(f"  ! Shutdown warning: {shutdown_exc}")

    text = response.text
    snippet = (text or "")[:200]
    print(f"  Response: {snippet!r}")
    print()
    print(_SEP)
    print("  STATUS: LLM server is healthy")
    print(_SEP)
    return 0


# ── Embedder check ──────────────────────────────────────────────────────────
async def _check_embedder(cfg) -> int:
    """Check embedder connectivity."""
    embedder_cfg = cfg.embedder
    provider: str = embedder_cfg.provider
    api_base: str = embedder_cfg.api_base
    model: str = embedder_cfg.model
    dim: int = embedder_cfg.dim

    print()
    print(_SEP)
    print(f"  EMBEDDER HEALTH CHECK     {time.strftime('%H:%M:%S')}")
    print(_SEP)
    print(f"  Provider: {provider}")
    print(f"  API base: {api_base}")
    print(f"  Model:    {model}")
    print(f"  Dim:      {dim}")
    print()

    embedder_data = EmbedderConfigData(
        model=model,
        api_base=api_base,
        api_key=embedder_cfg.api_key,
        dim=dim,
        timeout=embedder_cfg.timeout,
        connect_timeout=embedder_cfg.connect_timeout,
        n_gpu_layers=embedder_cfg.n_gpu_layers,
        n_batch=embedder_cfg.n_batch,
        n_ubatch=embedder_cfg.n_ubatch,
        mmap=embedder_cfg.mmap,
        mlock=embedder_cfg.mlock,
    )

    embedder = None
    try:
        embedder = create_adapter("embedder", provider, embedder_data)
        print("  Checking embedding...")
        embeddings = await embedder.embed(["Hello world"])
        if not embeddings or not embeddings[0]:
            print("  ! Empty embedding response")
            return 1
        if len(embeddings[0]) != embedder.dimension:
            print(
                f"  ! Dimension mismatch: expected {embedder.dimension}, "
                f"got {len(embeddings[0])}"
            )
            return 1
        print(f"  Embedding dimension: {len(embeddings[0])}")
        print()
        print(_SEP)
        print("  STATUS: Embedder is healthy")
        print(_SEP)
        return 0
    except Exception as exc:
        _print_troubleshooting("Embedder", provider, api_base, exc)
        return 1
    finally:
        if embedder is not None:
            try:
                await embedder.shutdown()
            except Exception as shutdown_exc:
                print(f"  ! Shutdown warning: {shutdown_exc}")


# ── Reranker check ──────────────────────────────────────────────────────────
async def _check_reranker(cfg) -> int:
    """Check reranker connectivity (skipped if provider is null)."""
    reranker_cfg = cfg.reranker
    if reranker_cfg is None or reranker_cfg.provider is None:
        print()
        print(_SEP)
        print(f"  RERANKER HEALTH CHECK     {time.strftime('%H:%M:%S')}")
        print(_SEP)
        print("  Provider: null (disabled)")
        print()
        print(_SEP)
        print("  STATUS: Reranker is disabled")
        print(_SEP)
        return 0

    provider: str = reranker_cfg.provider
    api_base: str = reranker_cfg.api_base
    model: str = reranker_cfg.model

    print()
    print(_SEP)
    print(f"  RERANKER HEALTH CHECK     {time.strftime('%H:%M:%S')}")
    print(_SEP)
    print(f"  Provider: {provider}")
    print(f"  API base: {api_base}")
    print(f"  Model:    {model}")
    print()

    reranker_data = RerankerConfigData(
        model=model,
        api_base=api_base,
        api_key=reranker_cfg.api_key,
        timeout=reranker_cfg.timeout,
    )

    reranker = None
    try:
        reranker = create_adapter("reranker", provider, reranker_data)
        print("  Checking rerank...")
        chunk = Chunk(
            id="test-1",
            text="Hello world",
            metadata=ChunkMetadata(source="test", index=0, total_chunks=1),
        )
        results = await reranker.rerank("test query", [chunk], top_k=1)
        if not results:
            print("  ! Empty rerank response")
            return 1
        print(f"  Rerank results: {len(results)}")
        print()
        print(_SEP)
        print("  STATUS: Reranker is healthy")
        print(_SEP)
        return 0
    except Exception as exc:
        _print_troubleshooting("Reranker", provider, api_base, exc)
        return 1
    finally:
        if reranker is not None:
            try:
                await reranker.shutdown()
            except Exception as shutdown_exc:
                print(f"  ! Shutdown warning: {shutdown_exc}")


# ── Troubleshooting ─────────────────────────────────────────────────────────
def _print_troubleshooting(
    label: str, provider: str, api_base: str, exc: Exception
) -> None:
    """Print structured troubleshooting block."""
    print()
    print(_SEP)
    print(f"  STATUS: {label} server is not running or not responding")
    print(_SEP)
    print(f"  Provider: {provider}")
    print(f"  API base: {api_base}")
    print(f"  Error: {exc}")
    print()
    print("  To start the server:")
    if label == "LLM":
        print("    1. llama-server.exe -m model.gguf --port 8080")
        print("    2. ollama serve")
    elif label == "Embedder":
        print("    1. llama-server.exe -m embed-model.gguf --port 8081 --embedding")
        print("    2. ollama serve")
    elif label == "Reranker":
        print("    1. llama-server.exe -m rerank-model.gguf --port 8082 --rerank")
    print("    3. Or check config.yaml for the correct api_base")
    print()
    print("  Troubleshooting:")
    print("    - Verify the model name matches what the server expects")
    print("    - Check server logs for errors")
    print(_SEP)
    print()


# ── Main ────────────────────────────────────────────────────────────────────
async def _check_all() -> int:
    """Run all adapter health checks."""
    config_path = _get_config_path()
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return 1

    try:
        cfg = load_config(str(config_path))
    except Exception as exc:
        print(f"Config error: {exc}")
        return 1

    results = [
        await _check_llm(cfg),
        await _check_embedder(cfg),
        await _check_reranker(cfg),
    ]
    return 0 if all(r == 0 for r in results) else 1


def main() -> int:
    """Entry point with graceful signal handling."""
    def _on_sigint(_signum: int, _frame: object) -> None:
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)

    try:
        return asyncio.run(_check_all())
    except KeyboardInterrupt:
        print("\n  ! Interrupted by user. Exiting.")
        return 0
    except Exception as exc:
        print(f"\n  ! Unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
