"""Core constants — shared across features."""

from __future__ import annotations

__all__ = ["CHAT_NS_PREFIX", "DEFAULT_NAMESPACE", "FROZEN_NO_INFO_PHRASES"]

DEFAULT_NAMESPACE = "default"

CHAT_NS_PREFIX = "chat_"

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
