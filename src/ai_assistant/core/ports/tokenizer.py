"""Tokenizer port interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

__all__ = ["ITokenizer"]


class ITokenizer(ABC):
    """Abstract tokenizer for counting tokens in text.

    Implementations may use BPE tokenizers (tiktoken, HuggingFace)
    or character-based heuristics. The contract is: count(text)
    returns a non-negative integer representing the token count.
    """

    @abstractmethod
    def count(self, text: str) -> int:
        """Count tokens in text.

        Args:
            text: Input text to tokenize.

        Returns:
            Token count (>= 0).
        """
