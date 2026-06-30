"""Single source of truth for RAG query prefix parsing."""

from __future__ import annotations

from ai_assistant.core.constants import DEFAULT_NAMESPACE, RAG_NS_MAP, RAG_PREFIX_RE

__all__ = ["parse_rag_query"]


def parse_rag_query(text: str) -> tuple[str, str]:
    """Extract RAG prefix and return (clean_text, namespace).

    Prefix-to-namespace mapping is intentionally hardcoded in
    constants.RAG_NS_MAP. Dynamic prefix configuration was
    rejected per architectural strategy (simplicity constraints,
    config freeze >=3 uses threshold). Custom namespaces are
    supported via the full namespace name or the namespace
    parameter in API requests.

    Examples:
        "[p] hello" -> ("hello", "personal")
        "[w] test"  -> ("test", "work")
        "hello"     -> ("hello", "default")
    """
    if not text:
        return ("", DEFAULT_NAMESPACE)

    match = RAG_PREFIX_RE.match(text)
    if not match:
        return (text, DEFAULT_NAMESPACE)

    prefix = match.group(1).lower()
    clean = match.group(2).strip()
    namespace = RAG_NS_MAP.get(prefix, DEFAULT_NAMESPACE)
    return (clean, namespace)
