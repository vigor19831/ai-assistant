"""Utility functions."""

from __future__ import annotations

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


# Маппинг: имя модели в config.yaml → папка в data/tokenizers/
_MODEL_TO_TOKENIZER: dict[str, str] = {
    "qwen2.5": "qwen2.5",
    "qwen2.5-7b-instruct": "qwen2.5",
    "qwen2.5-14b-instruct": "qwen2.5",
    "llama-3.2": "llama-3.2",
    "llama-3.2-3b-instruct": "llama-3.2",
    "llama-3.1": "llama-3.2",
    "gemma-3": "gemma-3",
    "gemma-3-4b-it": "gemma-3",
    "gemma-3-27b-it": "gemma-3",
}


def resolve_api_key(config_value: str | None, env_var: str = "OPENAI_API_KEY") -> str:
    """Resolve API key from config or environment."""
    if config_value:
        return config_value
    key = os.getenv(env_var)
    if key:
        return key
    raise ValueError(f"API key not found in config or env var {env_var}")


def _resolve_tokenizer_dir(model: str, local_dir: str) -> Path | None:
    """Map model name to local tokenizer directory."""
    base = Path(local_dir)
    # Normalize: underscores ↔ dashes, lowercase
    normalized = model.lower().strip().replace("_", "-")

    # Exact match after normalization
    for entry in base.iterdir():
        if entry.is_dir():
            entry_norm = entry.name.lower().replace("_", "-")
            if entry_norm == normalized:
                if (entry / "tokenizer.json").exists():
                    return entry

    # Partial match (e.g. qwen2.5-7b-instruct -> qwen2.5)
    for entry in base.iterdir():
        if entry.is_dir():
            entry_norm = entry.name.lower().replace("_", "-")
            if entry_norm in normalized or normalized.startswith(entry_norm + "-"):
                if (entry / "tokenizer.json").exists():
                    return entry

    return None


def get_tokenizer(
    model: str = "gpt-4o", local_dir: str = "./data/tokenizers"
) -> Any | None:
    """Get tokenizer: tiktoken first (OpenAI), then local HF, then None."""
    if tiktoken is not None:
        try:
            return tiktoken.encoding_for_model(model)
        except Exception:
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
        if hasattr(enc, "encode_batch"):
            return len(enc.encode(text).tokens)
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
