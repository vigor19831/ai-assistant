"""Fallback tokenizer using character heuristics.

ASCII text: len(text) // 4
CJK-heavy text (>30% CJK): len(text)
"""

from __future__ import annotations

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import TokenizerConfigData
from ai_assistant.core.ports.tokenizer import ITokenizer


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


@register("tokenizer", "char_fallback")
class CharFallbackTokenizer(ITokenizer):
    """Fallback tokenizer using character heuristics.

    ASCII text: len(text) // 4
    CJK-heavy text (>30% CJK): len(text)
    """

    def __init__(self, config: TokenizerConfigData) -> None:
        self.config = config

    async def shutdown(self) -> None:
        """No-op: tokenizer holds no external resources."""

    def count(self, text: str) -> int:
        """Count tokens in text."""
        if not text:
            return 0
        if _cjk_ratio(text) > 0.3:
            return len(text)
        return len(text) // 4
