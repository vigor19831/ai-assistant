"""Incremental read: unchanged files are not re-read from disk (drift #106)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.config import SourceConfig
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    VectorStoreConfigData,
)
from ai_assistant.features.rag import indexing
from ai_assistant.features.rag.indexing import index_folder

if TYPE_CHECKING:
    import pytest


def _make_source(docs_dir: Path) -> SourceConfig:
    return SourceConfig(
        namespace="scale",
        path=str(docs_dir),
        include=["*.md"],
        recursive=True,
    )


async def _run_index(
    docs_dir: Path, store: MemoryVectorStore, clear: bool = False
) -> dict[str, Any]:
    return await index_folder(
        target_namespace=None,
        clear=clear,
        chunker=SimpleChunker(ChunkerConfigData()),
        embedder=MockEmbedder(EmbedderConfigData()),
        vector_store=store,
        sources=[_make_source(docs_dir)],
        index_path=store.index_path,
    )


def _make_store(tmp_path: Path) -> MemoryVectorStore:
    return MemoryVectorStore(
        VectorStoreConfigData(index_path=str(tmp_path / "idx"))
    )


class TestIncrementalRead:
    """drift #106: unchanged + complete files skip the disk read."""

    async def test_unchanged_file_not_reread(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        f = docs_dir / "a.md"
        f.write_text("alpha beta gamma delta", encoding="utf-8")
        os.utime(f, (1_000_000, 1_000_000))

        calls = {"n": 0}
        real_read = indexing._read_file_sync

        def counting_read(path: Path) -> str:
            calls["n"] += 1
            return real_read(path)

        monkeypatch.setattr(indexing, "_read_file_sync", counting_read)

        store = _make_store(tmp_path)
        await _run_index(docs_dir, store)
        assert calls["n"] == 1

        calls["n"] = 0
        result: dict[str, Any] = await _run_index(docs_dir, store)
        assert calls["n"] == 0
        assert result["results"]["scale"]["indexed"] == 0

    async def test_changed_file_reread_and_replaced(
        self, tmp_path: Path
    ) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        f = docs_dir / "a.md"
        f.write_text("alpha beta gamma delta", encoding="utf-8")
        os.utime(f, (1_000_000, 1_000_000))

        store = _make_store(tmp_path)
        first: dict[str, Any] = await _run_index(docs_dir, store)
        n_first = first["results"]["scale"]["chunks"]
        assert n_first > 0

        f.write_text("completely different content epsilon zeta", encoding="utf-8")
        os.utime(f, (2_000_000, 2_000_000))
        second = await _run_index(docs_dir, store)
        assert second["results"]["scale"]["indexed"] == 1

        listed = await store.list_by_filter({}, namespace="scale")
        assert len(listed) == n_first

    async def test_clear_rereads_everything(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        f = docs_dir / "a.md"
        f.write_text("alpha beta gamma delta", encoding="utf-8")
        os.utime(f, (1_000_000, 1_000_000))

        calls = {"n": 0}
        real_read = indexing._read_file_sync

        def counting_read(path: Path) -> str:
            calls["n"] += 1
            return real_read(path)

        monkeypatch.setattr(indexing, "_read_file_sync", counting_read)

        store = _make_store(tmp_path)
        await _run_index(docs_dir, store)
        calls["n"] = 0

        result: dict[str, Any] = await _run_index(docs_dir, store, clear=True)
        assert calls["n"] == 1
        assert result["results"]["scale"]["indexed"] == 1
