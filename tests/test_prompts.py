"""Tests for versioned prompt loader with Jinja2."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from ai_assistant.core.prompts import _env_cache, _render, get_prompt


class TestPromptVersion:
    """Given: versioned prompt loader.
    When: get_prompt is called with various version arguments.
    Then: correct behavior for missing, valid, and invalid versions."""

    def test_get_prompt_requires_version(self):
        """Given: version is not provided.
        When: get_prompt is called.
        Then: ValueError is raised with descriptive message."""
        with pytest.raises(ValueError, match="prompt version is required"):
            get_prompt("rag_strict", query="test", context="ctx")

    def test_get_prompt_invalid_version_raises(self, tmp_path: Path, monkeypatch):
        """Given: version directory does not exist.
        When: get_prompt is called.
        Then: ValueError is raised."""
        monkeypatch.setattr(
            "ai_assistant.core.prompts.__file__", str(tmp_path / "prompts.py")
        )
        with pytest.raises(ValueError, match="Prompt version directory not found"):
            get_prompt("dummy", version="v999")


class TestPromptEnvCache:
    """Given: Jinja2 environment caching.
    When: get_prompt is called multiple times.
    Then: Environment is constructed once per version."""

    def test_get_prompt_env_cached_once(self, tmp_path: Path, monkeypatch):
        """Given: multiple calls with same version.
        When: get_prompt is called repeatedly.
        Then: Environment constructor called exactly once per version."""
        v1 = tmp_path / "v1"
        v1.mkdir()
        (v1 / "dummy.j2").write_text("{{ x }}")

        v2 = tmp_path / "v2"
        v2.mkdir()
        (v2 / "dummy.j2").write_text("{{ x }}")

        monkeypatch.setattr("ai_assistant.core.prompts._env_cache", {})
        monkeypatch.setattr(
            "ai_assistant.core.prompts.__file__", str(tmp_path / "prompts.py")
        )

        with mock.patch("ai_assistant.core.prompts.Environment") as MockEnv:
            fake_template = mock.Mock()
            fake_template.render.side_effect = lambda **kw: "ok"
            fake_env = mock.Mock()
            fake_env.get_template.return_value = fake_template
            MockEnv.return_value = fake_env

            # Two calls with the same version → Environment constructed once
            get_prompt("dummy", version="v1", x="a")
            get_prompt("dummy", version="v1", x="b")
            assert MockEnv.call_count == 1

            # Different version → new Environment
            get_prompt("dummy", version="v2", x="c")
            assert MockEnv.call_count == 2


class TestJinja2EnvironmentConfig:
    """Given: Jinja2 environment setup.
    When: Environment is constructed.
    Then: correct loader and options are applied."""

    def test_jinja2_environment_config(self, tmp_path: Path, monkeypatch):
        """Given: template directory with Jinja2 files.
        When: get_prompt triggers Environment creation.
        Then: Environment uses FileSystemLoader with trim_blocks and lstrip_blocks."""
        v1 = tmp_path / "v1"
        v1.mkdir()
        (v1 / "test.j2").write_text("line1\n  line2\n")

        monkeypatch.setattr("ai_assistant.core.prompts._env_cache", {})
        monkeypatch.setattr(
            "ai_assistant.core.prompts.__file__", str(tmp_path / "prompts.py")
        )

        with mock.patch("ai_assistant.core.prompts.Environment") as MockEnv:
            fake_template = mock.Mock()
            fake_template.render.return_value = "rendered"
            fake_env = mock.Mock()
            fake_env.get_template.return_value = fake_template
            MockEnv.return_value = fake_env

            get_prompt("test", version="v1")

            # Verify Environment was constructed with expected options
            MockEnv.assert_called_once()
            call_kwargs = MockEnv.call_args.kwargs
            assert "loader" in call_kwargs
            assert call_kwargs["trim_blocks"] is True
            assert call_kwargs["lstrip_blocks"] is True

    def test_template_rendering_with_blocks(self, tmp_path: Path, monkeypatch):
        """Given: template with Jinja2 block syntax.
        When: get_prompt renders it.
        Then: trim_blocks and lstrip_blocks produce clean output."""
        v1 = tmp_path / "v1"
        v1.mkdir()
        # Template with indentation and blocks
        (v1 / "blocks.j2").write_text(
            "{% for item in items %}\n  {{ item }}\n{% endfor %}\n"
        )

        monkeypatch.setattr("ai_assistant.core.prompts._env_cache", {})
        monkeypatch.setattr(
            "ai_assistant.core.prompts.__file__", str(tmp_path / "prompts.py")
        )

        result = get_prompt("blocks", version="v1", items=["a", "b"])
        # With trim_blocks=True and lstrip_blocks=True, output should be compact
        assert "a" in result
        assert "b" in result
