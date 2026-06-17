"""Tests for tokenizer resolution and counting."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_assistant.core.utils import (
    _resolve_tokenizer_dir,
    async_count_tokens,
    async_get_tokenizer,
    count_tokens,
    get_tokenizer,
)

logger = logging.getLogger(__name__)


class TestResolveTokenizerDir:
    """Given: local tokenizer directories with various naming conventions.
    When: _resolve_tokenizer_dir is called.
    Then: correct directory is resolved or None is returned."""

    def test_exact_match(self, tmp_path: Path) -> None:
        """Given: directory name exactly matches model name.
        When: _resolve_tokenizer_dir is called.
        Then: exact match directory is returned."""
        (tmp_path / "gpt-4o").mkdir(parents=True)
        (tmp_path / "gpt-4o" / "tokenizer.json").write_text("{}")
        result = _resolve_tokenizer_dir("gpt-4o", str(tmp_path))
        assert result is not None
        assert result.name == "gpt-4o"

    def test_partial_match(self, tmp_path: Path) -> None:
        """Given: directory name is a prefix of the model name.
        When: _resolve_tokenizer_dir is called.
        Then: prefix-matching directory is returned."""
        (tmp_path / "qwen2.5").mkdir(parents=True)
        (tmp_path / "qwen2.5" / "tokenizer.json").write_text("{}")
        result = _resolve_tokenizer_dir("qwen2.5-7b-instruct", str(tmp_path))
        assert result is not None
        assert result.name == "qwen2.5"

    def test_underscore_to_dash(self, tmp_path: Path) -> None:
        """Given: model name uses underscores, directory uses dashes.
        When: _resolve_tokenizer_dir is called.
        Then: underscore/dash normalization works."""
        (tmp_path / "gemma-3").mkdir(parents=True)
        (tmp_path / "gemma-3" / "tokenizer.json").write_text("{}")
        result = _resolve_tokenizer_dir("gemma_3_4b_it", str(tmp_path))
        assert result is not None
        assert result.name == "gemma-3"

    def test_no_match(self, tmp_path: Path) -> None:
        """Given: no matching directory exists.
        When: _resolve_tokenizer_dir is called.
        Then: None is returned."""
        result = _resolve_tokenizer_dir("unknown-model", str(tmp_path))
        assert result is None

    def test_resolve_tokenizer_dir_nonexistent_local(self, tmp_path: Path) -> None:
        """Given: local_dir does not exist at all.
        When: _resolve_tokenizer_dir is called.
        Then: None is returned without raising."""
        nonexistent = tmp_path / "does_not_exist"
        result = _resolve_tokenizer_dir("gpt-4o", str(nonexistent))
        assert result is None

    def test_no_tokenizer_json_skipped(self, tmp_path: Path) -> None:
        """Given: directory exists but lacks tokenizer.json.
        When: _resolve_tokenizer_dir is called.
        Then: directory is skipped, None is returned."""
        (tmp_path / "gpt-4o").mkdir(parents=True)
        # No tokenizer.json written
        result = _resolve_tokenizer_dir("gpt-4o", str(tmp_path))
        assert result is None


class TestCountTokens:
    """Given: text of various lengths and compositions.
    When: count_tokens is called.
    Then: correct token count is returned via tokenizer or fallback."""

    def test_empty_text(self) -> None:
        """Given: empty string.
        When: count_tokens is called.
        Then: 0 is returned."""
        assert count_tokens("") == 0

    def test_fallback_char_div4(self, tmp_path: Path) -> None:
        """Given: no tokenizer is available.
        When: count_tokens is called with ASCII text.
        Then: fallback len(text)//4 is used."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            assert count_tokens("hello world") == 2  # 11 // 4

    def test_fallback_cjk_high_ratio(self) -> None:
        """Given: CJK-heavy text (>30%) with no tokenizer.
        When: count_tokens is called.
        Then: fallback uses len(text) instead of //4."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            text = "这是一个测试"  # 100% CJK
            assert count_tokens(text) == len(text)

    def test_fallback_cjk_low_ratio(self) -> None:
        """Given: low CJK ratio text with no tokenizer.
        When: count_tokens is called.
        Then: fallback uses len(text)//4."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            text = "this is a test with one char: 这"  # ~4% CJK
            assert count_tokens(text) == len(text) // 4

    def test_fallback_cjk_exact_threshold(self) -> None:
        """Given: exactly 30% CJK with no tokenizer.
        When: count_tokens is called.
        Then: threshold is >0.3, so //4 fallback is used."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            # 3 CJK out of 10 chars = exactly 30%
            text = "abc这def日g中"
            assert len(text) == 10
            assert count_tokens(text) == 10 // 4  # 2

    def test_cjk_ratio_with_emoji(self) -> None:
        """Given: text with CJK characters and emoji.
        When: count_tokens is called without tokenizer.
        Then: emoji does not count as CJK; ratio is computed correctly."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            # 2 CJK out of 6 chars (emoji is not CJK) = 33.3%
            text = "你好😀世界"
            assert count_tokens(text) == len(text)  # >30% CJK

    def test_count_tokens_with_model_param(self) -> None:
        """Given: model parameter is provided.
        When: count_tokens is called.
        Then: model parameter is forwarded to get_tokenizer."""
        mock_enc = MagicMock()
        mock_enc.encode.return_value = [1, 2, 3, 4, 5]
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=mock_enc) as mock_get:
            result = count_tokens("hello", model="custom-model")
            mock_get.assert_called_once_with("custom-model", local_dir="./data/tokenizers")
            assert result == 5

    def test_count_tokens_very_long_text(self) -> None:
        """Given: very long text (100k chars).
        When: count_tokens is called without tokenizer.
        Then: returns quickly with approximate count; no crash."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            long_text = "a" * 100_000
            result = count_tokens(long_text)
            assert result == 100_000 // 4

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "data" / "tokenizers").exists(),
        reason="No offline tokenizers downloaded",
    )
    def test_offline_tokenizer_exists(self) -> None:
        """Given: offline tokenizers are available.
        When: count_tokens is called with discovered models.
        Then: all return positive counts for real text."""
        tokenizer_dir = Path(__file__).parent.parent / "data" / "tokenizers"
        available = [
            d.name
            for d in tokenizer_dir.iterdir()
            if d.is_dir() and (d / "tokenizer.json").exists()
        ]
        if not available:
            pytest.skip("No tokenizer subdirectories with tokenizer.json found")
        text = "Hello world, this is a test."
        results = [count_tokens(text, model=name) for name in available]
        assert all(r > 0 for r in results), f"Failed for: {available}"

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent / "data" / "tokenizers").exists(),
        reason="No offline tokenizers downloaded",
    )
    def test_model_mapping(self) -> None:
        """Given: multiple offline tokenizers.
        When: count_tokens is called with different models.
        Then: at least one returns a positive count."""
        tokenizer_dir = Path(__file__).parent.parent / "data" / "tokenizers"
        available = [
            d.name
            for d in tokenizer_dir.iterdir()
            if d.is_dir() and (d / "tokenizer.json").exists()
        ]
        if not available:
            pytest.skip("No tokenizer subdirectories with tokenizer.json found")
        text = "Привет мир"
        results = [count_tokens(text, model=m) for m in available]
        assert any(r > 0 for r in results), f"All tokenizers returned 0 for: {available}"


class TestGetTokenizer:
    """Given: various tokenizer backends.
    When: get_tokenizer is called.
    Then: correct backend is used or None is returned."""

    def test_tiktoken_for_openai(self) -> None:
        """Given: tiktoken is available.
        When: get_tokenizer is called with OpenAI model.
        Then: tiktoken encoding is returned."""
        with patch("ai_assistant.core.utils.tiktoken") as mock_tiktoken:
            mock_enc = MagicMock()
            mock_tiktoken.encoding_for_model.return_value = mock_enc
            result = get_tokenizer("gpt-4o")
            assert result is not None

    def test_tiktoken_fallback_encoding(self) -> None:
        """Given: tiktoken is available but model is unknown.
        When: get_tokenizer is called.
        Then: falls back to cl100k_base encoding."""
        with patch("ai_assistant.core.utils.tiktoken") as mock_tiktoken:
            mock_tiktoken.encoding_for_model.side_effect = KeyError("unknown")
            mock_enc = MagicMock()
            mock_tiktoken.get_encoding.return_value = mock_enc
            result = get_tokenizer("unknown-model")
            assert result is not None
            mock_tiktoken.get_encoding.assert_called_once_with("cl100k_base")

    def test_none_when_no_tokenizers(self) -> None:
        """Given: neither tiktoken nor tokenizers is available.
        When: get_tokenizer is called.
        Then: None is returned."""
        with (
            patch("ai_assistant.core.utils.tiktoken", None),
            patch("ai_assistant.core.utils.tokenizers", None),
        ):
            result = get_tokenizer("some-model")
            assert result is None

    def test_get_tokenizer_cache_behavior(self) -> None:
        """Given: tokenizer is loaded successfully.
        When: get_tokenizer is called multiple times.
        Then: no caching at get_tokenizer level; fresh resolution each call.
        Note: This verifies the function does not maintain internal cache."""
        with patch("ai_assistant.core.utils.tiktoken") as mock_tiktoken:
            mock_enc = MagicMock()
            mock_tiktoken.encoding_for_model.return_value = mock_enc
            r1 = get_tokenizer("gpt-4o")
            r2 = get_tokenizer("gpt-4o")
            # Each call should invoke tiktoken (no caching in get_tokenizer itself)
            assert mock_tiktoken.encoding_for_model.call_count == 2
            assert r1 is mock_enc
            assert r2 is mock_enc


class TestAsyncTokenizer:
    """Given: async tokenizer operations.
    When: async_count_tokens or async_get_tokenizer is called.
    Then: results match sync versions; run in event loop."""

    @pytest.mark.asyncio
    async def test_async_count_tokens(self) -> None:
        """Given: text to count.
        When: async_count_tokens is called.
        Then: result matches count_tokens."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            result = await async_count_tokens("hello world")
            assert result == count_tokens("hello world")

    @pytest.mark.asyncio
    async def test_async_get_tokenizer(self) -> None:
        """Given: model name.
        When: async_get_tokenizer is called.
        Then: result matches get_tokenizer."""
        with patch("ai_assistant.core.utils.tiktoken") as mock_tiktoken:
            mock_enc = MagicMock()
            mock_tiktoken.encoding_for_model.return_value = mock_enc
            result = await async_get_tokenizer("gpt-4o")
            assert result is not None
            assert result is mock_enc

    @pytest.mark.asyncio
    async def test_async_count_tokens_forwards_params(self) -> None:
        """Given: model and local_dir parameters.
        When: async_count_tokens is called.
        Then: parameters are forwarded to count_tokens."""
        mock_enc = MagicMock()
        mock_enc.encode.return_value = [1, 2, 3]
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=mock_enc):
            result = await async_count_tokens("hello", model="custom", local_dir=".pytest_tmp/tok")
            assert result == 3
