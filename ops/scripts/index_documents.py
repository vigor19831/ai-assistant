#!/usr/bin/env python3
"""Index documents from folders into RAG namespaces (direct adapter call)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# ── Windows: force UTF-8 output ─────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Add src/ to path for imports
_PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from ai_assistant.api.deps import init_adapters
from ai_assistant.core.config import load_config
from ai_assistant.features.rag.indexing import index_folder


async def main() -> int:
    parser = argparse.ArgumentParser(description="Index documents into RAG")
    parser.add_argument("--folder", "-f", help="Index only specific folder")
    parser.add_argument(
        "--clear", "-c", action="store_true", help="Clear before indexing"
    )
    args = parser.parse_args()

    cfg_path = _PROJECT_ROOT / "config.yaml"
    if not cfg_path.exists():
        print(f"[ERROR] Config not found: {cfg_path}")
        return 1

    config = load_config(str(cfg_path))

    try:
        state = await init_adapters(config)
    except Exception as exc:
        print(f"[ERROR] Failed to initialize adapters: {exc}")
        return 1

    try:
        result = await index_folder(
            folder=args.folder,
            clear=args.clear,
            chunker=state.chunker,
            embedder=state.embedder,
            vector_store=state.vector_store,
        )
    except Exception as exc:
        print(f"[ERROR] Indexing failed: {exc}")
        return 1
    finally:
        # Graceful cleanup of adapters
        if hasattr(state, "cleanup") and asyncio.iscoroutinefunction(state.cleanup):
            try:
                await state.cleanup()
            except Exception:
                pass

    result = result or {}
    for ns, data in result.get("results", {}).items():
        indexed = data.get("indexed", 0) if isinstance(data, dict) else 0
        chunks = data.get("chunks", 0) if isinstance(data, dict) else 0
        print(f"  [{ns}] {indexed} docs, {chunks} chunks")

    errors = result.get("errors", [])
    if errors:
        for err in errors:
            print(f"  Error: {err}")

    print("\n[OK] Indexing complete!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
