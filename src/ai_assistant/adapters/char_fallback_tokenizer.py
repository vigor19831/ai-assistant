"""Character-based fallback tokenizer."""

from __future__ import annotations

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import TokenizerConfigData
from ai_assistant.core.ports.tokenizer import ITokenizer

__all__ = ["CharFallbackTokenizer"]

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


@register("tokenizer", "char_fallback")
class CharFallbackTokenizer(ITokenizer):
    """Fallback tokenizer using character heuristics.

    ASCII text: len(text) // 4
    CJK-heavy text (>30% CJK): len(text)
    """

    def __init__(self, _config: TokenizerConfigData) -> None:
        """Config is accepted for factory uniformity but not used."""

    def count(self, text: str, _model: str) -> int:
        """Count tokens using character heuristics.

        Model parameter is ignored — this is a model-agnostic fallback.
        """
        if not text:
            return 0
        if _cjk_ratio(text) > _CJK_RATIO_THRESHOLD:
            return len(text)
        return len(text) // 4
