#!/usr/bin/env python3
"""Index documents from folders into RAG namespaces.

Usage:
    python scripts/index_documents.py                    # Index all folders
    python scripts/index_documents.py --folder personal  # Index only personal
    python scripts/index_documents.py --clear            # Clear and reindex
"""

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
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

API_BASE = "http://localhost:8000"
DOCUMENTS_ROOT = Path(__file__).parent.parent / "documents"
SUPPORTED_EXTENSIONS = {".txt", ".md", ".py", ".json", ".yaml", ".yml", ".csv", ".log"}
CHUNK_SIZE = 100000  # Max chars per document chunk


def read_file(path: Path) -> str:
    """Read text file with encoding fallback."""
    encodings = ["utf-8", "utf-8-sig", "cp1251", "cp1252", "latin-1"]
    for enc in encodings:
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return ""


def discover_documents(folder: str | None = None) -> dict[str, list[dict]]:
    """Discover documents in folders. Returns {namespace: [docs]}."""
    result: dict[str, list[dict]] = {}

    if folder:
        folders = [DOCUMENTS_ROOT / folder]
    else:
        folders = [d for d in DOCUMENTS_ROOT.iterdir() if d.is_dir()]

    for folder_path in folders:
        namespace = folder_path.name
        docs = []

        for file_path in folder_path.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            content = read_file(file_path)
            if not content.strip():
                continue

            # Split large files into chunks
            if len(content) > CHUNK_SIZE:
                for i, start in enumerate(range(0, len(content), CHUNK_SIZE)):
                    chunk = content[start : start + CHUNK_SIZE]
                    docs.append(
                        {
                            "id": f"{file_path.stem}_chunk{i}",
                            "content": chunk,
                            "metadata": {
                                "source": str(file_path.relative_to(DOCUMENTS_ROOT)),
                                "folder": namespace,
                                "chunk": i,
                            },
                        }
                    )
            else:
                docs.append(
                    {
                        "id": file_path.stem,
                        "content": content,
                        "metadata": {
                            "source": str(file_path.relative_to(DOCUMENTS_ROOT)),
                            "folder": namespace,
                        },
                    }
                )

        if docs:
            result[namespace] = docs

    return result


async def index_namespace(
    namespace: str, docs: list[dict], clear: bool = False, api_base: str = None
) -> dict:
    """Index documents into a namespace."""
    base = api_base or API_BASE
    async with httpx.AsyncClient() as client:
        # Clear existing if requested
        if clear:
            try:
                await client.post(
                    f"{base}/rag/delete",
                    json={"document_ids": [], "chunk_ids": [], "namespace": namespace},
                    timeout=30.0,
                )
                print(f"  Cleared namespace: {namespace}")
            except Exception as e:
                print(f"  Warning: could not clear {namespace}: {e}")

        # Index in batches of 10
        total_indexed = 0
        total_chunks = 0

        for i in range(0, len(docs), 10):
            batch = docs[i : i + 10]
            try:
                resp = await client.post(
                    f"{base}/rag/index",
                    json={"documents": batch, "namespace": namespace},
                    timeout=60.0,
                )
                resp.raise_for_status()
                data = resp.json()
                total_indexed += data.get("indexed_count", 0)
                total_chunks += data.get("chunk_count", 0)

                if data.get("errors"):
                    for err in data["errors"]:
                        print(f"  Error: {err}")

            except Exception as e:
                print(f"  Failed to index batch {i}: {e}")

        return {
            "namespace": namespace,
            "indexed": total_indexed,
            "chunks": total_chunks,
        }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Index documents into RAG")
    parser.add_argument("--folder", "-f", help="Index only specific folder")
    parser.add_argument(
        "--clear", "-c", action="store_true", help="Clear before indexing"
    )
    parser.add_argument("--api", "-a", default=API_BASE, help="API base URL")
    args = parser.parse_args()

    api_base = args.api

    # Check API is running
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{api_base}/health")
            resp.raise_for_status()
    except Exception:
        print(f"ERROR: API not available at {api_base}")
        print("Start the server first: python scripts/start.py")
        return 1

    # Discover documents
    docs_by_ns = discover_documents(args.folder)

    if not docs_by_ns:
        print(f"No documents found in {DOCUMENTS_ROOT}")
        print("Create folders: documents/personal, documents/work, documents/other")
        return 1

    print("Found documents:")
    for ns, docs in docs_by_ns.items():
        print(f"  [{ns}]: {len(docs)} items")

    # Index each namespace
    print("\nIndexing...")
    for namespace, docs in docs_by_ns.items():
        print(f"\n[{namespace}] {len(docs)} documents...")
        result = await index_namespace(namespace, docs, args.clear, api_base)
        print(f"  Done: {result['indexed']} docs, {result['chunks']} chunks")

    print("\n[OK] Indexing complete!")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
