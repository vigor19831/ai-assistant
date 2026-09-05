#!/usr/bin/env python3
"""Check LLM, embedder, reranker servers and local tokenizer.

Compact output: one line per component when healthy; a failing
component expands into a full troubleshooting block.

Returns 0 if all adapters are healthy; 1 otherwise.
"""

import asyncio
import contextlib
import logging
import os
import signal
import sys
import time
from pathlib import Path

from ai_assistant.adapters.factory import create_adapter
from ai_assistant.core.config import AppConfig, load_config
from ai_assistant.core.domain.configs import (
    EmbedderConfigData,
    LLMConfigData,
    RerankerConfigData,
    TokenizerConfigData,
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


def _fmt_health(name: str, detail: str, status: str) -> None:
    """One compact line: NAME  detail  STATUS."""
    print(f"  {name:<11} {detail:<44} {status}")


# ── Component checks ────────────────────────────────────────────────────────
async def _check_llm(cfg: AppConfig) -> bool:
    """True if the LLM server answers a completion."""
    llm_cfg = cfg.llm
    llm_data = LLMConfigData(
        model=llm_cfg.model,
        api_base=llm_cfg.api_base,
        api_key=llm_cfg.api_key,
        max_tokens=llm_cfg.max_tokens,
        temperature=llm_cfg.temperature,
        timeout=llm_cfg.timeout,
        connect_timeout=llm_cfg.connect_timeout,
        server_context_size=llm_cfg.server_context_size,
        top_p=llm_cfg.top_p,
        stop_sequences=_to_tuple(llm_cfg.stop_sequences),
        system_message=llm_cfg.system_message,
        available_models=_to_tuple(llm_cfg.available_models),
        n_gpu_layers=llm_cfg.n_gpu_layers,
    )

    llm: ILLM | None = None
    try:
        llm = create_adapter("llm", llm_cfg.provider, llm_data)
        await llm.complete([UserMessage(text="Hi")])
        return True
    except Exception:
        return False
    finally:
        if llm is not None:
            with contextlib.suppress(Exception):
                await llm.shutdown()


async def _check_embedder(cfg: AppConfig) -> bool:
    """True if the embedder returns a correct-dimension vector."""
    embedder_cfg = cfg.embedder
    embedder_data = EmbedderConfigData(
        model=embedder_cfg.model,
        api_base=embedder_cfg.api_base,
        api_key=embedder_cfg.api_key,
        dim=embedder_cfg.dim,
        timeout=embedder_cfg.timeout,
        connect_timeout=embedder_cfg.connect_timeout,
        n_gpu_layers=embedder_cfg.n_gpu_layers,
    )

    embedder = None
    try:
        embedder = create_adapter("embedder", embedder_cfg.provider, embedder_data)
        embeddings = await embedder.embed(["Hello world"])
        has_vector = bool(embeddings and embeddings[0])
        return has_vector and len(embeddings[0]) == embedder.dimension
    except Exception:
        return False
    finally:
        if embedder is not None:
            with contextlib.suppress(Exception):
                await embedder.shutdown()


async def _check_reranker(cfg: AppConfig) -> bool:
    """True if the reranker orders a test chunk."""
    reranker_cfg = cfg.reranker
    if reranker_cfg is None or reranker_cfg.provider is None:
        return True  # disabled is a valid state

    reranker_data = RerankerConfigData(
        model=reranker_cfg.model,
        api_base=reranker_cfg.api_base,
        api_key=reranker_cfg.api_key,
        timeout=reranker_cfg.timeout,
    )

    reranker = None
    try:
        reranker = create_adapter("reranker", reranker_cfg.provider, reranker_data)
        chunk = Chunk(
            id="test-1",
            text="Hello world",
            metadata=ChunkMetadata(source="test", index=0, total_chunks=1),
        )
        results = await reranker.rerank("test query", [chunk], top_k=1)
        return bool(results)
    except Exception:
        return False
    finally:
        if reranker is not None:
            with contextlib.suppress(Exception):
                await reranker.shutdown()


def _check_tokenizer(cfg: AppConfig) -> str:
    """Return 'ok', 'fallback', or 'error' for the local tokenizer.

    The tokenizer is the only file-backed adapter: a missing
    tokenizer.json degrades silently at server startup. This check
    makes the LOADED/FALLBACK state visible BEFORE a restart.
    """
    tok_cfg = cfg.tokenizer
    try:
        tokenizer = create_adapter(
            "tokenizer",
            tok_cfg.provider,
            TokenizerConfigData(
                provider=tok_cfg.provider,
                model_name=tok_cfg.model_name,
            ),
        )
    except Exception:
        return "error"

    if "char" in tokenizer.model_name.lower():
        return "fallback"
    return "ok"


def _to_tuple(value: list[str] | tuple[str, ...] | str | None) -> tuple[str, ...]:
    """Safely convert a config sequence to a tuple."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


# ── Main ────────────────────────────────────────────────────────────────────
async def _check_all() -> int:
    # Health check verdicts are OK/FAIL lines; adapter tracebacks
    # (ConnectError stacks on down servers) would bury them. The
    # application log keeps the full detail.
    logging.getLogger("ai_assistant").setLevel(logging.CRITICAL)

    config_path = _get_config_path()
    if not config_path.exists():
        print(f"Config file not found: {config_path}")
        return 1

    try:
        cfg = load_config(str(config_path))
    except Exception as exc:
        print(f"Config error: {exc}")
        return 1

    print()
    print(_SEP)
    print(f"  HEALTH CHECK                          {time.strftime('%H:%M:%S')}")
    print(_SEP)

    failures: list[str] = []

    llm_ok = await _check_llm(cfg)
    detail = f"{cfg.llm.provider}  {cfg.llm.model}"
    _fmt_health("LLM", detail, "OK" if llm_ok else "FAIL")
    if not llm_ok:
        failures.append("llm")

    embedder_ok = await _check_embedder(cfg)
    detail = f"{cfg.embedder.provider}  {cfg.embedder.model}  {cfg.embedder.dim}d"
    _fmt_health("Embedder", detail, "OK" if embedder_ok else "FAIL")
    if not embedder_ok:
        failures.append("embedder")

    reranker_ok = await _check_reranker(cfg)
    reranker_cfg = cfg.reranker
    if reranker_cfg is None or reranker_cfg.provider is None:
        detail = "disabled"
        status = "OK"
    else:
        detail = f"{reranker_cfg.provider}  {reranker_cfg.model}"
        status = "OK" if reranker_ok else "FAIL"
        if not reranker_ok:
            failures.append("reranker")
    _fmt_health("Reranker", detail, status)

    tok_state = _check_tokenizer(cfg)
    tok_cfg = cfg.tokenizer
    if tok_state == "ok":
        detail = f"{tok_cfg.provider}  {Path(tok_cfg.model_name).name}"
        _fmt_health("Tokenizer", detail, "OK (exact counts)")
    elif tok_state == "fallback":
        _fmt_health("Tokenizer", f"{tok_cfg.provider}  (file missing)", "FALLBACK")
        print()
        print("    ! tokenizer.json not found — char tokenizer active")
        print("      (approximate counts). Run scripts/download_tokenizers.py,")
        print("      then restart the servers.")
        failures.append("tokenizer-fallback")
    else:
        _fmt_health("Tokenizer", f"{tok_cfg.provider}  init failed", "FAIL")
        failures.append("tokenizer")

    print(_SEP)
    if failures:
        print(f"  RESULT: FAIL  ({', '.join(failures)})")
        return 1
    print("  RESULT: OK")
    return 0


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
