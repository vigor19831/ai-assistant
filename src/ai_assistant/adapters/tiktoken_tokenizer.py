"""Tokenizer adapter using tiktoken and HuggingFace tokenizers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import TokenizerConfigData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.tokenizer import ITokenizer

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]

try:
    import tokenizers
except ImportError:
    tokenizers = None  # type: ignore[assignment]

__all__ = ["TiktokenTokenizer"]

_logger = get_logger("adapters.tokenizer.tiktoken")


# Named constant for CJK ratio threshold
_CJK_RATIO_THRESHOLD: float = 0.3


def _cjk_ratio(text: str) -> float:
    """Return ratio of CJK characters in text."""
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


@register("tokenizer", "tiktoken")
class TiktokenTokenizer(ITokenizer):
    """Tokenizer backed by tiktoken (OpenAI) or local HF tokenizers."""

    def __init__(self, config: TokenizerConfigData) -> None:
        self.local_dir = config.local_dir

    def _get_tokenizer(self, model: str) -> Any | None:
        """Get tokenizer: tiktoken first, then local HF, then None."""
        if tiktoken is not None:
            try:
                return tiktoken.encoding_for_model(model)
            except KeyError:
                try:
                    return tiktoken.get_encoding("cl100k_base")
                except Exception:
                    pass
        if tokenizers is not None:
            tok_dir = _resolve_tokenizer_dir(model, self.local_dir)
            if tok_dir is not None:
                try:
                    return tokenizers.Tokenizer.from_file(str(tok_dir / "tokenizer.json"))
                except Exception:
                    pass
        return None

    def count(self, text: str, model: str) -> int:
        """Count tokens. Fallback to char-based heuristic if no tokenizer."""
        if not text:
            return 0
        enc = self._get_tokenizer(model)
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
