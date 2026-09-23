"""Tests for versioned prompt loader with Jinja2."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from ai_assistant.core.prompts import get_prompt


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


class TestRefusalConstantsSync:
    """Drift #50: the refusal matcher must stay in sync with what the
    prompt templates actually teach. If a template rule changes its
    refusal phrase without updating the constants, these tests fail —
    the alternative is refusals silently regaining sources.
    """

    def test_rag_strict_teaches_refusal_answer(self):
        from ai_assistant.core.constants import REFUSAL_ANSWER
        from ai_assistant.core.prompts import get_prompt

        # Rule 2 of rag_strict quotes the exact refusal string.
        rendered = get_prompt(
            "rag_strict", version="v1", query="q", context="[Document 1] x"
        )
        assert REFUSAL_ANSWER in rendered, (
            "rag_strict.j2 no longer contains REFUSAL_ANSWER verbatim — "
            "update the constant or the template so they match"
        )

    def test_rag_strict_teaches_injection_refusal(self):
        from ai_assistant.core.constants import INJECTION_REFUSAL_ANSWER
        from ai_assistant.core.prompts import get_prompt

        # Rule 9 of rag_strict quotes the exact injection refusal string.
        rendered = get_prompt(
            "rag_strict", version="v1", query="q", context="[Document 1] x"
        )
        assert INJECTION_REFUSAL_ANSWER in rendered, (
            "rag_strict.j2 no longer contains INJECTION_REFUSAL_ANSWER "
            "verbatim — update the constant or the template so they match"
        )

    def test_rag_simple_refusal_not_required(self):
        """rag_simple is a lenient template; it must not accidentally
        teach a different exact-refusal phrase that the matcher misses.
        """
        from ai_assistant.core.constants import REFUSAL_ANSWER
        from ai_assistant.core.prompts import get_prompt

        rendered = get_prompt(
            "rag_simple", version="v1", query="q", context="[Document 1] x"
        )
        # The lenient template must NOT teach the strict refusal phrase:
        # a refusal phrase without strict evidence rules would make
        # rag_simple answers refuse where evidence exists (#50 class).
        assert REFUSAL_ANSWER not in rendered, (
            "rag_simple accidentally teaches the strict refusal phrase"
        )

    def test_fallback_teaches_refusal_answer(self):
        """The degraded path (invalid prompt_name, drift: silent fallback
        FUTURE RISK) renders the same refusal contract — a drifting
        fallback phrase would produce refusals the matcher misses.
        """
        from ai_assistant.core.constants import REFUSAL_ANSWER
        from ai_assistant.core.prompts import get_prompt

        rendered = get_prompt(
            "fallback", version="v1", query="q", context="[Document 1] x"
        )
        assert REFUSAL_ANSWER in rendered, (
            "fallback.j2 no longer contains REFUSAL_ANSWER verbatim — "
            "update the constant or the template so they match"
        )

    def test_rag_strict_refusal_phrase_local_renders(self):
        """The owner-configured local refusal phrase must reach the
        rendered prompt — the variable is wired in rule 2 and the
        RU-question example; a silent drop would leave the model
        taught only the English closing phrase."""
        from ai_assistant.core.prompts import get_prompt

        rendered = get_prompt(
            "rag_strict",
            version="v1",
            query="q",
            context="[Document 1] x",
            refusal_phrase_local="Test local refusal.",
        )
        assert "Test local refusal." in rendered, (
            "refusal_phrase_local does not reach the rendered prompt — "
            "check the get_prompt call sites in chat/rag managers"
        )

    def test_rag_strict_english_fallback_when_local_unset(self):
        """Unset local phrase: both teaching spots fall back to the
        English constant (the {% else %} branch of the example)."""
        from ai_assistant.core.constants import REFUSAL_ANSWER
        from ai_assistant.core.prompts import get_prompt

        rendered = get_prompt(
            "rag_strict", version="v1", query="q", context="[Document 1] x"
        )
        assert rendered.count(REFUSAL_ANSWER) >= 2, (
            "unset refusal_phrase_local must fall back to REFUSAL_ANSWER "
            "in rule 2 and the RU-question example"
        )


    def test_rag_strict_teaches_local_refusal_when_configured(self):
        """The configured local phrase must reach the rendered prompt:
        the template wires the refusal_phrase_local render variable
        into rule 2 and the RU-question example."""
        from ai_assistant.core.prompts import get_prompt

        rendered = get_prompt(
            "rag_strict",
            version="v1",
            query="q",
            context="[Document 1] x",
            refusal_phrase_local="Test local refusal.",
        )
        assert "Test local refusal." in rendered, (
            "rag_strict.j2 does not render refusal_phrase_local — "
            "the local refusal is configured but never taught"
        )

    def test_rag_strict_english_refusal_when_local_unset(self):
        """Unset local phrase: every refusal-teaching spot falls back
        to the English constant — the RU-question example must not
        close with an empty answer."""
        from ai_assistant.core.constants import REFUSAL_ANSWER
        from ai_assistant.core.prompts import get_prompt

        rendered = get_prompt(
            "rag_strict", version="v1", query="q", context="[Document 1] x"
        )
        assert rendered.count(REFUSAL_ANSWER) >= 2, (
            "unset refusal_phrase_local must fall back to REFUSAL_ANSWER "
            "in both teaching spots (rule 2 and the RU-question example)"
        )
