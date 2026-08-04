"""Tests for tokenizer resolution and counting."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ai_assistant.adapters._registry import get_registry
from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
from ai_assistant.adapters.huggingface_tokenizer import HuggingFaceTokenizer
from ai_assistant.adapters.tiktoken_tokenizer import TiktokenTokenizer
from ai_assistant.core.domain.configs import TokenizerConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.ports.tokenizer import ITokenizer

logger = logging.getLogger(__name__)


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
        tok = TiktokenTokenizer(TokenizerConfigData())
        assert tok.count("") == 0

    def test_char_fallback_tokenizer_empty(self) -> None:
        """Given: empty text.
        When: CharFallbackTokenizer.count is called.
        Then: 0 is returned."""
        tok = CharFallbackTokenizer(TokenizerConfigData())
        assert tok.count("") == 0

    def test_char_fallback_ascii(self) -> None:
        """Given: ASCII text.
        When: CharFallbackTokenizer.count is called.
        Then: len(text) // 4 is returned."""
        tok = CharFallbackTokenizer(TokenizerConfigData())
        assert tok.count("hello world") == 11 // 4  # 2

    def test_char_fallback_cjk_high(self) -> None:
        """Given: CJK-heavy text.
        When: CharFallbackTokenizer.count is called.
        Then: len(text) is returned."""
        tok = CharFallbackTokenizer(TokenizerConfigData())
        text = "这是一个测试"
        assert tok.count(text) == len(text)

    def test_char_fallback_cjk_low(self) -> None:
        """Given: low CJK ratio text.
        When: CharFallbackTokenizer.count is called.
        Then: len(text) // 4 is returned."""
        tok = CharFallbackTokenizer(TokenizerConfigData())
        text = "this is a test with one char: 这"
        assert tok.count(text) == len(text) // 4

    def test_tiktoken_with_mock_encoder(self) -> None:
        """Given: mock encoder returning 5 tokens.
        When: TiktokenTokenizer.count is called.
        Then: 5 is returned."""
        tok = TiktokenTokenizer(TokenizerConfigData())
        mock_enc = MagicMock(spec=["encode"])
        mock_enc.encode.return_value = [1, 2, 3, 4, 5]
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken") as mock_tiktoken:
            mock_tiktoken.get_encoding.return_value = mock_enc
            assert tok.count("hello") == 5

    def test_tiktoken_model_name_default(self) -> None:
        """Given: default TokenizerConfigData.
        When: TiktokenTokenizer.model_name is accessed.
        Then: 'cl100k_base' is returned."""
        tok = TiktokenTokenizer(TokenizerConfigData())
        assert tok.model_name == "cl100k_base"

    def test_tiktoken_model_name_from_config(self) -> None:
        """Given: TokenizerConfigData with model_name='o200k_base'.
        When: TiktokenTokenizer.model_name is accessed.
        Then: 'o200k_base' is returned."""
        tok = TiktokenTokenizer(TokenizerConfigData(model_name="o200k_base"))
        assert tok.model_name == "o200k_base"

    def test_char_fallback_model_name(self) -> None:
        """Given: CharFallbackTokenizer.
        When: model_name is accessed.
        Then: 'char_fallback' is returned."""
        tok = CharFallbackTokenizer(TokenizerConfigData())
        assert tok.model_name == "char_fallback"

    def test_itokenizer_is_abstract(self) -> None:
        """Given: ITokenizer port.
        When: instantiated without concrete count() or model_name.
        Then: TypeError is raised."""
        with pytest.raises(TypeError, match="abstract"):
            ITokenizer()  # type: ignore[abstract]


class TestTokenizerAdapterRegistry:
    """Given: adapter registry.
    When: tokenizer adapters are inspected.
    Then: both are registered."""

    def test_tiktoken_registered(self) -> None:
        """Given: registry loaded.
        When: tokenizer port is inspected.
        Then: TiktokenTokenizer is registered under 'tiktoken'."""
        registry = get_registry()
        assert registry["tokenizer"]["tiktoken"] is TiktokenTokenizer

    def test_char_fallback_registered(self) -> None:
        """Given: registry loaded.
        When: tokenizer port is inspected.
        Then: CharFallbackTokenizer is registered under 'char_fallback'."""
        registry = get_registry()
        assert registry["tokenizer"]["char_fallback"] is CharFallbackTokenizer


