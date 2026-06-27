"""Tokenizer port interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["ITokenizer"]


class ITokenizer(ABC):
    """Abstract tokenizer for counting tokens in text.

    Implementations may use BPE tokenizers (tiktoken, HuggingFace)
    or character-based heuristics. The contract is: count(text, model)
    returns a non-negative integer representing the token count.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier this tokenizer was initialized for."""
        ...

    @abstractmethod
    def count(self, text: str, model: str) -> int:
        """Count tokens in text for the given model.

        Args:
            text: Input text to tokenize.
            model: Model identifier used for tokenizer selection.

        Returns:
            Token count (>= 0).
        """
