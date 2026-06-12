"""Tests for versioned prompt loader with Jinja2 and LRU cache."""

from __future__ import annotations

import dataclasses
import logging
from pathlib import Path
from unittest import mock

import pytest

from ai_assistant.core.prompts import (
    _env_cache,
    _make_hashable,
    _render,
    get_prompt,
)

logger = logging.getLogger(__name__)


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


class TestPromptCache:
    """Given: Jinja2 environment caching via lru_cache.
    When: get_prompt is called multiple times.
    Then: Environment is constructed once per version; cache keys are hashable."""

    def test_get_prompt_env_cached_once(self, tmp_path: Path, monkeypatch):
        """Given: multiple calls with same version.
        When: get_prompt is called repeatedly.
        Then: Environment constructor called exactly once per version."""
        # Prepare fake template directories
        v1 = tmp_path / "v1"
        v1.mkdir()
        (v1 / "dummy.j2").write_text("{{ x }}")

        v2 = tmp_path / "v2"
        v2.mkdir()
        (v2 / "dummy.j2").write_text("{{ x }}")

        # Reset cache and repoint module's __file__
        monkeypatch.setattr("ai_assistant.core.prompts._env_cache", {})
        monkeypatch.setattr(
            "ai_assistant.core.prompts.__file__", str(tmp_path / "prompts.py")
        )
        _render.cache_clear()

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

    def test_cache_hit_same_version(self, tmp_path: Path, monkeypatch):
        """Given: identical name, version, and kwargs.
        When: get_prompt is called twice with same args.
        Then: second call is a cache hit; render called once."""
        v1 = tmp_path / "v1"
        v1.mkdir()
        (v1 / "test.j2").write_text("{{ msg }}")

        monkeypatch.setattr("ai_assistant.core.prompts._env_cache", {})
        monkeypatch.setattr(
            "ai_assistant.core.prompts.__file__", str(tmp_path / "prompts.py")
        )
        _render.cache_clear()

        with mock.patch("ai_assistant.core.prompts.Environment") as MockEnv:
            fake_template = mock.Mock()
            fake_template.render.return_value = "rendered"
            fake_env = mock.Mock()
            fake_env.get_template.return_value = fake_template
            MockEnv.return_value = fake_env

            r1 = get_prompt("test", version="v1", msg="hello")
            r2 = get_prompt("test", version="v1", msg="hello")

            # Environment created once; template.render once (cache hit on second)
            assert MockEnv.call_count == 1
            assert fake_template.render.call_count == 1
            assert r1 == r2 == "rendered"

    def test_cache_miss_different_version(self, tmp_path: Path, monkeypatch):
        """Given: same name and kwargs but different version.
        When: get_prompt is called.
        Then: cache miss; new Environment and render."""
        v1 = tmp_path / "v1"
        v1.mkdir()
        (v1 / "test.j2").write_text("v1: {{ msg }}")

        v2 = tmp_path / "v2"
        v2.mkdir()
        (v2 / "test.j2").write_text("v2: {{ msg }}")

        monkeypatch.setattr("ai_assistant.core.prompts._env_cache", {})
        monkeypatch.setattr(
            "ai_assistant.core.prompts.__file__", str(tmp_path / "prompts.py")
        )
        _render.cache_clear()

        with mock.patch("ai_assistant.core.prompts.Environment") as MockEnv:
            def make_env(version_dir):
                fake_template = mock.Mock()
                fake_template.render.return_value = f"from {version_dir.name}"
                fake_env = mock.Mock()
                fake_env.get_template.return_value = fake_template
                return fake_env

            MockEnv.side_effect = lambda **kw: make_env(Path(kw["loader"].searchpath[0]))

            r1 = get_prompt("test", version="v1", msg="hello")
            r2 = get_prompt("test", version="v2", msg="hello")

            assert MockEnv.call_count == 2
            assert r1 == "from v1"
            assert r2 == "from v2"


class TestMakeHashable:
    """Given: various Python types as kwargs values.
    When: _make_hashable is called.
    Then: value is converted to a hashable form suitable for cache keys."""

    def test_hashable_primitives(self):
        """Given: primitive types.
        When: _make_hashable is called.
        Then: primitives pass through unchanged."""
        assert _make_hashable("str") == "str"
        assert _make_hashable(42) == 42
        assert _make_hashable(3.14) == 3.14
        assert _make_hashable(True) is True
        assert _make_hashable(None) is None

    def test_hashable_list(self):
        """Given: list of primitives.
        When: _make_hashable is called.
        Then: converted to tuple recursively."""
        result = _make_hashable([1, 2, "three"])
        assert result == (1, 2, "three")
        assert isinstance(result, tuple)

    def test_hashable_dict(self):
        """Given: dict with primitive values.
        When: _make_hashable is called.
        Then: converted to sorted tuple of key-value pairs."""
        result = _make_hashable({"b": 2, "a": 1})
        assert result == (("a", 1), ("b", 2))

    def test_hashable_nested(self):
        """Given: nested structures.
        When: _make_hashable is called.
        Then: deeply converted to hashable form."""
        result = _make_hashable({"items": [{"id": 1}, {"id": 2}]})
        assert isinstance(result, tuple)

    def test_hashable_dataclass(self):
        """Given: a dataclass instance.
        When: _make_hashable is called.
        Then: converted to tuple of (field_name, value) pairs."""
        @dataclasses.dataclass
        class Dummy:
            name: str
            value: int

        obj = Dummy(name="test", value=42)
        result = _make_hashable(obj)
        assert result == (("name", "test"), ("value", 42))

    def test_hashable_unsupported_type(self):
        """Given: an unsupported type (e.g., a set).
        When: _make_hashable is called.
        Then: falls back to str() representation."""
        result = _make_hashable({1, 2, 3})
        assert isinstance(result, str)


class TestHashableChunksInCacheKey:
    """Given: kwargs containing lists and dicts.
    When: _kwargs_to_tuple is used for cache key.
    Then: complex structures become hashable cache keys."""

    def test_list_of_strings_in_kwargs(self):
        """Given: list of strings as kwarg value.
        When: cache key is built.
        Then: list is converted to tuple; same list produces same key."""
        from ai_assistant.core.prompts import _kwargs_to_tuple

        kwargs1 = {"items": ["a", "b", "c"]}
        kwargs2 = {"items": ["a", "b", "c"]}
        assert _kwargs_to_tuple(kwargs1) == _kwargs_to_tuple(kwargs2)

    def test_dict_in_kwargs(self):
        """Given: dict as kwarg value.
        When: cache key is built.
        Then: dict is converted to sorted tuple; same dict produces same key."""
        from ai_assistant.core.prompts import _kwargs_to_tuple

        kwargs1 = {"meta": {"z": 1, "a": 2}}
        kwargs2 = {"meta": {"a": 2, "z": 1}}
        assert _kwargs_to_tuple(kwargs1) == _kwargs_to_tuple(kwargs2)

    def test_different_kwargs_produce_different_keys(self):
        """Given: different kwarg values.
        When: cache key is built.
        Then: different values produce different keys."""
        from ai_assistant.core.prompts import _kwargs_to_tuple

        assert _kwargs_to_tuple({"a": 1}) != _kwargs_to_tuple({"a": 2})


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
        _render.cache_clear()

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
            assert call_kwargs.get("trim_blocks") is True
            assert call_kwargs.get("lstrip_blocks") is True

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
        _render.cache_clear()

        result = get_prompt("blocks", version="v1", items=["a", "b"])
        # With trim_blocks=True and lstrip_blocks=True, output should be compact
        assert "a" in result
        assert "b" in result
