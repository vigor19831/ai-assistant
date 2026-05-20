"""Local voice recognizer via whisper.cpp HTTP server."""

from __future__ import annotations

from typing import Any

import httpx

from core.ports.voice import IVoiceRecognizer
from core.registry import register


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
        except Exception:
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
                text = result.get("text", "")
                return text.strip()
        except Exception:
            return ""
