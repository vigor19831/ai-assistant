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
        assert count_tokens("", model="gpt-4o") == 0

    def test_fallback_char_div4(self, tmp_path: Path) -> None:
        """Given: no tokenizer is available.
        When: count_tokens is called with ASCII text.
        Then: fallback len(text)//4 is used."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            assert count_tokens("hello world", model="gpt-4o") == 2  # 11 // 4

    def test_fallback_cjk_high_ratio(self) -> None:
        """Given: CJK-heavy text (>30%) with no tokenizer.
        When: count_tokens is called.
        Then: fallback uses len(text) instead of //4."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            text = "这是一个测试"  # 100% CJK
            assert count_tokens(text, model="gpt-4o") == len(text)

    def test_fallback_cjk_low_ratio(self) -> None:
        """Given: low CJK ratio text with no tokenizer.
        When: count_tokens is called.
        Then: fallback uses len(text)//4."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            text = "this is a test with one char: 这"  # ~4% CJK
            assert count_tokens(text, model="gpt-4o") == len(text) // 4

    def test_fallback_cjk_exact_threshold(self) -> None:
        """Given: exactly 30% CJK with no tokenizer.
        When: count_tokens is called.
        Then: threshold is >0.3, so //4 fallback is used."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            # 3 CJK out of 10 chars = exactly 30%
            text = "abc这def日g中"
            assert len(text) == 10
            assert count_tokens(text, model="gpt-4o") == 10 // 4  # 2

    def test_cjk_ratio_with_emoji(self) -> None:
        """Given: text with CJK characters and emoji.
        When: count_tokens is called without tokenizer.
        Then: emoji does not count as CJK; ratio is computed correctly."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            # 2 CJK out of 6 chars (emoji is not CJK) = 33.3%
            text = "你好😀世界"
            assert count_tokens(text, model="gpt-4o") == len(text)  # >30% CJK

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
            result = count_tokens(long_text, model="gpt-4o")
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


class TestCJKThresholdConstant:
    """Given: CJK threshold constant exists.
    When: _CJK_RATIO_THRESHOLD is accessed.
    Then: it has expected value and is used in count_tokens."""

    def test_threshold_constant_value(self) -> None:
        """Given: _CJK_RATIO_THRESHOLD is defined.
        When: accessing its value.
        Then: it equals 0.3."""
        from ai_assistant.core.utils import _CJK_RATIO_THRESHOLD
        assert _CJK_RATIO_THRESHOLD == 0.3
        assert isinstance(_CJK_RATIO_THRESHOLD, float)

    def test_threshold_used_in_count_tokens(self) -> None:
        """Given: text with CJK ratio exactly at threshold.
        When: count_tokens is called without tokenizer.
        Then: threshold comparison uses > (strict), so //4 fallback applies."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            # 3 CJK out of 10 chars = exactly 30% = threshold
            # Since comparison is > threshold, this should use //4
            text = "abc这def日g中"
            assert len(text) == 10
            from ai_assistant.core.utils import _CJK_RATIO_THRESHOLD
            ratio = 3 / 10  # 0.3 exactly
            assert ratio == _CJK_RATIO_THRESHOLD
            result = count_tokens(text, model="gpt-4o")
            assert result == 10 // 4  # Uses //4 because ratio is NOT > threshold

    def test_threshold_above_uses_len(self) -> None:
        """Given: text with CJK ratio above threshold.
        When: count_tokens is called without tokenizer.
        Then: len(text) fallback is used."""
        with patch("ai_assistant.core.utils.get_tokenizer", return_value=None):
            from ai_assistant.core.utils import _CJK_RATIO_THRESHOLD
            # 4 CJK out of 10 chars = 40% > 0.3 threshold
            text = "abc这def日g中日"
            ratio = 4 / 10  # 0.4
            assert ratio > _CJK_RATIO_THRESHOLD
            result = count_tokens(text, model="gpt-4o")
            assert result == len(text)  # Uses len because ratio > threshold


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
            result = await async_count_tokens("hello world", model="gpt-4o")
            assert result == count_tokens("hello world", model="gpt-4o")

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


