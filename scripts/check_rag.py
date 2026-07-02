#!/usr/bin/env python3
"""Standalone RAG diagnostic — checks REAL end-to-end RAG flow."""

import asyncio
import sys
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WIDTH = 70


@contextmanager
def _project_path():
    src = str(PROJECT_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
        inserted = True
    else:
        inserted = False
    try:
        yield
    finally:
        if inserted:
            sys.path.remove(src)


async def main() -> int:
    print(" RAG REALITY CHECK ".center(WIDTH, "="))

    with _project_path():
        from ai_assistant.core.config import load_config
        from ai_assistant.core.domain.messages import UserMessage
        from ai_assistant.core.domain.pipeline import PipelineConfig, PipelineData
        from ai_assistant.core.query_parser import build_prefix_map, parse_rag_query
        from ai_assistant.adapters.factory import create_adapter
        from ai_assistant.core.pipeline_steps import (
        embed_query, retrieve, build_context, rerank
        )
        from ai_assistant.core.logger import get_logger

    _logger = get_logger("check_rag")

    # ── 1. Config ──
    cfg_path = PROJECT_ROOT / "config.yaml"
    if not cfg_path.exists():
        print(f"[FAIL] config.yaml not found at {cfg_path}")
        return 1

    cfg = load_config(str(cfg_path))
    print(f"[OK]   Config: app={cfg.app_name}, embedder.dim={cfg.embedder.dim}, "
          f"vector_store.dim={cfg.vector_store.dim}")

    if cfg.embedder.dim != cfg.vector_store.dim:
        print(f"[FAIL] DIMENSION MISMATCH! embedder.dim={cfg.embedder.dim} "
              f"!= vector_store.dim={cfg.vector_store.dim}")
        print("       Fix: set embedder.dim = vector_store.dim in config.yaml")
        return 1

    # ── 2. Check source files exist ──
    print(f"\n  --- Source files ---")
    for source in cfg.rag.sources:
        ns_dir = Path(source.path)
        if ns_dir.exists():
            files = [f for f in ns_dir.iterdir() if f.is_file()]
            filtered = [f for f in files if any(
                fnmatch.fnmatch(f.name, pat) for pat in source.include
            )]
            print(f"  [{source.namespace}] -> {len(filtered)} files in {ns_dir}")
            for f in filtered[:3]:
                print(f"         - {f.name} ({f.stat().st_size} bytes)")
            if len(filtered) > 3:
                print(f"         ... and {len(filtered)-3} more")
        else:
            print(f"  [{source.namespace}] -> MISSING directory {ns_dir}")

    # ── 3. Init REAL embedder (not mock!) ──
    print(f"\n  --- Initializing REAL embedder ---")
    try:
        embedder = create_adapter("embedder", cfg.embedder.provider, cfg.embedder)
        print(f"[OK]   Embedder: {type(embedder).__name__}, dim={embedder.dimension}")
    except Exception as exc:
        print(f"[FAIL] Embedder init failed: {exc}")
        print("       Falling back to MOCK (results will be meaningless for existing indices)")
        from ai_assistant.core.domain.configs import EmbedderConfigData
        mock_cfg = EmbedderConfigData(
            dim=cfg.vector_store.dim,
            timeout=1.0,
            model="mock",
            api_base="",
            api_key=None,
        )
        embedder = create_adapter("embedder", "mock", mock_cfg)

    # ── 4. Init vector store ──
    print(f"\n  --- Initializing vector store ---")
    try:
        vector_store = create_adapter(
            "vector_store", cfg.vector_store.provider, cfg.vector_store
        )
        print(f"[OK]   VectorStore: {type(vector_store).__name__}")
    except Exception as exc:
        print(f"[FAIL] VectorStore init failed: {exc}")
        return 1

    # ── 5. Load indices ──
    print(f"\n  --- Loading indices ---")
    index_path = cfg.vector_store.index_path
    total_chunks = 0
    if index_path:
        try:
            namespaces = await vector_store.list_namespaces(index_path)
            for ns in namespaces:
                await vector_store.load(index_path, namespace=ns)
                # Try to count chunks
                try:
                    test_emb = await embedder.embed(["count_test"])
                    all_chunks = await vector_store.search(
                        test_emb[0], top_k=10000, namespace=ns
                    )
                    print(f"  [OK]   {ns}: loaded, ~{len(all_chunks)} chunks")
                    total_chunks += len(all_chunks)
                except Exception:
                    print(f"  [OK]   {ns}: loaded (chunk count unknown)")
            print(f"[INFO] Total loaded: {len(namespaces)} namespaces, {total_chunks} chunks")
        except Exception as exc:
            print(f"[WARN] Could not load indices: {exc}")
            print("       Run: python scripts/index_documents.py")

    if total_chunks == 0:
        print(f"\n[!] WARNING: No chunks found in any namespace!")
        print(f"    Run: python scripts/index_documents.py")

    # ── 6. Test REAL query through pipeline ──
    print(f"\n  --- REAL RAG test ---")
    prefix_map = build_prefix_map(cfg.namespaces)

    # Build test queries dynamically from actual config instead of hardcoded prefixes
    test_queries: list[tuple[str, str]] = []
    for ns_name, ns_cfg in cfg.namespaces.items():
        if ns_cfg.prefix:
            test_queries.append((f"[{ns_cfg.prefix}] test query {ns_name}", ns_name))
        else:
            test_queries.append((f"test query {ns_name}", ns_name))
    # Always test default namespace without prefix
    if cfg.rag.default_namespace not in {ns for _, ns in test_queries}:
        test_queries.append(("no prefix query", cfg.rag.default_namespace))

    if not test_queries:
        print("  [WARN] No namespaces configured — cannot run RAG tests")
        return 0

    for raw_query, expected_ns in test_queries:
        print(f"\n  Query: '{raw_query}'")

        query_text, namespace = parse_rag_query(raw_query, prefix_map)
        if namespace is None and raw_query == query_text:
            namespace = expected_ns
        print(f"        -> Parsed: ns='{namespace}', text='{query_text}'")

        # Get namespace config
        ns_cfg = cfg.namespaces.get(namespace)
        threshold = ns_cfg.relevance_threshold if ns_cfg else cfg.rag.relevance_threshold
        print(f"        -> relevance_threshold={threshold}")

        # Build pipeline config and data
        pipeline_config = PipelineConfig(
            top_k=cfg.rag.top_k,
            namespace=namespace,
            relevance_threshold=threshold,
            prompt_name=cfg.rag.prompt_name,
            prompt_version=cfg.rag.prompt_version,
            token_margin_min=cfg.rag.token_margin_min,
            token_margin_pct=cfg.rag.token_margin_pct,
        )

        # Create NullReranker for diagnostic pipeline
        from ai_assistant.core.domain.configs import RerankerConfigData
        reranker = create_adapter("reranker", "null", RerankerConfigData())

        data = PipelineData(
            query=UserMessage(text=query_text),
            embedder=embedder,
            vector_store=vector_store,
            reranker=reranker,
            pipeline_config=pipeline_config,
        )

        # Step 1: embed
        data = await embed_query(data)
        if data.errors:
            print(f"        [FAIL] embed_query: {data.errors}")
            continue
        emb = data.query_embedding
        print(f"        [OK] embed_query: embedding len={len(emb) if emb else 'NONE'}")

        # Step 2: retrieve
        data = await retrieve(data)
        print(f"        [OK] retrieve: {len(data.chunks)} chunks found")
        if not data.chunks:
            print(f"        [WARN] NO CHUNKS! Possible causes:")
            print(f"               - Index not built (run index_documents.py)")
            print(f"               - Wrong embedder (mock vs real mismatch)")
            print(f"               - Wrong namespace")
            print(f"               - Documents don't match query semantically")
            continue

        # Show found chunks
        for i, chunk in enumerate(data.chunks[:3]):
            preview = chunk.text[:80].replace('\n', ' ')
            print(f"               chunk[{i}]: {preview}...")

        # Step 3: rerank (if configured)
        if cfg.reranker and cfg.reranker.provider:
            print(f"        [INFO] Reranker configured, would run rerank step")
        else:
            print(f"        [INFO] No reranker (NullReranker)")

        # Step 4: build context
        data = await build_context(data)
        print(f"        [OK] build_context: {len(data.context)} chars")
        if data.context:
            preview = data.context[:100].replace('\n', ' ')
            print(f"               Context preview: {preview}...")
            print(f"        [PASS] RAG WILL WORK for this query")
        else:
            print(f"        [FAIL] EMPTY CONTEXT — RAG disabled for this query")

    # ── 7. Summary ──
    print("\n" + "=" * WIDTH)
    print("DIAGNOSIS CHECKLIST:")
    print("  [ ] embedder.dim == vector_store.dim")
    print("  [ ] rag.sources configured with existing paths")
    print("  [ ] scripts/index_documents.py was run")
    print("  [ ] Index files exist in data/indices/")
    print("  [ ] Query embedding matches index embedding (same model)")
    print("  [ ] relevance_threshold not too high")
    print("=" * WIDTH)
    return 0


if __name__ == "__main__":
    asyncio.run(main())
