"""Voice ports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IVoiceRecognizer(ABC):
    """Speech-to-text."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def transcribe(
        self, audio_bytes: bytes, mime_type: str = "audio/wav"
    ) -> str: ...


class IVoiceSynthesizer(ABC):
    """Text-to-speech."""

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> bytes: ...
