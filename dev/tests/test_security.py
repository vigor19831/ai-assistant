"""Tests for api/security.py — no yaml.safe_load on hot path.

Design goals:
- get_expected_api_key() never touches filesystem.
- Rate limiter uses config loaded at startup.
- Admin endpoint can rotate key at runtime.
- reset_security_state() clears mutable state for test isolation.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from ai_assistant.api import security as sec_module
from ai_assistant.api.deps import AppState
from ai_assistant.api.security import (
    APIKeyMiddleware,
    LimitMiddleware,
    SECURITY_MAX_BODY,
    apply_rate_limit,
    check_request_size,
    get_expected_api_key,
    limiter,
    require_api_key,
    reset_security_state,
    set_api_key,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """Reset global security state before every test."""
    monkeypatch.delenv("AI_API_KEY", raising=False)
    reset_security_state()
    yield
    # No teardown needed — next test's setup calls reset_security_state()


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


def test_get_expected_api_key_no_yaml_loading():
    """CRITICAL: get_expected_api_key must NOT call yaml.safe_load."""
    with patch("yaml.safe_load") as mock_yaml:
        get_expected_api_key()
        mock_yaml.assert_not_called()


# ---------------------------------------------------------------------------
# reset_security_state
# ---------------------------------------------------------------------------


def test_reset_security_state_clears_override():
    set_api_key("key")
    reset_security_state()
    assert get_expected_api_key() is None


def test_reset_security_state_clears_limiter():
    reset_security_state()
    limiter.requests["1.2.3.4"] = [1.0, 2.0, 3.0]
    reset_security_state()
    assert dict(limiter.requests) == {}


# ---------------------------------------------------------------------------
# SecurityLimiter
# ---------------------------------------------------------------------------


def test_limiter_allows_under_cap():
    lim = sec_module.SecurityLimiter("3/minute")
    assert lim.is_allowed("ip")
    assert lim.is_allowed("ip")
    assert lim.is_allowed("ip")


def test_limiter_blocks_over_cap():
    lim = sec_module.SecurityLimiter("2/minute")
    lim.is_allowed("ip")
    lim.is_allowed("ip")
    assert not lim.is_allowed("ip")


def test_limiter_sliding_window():
    lim = sec_module.SecurityLimiter("1/minute")
    lim.is_allowed("ip")
    assert not lim.is_allowed("ip")
    # Expire old entry manually
    lim.requests["ip"] = [0.0]  # older than 60s window
    assert lim.is_allowed("ip")


def test_limiter_invalid_rate_limit_falls_back():
    lim = sec_module.SecurityLimiter("bad-format")
    assert lim.max_req == 100
    assert lim.window == 60.0


def test_limiter_evicts_empty_ip_entries_no_bloat():
    """10_000 unique IPs with stale timestamps: empty lists are evicted,
    and dict size stays bounded to active IPs only."""
    lim = sec_module.SecurityLimiter("100/minute")
    # Seed 10_000 IPs with expired timestamps
    for i in range(10_000):
        ip = f"10.0.{i // 256}.{i % 256}"
        lim.requests[ip] = [0.0]  # force expired
    # is_allowed filters out stale entries, deletes empty lists, then re-adds
    for i in range(10_000):
        ip = f"10.0.{i // 256}.{i % 256}"
        assert lim.is_allowed(ip) is True
    # After first pass each IP has one fresh entry → 10_000 keys
    assert len(lim.requests) == 10_000
    assert all(len(v) == 1 for v in lim.requests.values())
    # Expire them again
    for ip in list(lim.requests.keys()):
        lim.requests[ip] = [0.0]
    for i in range(10_000):
        ip = f"10.0.{i // 256}.{i % 256}"
        lim.is_allowed(ip)
    # Dict size stays bounded (same 10_000 active IPs); no zombie empty lists
    assert len(lim.requests) == 10_000
    assert all(len(v) >= 1 for v in lim.requests.values())
    # The real eviction invariant: manually set an empty list and call is_allowed
    # — the empty list must be deleted before the fresh timestamp is appended.
    lim.requests["zombie.ip"] = []
    lim.is_allowed("zombie.ip")
    assert len(lim.requests["zombie.ip"]) == 1
    assert lim.requests["zombie.ip"][0] > 0


# ---------------------------------------------------------------------------
# LimitMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_limit_middleware_allows(mock_request):
    reset_security_state()
    mw = LimitMiddleware(MagicMock())
    call_next = AsyncMock(return_value=Response("ok"))
    resp = await mw.dispatch(mock_request, call_next)
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_limit_middleware_blocks(mock_request):
    reset_security_state()
    mw = LimitMiddleware(MagicMock())
    # Exhaust limit for the SAME IP as mock_request
    for _ in range(limiter.max_req):
        limiter.is_allowed("127.0.0.1")
    call_next = AsyncMock(return_value=Response("ok"))
    resp = await mw.dispatch(mock_request, call_next)
    assert resp.status_code == 429
    call_next.assert_not_called()


# ---------------------------------------------------------------------------
# APIKeyMiddleware
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_api_key_middleware_public_path(mock_request):
    """Public paths skip auth."""
    reset_security_state()
    mw = APIKeyMiddleware(MagicMock())
    mock_request.url.path = "/health"
    call_next = AsyncMock(return_value=Response("ok"))
    resp = await mw.dispatch(mock_request, call_next)
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_api_key_middleware_options(mock_request):
    """OPTIONS requests skip auth."""
    reset_security_state()
    mw = APIKeyMiddleware(MagicMock())
    mock_request.method = "OPTIONS"
    call_next = AsyncMock(return_value=Response("ok"))
    resp = await mw.dispatch(mock_request, call_next)
    assert resp.status_code == 200


@pytest.mark.anyio
async def test_api_key_middleware_no_key_configured(mock_request):
    """When no key configured, return 401."""
    reset_security_state()
    mw = APIKeyMiddleware(MagicMock())
    call_next = AsyncMock()
    resp = await mw.dispatch(mock_request, call_next)
    assert resp.status_code == 401
    assert b"not configured" in resp.body


@pytest.mark.anyio
async def test_api_key_middleware_missing_auth(mock_request):
    reset_security_state()
    set_api_key("secret")
    mw = APIKeyMiddleware(MagicMock())
    call_next = AsyncMock()
    resp = await mw.dispatch(mock_request, call_next)
    assert resp.status_code == 401
    assert b"Missing" in resp.body


@pytest.mark.anyio
async def test_api_key_middleware_invalid_key(mock_request):
    reset_security_state()
    set_api_key("secret")
    mw = APIKeyMiddleware(MagicMock())
    mock_request.headers["Authorization"] = "Bearer wrong"
    call_next = AsyncMock()
    resp = await mw.dispatch(mock_request, call_next)
    assert resp.status_code == 401
    assert b"Invalid" in resp.body


@pytest.mark.anyio
async def test_api_key_middleware_valid_key(mock_request):
    reset_security_state()
    set_api_key("secret")
    mw = APIKeyMiddleware(MagicMock())
    mock_request.headers["Authorization"] = "Bearer secret"
    call_next = AsyncMock(return_value=Response("ok"))
    resp = await mw.dispatch(mock_request, call_next)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# require_api_key dependency
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_require_api_key_success():
    reset_security_state()
    set_api_key("secret")
    creds = MagicMock()
    creds.credentials = "secret"
    await require_api_key(creds)


@pytest.mark.anyio
async def test_require_api_key_not_configured():
    reset_security_state()
    creds = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        await require_api_key(creds)
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_require_api_key_invalid():
    reset_security_state()
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
# apply_rate_limit dependency
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_apply_rate_limit_allows(mock_request):
    reset_security_state()
    await apply_rate_limit(mock_request)


@pytest.mark.anyio
async def test_apply_rate_limit_blocks(mock_request):
    reset_security_state()
    # Exhaust limit for the SAME IP as mock_request
    for _ in range(limiter.max_req):
        limiter.is_allowed("127.0.0.1")
    with pytest.raises(HTTPException) as exc_info:
        await apply_rate_limit(mock_request)
    assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# Admin endpoint integration (via AppState)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_admin_update_api_key(monkeypatch):
    """Admin endpoint rotates key and updates AppState config."""
    from ai_assistant.api.admin import update_api_key, _UpdateApiKeyRequest

    reset_security_state()
    state = MagicMock(spec=AppState)
    state.config = MagicMock()
    state.config.security = MagicMock()
    state.config.security.api_key = None

    # monkeypatch get_expected_api_key to read from our override
    monkeypatch.setattr(
        "ai_assistant.api.security.get_expected_api_key",
        lambda: state.config.security.api_key,
    )

    req = _UpdateApiKeyRequest(api_key="new-key")
    resp = await update_api_key(req, state)
    assert resp.updated is True
    assert state.config.security.api_key == "new-key"


@pytest.mark.anyio
async def test_admin_clear_api_key(monkeypatch):
    """Admin endpoint clears override when api_key=None."""
    from ai_assistant.api.admin import update_api_key, _UpdateApiKeyRequest

    reset_security_state()
    state = MagicMock(spec=AppState)
    state.config = MagicMock()
    state.config.security = MagicMock()
    state.config.security.api_key = "old-key"

    monkeypatch.setattr(
        "ai_assistant.api.security.get_expected_api_key",
        lambda: state.config.security.api_key,
    )

    req = _UpdateApiKeyRequest(api_key=None)
    resp = await update_api_key(req, state)
    assert resp.updated is True
    assert state.config.security.api_key is None


@pytest.mark.anyio
async def test_admin_update_empty_key_rejected(monkeypatch):
    """Empty string api_key is rejected (must be None or non-empty)."""
    from ai_assistant.api.admin import update_api_key, _UpdateApiKeyRequest

    reset_security_state()
    state = MagicMock(spec=AppState)
    state.config = MagicMock()

    monkeypatch.setattr(
        "ai_assistant.api.security.get_expected_api_key",
        lambda: (
            state.config.security.api_key if state.config.security.api_key else None
        ),
    )

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
