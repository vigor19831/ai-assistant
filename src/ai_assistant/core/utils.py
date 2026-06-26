"""Utility functions."""

from __future__ import annotations

import asyncio
import os
import warnings
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
    "count_tokens",
    "resolve_api_key",
]

# Named constant for CJK ratio threshold to avoid magic numbers
# CJK-heavy text above this threshold uses len(text) instead of len(text)//4
_CJK_RATIO_THRESHOLD: float = 0.3


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
    model: str, local_dir: str = "./data/tokenizers"
) -> Any | None:
    """Get tokenizer: tiktoken first (OpenAI), then local HF, then None.

    .. deprecated::
        Use ITokenizer port (TiktokenTokenizer or CharFallbackTokenizer)
        instead of this function. Will be removed in next config_version.
    """
    warnings.warn(
        "get_tokenizer is deprecated; use ITokenizer port",
        DeprecationWarning,
        stacklevel=2,
    )
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


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    cjk_count = sum(
        1
        for c in text
        if (
            "\u4e00" <= c <= "\u9fff"  # CJK Unified
            or "\u3400" <= c <= "\u4dbf"  # CJK Extension A
            or "\u3040" <= c <= "\u30ff"  # Hiragana + Katakana
            or "\uac00" <= c <= "\ud7af"  # Hangul Syllables
        )
    )
    return cjk_count / len(text)


def count_tokens(
    text: str, model: str, local_dir: str = "./data/tokenizers"
) -> int:
    """Count tokens. Fallback to char//4 if no tokenizer available.
    CJK-heavy text (>threshold) falls back to len(text) instead of len(text)//4.

    .. deprecated::
        Use ITokenizer.count() instead. Will be removed in next config_version.
    """
    warnings.warn(
        "count_tokens is deprecated; use ITokenizer.count()",
        DeprecationWarning,
        stacklevel=2,
    )
    if not text:
        return 0
    enc = get_tokenizer(model, local_dir=local_dir)
    if enc is None:
        if _cjk_ratio(text) > _CJK_RATIO_THRESHOLD:
            return len(text)
        return len(text) // 4
    try:
        # HF tokenizers: encode() returns Encoding with .tokens
        return len(enc.encode(text).tokens)
    except AttributeError:
        # tiktoken: encode() returns list[int]
        return len(enc.encode(text))
    except Exception:
        if _cjk_ratio(text) > _CJK_RATIO_THRESHOLD:
            return len(text)
        return len(text) // 4


async def async_count_tokens(
    text: str, model: str, local_dir: str = "./data/tokenizers"
) -> int:
    """Async wrapper for count_tokens.

    .. deprecated::
        Use ITokenizer.count() via asyncio.to_thread instead.
        Will be removed in next config_version.
    """
    warnings.warn(
        "async_count_tokens is deprecated; use ITokenizer.count()",
        DeprecationWarning,
        stacklevel=2,
    )
    return await asyncio.to_thread(count_tokens, text, model, local_dir)


async def async_get_tokenizer(
    model: str, local_dir: str = "./data/tokenizers"
) -> Any | None:
    """Async wrapper for get_tokenizer.

    .. deprecated::
        Use ITokenizer implementations directly.
        Will be removed in next config_version.
    """
    warnings.warn(
        "async_get_tokenizer is deprecated",
        DeprecationWarning,
        stacklevel=2,
    )
    return await asyncio.to_thread(get_tokenizer, model, local_dir)
