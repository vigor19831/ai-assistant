#!/usr/bin/env python3
"""Convert offline GGUF models to Ollama blobs — portable, Windows/Linux."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import yaml


def get_project_root() -> Path:
    """Resolve project root from script location: scripts/ -> parent."""
    return Path(__file__).parent.parent.resolve()


def get_config() -> dict:
    """Load config.yaml from project root."""
    project_root = get_project_root()
    config_path = project_root / "config.yaml"
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def get_ollama_exe(project_root: Path) -> Path | None:
    """Find Ollama binary in vendor/ or PATH."""
    candidates = [
        project_root / "vendor" / "ollama.exe",
        project_root / "vendor" / "ollama",
        project_root / "vendor" / f"ollama-{platform.system().lower()}-{platform.machine().lower()}",
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()

    for path_dir in os.getenv("PATH", "").split(os.pathsep):
        for name in ("ollama.exe", "ollama"):
            p = Path(path_dir) / name
            if p.exists():
                return p.resolve()
    return None


def is_ollama_running(ollama_exe: Path) -> bool:
    """Check if ollama serve is responding."""
    try:
        result = subprocess.run(
            [str(ollama_exe), "list"],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def start_ollama(ollama_exe: Path, project_root: Path) -> bool:
    """Launch ollama serve as background process."""
    env = os.environ.copy()
    ollama_home = project_root / "vendor" / "ollama"
    ollama_home.mkdir(parents=True, exist_ok=True)
    env["OLLAMA_MODELS"] = str(ollama_home / "models")
    env["OLLAMA_HOST"] = "127.0.0.1:11434"

    kwargs: dict[str, Any] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
        "env": env,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    try:
        subprocess.Popen([str(ollama_exe), "serve"], **kwargs)
        for _ in range(30):
            time.sleep(0.5)
            if is_ollama_running(ollama_exe):
                print("[convert] Ollama server ready")
                return True
        print("[convert] WARNING: Ollama did not respond in 15s")
        return False
    except Exception as e:
        print(f"[convert] Failed to start Ollama: {e}")
        return False


def normalize_name(stem: str) -> str:
    """Convert filename to Ollama model name: lowercase, _ and spaces -> -."""
    return stem.lower().replace("_", "-").replace(" ", "-")


def convert_all(project_root: Path, ollama_exe: Path, config: dict) -> int:
    """Scan models_dir/*.gguf and register each in Ollama."""
    ollama_cfg = config.get("ollama", {})
    models_dir = project_root / ollama_cfg.get("models_dir", "vendor/ollama/models")
    if not models_dir.exists():
        print(f"[convert] Models directory not found: {models_dir}")
        return 1

    gguf_files = sorted(models_dir.glob("*.gguf"))
    if not gguf_files:
        print(f"[convert] No .gguf files found in {models_dir}")
        return 0

    existing: set[str] = set()
    try:
        result = subprocess.run(
            [str(ollama_exe), "list"],
            capture_output=True, text=True, timeout=15
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and not line.startswith("NAME"):
                existing.add(parts[0].split(":")[0].strip())
    except Exception as e:
        print(f"[convert] Could not query existing models: {e}")

    converted = 0
    skipped = 0

    for gguf in gguf_files:
        name = normalize_name(gguf.stem)

        if name in existing:
            print(f"[convert] Skip (already exists): {name}")
            skipped += 1
            continue

        modelfile = models_dir / f"{gguf.stem}.modelfile"
        if not modelfile.exists():
            modelfile.write_text(f'FROM ./{gguf.name}\n', encoding="utf-8")

        print(f"[convert] Registering: {name} <- {gguf.name}")
        try:
            result = subprocess.run(
                [str(ollama_exe), "create", name, "-f", str(modelfile)],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                print(f"[convert] OK: {name}")
                converted += 1
            else:
                err = result.stderr.strip() or "unknown error"
                print(f"[convert] FAILED: {name} — {err}")
        except subprocess.TimeoutExpired:
            print(f"[convert] TIMEOUT: {name}")
        except Exception as e:
            print(f"[convert] ERROR: {name} — {e}")

    print(f"\n[convert] Done: {converted} converted, {skipped} skipped, {len(gguf_files)} total")
    return 0


def main() -> int:
    project_root = get_project_root()
    config = get_config()

    ollama_exe = get_ollama_exe(project_root)
    if ollama_exe is None:
        print("[convert] ERROR: ollama.exe not found")
        print("[convert] Expected: vendor/ollama.exe or vendor/ollama")
        return 1

    print(f"[convert] Using Ollama: {ollama_exe}")

    if not is_ollama_running(ollama_exe):
        print("[convert] Ollama not running, starting...")
        if not start_ollama(ollama_exe, project_root):
            return 1

    return convert_all(project_root, ollama_exe, config)


if __name__ == "__main__":
    sys.exit(main())