class TestResolveApiKey:
    """Given: API key resolution from config or environment.
    When: resolve_api_key is called.
    Then: correct key is returned or ValueError is raised."""

    def test_resolve_api_key_from_env(self, monkeypatch) -> None:
        """Given: env var is set and config value is None.
        When: resolve_api_key is called.
        Then: env var value is returned."""
        from ai_assistant.core.utils import resolve_api_key

        monkeypatch.setenv("TEST_API_KEY", "secret-from-env")
        result = resolve_api_key(None, "TEST_API_KEY")
        assert result == "secret-from-env"

    def test_resolve_api_key_missing_raises(self, monkeypatch) -> None:
        """Given: env var is not set and config value is None.
        When: resolve_api_key is called.
        Then: ValueError is raised with descriptive message."""
        from ai_assistant.core.utils import resolve_api_key

        monkeypatch.delenv("MISSING_KEY", raising=False)
        with pytest.raises(ValueError, match="API key not found in config or env var MISSING_KEY"):
            resolve_api_key(None, "MISSING_KEY")

    def test_resolve_api_key_from_config(self) -> None:
        """Given: config value is provided.
        When: resolve_api_key is called.
        Then: config value is returned; env var is ignored."""
        from ai_assistant.core.utils import resolve_api_key

        result = resolve_api_key("config-secret", "SOME_VAR")
        assert result == "config-secret"


class TestResolveTokenizerDirErrors:
    """Given: filesystem errors during tokenizer resolution.
    When: _resolve_tokenizer_dir encounters OSError.
    Then: None is returned gracefully."""

    def test_permission_error_returns_none(self, tmp_path: Path) -> None:
        """Given: local_dir exists but iterdir raises PermissionError.
        When: _resolve_tokenizer_dir is called.
        Then: None is returned without propagating exception."""
        with patch("ai_assistant.core.utils.Path.iterdir", side_effect=PermissionError("denied")):
            result = _resolve_tokenizer_dir("gpt-4o", str(tmp_path))
            assert result is None


class TestGetTokenizerImportErrors:
    """Given: optional tokenizer libraries are unavailable.
    When: get_tokenizer is called.
    Then: None is returned or fallback behavior works."""

    def test_tiktoken_import_error_falls_back_to_tokenizers(self) -> None:
        """Given: tiktoken is None but tokenizers is available.
        When: get_tokenizer is called with local tokenizer.
        Then: tokenizers path is attempted."""
        from ai_assistant.core import utils as utils_module

        mock_tokenizers = MagicMock()
        mock_tokenizers.Tokenizer.from_file.return_value = MagicMock()

        with patch.object(utils_module, "tiktoken", None):
            with patch.object(utils_module, "tokenizers", mock_tokenizers):
                with patch.object(utils_module, "_resolve_tokenizer_dir", return_value=Path("/fake")):
                    result = get_tokenizer("gpt-4o", local_dir="/fake")
                    assert result is not None

    def test_both_libraries_none_returns_none(self) -> None:
        """Given: both tiktoken and tokenizers are None.
        When: get_tokenizer is called.
        Then: None is returned."""
        from ai_assistant.core import utils as utils_module

        with patch.object(utils_module, "tiktoken", None):
            with patch.object(utils_module, "tokenizers", None):
                result = get_tokenizer("gpt-4o")
                assert result is None

    def test_tokenizers_exception_returns_none(self) -> None:
        """Given: tokenizers raises Exception during from_file.
        When: get_tokenizer is called.
        Then: None is returned due to broad except."""
        from ai_assistant.core import utils as utils_module

        mock_tokenizers = MagicMock()
        mock_tokenizers.Tokenizer.from_file.side_effect = RuntimeError("fail")

        with patch.object(utils_module, "tiktoken", None):
            with patch.object(utils_module, "tokenizers", mock_tokenizers):
                with patch.object(utils_module, "_resolve_tokenizer_dir", return_value=Path("/fake")):
                    result = get_tokenizer("gpt-4o", local_dir="/fake")
                    assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# ITokenizer port tests (NEW)
# ═══════════════════════════════════════════════════════════════════════════


