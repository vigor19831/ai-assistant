"""Core constants — shared across features."""

from __future__ import annotations

__all__ = ["CHAT_NS_PREFIX", "DEFAULT_NAMESPACE", "FROZEN_NO_INFO_PHRASES"]

DEFAULT_NAMESPACE = "default"

CHAT_NS_PREFIX = "chat_"

FROZEN_NO_INFO_PHRASES: frozenset[str] = frozenset(
    {
        # Russian phrases
        "не достаточно",
        "недостаточно",
        "не имею",
        "не знаю",
        "не найдено",
        "у меня недостаточно",
        "у меня нет",
        # English phrases (must match rag_strict.j2 exactly, case-insensitive checked)
        "i don't know",
        "not sure",
        "no information",
        "not mentioned",
        "not specified",
        "don't have",
        "no data",
        "cannot answer",
        "not enough",
        "not found",
        "i do not have",
        "don't know",
        "do not know",
    }
)
