#!/usr/bin/env python3
"""Download offline tokenizer files from HuggingFace."""

from __future__ import annotations

import os
import ssl
import sys
from pathlib import Path
from urllib.request import Request, urlopen

# ── Project root discovery ──
_SCRIPT_DIR = Path(__file__).parent.resolve()


def _find_project_root(start: Path) -> Path:
    """Walk up to find project root (contains pyproject.toml or src/ai_assistant)."""
    current = start
    for _ in range(5):
        if (current / "pyproject.toml").exists() or (current / "src" / "ai_assistant").exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return start


PROJECT_ROOT = _find_project_root(_SCRIPT_DIR.parent)
BASE_URL = "https://huggingface.co/{}/resolve/main/tokenizer.json"
DEFAULT_DIR = PROJECT_ROOT / "data" / "tokenizers"

# Preset models (name_in_config -> HF repo)
PRESETS: dict[str, str | None] = {
    "gpt-4o": None,
    "gpt-4": None,
    "gpt-4-turbo": None,
    "gpt-3.5-turbo": None,
    "gpt-4o-mini": None,
    "qwen": "Qwen/Qwen2.5-7B-Instruct",
    "qwen2.5": "Qwen/Qwen2.5-7B-Instruct",
    "qwen2.5-7b-instruct": "Qwen/Qwen2.5-7B-Instruct",
    "qwen2.5-14b-instruct": "Qwen/Qwen2.5-14B-Instruct",
    "qwen3": "Qwen/Qwen3-8B",
    "qwen3.5": "Qwen/Qwen3.5-4B",
    "llama": "meta-llama/Llama-3.2-3B-Instruct",
    "llama-3.2": "meta-llama/Llama-3.2-3B-Instruct",
    "llama-3.2-3b-instruct": "meta-llama/Llama-3.2-3B-Instruct",
    "llama-3.1": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "llama-3.1-8b-instruct": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "llama-3": "meta-llama/Meta-Llama-3-8B-Instruct",
    "gemma": "google/gemma-3-4b-it",
    "gemma-3": "google/gemma-3-4b-it",
    "gemma-3-4b-it": "google/gemma-3-4b-it",
    "gemma-3-27b-it": "google/gemma-3-27b-it",
    "gemma-2": "google/gemma-2-9b-it",
    "gemma-4": "google/gemma-3-4b-it",
    "phi": "microsoft/Phi-4-mini-instruct",
    "phi-4": "microsoft/Phi-4-mini-instruct",
    "phi-4-mini-instruct": "microsoft/Phi-4-mini-instruct",
    "phi-4-mini-reasoning": "microsoft/Phi-4-mini-instruct",
    "phi-3": "microsoft/Phi-3-mini-4k-instruct",
    "mistral": "mistralai/Mistral-7B-Instruct-v0.3",
    "mistral-7b-instruct": "mistralai/Mistral-7B-Instruct-v0.3",
    "mistral-small": "mistralai/Mistral-Small-24B-Instruct-2501",
    "deepseek": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "deepseek-r1": "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
    "deepseek-v3": "deepseek-ai/DeepSeek-V3",
    "yi": "01-ai/Yi-1.5-9B-Chat",
    "yi-1.5": "01-ai/Yi-1.5-9B-Chat",
    "falcon": "tiiuae/Falcon3-7B-Instruct",
    "falcon-3": "tiiuae/Falcon3-7B-Instruct",
    "stablelm": "stabilityai/stablelm-3b-4e1t",
    "command-r": "CohereForAI/c4ai-command-r7b-12-2024",
    "cohere": "CohereForAI/c4ai-command-r7b-12-2024",
    "granite": "ibm-granite/granite-3.1-8b-instruct",
    "granite-3": "ibm-granite/granite-3.1-8b-instruct",
    "smollm": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    "smollm2": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
    "olmo": "allenai/OLMo-2-1124-7B-Instruct",
    "olmo-2": "allenai/OLMo-2-1124-7B-Instruct",
    "nemotron": "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
    "nemotron-70b": "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
    "exaone": "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct",
    "internlm": "internlm/internlm3-8b-instruct",
    "internlm3": "internlm/internlm3-8b-instruct",
}

VENDOR_MAP: dict[str, str] = {
    "gemma": "google",
    "phi": "microsoft",
    "qwen": "Qwen",
    "llama": "meta-llama",
    "mistral": "mistralai",
    "deepseek": "deepseek-ai",
    "yi": "01-ai",
    "falcon": "tiiuae",
    "stablelm": "stabilityai",
    "command": "CohereForAI",
    "cohere": "CohereForAI",
    "granite": "ibm-granite",
    "smollm": "HuggingFaceTB",
    "olmo": "allenai",
    "nemotron": "nvidia",
    "exaone": "LGAI-EXAONE",
    "internlm": "internlm",
    "mixtral": "mistralai",
    "codestral": "mistralai",
    "ministral": "mistralai",
}

