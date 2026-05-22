"""Local Whisper voice recognizer — friendly fallback."""

from __future__ import annotations

from typing import Any

from core.logger import get_logger
from core.ports.voice import IVoiceRecognizer
from core.registry import register

__all__ = ["WhisperLocalRecognizer"]

_logger = get_logger("voice.whisper_local")


@register("voice_recognizer", "whisper_local")
class WhisperLocalRecognizer(IVoiceRecognizer):
    """Stub with graceful fallback message."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
        _logger.warning("Voice transcribe called but Whisper is not configured")
        return (
            "🔧 Voice transcription is not yet configured. "
            "To enable speech-to-text, install faster-whisper and set "
            "voice.enabled=true in config.yaml."
        )
