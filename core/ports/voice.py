"""Voice ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

__all__ = ["IVoiceRecognizer", "IVoiceSynthesizer"]


class IVoiceRecognizer(ABC):
    """Speech-to-text."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        mime_type: str = "audio/wav",
    ) -> str:
        """Transcribe audio to text.

        Args:
            audio_bytes: Raw audio data.
            mime_type: Audio format identifier.

        Returns:
            Transcribed text.
        """
        ...


class IVoiceSynthesizer(ABC):
    """Text-to-speech."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """Synthesize text to audio.

        Args:
            text: Text to synthesize.
            voice: Optional voice identifier.

        Returns:
            Raw audio bytes.
        """
        ...
