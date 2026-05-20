"""Utility functions."""

from __future__ import annotations

import os
from typing import Any

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]


def resolve_api_key(config_value: str | None, env_var: str = "OPENAI_API_KEY") -> str:
    """Resolve API key from config or environment.

    Args:
        config_value: Key from config file.
        env_var: Environment variable name to check.

    Returns:
        Resolved API key.

    Raises:
        ValueError: If no key found.
    """
    if config_value:
        return config_value
    key = os.getenv(env_var)
    if key:
        return key
    raise ValueError(f"API key not found in config or env var {env_var}")


def get_tokenizer(model: str = "gpt-4o") -> Any | None:
    """Get tiktoken tokenizer with fallback to cl100k_base."""
    if tiktoken is None:
        return None
    try:
        return tiktoken.encoding_for_model(model)
    except Exception:
        try:
            return tiktoken.get_encoding("cl100k_base")
        except Exception:
            return None


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens in text. Fallback to char//4 if tiktoken unavailable."""
    if not text:
        return 0
    enc = get_tokenizer(model)
    if enc is None:
        return len(text) // 4
    try:
        return len(enc.encode(text))
    except Exception:
        return len(text) // 4


def get_context_limit(llm: Any) -> int | None:
    """Extract context window size from LLM adapter config."""
    cfg = getattr(llm, "config", None)
    if cfg is None:
        return None
    limit = getattr(cfg, "server_context_size", None)
    if limit is None:
        limit = getattr(cfg, "context_size", None)
    if limit is None:
        limit = getattr(cfg, "max_tokens", None)
    if isinstance(limit, (int, float)) and limit > 0:
        return int(limit)
    return None