class TestTiktokenTokenizerInternals:
    """Given: TiktokenTokenizer with various backend states.
    When: count is called.
    Then: all error paths raise AdapterError instead of silent fallback."""

    def test_keyerror_on_unknown_encoding_falls_through_to_hf(self) -> None:
        """Given: tiktoken raises KeyError for unknown encoding.
        When: count is called with no HF tokenizer available.
        Then: AdapterError is raised with model_name in message."""
        tok = TiktokenTokenizer(TokenizerConfigData(model_name="unknown_encoding"))
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken") as mock_tiktoken:
            mock_tiktoken.get_encoding.side_effect = KeyError("unknown_encoding")
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", None):
                with pytest.raises(AdapterError, match="No tokenizer backend available for model_name="):
                    tok.count("hello")
            assert mock_tiktoken.get_encoding.call_count == 1

    def test_tiktoken_both_paths_fail_raises_adapter_error(self) -> None:
        """Given: tiktoken get_encoding raises.
        When: count is called.
        Then: AdapterError is raised."""
        tok = TiktokenTokenizer(TokenizerConfigData())
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken") as mock_tiktoken:
            mock_tiktoken.get_encoding.side_effect = Exception("fail")
            with pytest.raises(AdapterError, match="tiktoken failed"):
                tok.count("hello world")

    def test_hf_tokenizer_success(self, tmp_path: Path) -> None:
        """Given: tiktoken is None but tokenizers is available with local file.
        When: count is called.
        Then: HF tokenizer is used and returns correct count."""
        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf_tok = MagicMock(spec=["encode"])
        mock_tokens = MagicMock(spec=["tokens"])
        mock_tokens.tokens = [1, 2, 3, 4, 5]
        mock_hf_tok.encode.return_value = mock_tokens
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.return_value = mock_hf_tok

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "cl100k_base").mkdir()
                (tmp_path / "cl100k_base" / "tokenizer.json").write_text("{}")
                result = tok.count("hello")
                assert result == 5

    def test_hf_tokenizer_from_file_fails_raises_adapter_error(self, tmp_path: Path) -> None:
        """Given: tokenizers raises during from_file.
        When: count is called.
        Then: AdapterError is raised."""
        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.side_effect = RuntimeError("corrupt")

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "cl100k_base").mkdir()
                (tmp_path / "cl100k_base" / "tokenizer.json").write_text("{}")
                with pytest.raises(AdapterError, match="HF tokenizer failed"):
                    tok.count("hello world")

    def test_count_hf_returns_list(self, tmp_path: Path) -> None:
        """Given: HF tokenizer encode returns list (tiktoken-style).
        When: count is called.
        Then: len(list) is returned without error."""
        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf_tok = MagicMock(spec=["encode"])
        # Simulate tiktoken-style: encode() returns list[int], no .tokens attribute
        mock_hf_tok.encode.return_value = [1, 2, 3, 4, 5, 6]
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.return_value = mock_hf_tok

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "cl100k_base").mkdir()
                (tmp_path / "cl100k_base" / "tokenizer.json").write_text("{}")
                result = tok.count("hello")
                assert result == 6

    def test_count_hf_encode_raises_adapter_error(self, tmp_path: Path) -> None:
        """Given: encoder raises Exception during encode.
        When: count is called.
        Then: AdapterError is raised."""
        tok = TiktokenTokenizer(TokenizerConfigData(local_dir=str(tmp_path)))
        mock_hf_tok = MagicMock(spec=["encode"])
        mock_hf_tok.encode.side_effect = RuntimeError("boom")
        mock_hf = MagicMock()
        mock_hf.Tokenizer.from_file.return_value = mock_hf_tok

        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", mock_hf):
                (tmp_path / "cl100k_base").mkdir()
                (tmp_path / "cl100k_base" / "tokenizer.json").write_text("{}")
                with pytest.raises(AdapterError, match="HF tokenizer failed"):
                    tok.count("这是一个测试")

    def test_count_no_tiktoken_no_tokenizers_raises_adapter_error(self) -> None:
        """Given: neither tiktoken nor tokenizers available.
        When: count is called.
        Then: AdapterError is raised with helpful message."""
        tok = TiktokenTokenizer(TokenizerConfigData())
        with patch("ai_assistant.adapters.tiktoken_tokenizer.tiktoken", None):
            with patch("ai_assistant.adapters.tiktoken_tokenizer.tokenizers", None):
                with pytest.raises(AdapterError, match="No tokenizer backend available"):
                    tok.count("hello world")

# ═══════════════════════════════════════════════════════════════════════════
# HuggingFaceTokenizer tests
# ═══════════════════════════════════════════════════════════════════════════


