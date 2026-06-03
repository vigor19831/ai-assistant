"""Utility functions."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]

try:
    import tokenizers
except ImportError:
    tokenizers = None  # type: ignore[assignment]

__all__ = [
    "async_count_tokens",
    "async_get_tokenizer",
    "count_tokens",
    "get_context_limit",
    "get_tokenizer",
    "resolve_api_key",
]


def resolve_api_key(config_value: str | None, env_var: str = "OPENAI_API_KEY") -> str:
    """Resolve API key from config or environment."""
    if config_value is not None and config_value != "":
        return config_value
    key = os.getenv(env_var)
    if key:
        return key
    raise ValueError(f"API key not found in config or env var {env_var}")


def _resolve_tokenizer_dir(model: str, local_dir: str) -> Path | None:
    """Map model name to local tokenizer directory."""
    base = Path(local_dir)
    if not base.exists():
        return None

    normalized = model.lower().strip().replace("_", "-")

    try:
        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            entry_norm = entry.name.lower().replace("_", "-")
            if entry_norm == normalized and (entry / "tokenizer.json").exists():
                return entry

        for entry in base.iterdir():
            if not entry.is_dir():
                continue
            entry_norm = entry.name.lower().replace("_", "-")
            if (
                entry_norm in normalized or normalized.startswith(entry_norm + "-")
            ) and (entry / "tokenizer.json").exists():
                return entry
    except OSError:
        return None

    return None


def get_tokenizer(
    model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> Any | None:
    """Get tokenizer: tiktoken first (OpenAI), then local HF, then None."""
    if tiktoken is not None:
        try:
            return tiktoken.encoding_for_model(model)
        except KeyError:
            try:
                return tiktoken.get_encoding("cl100k_base")
            except Exception:
                pass
    if tokenizers is not None:
        tok_dir = _resolve_tokenizer_dir(model, local_dir)
        if tok_dir is not None:
            try:
                return tokenizers.Tokenizer.from_file(str(tok_dir / "tokenizer.json"))
            except Exception:
                pass
    return None


def count_tokens(
    text: str, model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> int:
    """Count tokens. Fallback to char//4 if no tokenizer available."""
    if not text:
        return 0
    enc = get_tokenizer(model, local_dir=local_dir)
    if enc is None:
        return len(text) // 4
    try:
        # HF tokenizers: encode() returns Encoding с .tokens
        return len(enc.encode(text).tokens)
    except AttributeError:
        # tiktoken: encode() возвращает list[int]
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def get_context_limit(llm: Any) -> int | None:
    """Extract context window size from LLM adapter config."""
    cfg = getattr(llm, "config", None)
    if cfg is None:
        return None
    for attr in ("context_size", "server_context_size", "max_tokens"):
        limit = getattr(cfg, attr, None)
        if isinstance(limit, (int, float)) and limit > 0:
            return int(limit)
    return None


async def async_count_tokens(
    text: str, model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> int:
    """Async wrapper for count_tokens — offloads CPU-bound tiktoken/HF encoding to thread pool."""
    return await asyncio.to_thread(count_tokens, text, model, local_dir)


async def async_get_tokenizer(
    model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> Any | None:
    """Async wrapper for get_tokenizer — offloads CPU-bound tokenizer loading to thread pool."""
    return await asyncio.to_thread(get_tokenizer, model, local_dir)
