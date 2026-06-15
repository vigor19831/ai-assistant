"""Single source of truth for RAG query prefix parsing."""

from __future__ import annotations

from ai_assistant.core.constants import RAG_NS_MAP, RAG_PREFIX_RE

__all__ = ["parse_rag_query"]


def parse_rag_query(text: str) -> tuple[str, str]:
    """Extract RAG prefix and return (clean_text, namespace).

    Examples:
        "[p] hello" -> ("hello", "personal")
        "[w] test"  -> ("test", "work")
        "hello"     -> ("hello", "default")
    """
    if not text:
        return ("", "default")

    match = RAG_PREFIX_RE.match(text)
    if not match:
        return (text, "default")

    prefix = match.group(1).lower()
    clean = match.group(2).strip()
    namespace = RAG_NS_MAP.get(prefix, "default")
    return (clean, namespace)
