"""Tests for core utility funcions.

Coverage: resolve_api_key.
Design: Given/When/Then docstrings, one function per test case.
"""

from __future__ import annotations

import logging

import pytest

from ai_assistant.core.utils import resolve_api_key

logger = logging.getLogger(__name__)


class TestResolveApiKey:
    """Given: API key resolution from config or environment.
    When: resolve_api_key is called.
    Then: correct key is returned or ValueError is raised."""

    def test_resolve_api_key_from_env(self, monkeypatch) -> None:
        """Given: env var is set and config value is None.
        When: resolve_api_key is called.
        Then: env var value is returned."""
        monkeypatch.setenv("TEST_API_KEY", "secret-from-env")
        result = resolve_api_key(None, "TEST_API_KEY")
        assert result == "secret-from-env"

    def test_resolve_api_key_missing_raises(self, monkeypatch) -> None:
        """Given: env var is not set and config value is None.
        When: resolve_api_key is called.
        Then: ValueError is raised with descriptive message."""
        monkeypatch.delenv("MISSING_KEY", raising=False)
        with pytest.raises(
            ValueError, match="API key not found in config or env var MISSING_KEY"
        ):
            resolve_api_key(None, "MISSING_KEY")

    def test_resolve_api_key_from_config(self) -> None:
        """Given: config value is provided.
        When: resolve_api_key is called.
        Then: config value is returned; env var is ignored."""
        result = resolve_api_key("config-secret", "SOME_VAR")
        assert result == "config-secret"
