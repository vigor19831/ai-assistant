#!/usr/bin/env python3
"""Standalone RAG diagnostic — works offline with mock fallback."""

import asyncio
import sys
from pathlib import Path

# Ensure project root is importable (src/ layout)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# Trigger @register side-effects — must match deps.py adapter list
import ai_assistant.adapters.chunker_simple  # noqa: F401, E402
import ai_assistant.adapters.embedder_mock  # noqa: F401, E402
import ai_assistant.adapters.vector_store_faiss  # noqa: F401, E402
import ai_assistant.adapters.vector_store_memory  # noqa: F401, E402
from ai_assistant.core.config import load_config  # noqa: E402
from ai_assistant.core.domain.messages import UserMessage  # noqa: E402
from ai_assistant.core.constants import RAG_NS_MAP, RAG_PREFIX_RE  # noqa: E402
from ai_assistant.core.domain.pipeline import PipelineData  # noqa: E402
from ai_assistant.core.logger import get_logger  # noqa: E402
from ai_assistant.adapters.factory import create_adapter  # noqa: E402
from ai_assistant.core.pipeline_steps import (  # noqa: E402
    build_context,
    embed_query,
    retrieve,
)

logger = get_logger("check_rag")


async def main() -> int:
    print(" RAG DIAGNOSTIC ".center(60, "="))

    # Load config
    cfg_path = PROJECT_ROOT / "config.yaml"
    if not cfg_path.exists():
        print(f"[FAIL] config.yaml not found at {cfg_path}")
        return 1

    cfg = load_config(str(cfg_path))
    print(f"[OK]   Config loaded: app_name={cfg.app_name}")

    # Init embedder (mock for offline diagnostic)
    dim = getattr(cfg.vector_store, "dim", None) or 768
    mock_cfg = type(
        "MockEmbedderConfig",
        (),
        {
            "provider": "mock",
            "dim": dim,
            "timeout": 1.0,
            "model": "mock-embedder",
            "api_base": "",
            "api_key": None,
        },
    )()
    embedder = create_adapter("embedder", "mock", mock_cfg)
    print(f"[OK]   Embedder: {type(embedder).__name__} (dim={embedder.dimension}) [MOCK]")

    # Init vector store
    try:
        vector_store = create_adapter(
            "vector_store", cfg.vector_store.provider, cfg.vector_store
        )
        print(f"[OK]   VectorStore: {type(vector_store).__name__}")
    except Exception as exc:
        print(f"[FAIL] VectorStore init failed: {exc}")
        return 1

    # Load existing indices from disk
    index_path = getattr(cfg.vector_store, "index_path", None)
    if index_path:
        try:
            namespaces = await vector_store.list_namespaces(index_path)
            for ns in namespaces:
                await vector_store.load(index_path, namespace=ns)
            print(f"[OK]   Loaded {len(namespaces)} namespaces: {namespaces}")
        except Exception as exc:
            print(f"[WARN] Could not load indices: {exc}")

    # Check namespaces with a real embedding (not zero vector)
    print("\n  --- Namespace inventory ---")
    test_text = "test query for namespace check"
    try:
        test_embeddings = await embedder.embed([test_text])
        test_embedding = test_embeddings[0] if test_embeddings else None
    except Exception as exc:
        print(f"[WARN] Could not generate test embedding: {exc}")
        test_embedding = None

    for short, ns in RAG_NS_MAP.items():
        try:
            if test_embedding:
                results = await vector_store.search(test_embedding, top_k=1, namespace=ns)
            else:
                # Fallback to zero vector only if embedder failed
                dummy = [0.0] * dim
                results = await vector_store.search(dummy, top_k=1, namespace=ns)
            print(f"  [{short}] {ns:<10} → {len(results)} chunks found")
        except Exception as exc:
            print(f"  [{short}] {ns:<10} → ERROR: {exc}")

    # Test full pipeline for each prefix
    test_queries = [
        (f"[{short}] test query {ns}", ns)
        for short, ns in RAG_NS_MAP.items()
    ] + [("no prefix at all", cfg.rag.default_namespace)]

    relevance_threshold = getattr(
        cfg.rag, "relevance_threshold",
        getattr(cfg.vector_store, "relevance_threshold", 0.1)
    )

    print("\n  --- Pipeline steps ---")
    for raw_query, expected_ns in test_queries:
        print(f"\n  Query: '{raw_query}'")

        m = RAG_PREFIX_RE.match(raw_query)
        if not m:
            print(f"        → No RAG prefix, using default namespace '{expected_ns}'")
            query_text = raw_query
            namespace = expected_ns
        else:
            ns_short = m.group(1).lower()
            query_text = m.group(2)
            namespace = RAG_NS_MAP.get(ns_short, expected_ns)

        data = PipelineData(
            query=UserMessage(text=query_text),
            metadata={
                "top_k": cfg.rag.top_k,
                "namespace": namespace,
                "relevance_threshold": relevance_threshold,
                "embedder": embedder,
                "vector_store": vector_store,
            },
        )

        # Step 1: embed
        try:
            data = await embed_query(data)
            emb = data.metadata.get("query_embedding")
            print(f"        embed_query  → {'OK' if emb else 'NO EMBEDDING'}")
            if data.errors:
                print(f"        embed errors   → {data.errors}")
                continue
        except Exception as exc:
            print(f"        embed_query  → EXCEPTION: {exc}")
            continue

        # Step 2: retrieve
        try:
            data = await retrieve(data)
            print(f"        retrieve     → {len(data.chunks)} chunks")
            if data.errors:
                print(f"        retrieve errors→ {data.errors}")
                continue
        except Exception as exc:
            print(f"        retrieve     → EXCEPTION: {exc}")
            continue

        # Step 3: build context
        try:
            data = await build_context(data)
            print(f"        build_context→ {len(data.context)} chars")
        except Exception as exc:
            print(f"        build_context→ EXCEPTION: {exc}")
            continue

        if not data.context:
            print("        ⚠️  RAG will be SKIPPED (no context)")
        else:
            print("        ✓  RAG will be ACTIVE")

    print("\n" + "=" * 60)
    print("  Done.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
