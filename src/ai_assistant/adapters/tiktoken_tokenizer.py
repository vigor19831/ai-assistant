"""Tokenizer backed by tiktoken (OpenAI) or local HF tokenizers."""

from __future__ import annotations

from pathlib import Path

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import TokenizerConfigData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.tokenizer import ITokenizer

_logger = get_logger("adapters.tiktoken_tokenizer")

try:
    import tiktoken
except ImportError:
    tiktoken = None  # type: ignore[assignment]

try:
    import tokenizers
except ImportError:
    tokenizers = None  # type: ignore[assignment]


def _cjk_ratio(text: str) -> float:
    """Return ratio of CJK characters in text."""
    if not text:
        return 0.0
    cjk_count = sum(
        1
        for c in text
        if (
            "\u4e00" <= c <= "\u9fff"
            or "\u3400" <= c <= "\u4dbf"
            or "\u3040" <= c <= "\u30ff"
            or "\uac00" <= c <= "\ud7af"
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
        self.config = config
        self._model_name = config.provider

    @property
    def model_name(self) -> str:
        """Model identifier this tokenizer was initialized for."""
        return self._model_name

    def count(self, text: str, model: str) -> int:
        """Count tokens in text for the given model."""
        if not text:
            return 0

        if tiktoken is not None:
            try:
                try:
                    enc = tiktoken.encoding_for_model(model)
                except KeyError:
                    enc = tiktoken.get_encoding("cl100k_base")
                return len(enc.encode(text))
            except Exception:
                _logger.exception("tiktoken failed")

        if tokenizers is not None:
            tok_dir = _resolve_tokenizer_dir(model, self.config.local_dir)
            if tok_dir is not None:
                try:
                    hf_tok = tokenizers.Tokenizer.from_file(str(tok_dir / "tokenizer.json"))
                    result = hf_tok.encode(text)
                    try:
                        return len(result.tokens)
                    except AttributeError:
                        return len(result)
                except Exception:
                    _logger.exception("HF tokenizer failed")

        return self._fallback_count(text)

    def _fallback_count(self, text: str) -> int:
        """Fallback to character heuristic when tiktoken is unavailable."""
        if _cjk_ratio(text) > 0.3:
            return len(text)
        return len(text) // 4