class TestITokenizerPort:
    """Given: ITokenizer port contract.
    When: concrete implementations are instantiated.
    Then: count() returns non-negative int and respects the contract."""

    def test_tiktoken_tokenizer_empty(self) -> None:
        """Given: empty text.
        When: TiktokenTokenizer.count is called.
        Then: 0 is returned."""
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData())
        assert tok.count("", "gpt-4o") == 0

    def test_char_fallback_tokenizer_empty(self) -> None:
        """Given: empty text.
        When: CharFallbackTokenizer.count is called.
        Then: 0 is returned."""
        from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = CharFallbackTokenizer(TokenizerConfigData())
        assert tok.count("", "any") == 0

    def test_char_fallback_ascii(self) -> None:
        """Given: ASCII text.
        When: CharFallbackTokenizer.count is called.
        Then: len(text) // 4 is returned."""
        from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = CharFallbackTokenizer(TokenizerConfigData())
        assert tok.count("hello world", "any") == 11 // 4  # 2

    def test_char_fallback_cjk_high(self) -> None:
        """Given: CJK-heavy text.
        When: CharFallbackTokenizer.count is called.
        Then: len(text) is returned."""
        from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = CharFallbackTokenizer(TokenizerConfigData())
        text = "这是一个测试"
        assert tok.count(text, "any") == len(text)

    def test_char_fallback_cjk_low(self) -> None:
        """Given: low CJK ratio text.
        When: CharFallbackTokenizer.count is called.
        Then: len(text) // 4 is returned."""
        from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = CharFallbackTokenizer(TokenizerConfigData())
        text = "this is a test with one char: 这"
        assert tok.count(text, "any") == len(text) // 4

    def test_tiktoken_fallback_when_no_libs(self) -> None:
        """Given: no tokenizer libraries available.
        When: TiktokenTokenizer.count is called.
        Then: falls back to char heuristic."""
        from unittest.mock import patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData())
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", None):
                assert tok.count("hello world", "gpt-4o") == 11 // 4

    def test_tiktoken_with_mock_encoder(self) -> None:
        """Given: mock encoder returning 5 tokens.
        When: TiktokenTokenizer.count is called.
        Then: 5 is returned."""
        from unittest.mock import MagicMock, patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData())
        mock_enc = MagicMock()
        mock_enc.encode.return_value = [1, 2, 3, 4, 5]
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken") as mock_tiktoken:
            mock_tiktoken.encoding_for_model.return_value = mock_enc
            assert tok.count("hello", "gpt-4o") == 5

    def test_itokenizer_is_abstract(self) -> None:
        """Given: ITokenizer port.
        When: inspected.
        Then: it is abstract and count is abstractmethod."""
        import inspect
        from ai_assistant.core.ports.tokenizer import ITokenizer

        assert inspect.isabstract(ITokenizer)
        assert getattr(ITokenizer.count, "__isabstractmethod__", False)


class TestTokenizerAdapterRegistry:
    """Given: adapter registry.
    When: tokenizer adapters are inspected.
    Then: both are registered."""

    def test_tiktoken_registered(self) -> None:
        """Given: registry loaded.
        When: tokenizer port is inspected.
        Then: TiktokenTokenizer is registered under 'tiktoken'."""
        from ai_assistant.adapters._registry import get_registry
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer

        registry = get_registry()
        assert registry["tokenizer"]["tiktoken"] is TiktokenTokenizer

    def test_char_fallback_registered(self) -> None:
        """Given: registry loaded.
        When: tokenizer port is inspected.
        Then: CharFallbackTokenizer is registered under 'char_fallback'."""
        from ai_assistant.adapters._registry import get_registry
        from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer

        registry = get_registry()
        assert registry["tokenizer"]["char_fallback"] is CharFallbackTokenizer


