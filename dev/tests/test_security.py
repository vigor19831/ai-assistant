"""Tests for api/security.py — no yaml.safe_load on hot path.

Design goals:
- get_expected_api_key() never touches filesystem.
- Admin endpoint can rotate key at runtime.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from ai_assistant.api.deps import AppState
from ai_assistant.api.security import (
    SECURITY_MAX_BODY,
    check_request_size,
    get_expected_api_key,
    require_api_key,
    set_api_key,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Reset global security state before every test."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    set_api_key(None)
    yield
    set_api_key(None)


@pytest.fixture
def mock_request():
    """Minimal ASGI request stub."""
    req = MagicMock(spec=Request)
    req.method = "GET"
    req.url.path = "/api/v1/chat"
    req.client = MagicMock(host="127.0.0.1")
    req.headers = {}
    return req


# ---------------------------------------------------------------------------
# get_expected_api_key
# ---------------------------------------------------------------------------


def test_get_expected_api_key_env_var_priority(monkeypatch):
    """Env var AI_API_KEY always wins over runtime override and config."""
    monkeypatch.setenv("AI_API_KEY", "env-secret")
    set_api_key("override-secret")
    assert get_expected_api_key() == "env-secret"


def test_get_expected_api_key_runtime_override():
    """Without env var, runtime override is returned."""
    set_api_key("override-secret")
    assert get_expected_api_key() == "override-secret"


def test_get_expected_api_key_none_when_empty():
    """When nothing set, returns None."""
    assert get_expected_api_key() is None


def test_get_expected_api_key_empty_env_returns_none(monkeypatch):
    """Empty string in AI_API_KEY must be treated as absent; override ignored."""
    monkeypatch.setenv("AI_API_KEY", "")
    set_api_key("override-secret")
    assert get_expected_api_key() is None


def test_get_expected_api_key_no_yaml_loading():
    """CRITICAL: get_expected_api_key must NOT call yaml.safe_load."""
    with patch("yaml.safe_load") as mock_yaml:
        get_expected_api_key()
        mock_yaml.assert_not_called()


# ---------------------------------------------------------------------------
# require_api_key dependency
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_require_api_key_success():
    set_api_key("secret")
    creds = MagicMock()
    creds.credentials = "secret"
    await require_api_key(creds)


@pytest.mark.anyio
async def test_require_api_key_not_configured():
    set_api_key(None)
    creds = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await require_api_key(creds)
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_require_api_key_invalid():
    set_api_key("secret")
    creds = MagicMock()
    creds.credentials = "wrong"
    with pytest.raises(HTTPException) as exc_info:
        await require_api_key(creds)
    assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# check_request_size
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_check_request_size_ok(mock_request):
    mock_request.headers = {"content-length": "1024"}
    await check_request_size(mock_request)  # no exception


@pytest.mark.anyio
async def test_check_request_size_too_large(mock_request):
    mock_request.headers = {"content-length": str(SECURITY_MAX_BODY + 1)}
    with pytest.raises(HTTPException) as exc_info:
        await check_request_size(mock_request)
    assert exc_info.value.status_code == 413


@pytest.mark.anyio
async def test_check_request_size_no_header(mock_request):
    mock_request.headers = {}
    await check_request_size(mock_request)  # no exception


# ---------------------------------------------------------------------------
# Admin endpoint integration (via AppState)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_admin_update_api_key():
    """Admin endpoint rotates key via set_api_key; config is NOT mutated."""
    from ai_assistant.api.admin import update_api_key, _UpdateApiKeyRequest

    set_api_key(None)
    state = MagicMock(spec=AppState)

    req = _UpdateApiKeyRequest(api_key="new-key")
    resp = await update_api_key(req, state)
    assert resp.updated is True
    assert get_expected_api_key() == "new-key"


@pytest.mark.anyio
async def test_admin_clear_api_key():
    """Admin endpoint clears override when api_key=None; config is NOT mutated."""
    from ai_assistant.api.admin import update_api_key, _UpdateApiKeyRequest

    set_api_key("old-key")
    state = MagicMock(spec=AppState)

    req = _UpdateApiKeyRequest(api_key=None)
    resp = await update_api_key(req, state)
    assert resp.updated is True
    assert get_expected_api_key() is None


@pytest.mark.anyio
async def test_admin_update_empty_key_rejected():
    """Empty string api_key is rejected (must be None or non-empty)."""
    from ai_assistant.api.admin import update_api_key, _UpdateApiKeyRequest

    set_api_key(None)
    state = MagicMock(spec=AppState)

    req = _UpdateApiKeyRequest(api_key="")
    with pytest.raises(HTTPException) as exc_info:
        await update_api_key(req, state)
    assert exc_info.value.status_code == 400


def test_save_chat_path_traversal_blocked_by_pydantic(client):
    payload = {
        "content": "test",
        "namespace": "personal",
        "filename": "../../../etc/passwd",
    }
    resp = client.post(
        "/api/v1/rag/save-chat",
        json=payload,
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 422


def test_save_chat_invalid_namespace_blocked_by_pydantic(client):
    payload = {"content": "test", "namespace": "hacked", "filename": "test.md"}
    resp = client.post(
        "/api/v1/rag/save-chat",
        json=payload,
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 422
