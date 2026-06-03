"""Core constants — shared across features."""

from __future__ import annotations

import re

__all__ = ["FROZEN_NO_INFO_PHRASES", "RAG_NS_MAP", "RAG_PREFIX_RE"]

RAG_NS_MAP: dict[str, str] = {
    "p": "personal",
    "w": "work",
    "o": "other",
    "c": "code",
    "b": "books",
}
RAG_PREFIX_RE: re.Pattern[str] = re.compile(r"^\[(p|w|o|c|b)\]\s*(.*)", re.IGNORECASE)

FROZEN_NO_INFO_PHRASES: frozenset[str] = frozenset(
    {
        "не достаточно",
        "недостаточно",
        "не имею",
        "не знаю",
        "not enough",
        "don't have",
        "no information",
        "не найдено",
        "not found",
        "i don't have",
        "i do not have",
        "don't know",
        "do not know",
        "у меня недостаточно",
        "у меня нет",
    }
)