class TestTiktokenTokenizerInternals:
    """Given: TiktokenTokenizer with various backend states.
    When: count is called.
    Then: all error paths and fallback paths are covered."""

    def test_keyerror_fallback_to_cl100k_base(self) -> None:
        """Given: tiktoken raises KeyError for unknown model.
        When: count is called.
        Then: falls back to cl100k_base encoding and returns correct count."""
        from unittest.mock import MagicMock, patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData())
        mock_enc = MagicMock()
        mock_enc.encode.return_value = [1, 2, 3, 4, 5]
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken") as mock_tiktoken:
            mock_tiktoken.encoding_for_model.side_effect = KeyError("unknown")
            mock_tiktoken.get_encoding.return_value = mock_enc
            result = tok.count("hello", "unknown-model")
            assert result == 5
            mock_tiktoken.get_encoding.assert_called_once_with("cl100k_base")

    def test_tiktoken_both_paths_fail_returns_fallback(self) -> None:
        """Given: tiktoken encoding_for_model and get_encoding both raise.
        When: count is called with ASCII text.
        Then: fallback len(text)//4 is returned."""
        from unittest.mock import patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData())
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken") as mock_tiktoken:
            mock_tiktoken.encoding_for_model.side_effect = KeyError("unknown")
            mock_tiktoken.get_encoding.side_effect = Exception("fail")
            result = tok.count("hello world", "some-model")
            assert result == 11 // 4

    def test_hf_tokenizer_success(self, tmp_path: Path) -> None:
        """Given: tiktoken is None but tokenizers is available with local file.
        When: count is called.
        Then: HF tokenizer is used and returns correct count."""
        from unittest.mock import MagicMock, patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf_tok = MagicMock()
        mock_tokens = MagicMock()
        mock_tokens.tokens = [1, 2, 3, 4, 5]
        mock_hf_tok.encode.return_value = mock_tokens
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.return_value = mock_hf_tok

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "gpt-4o").mkdir()
                (tmp_path / "gpt-4o" / "tokenizer.json").write_text("{}")
                result = tok.count("hello", "gpt-4o")
                assert result == 5

    def test_hf_tokenizer_from_file_fails(self, tmp_path: Path) -> None:
        """Given: tokenizers raises during from_file.
        When: count is called.
        Then: fallback len(text)//4 is returned."""
        from unittest.mock import MagicMock, patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.side_effect = RuntimeError("corrupt")

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "gpt-4o").mkdir()
                (tmp_path / "gpt-4o" / "tokenizer.json").write_text("{}")
                result = tok.count("hello world", "gpt-4o")
                assert result == 11 // 4

    def test_count_attribute_error_fallback(self, tmp_path: Path) -> None:
        """Given: HF tokenizer encoder returns list (no .tokens).
        When: count is called.
        Then: AttributeError triggers tiktoken-style path, len(list) returned."""
        from unittest.mock import MagicMock, patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf_tok = MagicMock()
        # Simulate tiktoken-style: encode() returns list[int], no .tokens attribute
        mock_hf_tok.encode.return_value = [1, 2, 3, 4, 5, 6]
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.return_value = mock_hf_tok

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "gpt-4o").mkdir()
                (tmp_path / "gpt-4o" / "tokenizer.json").write_text("{}")
                result = tok.count("hello", "gpt-4o")
                assert result == 6

    def test_count_exception_fallback_to_cjk(self, tmp_path: Path) -> None:
        """Given: encoder raises Exception during encode.
        When: count is called with CJK-heavy text.
        Then: fallback len(text) is returned."""
        from unittest.mock import MagicMock, patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf_tok = MagicMock()
        mock_hf_tok.encode.side_effect = RuntimeError("boom")
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.return_value = mock_hf_tok

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "gpt-4o").mkdir()
                (tmp_path / "gpt-4o" / "tokenizer.json").write_text("{}")
                text = "这是一个测试"
                result = tok.count(text, "gpt-4o")
                assert result == len(text)

    def test_count_exception_fallback_to_ascii(self, tmp_path: Path) -> None:
        """Given: encoder raises Exception during encode.
        When: count is called with ASCII text.
        Then: fallback len(text)//4 is returned."""
        from unittest.mock import MagicMock, patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf_tok = MagicMock()
        mock_hf_tok.encode.side_effect = RuntimeError("boom")
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.return_value = mock_hf_tok

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "gpt-4o").mkdir()
                (tmp_path / "gpt-4o" / "tokenizer.json").write_text("{}")
                result = tok.count("hello world", "gpt-4o")
                assert result == 11 // 4

    def test_count_no_tiktoken_no_tokenizers_ascii(self) -> None:
        """Given: neither tiktoken nor tokenizers available.
        When: count is called with ASCII text.
        Then: fallback len(text)//4 is returned."""
        from unittest.mock import patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData())
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", None):
                result = tok.count("hello world", "gpt-4o")
                assert result == 11 // 4

    def test_count_no_tiktoken_no_tokenizers_cjk(self) -> None:
        """Given: neither tiktoken nor tokenizers available.
        When: count is called with CJK text.
        Then: fallback len(text) is returned."""
        from unittest.mock import patch
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData())
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", None):
                text = "这是一个测试"
                result = tok.count(text, "gpt-4o")
                assert result == len(text)
