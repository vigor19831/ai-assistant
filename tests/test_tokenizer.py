"""Tests for tokenizer resolution and counting."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        with pytest.raises(ValueError, match="API key not found in config or env var MISSING_KEY"):
            resolve_api_key(None, "MISSING_KEY")

    def test_resolve_api_key_from_config(self) -> None:
        """Given: config value is provided.
        When: resolve_api_key is called.
        Then: config value is returned; env var is ignored."""
        result = resolve_api_key("config-secret", "SOME_VAR")
        assert result == "config-secret"


# ═══════════════════════════════════════════════════════════════════════════
# ITokenizer port tests
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
        Then: AdapterError is raised with helpful message."""
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData
        from ai_assistant.core.domain.errors import AdapterError

        tok = TiktokenTokenizer(TokenizerConfigData())
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", None):
                with pytest.raises(AdapterError, match="No tokenizer backend available"):
                    tok.count("hello world", "gpt-4o")

    def test_tiktoken_with_mock_encoder(self) -> None:
        """Given: mock encoder returning 5 tokens.
        When: TiktokenTokenizer.count is called.
        Then: 5 is returned."""
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

    def test_tiktoken_model_name_returns_str(self) -> None:
        """Given: TiktokenTokenizer initialized.
        When: model_name property is accessed.
        Then: returns expected string."""
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = TiktokenTokenizer(TokenizerConfigData())
        assert tok.model_name == "tiktoken"
        assert isinstance(tok.model_name, str)

    def test_char_fallback_model_name_returns_str(self) -> None:
        """Given: CharFallbackTokenizer initialized.
        When: model_name property is accessed.
        Then: returns expected string."""
        from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok = CharFallbackTokenizer(TokenizerConfigData())
        assert tok.model_name == "char-fallback"
        assert isinstance(tok.model_name, str)

    def test_model_name_is_str_not_optional(self) -> None:
        """Given: any ITokenizer implementation.
        When: model_name property is accessed.
        Then: returns str, not None, not Optional."""
        from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData

        tok1 = TiktokenTokenizer(TokenizerConfigData())
        tok2 = CharFallbackTokenizer(TokenizerConfigData())
        assert type(tok1.model_name) is str
        assert type(tok2.model_name) is str
        assert tok1.model_name is not None
        assert tok2.model_name is not None


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
    Then: all error paths raise AdapterError instead of silent fallback."""

    def test_keyerror_fallback_to_cl100k_base(self) -> None:
        """Given: tiktoken raises KeyError for unknown model.
        When: count is called.
        Then: falls back to cl100k_base encoding and returns correct count."""
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

    def test_tiktoken_both_paths_fail_raises_adapter_error(self) -> None:
        """Given: tiktoken encoding_for_model and get_encoding both raise.
        When: count is called.
        Then: AdapterError is raised."""
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData
        from ai_assistant.core.domain.errors import AdapterError

        tok = TiktokenTokenizer(TokenizerConfigData())
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken") as mock_tiktoken:
            mock_tiktoken.encoding_for_model.side_effect = KeyError("unknown")
            mock_tiktoken.get_encoding.side_effect = Exception("fail")
            with pytest.raises(AdapterError, match="tiktoken failed"):
                tok.count("hello world", "some-model")

    def test_hf_tokenizer_success(self, tmp_path: Path) -> None:
        """Given: tiktoken is None but tokenizers is available with local file.
        When: count is called.
        Then: HF tokenizer is used and returns correct count."""
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

    def test_hf_tokenizer_from_file_fails_raises_adapter_error(self, tmp_path: Path) -> None:
        """Given: tokenizers raises during from_file.
        When: count is called.
        Then: AdapterError is raised."""
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData
        from ai_assistant.core.domain.errors import AdapterError

        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.side_effect = RuntimeError("corrupt")

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "gpt-4o").mkdir()
                (tmp_path / "gpt-4o" / "tokenizer.json").write_text("{}")
                with pytest.raises(AdapterError, match="HF tokenizer failed"):
                    tok.count("hello world", "gpt-4o")

    def test_count_attribute_error_on_no_tokens_attr(self, tmp_path: Path) -> None:
        """Given: HF tokenizer encoder returns list (no .tokens).
        When: count is called.
        Then: len(list) is returned without error."""
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

    def test_count_hf_encode_raises_adapter_error(self, tmp_path: Path) -> None:
        """Given: encoder raises Exception during encode.
        When: count is called.
        Then: AdapterError is raised."""
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData
        from ai_assistant.core.domain.errors import AdapterError

        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf_tok = MagicMock()
        mock_hf_tok.encode.side_effect = RuntimeError("boom")
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.return_value = mock_hf_tok

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "gpt-4o").mkdir()
                (tmp_path / "gpt-4o" / "tokenizer.json").write_text("{}")
                with pytest.raises(AdapterError, match="HF tokenizer failed"):
                    tok.count("这是一个测试", "gpt-4o")

    def test_count_no_tiktoken_no_tokenizers_raises_adapter_error(self) -> None:
        """Given: neither tiktoken nor tokenizers available.
        When: count is called.
        Then: AdapterError is raised with helpful message."""
        from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
        from ai_assistant.core.domain.configs import TokenizerConfigData
        from ai_assistant.core.domain.errors import AdapterError

        tok = TiktokenTokenizer(TokenizerConfigData())
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", None):
                with pytest.raises(AdapterError, match="No tokenizer backend available"):
                    tok.count("hello world", "gpt-4o")
