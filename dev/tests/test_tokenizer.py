"""Tests for tokenizer resolution and counting."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_assistant.core.utils import _resolve_tokenizer_dir, count_tokens, get_tokenizer


class TestResolveTokenizerDir:
    def test_exact_match(self, tmp_path: Path) -> None:
        (tmp_path / "gpt-4o").mkdir(parents=True)
        (tmp_path / "gpt-4o" / "tokenizer.json").write_text("{}")
        result = _resolve_tokenizer_dir("gpt-4o", str(tmp_path))
        assert result is not None
        assert result.name == "gpt-4o"

    def test_partial_match(self, tmp_path: Path) -> None:
        (tmp_path / "qwen2.5").mkdir(parents=True)
        (tmp_path / "qwen2.5" / "tokenizer.json").write_text("{}")
        result = _resolve_tokenizer_dir("qwen2.5-7b-instruct", str(tmp_path))
        assert result is not None
        assert result.name == "qwen2.5"

    def test_underscore_to_dash(self, tmp_path: Path) -> None:
        (tmp_path / "gemma-3").mkdir(parents=True)
        (tmp_path / "gemma-3" / "tokenizer.json").write_text("{}")
        result = _resolve_tokenizer_dir("gemma_3_4b_it", str(tmp_path))
        assert result is not None
        assert result.name == "gemma-3"

    def test_no_match(self, tmp_path: Path) -> None:
        result = _resolve_tokenizer_dir("unknown-model", str(tmp_path))
        assert result is None


class TestCountTokens:
    def test_empty_text(self) -> None:
        assert count_tokens("") == 0

    def test_fallback_char_div4(self, tmp_path: Path) -> None:
        """When no tokenizer exists, fallback to len(text)//4."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            assert count_tokens("hello world") == 2  # 11 // 4

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent.parent / "data" / "tokenizers").exists(),
        reason="No offline tokenizers downloaded",
    )
    def test_offline_tokenizer_exists(self) -> None:
        """If tokenizer.json exists, count returns > 0 for real text."""
        text = "Hello world, this is a test."
        result = count_tokens(text, model="gemma-3-4b-it")
        assert result > 0

    @pytest.mark.skipif(
        not (Path(__file__).parent.parent.parent / "data" / "tokenizers").exists(),
        reason="No offline tokenizers downloaded",
    )
    def test_model_mapping(self) -> None:
        """Different models may count differently."""
        text = "Привет мир"
        # At least one model should work if tokenizers exist
        models = ["gemma-3-4b-it", "qwen2.5-7b-instruct", "llama-3.2-3b-instruct"]
        results = [count_tokens(text, model=m) for m in models]
        assert any(r > 0 for r in results)


class TestGetTokenizer:
    def test_tiktoken_for_openai(self) -> None:
        """OpenAI models should use tiktoken if available."""
        with patch("ai_assistant.core.utils.tiktoken") as mock_tiktoken:
            mock_enc = MagicMock()
            mock_tiktoken.encoding_for_model.return_value = mock_enc
            result = get_tokenizer("gpt-4o")
            assert result is not None

    def test_none_when_no_tokenizers(self) -> None:
        """Returns None when neither tiktoken nor tokenizers available."""
        with (
            patch("ai_assistant.core.utils.tiktoken", None),
            patch("ai_assistant.core.utils.tokenizers", None),
        ):
            result = get_tokenizer("some-model")
            assert result is None
