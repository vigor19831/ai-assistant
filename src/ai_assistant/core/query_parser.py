"""Single source of truth for RAG query prefix parsing."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Protocol

from ai_assistant.core.domain.pipeline import DateFilter

__all__ = ["build_prefix_map", "parse_date_phrase", "parse_rag_query"]


class _HasPrefix(Protocol):
    prefix: str | None


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


# --- Date-phrase parsing (date campaign stage 2, variant 4b) ---
# The month dictionary and prepositions come from config
# (rag.date_month_names / rag.date_prepositions) — src stays
# language-agnostic. Recognized shapes (the phrase stays in the
# query text; only the search frame changes):
#   preposition + month name         -> month, any year
#   preposition + month name + year  -> month + year
#   "2026-03"                        -> month + year (digital)
# Returns None when no date phrase is found (the default path —
# byte-identical pre-stage-2 behavior).
_DIGITAL_DATE_RE = re.compile(r"(?:^|\W)(\d{4})-(\d{2})(?:\W|$)")


def _date_phrase_pattern(
    prepositions: list[str], months_alt: str
) -> re.Pattern[str]:
    preps = "|".join(
        sorted((re.escape(p) for p in prepositions), key=len, reverse=True)
    )
    return re.compile(
        rf"(?:^|\W)(?:{preps})\s+({months_alt})"
        r"(?:\s+(\d{4}))?(?:\W|$)",
        re.IGNORECASE,
    )


def parse_date_phrase(
    text: str,
    month_names: dict[str, int],
    prepositions: list[str] | None = None,
) -> DateFilter | None:
    """Extract a date frame from the query text, or None.

    First matching phrase wins; ties impossible (leftmost match).
    The matched phrase is NOT removed from the text. prepositions
    are language data from config (rag.date_prepositions), like the
    month names: no language knowledge lives in src.
    """
    if not text:
        return None
    m = _DIGITAL_DATE_RE.search(text)
    if m is not None:
        return DateFilter(year=int(m.group(1)), month=int(m.group(2)))
    if not month_names or not prepositions:
        return None
    alt = "|".join(
        sorted((re.escape(name) for name in month_names), key=len, reverse=True)
    )
    pattern = _date_phrase_pattern(prepositions, alt)
    match = pattern.search(text)
    if match is not None:
        year = int(match.group(2)) if match.group(2) is not None else None
        return DateFilter(year=year, month=month_names[match.group(1).lower()])
    return None


def build_prefix_map(namespaces: Mapping[str, _HasPrefix]) -> dict[str, str]:
    """Build prefix -> namespace mapping from NamespaceConfig dict."""
    result: dict[str, str] = {}
    for ns_name, cfg in namespaces.items():
        prefix = cfg.prefix
        if prefix and len(prefix) >= 1:
            result[prefix.lower()] = ns_name
    return result
