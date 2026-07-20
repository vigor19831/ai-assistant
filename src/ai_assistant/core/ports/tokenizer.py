"""Tokenizer port interface."""

from __future__ import annotations

from abc import abstractmethod

from ai_assistant.core.ports.closable import IClosable

__all__ = ["ITokenizer"]


class ITokenizer(IClosable):
    """Abstract tokenizer for counting tokens in text.

    Implementations may use BPE tokenizers (tiktoken, HuggingFace)
    or character-based heuristics. The contract is: count(text)
    returns a non-negative integer representing the token count.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the tokenizer model/encoding identifier."""
        ...

    @abstractmethod
    def count(self, text: str) -> int:
        """Count tokens in text.

        Args:
            text: Input text to tokenize.

        Returns:
            Token count (>= 0).
        """