MIRRORS: dict[str, str] = {
    "meta-llama/": "unsloth/",
    "google/": "unsloth/",
    "microsoft/": "unsloth/",
    "mistralai/": "unsloth/",
    "deepseek-ai/": "unsloth/",
    "nvidia/": "unsloth/",
}


def _try_mirror(repo: str) -> str | None:
    for prefix, mirror in MIRRORS.items():
        if repo.startswith(prefix):
            return mirror + repo[len(prefix):]
    return None


def _guess_vendor(name: str) -> str | None:
    clean = name.lower().replace("_", "-")
    for prefix, vendor in VENDOR_MAP.items():
        if clean.startswith(prefix):
            return f"{vendor}/{name}"
    return None


def _remove_quant_suffix(name: str) -> str:
    suffixes = [
        "-q4-k-m", "-q4-0", "-q8-0", "-iq4-xs", "-iq4-xxs",
        "-q6-k", "-q5-k-m", "-f16", "-bf16", "-q4-k",
        "-q4-k-s", "-q5-0", "-q5-1", "-q3-k-m", "-q3-k-s",
        "-q2-k", "-iq3-xs", "-iq3-xxs", "-q4-1", "-q5-k-s",
    ]
    for suffix in suffixes:
        if name.lower().endswith(suffix):
            return name[: -len(suffix)]
    return name


def _resolve_preset(model_name: str) -> str | None:
    name = model_name.lower().strip()
    if name in PRESETS:
        return PRESETS[name]
    for key in sorted(PRESETS.keys(), key=len, reverse=True):
        if name.startswith(key):
            return PRESETS[key]
    for key in sorted(PRESETS.keys(), key=len, reverse=True):
        if key in name:
            return PRESETS[key]
    if "_" in name:
        parts = name.split("_", 1)
        vendor = parts[0]
        model_part = parts[1].replace("_", "-")
        clean = _remove_quant_suffix(model_part)
        return f"{vendor}/{clean}"
    vendor_repo = _guess_vendor(name)
    if vendor_repo:
        return vendor_repo
    if "/" in name:
        return name
    return f"unsloth/{name}"


def download(repo: str, dest: Path, token: str | None) -> bool:
    if repo is None:
        return True
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / "tokenizer.json"
    if out.exists():
        print(f"  already exists ({out})")
        return True

    url = BASE_URL.format(repo)
    print(f"  downloading {url} ...")
    try:
        req = Request(url, headers={"User-Agent": "ai-assistant/1.0"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        ctx = ssl.create_default_context()
        with urlopen(req, timeout=30, context=ctx) as resp:
            if resp.status != 200:
                print(f"  HTTP {resp.status}")
                return False
            with open(out, "wb") as f_out:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f_out.write(chunk)
        size = out.stat().st_size
        print(f"  saved {size} bytes")
        return True
    except Exception as e:
        print(f"  FAILED — {e}")
        return False


def _read_models_from_config() -> list[str]:
    try:
        import yaml
    except ImportError:
        print("[WARNING] PyYAML not installed. Install: pip install pyyaml")
        return []

    try:
        path = PROJECT_ROOT / "config.yaml"
        if not path.exists():
            return []
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        llm = data.get("llm", {})
        models = [llm.get("model")]
        available = llm.get("available_models", [])
        models.extend(available)
        seen: set[str] = set()
        result: list[str] = []
        for m in models:
            if m and m not in seen:
                seen.add(m)
                result.append(m)
        return result
    except Exception:
        return []


def main() -> int:
    models = _read_models_from_config()
    if not models:
        print("No models found in config.yaml")
        return 1

    print(f"Models from config.yaml: {', '.join(models)}")
    print(f"\nTarget directory: {DEFAULT_DIR.resolve()}")

    token = os.getenv("HF_TOKEN")
    ok = 0
    skipped = 0
    failed = 0

    for model in models:
        repo = _resolve_preset(model)
        if repo is None:
            print(f"\n[{model}] -> tiktoken (OpenAI), skip")
            continue

        name = model.split("/")[-1].replace("_", "-")[:30]
        dest = DEFAULT_DIR / name
        out = dest / "tokenizer.json"

        if out.exists():
            print(f"\n[{name}] -> already exists, skip")
            skipped += 1
            continue

        print(f"\n[{name}] -> {repo}")
        if download(repo, dest, token):
            ok += 1
            continue
        mirror = _try_mirror(repo)
        if mirror:
            print(f"  trying mirror {mirror} ...")
            if download(mirror, dest, token):
                ok += 1
                continue
        print(f"  [{name}] FAILED")
        failed += 1

    print(f"\nDone: {ok} downloaded, {skipped} skipped, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
