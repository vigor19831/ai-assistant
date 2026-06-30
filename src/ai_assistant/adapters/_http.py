"""Shared HTTP helpers for OpenAI-compatible adapters.

Extracts the common POST + raise_for_status + JSON pattern
used by embedder, LLM, and reranker adapters.
"""

from __future__ import annotations

from typing import Any

import httpx

from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.logger import get_logger

__all__ = ["async_post_json"]

_logger = get_logger("adapters.http")


async def async_post_json(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Execute POST request and return parsed JSON response.

    Args:
    client: httpx.AsyncClient instance owned by the calling adapter.
        Per architectural strategy §4.2, each adapter creates and closes
        its own client; this parameter is NOT for cross-adapter sharing.        url: Full request URL.
        headers: HTTP headers including Authorization if needed.
        payload: JSON-serializable request body.

    Returns:
        Parsed JSON response as dict.

    Raises:
        AdapterError: On HTTP failure or invalid JSON response.
            Original exception is chained via ``from``.
    """
    try:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        _logger.exception(
            "HTTP request failed",
            extra={"url": url, "error": str(exc)},
        )
        raise AdapterError(f"HTTP request failed: {exc}") from exc

    try:
        data: dict[str, Any] = resp.json()
    except (ValueError, TypeError) as exc:
        _logger.exception(
            "Invalid JSON in response",
            extra={"url": url, "preview": resp.text[:200]},
        )
        raise AdapterError(f"Invalid JSON response from {url!r}: {exc}") from exc

    return data