class TestHuggingFaceTokenizer:
    """Given: HuggingFaceTokenizer adapter.
    When: various scenarios are tested.
    Then: all error paths and success paths are covered."""

    def test_tokenizers_not_installed_raises_adapter_error(self) -> None:
        """Given: tokenizers package not installed.
        When: HuggingFaceTokenizer is instantiated.
        Then: AdapterError is raised."""
        with patch(
            "ai_assistant.adapters.huggingface_tokenizer.Tokenizer", None
        ):
            with pytest.raises(
                AdapterError,
                match="tokenizers package is not installed",
            ):
                HuggingFaceTokenizer(TokenizerConfigData(model_name="dummy"))

    def test_empty_model_name_raises_adapter_error(self) -> None:
        """Given: config with empty model_name.
        When: HuggingFaceTokenizer is instantiated.
        Then: AdapterError is raised."""
        mock_tok = MagicMock()
        with patch(
            "ai_assistant.adapters.huggingface_tokenizer.Tokenizer", mock_tok
        ):
            with pytest.raises(
                AdapterError,
                match="requires model_name",
            ):
                HuggingFaceTokenizer(TokenizerConfigData(model_name=""))

    def test_file_not_found_raises_adapter_error(self) -> None:
        """Given: path to non-existent file.
        When: HuggingFaceTokenizer is instantiated.
        Then: AdapterError is raised."""
        mock_tok = MagicMock()
        with patch(
            "ai_assistant.adapters.huggingface_tokenizer.Tokenizer", mock_tok
        ):
            with pytest.raises(
                AdapterError,
                match="Tokenizer file not found",
            ):
                HuggingFaceTokenizer(
                    TokenizerConfigData(model_name="/nonexistent/tokenizer.json")
                )

    def test_load_failure_raises_adapter_error(self, tmp_path: Path) -> None:
        """Given: valid file path but Tokenizer.from_file raises.
        When: HuggingFaceTokenizer is instantiated.
        Then: AdapterError is raised."""
        tokenizer_file = tmp_path / "tokenizer.json"
        tokenizer_file.write_text("invalid")

        mock_tok = MagicMock()
        mock_tok.from_file.side_effect = RuntimeError("corrupt")

        with patch(
            "ai_assistant.adapters.huggingface_tokenizer.Tokenizer", mock_tok
        ):
            with pytest.raises(
                AdapterError,
                match="Failed to load tokenizer",
            ):
                HuggingFaceTokenizer(
                    TokenizerConfigData(model_name=str(tokenizer_file))
                )

    def test_successful_load_and_count(self, tmp_path: Path) -> None:
        """Given: valid tokenizer.json.
        When: count is called.
        Then: correct token count is returned."""
        tokenizer_file = tmp_path / "tokenizer.json"
        tokenizer_file.write_text("{}")

        mock_encoding = MagicMock()
        mock_encoding.tokens = [1, 2, 3, 4, 5]

        mock_instance = MagicMock()
        mock_instance.encode.return_value = mock_encoding

        mock_tok = MagicMock()
        mock_tok.from_file.return_value = mock_instance

        with patch(
            "ai_assistant.adapters.huggingface_tokenizer.Tokenizer", mock_tok
        ):
            tok = HuggingFaceTokenizer(
                TokenizerConfigData(model_name=str(tokenizer_file))
            )
            assert tok.count("hello") == 5

    def test_count_failure_raises_adapter_error(self, tmp_path: Path) -> None:
        """Given: loaded tokenizer.
        When: encode raises.
        Then: AdapterError is raised."""
        tokenizer_file = tmp_path / "tokenizer.json"
        tokenizer_file.write_text("{}")

        mock_instance = MagicMock()
        mock_instance.encode.side_effect = RuntimeError("fail")

        mock_tok = MagicMock()
        mock_tok.from_file.return_value = mock_instance

        with patch(
            "ai_assistant.adapters.huggingface_tokenizer.Tokenizer", mock_tok
        ):
            tok = HuggingFaceTokenizer(
                TokenizerConfigData(model_name=str(tokenizer_file))
            )
            with pytest.raises(
                AdapterError,
                match="Tokenization failed",
            ):
                tok.count("hello")

    def test_model_name_property(self, tmp_path: Path) -> None:
        """Given: loaded tokenizer with path.
        When: model_name is accessed.
        Then: path is returned."""
        tokenizer_file = tmp_path / "tokenizer.json"
        tokenizer_file.write_text("{}")

        mock_instance = MagicMock()
        mock_instance.encode.return_value = MagicMock(tokens=[])

        mock_tok = MagicMock()
        mock_tok.from_file.return_value = mock_instance

        with patch(
            "ai_assistant.adapters.huggingface_tokenizer.Tokenizer", mock_tok
        ):
            tok = HuggingFaceTokenizer(
                TokenizerConfigData(model_name=str(tokenizer_file))
            )
            assert tok.model_name == str(tokenizer_file)

    def test_shutdown_does_nothing(self, tmp_path: Path) -> None:
        """Given: loaded tokenizer.
        When: shutdown is called.
        Then: no error occurs."""
        tokenizer_file = tmp_path / "tokenizer.json"
        tokenizer_file.write_text("{}")

        mock_instance = MagicMock()
        mock_instance.encode.return_value = MagicMock(tokens=[])

        mock_tok = MagicMock()
        mock_tok.from_file.return_value = mock_instance

        with patch(
            "ai_assistant.adapters.huggingface_tokenizer.Tokenizer", mock_tok
        ):
            tok = HuggingFaceTokenizer(
                TokenizerConfigData(model_name=str(tokenizer_file))
            )
            import asyncio
            asyncio.run(tok.shutdown())
