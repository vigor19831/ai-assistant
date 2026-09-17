from __future__ import annotations

import os

from ai_assistant.adapters._registry import register
from ai_assistant.adapters.char_fallback_tokenizer import CharFallbackTokenizer
from ai_assistant.core.domain.configs import TokenizerConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.tokenizer import ITokenizer

logger = get_logger(__name__)

try:
    from tokenizers import Tokenizer
except ImportError:  # pragma: no cover
    Tokenizer = None  # type: ignore[misc, assignment]


@register("tokenizer", "huggingface")
class HuggingFaceTokenizer(ITokenizer):
    """Tokenizer backed by a HuggingFace tokenizers.json file.

    Set ``model_name`` in config to the absolute or relative path of the
    downloaded ``tokenizer.json`` (e.g. ``./data/tokenizers/qwen3.5-4b/
    tokenizer.json``). If the file is missing, the adapter degrades to
    CharFallbackTokenizer with a warning (approximate counts) instead of
    failing startup — model switches in config must not brick the app.
    """

    def __init__(self, config: TokenizerConfigData) -> None:
        if Tokenizer is None:
            raise AdapterError(
                "tokenizers package is not installed but "
                "tokenizer.provider='huggingface'"
            )

        self._model_name = config.model_name or "huggingface"

        # None = exact tokenizer active; instance = char fallback.
        self._fallback: CharFallbackTokenizer | None = None

        path = config.model_name
        if not path:
            raise AdapterError(
                "HuggingFaceTokenizer requires model_name (path to tokenizer.json)"
            )

        resolved = os.path.expanduser(path)
        if not os.path.isfile(resolved):
            logger.warning(
                f"Tokenizer file not found: {resolved} — falling back to "
                "the char tokenizer (approximate counts, conservative "
                "budgeting). Run scripts/download_tokenizers.py, then "
                "restart the servers for exact counts."
            )
            self._fallback = CharFallbackTokenizer(config)
            return

        try:
            self._tokenizer = Tokenizer.from_file(resolved)
        except Exception as exc:
            logger.exception(f"Failed to load tokenizer from {resolved}")
            raise AdapterError(
                f"Failed to load tokenizer from {resolved}: {exc}"
            ) from exc

    @property
    def model_name(self) -> str:
        if self._fallback is not None:
            return self._fallback.model_name
        return self._model_name

    def count(self, text: str) -> int:
        if self._fallback is not None:
            return self._fallback.count(text)
        try:
            encoding = self._tokenizer.encode(text)
            return len(encoding.tokens)
        except Exception as exc:
            logger.exception("HuggingFace tokenization failed")
            raise AdapterError(f"Tokenization failed: {exc}") from exc

    async def shutdown(self) -> None:
        pass
