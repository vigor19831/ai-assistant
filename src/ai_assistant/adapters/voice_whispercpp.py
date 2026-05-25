"""Local voice recognizer via whisper.cpp HTTP server."""

from __future__ import annotations

from typing import Any

import httpx

from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.voice import IVoiceRecognizer
from ai_assistant.core.registry import register

__all__ = ["WhisperCppRecognizer"]

_logger = get_logger("voice.whispercpp")


@register("voice_recognizer", "whispercpp")
class WhisperCppRecognizer(IVoiceRecognizer):
    """Speech-to-text using whisper.cpp HTTP API."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.api_base: str = getattr(config, "api_base", "http://127.0.0.1:8082")
        self._timeout: float = getattr(config, "timeout", 60.0)
        self._available: bool | None = None

    async def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.api_base}/health")
                self._available = resp.status_code < 500
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as exc:
            _logger.debug("whisper.cpp health check failed: %s", exc)
            self._available = False
        return self._available

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
        if not await self._check_available():
            return ""

        files = {"file": ("audio.wav", audio_bytes, mime_type)}
        data = {"language": getattr(self.config, "language", "auto")}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self.api_base}/inference",
                    files=files,
                    data=data,
                )
                resp.raise_for_status()
                result = resp.json()
                return result.get("text", "").strip()
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as exc:
            _logger.warning("whisper.cpp transcription failed: %s", exc)
            return ""
