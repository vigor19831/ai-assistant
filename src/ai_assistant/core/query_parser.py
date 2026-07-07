"""Single source of truth for RAG query prefix parsing."""

from __future__ import annotations

import re
from collections.abc import Mapping

__all__ = ["build_prefix_map", "parse_rag_query"]


def parse_rag_query(text: str, prefix_map: dict[str, str]) -> tuple[str, str | None]:
    """Extract RAG prefix and return (clean_text, namespace).

    RAG is strictly opt-in: no prefix match returns namespace=None.
    All prefixes are provided via *prefix_map* from configuration.

    Args:
        text: Raw user message.
        prefix_map: Mapping of prefix string -> namespace name,
            built from NamespaceConfig.prefix values.

    Returns:
        (clean_text, namespace). namespace is None when no prefix matches.
    """
    if not text:
        return ("", None)
    if not prefix_map:
        return (text, None)

    escaped = [re.escape(k) for k in prefix_map]
    pattern = re.compile(r"^\[(" + "|".join(escaped) + r")\]\s*(.*)", re.IGNORECASE)
    match = pattern.match(text)
    if not match:
        return (text, None)

    prefix = match.group(1).lower()
    clean = match.group(2).strip()
    namespace = prefix_map.get(prefix)
    return (clean, namespace)


def build_prefix_map(namespaces: Mapping[str, object]) -> dict[str, str]:
    """Build prefix -> namespace mapping from NamespaceConfig dict."""
    result: dict[str, str] = {}
    for ns_name, cfg in namespaces.items():
        prefix = getattr(cfg, "prefix", None)
        if prefix and len(prefix) >= 1:
            result[prefix.lower()] = ns_name
    return result
