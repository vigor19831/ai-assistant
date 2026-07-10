#!/usr/bin/env python3
"""Index documents from folders into RAG namespaces (direct adapter call)."""

from __future__ import annotations

import argparse
import asyncio
import os
import socket
import sys
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

# ── Windows: force UTF-8 output ─────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


@contextmanager
def _project_path():
    """Temporarily add src/ to sys.path."""
    root = Path(__file__).parent.parent.resolve()
    src = str(root / "src")
    inserted = False
    if src not in sys.path:
        sys.path.insert(0, src)
        inserted = True
    try:
        yield root
    finally:
        if inserted:
            sys.path.remove(src)


# ── Imports (must be after path setup) ──────────────────────────────────────
with _project_path():
    from ai_assistant.api.deps import init_adapters
    from ai_assistant.core.config import load_config
    from ai_assistant.features.rag.indexing import index_folder


def _check_embedder_reachable(cfg) -> tuple[bool, str]:
    """Return (ok, message). Skip check for mock or remote embedders."""
    provider = getattr(cfg.embedder, "provider", "mock")
    if provider == "mock":
        return True, "mock"

    base = getattr(cfg.embedder, "api_base", "")
    if not base:
        return False, "embedder.api_base is empty"

    parsed = urlparse(base.rstrip("/"))
    if not parsed.hostname:
        return False, f"invalid embedder api_base: {base}"

    if parsed.hostname not in ("127.0.0.1", "localhost"):
        return True, "remote"

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    host = parsed.hostname

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(2.0)
            if s.connect_ex((host, port)) != 0:
                return False, f"embedder not responding at {host}:{port}"
    except (OSError, socket.gaierror) as exc:
        return False, f"embedder connection check failed: {exc}"
    return True, "local"


async def _shutdown_adapters(state) -> None:
    """Gracefully shutdown all adapters unconditionally."""
    for adapter in (state.llm, state.embedder, state.vector_store,
                    state.reranker, state.storage):
        try:
            await adapter.shutdown()
        except Exception:
            pass


async def _trigger_reload(host: str, port: int, api_key: str | None) -> tuple[bool, str]:
    """Trigger index reload on the running server via admin endpoint.

    Returns (success, message).
    """
    import httpx

    url = f"http://{host}:{port}/admin/reload-indices"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=headers)
            if resp.status_code == 404:
                return False, (
                    "Admin endpoint not found. "
                    "Enable admin_enabled in config.yaml and restart the server, "
                    "or restart the server manually after indexing."
                )
            if resp.status_code == 401:
                return False, (
                    "Admin endpoint requires API key. "
                    "Set security.api_key in config.yaml, restart the server, "
                    "and re-run this script."
                )
            if resp.status_code == 503:
                return False, "Vector store not initialized on server."
            resp.raise_for_status()
            data = resp.json()
            return True, (
                f"Server reloaded {data.get('reloaded', 0)} namespace(s), "
                f"skipped {data.get('skipped', 0)}."
            )
    except httpx.ConnectError:
        return False, (
            f"Could not connect to server at {host}:{port}. "
            f"Is the server running? If not, start it and the new indices "
            f"will be loaded automatically on startup."
        )
    except Exception as exc:
        return False, f"Reload request failed: {exc}"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Index documents into RAG")
    parser.add_argument("--namespace", "-n", help="Index only specific namespace")
    parser.add_argument(
        "--clear", "-c", action="store_true", help="Clear before indexing"
    )
    parser.add_argument(
        "--config", help="Path to config file (default: config.yaml)"
    )
    parser.add_argument(
        "--no-reload", action="store_true",
        help="Skip triggering server reload after indexing"
    )
    args = parser.parse_args()

    project_root = Path(__file__).parent.parent.resolve()

    cfg_path = Path(args.config).resolve() if args.config else project_root / "config.yaml"
    if not cfg_path.exists():
        print(f"[ERROR] Config not found: {cfg_path}")
        return 1

    config = load_config(str(cfg_path))

    # ── Check embedder ──
    ok, msg = _check_embedder_reachable(config)
    if not ok:
        print(f"[ERROR] {msg}")
        print("[HINT] Start server: python scripts/start.py")
        return 1

    try:
        state = await init_adapters(config)
    except Exception as exc:
        print(f"[ERROR] Failed to initialize adapters: {exc}")
        return 1

    try:
        result = await index_folder(
            folder=args.namespace,
            clear=args.clear,
            chunker=state.chunker,
            embedder=state.embedder,
            vector_store=state.vector_store,
            max_file_size=config.vector_store.max_document_size,
            sources=config.rag.sources,
            index_path=config.vector_store.index_path,
        )
    except Exception as exc:
        print(f"[ERROR] Indexing failed: {exc}")
        return 1
    finally:
        await _shutdown_adapters(state)

    result = result or {}
    results = result.get("results", {})
    if not isinstance(results, dict):
        print(f"[ERROR] Invalid result format from index_folder")
        return 1

    for ns, data in results.items():
        if isinstance(data, dict):
            indexed = data.get("indexed", 0)
            chunks = data.get("chunks", 0)
        else:
            indexed = chunks = 0
        print(f"  [{ns}] {indexed} docs, {chunks} chunks")

    errors = result.get("errors", [])
    if errors:
        for err in errors:
            print(f"  [ERROR] {err}")
        return 1

    print("\n[OK] Indexing complete!")

    # ── Trigger server reload ──
    if not args.no_reload:
        print("[INFO] Triggering server index reload...")
        ok, msg = await _trigger_reload(
            host=config.host,
            port=config.port,
            api_key=config.security.api_key,
        )
        if ok:
            print(f"[OK] {msg}")
            print("[INFO] New documents are now searchable without restart.")
        else:
            print(f"[WARN] {msg}")
            print("[INFO] You will need to restart the server for new documents to be searchable.")
    else:
        print("[INFO] Skipped server reload (--no-reload). Restart server to search new documents.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
