"""Piper TTS synthesizer — friendly fallback and real implementation."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
from typing import Any

import httpx

from core.logger import get_logger
from core.ports.voice import IVoiceSynthesizer
from core.registry import register

__all__ = ["PiperRealSynthesizer", "PiperSynthesizer"]

_logger = get_logger("voice.piper")


@register("voice_synthesizer", "piper")
class PiperSynthesizer(IVoiceSynthesizer):
    """Stub with graceful fallback."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        _logger.warning("TTS synthesize called but Piper is not configured")
        return b""


@register("voice_synthesizer", "piper_real")
class PiperRealSynthesizer(IVoiceSynthesizer):
    """Real TTS using Piper HTTP server or local executable."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.api_base: str | None = getattr(config, "api_base", None)
        self.local_bin: str | None = getattr(config, "local_bin", None)
        self.model_path: str | None = getattr(config, "model_path", None)
        self._timeout: float = getattr(config, "timeout", 30.0)
        self._available: bool | None = None

    async def _check_available(self) -> bool:
        if self._available is not None:
            return self._available
        if self.api_base:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"{self.api_base}/health")
                    self._available = resp.status_code < 500
                    return self._available
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as exc:
                _logger.debug("Piper HTTP health check failed: %s", exc)
        if self.local_bin:
            self._available = shutil.which(self.local_bin) is not None
            return self._available
        self._available = False
        return self._available

    async def synthesize(self, text: str, voice: str | None = None) -> bytes:
        if not await self._check_available():
            return b""

        if self.api_base:
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.post(
                        f"{self.api_base}/synthesize",
                        json={"text": text, "voice": voice},
                    )
                    resp.raise_for_status()
                    return resp.content
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception as exc:
                _logger.warning("Piper HTTP synthesis failed: %s", exc)

        if self.local_bin and self.model_path:
            try:
                proc = await asyncio.create_subprocess_exec(
                    self.local_bin,
                    "--model",
                    self.model_path,
                    "--output_file",
                    "-",
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=text.encode()),
                    timeout=self._timeout,
                )
                if proc.returncode != 0:
                    _logger.warning(
                        "Piper subprocess failed (rc=%d): %s",
                        proc.returncode,
                        stderr.decode().strip(),
                    )
                    return b""
                return stdout
            except (SystemExit, KeyboardInterrupt):
                raise
            except TimeoutError:
                _logger.warning(
                    "Piper subprocess timed out after %.1fs",
                    self._timeout,
                )
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            except Exception as exc:
                _logger.warning("Piper subprocess failed: %s", exc)

        return b""
