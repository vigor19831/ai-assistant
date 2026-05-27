#!/usr/bin/env python3
"""Index documents from folders into RAG namespaces (direct adapter call)."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# ── Windows: force UTF-8 output ─────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io

        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
PROJECT_ROOT = Path(__file__).parent.parent.parent.resolve()

import os

# Set config path before importing project modules
os.environ.setdefault("AI_CONFIG_PATH", str(PROJECT_ROOT / "config.yaml"))

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

    config = load_config(os.getenv("AI_CONFIG_PATH", "config.yaml"))
    state = await init_adapters(config)

    result = await index_folder(
        folder=args.folder,
        clear=args.clear,
        chunker=state.chunker,
        embedder=state.embedder,
        vector_store=state.vector_store,
    )

    for ns, data in result.get("results", {}).items():
        print(f"  [{ns}] {data['indexed']} docs, {data['chunks']} chunks")

    if result.get("errors"):
        for err in result["errors"]:
            print(f"  Error: {err}")

    print("\n[OK] Indexing complete!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
