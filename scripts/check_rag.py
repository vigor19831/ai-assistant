#!/usr/bin/env python3
"""Standalone RAG diagnostic — no project code changes needed."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

# ── Ensure project root is importable (BEFORE any project imports) ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Eager-load adapters to trigger @register side-effects
import adapters.chunker_simple        # noqa: F401
import adapters.embedder_mock         # noqa: F401
import adapters.embedder_openai_compatible  # noqa: F401
import adapters.llm_mock            # noqa: F401
import adapters.llm_openai_compatible     # noqa: F401
import adapters.memory_sqlite       # noqa: F401
import adapters.reranker_api        # noqa: F401
import adapters.reranker_dummy      # noqa: F401
import adapters.storage_sqlite      # noqa: F401
import adapters.tools_calculator    # noqa: F401
import adapters.vector_store_faiss  # noqa: F401
import adapters.vector_store_memory # noqa: F401

# ── Imports from project ──
from core.config import load_config
from core.domain.documents import Chunk
from core.domain.messages import UserMessage
from core.domain.pipeline import PipelineData
from core.logger import get_logger
from core.registry import create as registry_create
from pipeline.steps import build_context, embed_query, retrieve

logger = get_logger("check_rag")

_NS_MAP = {"p": "personal", "w": "work", "o": "other"}
_PREFIX_RE = re.compile(r"^\[(p|w|o)\]\s*(.*)", re.IGNORECASE)


async def main() -> int:
    print("=" * 60)
    print("  R A G   D I A G N O S T I C")
    print("=" * 60)

    # ── Load config ──
    cfg_path = PROJECT_ROOT / "config.yaml"
    if not cfg_path.exists():
        print(f"[FAIL] config.yaml not found at {cfg_path}")
        return 1

    cfg = load_config(str(cfg_path))
    print(f"[OK]   Config loaded: app_name={cfg.app_name}")

    # ── Init embedder ──
    try:
        embedder = registry_create("embedder", cfg.embedder.provider, cfg.embedder)
        print(f"[OK]   Embedder: {type(embedder).__name__} (dim={embedder.dimension})")
    except Exception as exc:
        print(f"[FAIL] Embedder init failed: {exc}")
        return 1

    # ── Init vector store ──
    try:
        vector_store = registry_create(
            "vector_store", cfg.vector_store.provider, cfg.vector_store
        )
        print(f"[OK]   VectorStore: {type(vector_store).__name__}")
    except Exception as exc:
        print(f"[FAIL] VectorStore init failed: {exc}")
        return 1

    # ── Load existing indices from disk ──
    index_path = getattr(cfg.vector_store, "index_path", None)
    if index_path:
        try:
            namespaces = await vector_store.list_namespaces(index_path)
            for ns in namespaces:
                await vector_store.load(index_path, namespace=ns)
            print(f"[OK]   Loaded {len(namespaces)} namespaces from disk: {namespaces}")
        except Exception as exc:
            print(f"[WARN] Could not load indices: {exc}")

    # ── Check namespaces ──
    print("\n  --- Namespace inventory ---")
    for short, ns in _NS_MAP.items():
        try:
            dummy = [0.0] * cfg.vector_store.dim
            results = await vector_store.search(dummy, top_k=1, namespace=ns)
            count = len(results)
            print(f"  [{short}] {ns:<10} → {count} chunks found")
        except Exception as exc:
            print(f"  [{short}] {ns:<10} → ERROR: {exc}")

    # ── Test full pipeline for each prefix ──
    test_queries = [
        ("[p] test query personal", "personal"),
        ("[w] test query work", "work"),
        ("[o] test query other", "other"),
        ("no prefix at all", "default"),
    ]

    print("\n  --- Pipeline steps ---")
    for raw_query, expected_ns in test_queries:
        print(f"\n  Query: '{raw_query}'")

        m = _PREFIX_RE.match(raw_query)
        if not m:
            print("        → No RAG prefix, skipping pipeline")
            continue

        ns_short = m.group(1).lower()
        query_text = m.group(2)
        namespace = _NS_MAP.get(ns_short, "default")

        data = PipelineData(
            query=UserMessage(text=query_text),
            metadata={
                "top_k": 5,
                "namespace": namespace,
                "relevance_threshold": 0.3,
            },
        )

        # Step 1: embed
        try:
            data = await embed_query(data, embedder=embedder)
            emb = data.metadata.get("query_embedding")
            print(f"        embed_query  → {'OK' if emb else 'NO EMBEDDING'}")
            if data.errors:
                print(f"        embed errors   → {data.errors}")
        except Exception as exc:
            print(f"        embed_query  → EXCEPTION: {exc}")
            continue

        # Step 2: retrieve
        try:
            data = await retrieve(data, vector_store=vector_store)
            print(f"        retrieve     → {len(data.chunks)} chunks")
            if data.errors:
                print(f"        retrieve errors→ {data.errors}")
        except Exception as exc:
            print(f"        retrieve     → EXCEPTION: {exc}")
            continue

        # Step 3: build context
        data = await build_context(data)
        ctx_len = len(data.context)
        print(f"        build_context→ {ctx_len} chars")

        if not data.context:
            print("        ⚠️  RAG will be SKIPPED (no context)")
        else:
            print("        ✓  RAG will be ACTIVE")

    # ── Test ChatManager._maybe_rag logic (dry-run) ──
    print("\n  --- ChatManager._maybe_rag simulation ---")
    from features.chat.manager import ChatManager

    mgr = ChatManager(
        llm=None,
        embedder=embedder,
        vector_store=vector_store,
    )

    for raw_query, _ in test_queries:
        prompt, original, count = await mgr._maybe_rag(raw_query)
        status = "RAG ON" if count > 0 else "RAG OFF"
        print(f"  '{raw_query[:40]:<<40}' → {status} (chunks={count})")

    print("\n" + "=" * 60)
    print("  Done.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
