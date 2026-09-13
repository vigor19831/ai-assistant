"""Incremental read (drift #106), pre-flight max_chunks (stage 1),
run success semantics, watcher visibility (#113), namespace order (#114),
index save timeouts (#115), chat export size guard (#116),
targeted read scope (#118)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock

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

        def counting_read(path: Path) -> str | None:
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

        def counting_read(path: Path) -> str | None:
            calls["n"] += 1
            return real_read(path)

        monkeypatch.setattr(indexing, "_read_file_sync", counting_read)

        store = _make_store(tmp_path)
        await _run_index(docs_dir, store)
        calls["n"] = 0

        result: dict[str, Any] = await _run_index(docs_dir, store, clear=True)
        assert calls["n"] == 1
        assert result["results"]["scale"]["indexed"] == 1


class TestPreflightMaxChunks:
    """Scale stage 1: refuse BEFORE embedding when max_chunks would overflow."""

    async def test_refused_before_embedding(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        for name in ("a.md", "b.md"):
            f = docs_dir / name
            f.write_text("alpha beta gamma delta", encoding="utf-8")
            os.utime(f, (1_000_000, 1_000_000))

        store = MemoryVectorStore(
            VectorStoreConfigData(index_path=str(tmp_path / "idx"), max_chunks=1)
        )
        result: dict[str, Any] = await _run_index(docs_dir, store)

        assert result["success"] is False
        assert result["results"]["scale"] == {"indexed": 0, "chunks": 0}
        assert any("max_chunks" in e for e in result["errors"])
        listed = await store.list_by_filter({}, namespace="scale")
        assert listed == []

    async def test_exact_limit_passes(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        f = docs_dir / "a.md"
        f.write_text("alpha beta gamma delta", encoding="utf-8")
        os.utime(f, (1_000_000, 1_000_000))

        # Measure the real chunk count with a default store first —
        # the test must not assume how SimpleChunker splits the text.
        probe = await _run_index(docs_dir, _make_store(tmp_path))
        n_chunks = probe["results"]["scale"]["chunks"]
        assert n_chunks > 0

        store = MemoryVectorStore(
            VectorStoreConfigData(
                index_path=str(tmp_path / "idx2"), max_chunks=n_chunks
            )
        )
        result: dict[str, Any] = await _run_index(docs_dir, store)
        assert result["success"] is True
        assert result["results"]["scale"]["chunks"] == n_chunks

    async def test_replacement_at_limit_passes(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        f = docs_dir / "a.md"
        f.write_text("alpha beta gamma delta", encoding="utf-8")
        os.utime(f, (1_000_000, 1_000_000))

        probe = await _run_index(docs_dir, _make_store(tmp_path))
        n_chunks = probe["results"]["scale"]["chunks"]
        assert n_chunks > 0

        store = MemoryVectorStore(
            VectorStoreConfigData(
                index_path=str(tmp_path / "idx2"), max_chunks=n_chunks
            )
        )
        await _run_index(docs_dir, store)

        # Replace the only document with same-size content: the
        # projected size after replacement equals the limit — must
        # pass (no false refusal on re-indexing changed files).
        f.write_text("completely different content epsilon zeta", encoding="utf-8")
        os.utime(f, (2_000_000, 2_000_000))
        result: dict[str, Any] = await _run_index(docs_dir, store)
        assert result["success"] is True
        assert result["results"]["scale"]["indexed"] == 1
        listed = await store.list_by_filter({}, namespace="scale")
        assert len(listed) == n_chunks


class TestUnreadableFiles:
    """Unreadable is not deleted (#112): the uri stays in the inventory."""

    async def test_read_error_returns_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An OS-level read failure returns None, not an empty string."""
        target = tmp_path / "note.md"
        target.write_text("content", encoding="utf-8")

        def locked_read(self: Path, *args: object, **kwargs: object) -> str:
            raise PermissionError("locked by another process")

        monkeypatch.setattr(Path, "read_text", locked_read)
        assert indexing._read_file_sync(target) is None

    async def test_collect_unreadable_keeps_uri(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unreadable file stays in the disk inventory — not an orphan."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "a.md").write_text("content", encoding="utf-8")

        def unreadable(path: Path) -> str | None:
            return None

        monkeypatch.setattr(indexing, "_read_file_sync", unreadable)
        docs, uris = indexing._collect_files_sync(_make_source(docs_dir))
        assert docs == []
        assert uris == {"a.md"}

    async def test_collect_empty_file_drops_uri(self, tmp_path: Path) -> None:
        """A readable empty file is not kept: emptied means removed."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "a.md").write_text("", encoding="utf-8")
        docs, uris = indexing._collect_files_sync(_make_source(docs_dir))
        assert docs == []
        assert uris == set()

    async def test_changed_unreadable_file_keeps_chunks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A changed file that cannot be read loses no stored chunks."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        f = docs_dir / "a.md"
        f.write_text("alpha beta gamma delta", encoding="utf-8")
        os.utime(f, (1_000_000, 1_000_000))

        store = _make_store(tmp_path)
        first = await _run_index(docs_dir, store)
        assert first["results"]["scale"]["indexed"] == 1
        before = await store.list_by_filter({}, namespace="scale")
        assert len(before) > 0

        # New mtime: the pre-read skip must not fire — the run has to
        # attempt the read and hit the unreadable path.
        os.utime(f, (2_000_000, 2_000_000))

        def unreadable(path: Path) -> str | None:
            return None

        monkeypatch.setattr(indexing, "_read_file_sync", unreadable)
        second = await _run_index(docs_dir, store)
        assert second["success"] is True
        assert second["results"]["scale"]["indexed"] == 0
        after = await store.list_by_filter({}, namespace="scale")
        assert {cid for cid, _meta in after} == {cid for cid, _meta in before}


class TestRunSuccessSemantics:
    """Success means "no errors" — no substring matching on text (#113)."""

    async def test_empty_source_is_failed_run(self, tmp_path: Path) -> None:
        """A source with no readable documents fails the run.

        A typo in source.path or a fully emptied tree must be visible,
        not a silent success.
        """
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        store = _make_store(tmp_path)
        result: dict[str, Any] = await _run_index(docs_dir, store)
        assert result["success"] is False
        assert result["errors"] == ["No documents found"]

    async def test_chunker_error_is_failed_run(self, tmp_path: Path) -> None:
        """A chunking error must fail the run.

        "Failed to chunk document ..." starts with a capital F — under
        the old "failed"-substring check it passed as a success. This
        is the exact blind spot #113 removes.
        """
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "a.md").write_text("alpha beta gamma delta", encoding="utf-8")

        chunker = AsyncMock(spec=SimpleChunker)
        chunker.chunk.side_effect = RuntimeError("boom")

        store = _make_store(tmp_path)
        result: dict[str, Any] = await index_folder(
            target_namespace=None,
            clear=False,
            chunker=chunker,
            embedder=MockEmbedder(EmbedderConfigData()),
            vector_store=store,
            sources=[_make_source(docs_dir)],
            index_path=store.index_path,
        )
        assert result["success"] is False
        assert any("Failed to chunk" in e for e in result["errors"])


class TestWatcherVisibility:
    """The watcher path must be loud on failure (#13, drift #113)."""

    async def test_failed_run_logs_error(
        self, mock_state: Any, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A run reporting failure produces an ERROR record on the lifespan logger."""
        from ai_assistant.api.lifespan import _index_source

        src = SourceConfig(
            namespace="default",
            path=str(tmp_path / "missing"),
            include=["*.md"],
            recursive=False,
        )
        with caplog.at_level(logging.ERROR, logger="lifespan"):
            await _index_source(mock_state, mock_state.config, src)
        assert any(
            "Watcher reindex failed" in r.getMessage() for r in caplog.records
        )

    async def test_successful_run_is_silent(
        self,
        mock_state: Any,
        tmp_path: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A successful run produces no ERROR records — no false alarms."""
        import ai_assistant.api.lifespan as lifespan_module
        from ai_assistant.api.lifespan import _index_source

        monkeypatch.setattr(
            lifespan_module,
            "index_folder",
            AsyncMock(
                return_value={"success": True, "results": {}, "errors": []}
            ),
        )
        src = SourceConfig(
            namespace="default",
            path=str(tmp_path),
            include=["*.md"],
            recursive=False,
        )
        with caplog.at_level(logging.ERROR, logger="lifespan"):
            await _index_source(mock_state, mock_state.config, src)
        assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


class TestNamespaceOrder:
    """Cross-process determinism: the main loop processes sorted namespaces (#114)."""

    async def test_namespaces_processed_in_sorted_order(
        self, tmp_path: Path
    ) -> None:
        """The results dict mirrors the main loop order — must be sorted.

        Raw set iteration order varies with string-hash randomization
        across processes; the file collection is sorted for the same
        reason.
        """
        sources = []
        for ns in ("zeta", "alpha"):
            ns_dir = tmp_path / ns
            ns_dir.mkdir()
            (ns_dir / "a.md").write_text("alpha beta gamma delta", encoding="utf-8")
            sources.append(
                SourceConfig(
                    namespace=ns,
                    path=str(ns_dir),
                    include=["*.md"],
                    recursive=True,
                )
            )
        store = _make_store(tmp_path)
        result: dict[str, Any] = await index_folder(
            target_namespace=None,
            clear=False,
            chunker=SimpleChunker(ChunkerConfigData()),
            embedder=MockEmbedder(EmbedderConfigData()),
            vector_store=store,
            sources=sources,
            index_path=store.index_path,
        )
        assert result["success"] is True
        assert list(result["results"]) == ["alpha", "zeta"]


class TestSaveTimeouts:
    """Index saves are bounded by INDEX_IO_TIMEOUT (#115)."""

    async def test_checkpoint_save_timeout_fails_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hanging checkpoint save must not stall the indexing loop."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "a.md").write_text("alpha beta gamma delta", encoding="utf-8")

        monkeypatch.setattr(indexing, "INDEX_IO_TIMEOUT", 0.05)
        store = _make_store(tmp_path)

        async def hanging_save(path: str, namespace: str = "default") -> None:
            await asyncio.sleep(1.0)  # sleep: intentional — past the timeout

        monkeypatch.setattr(store, "save", hanging_save)
        result: dict[str, Any] = await _run_index(docs_dir, store)
        assert result["success"] is False
        assert any("timed out" in e for e in result["errors"])

    async def test_chat_export_save_timeout_is_reported(
        self,
        isolated_app_state: Any,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A hanging chat-export save answers indexed=False with the reason."""
        from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
        from ai_assistant.features.rag.handlers import save_chat
        from ai_assistant.features.rag.schemas import SaveChatRequest

        isolated_app_state.config.rag.index_chat_exports = True

        async def hanging_save(path: str, namespace: str = "default") -> None:
            await asyncio.sleep(1.0)  # sleep: intentional — past the timeout

        isolated_app_state.vector_store.save = AsyncMock(side_effect=hanging_save)
        isolated_app_state.chunker.chunk = AsyncMock(
            return_value=[
                Chunk(
                    id="c1",
                    text="hello",
                    metadata=ChunkMetadata(source="doc", index=0, total_chunks=1),
                )
            ]
        )
        monkeypatch.setattr(
            "ai_assistant.features.rag.handlers.INDEX_IO_TIMEOUT", 0.05
        )

        req = SaveChatRequest(namespace="test", filename="chat.md", content="hello")
        response: dict[str, Any] = await save_chat(req, isolated_app_state)
        assert response["saved"] is True
        assert response["indexed"] is False
        assert "timed out" in response["error"]


class TestChatExportSizeGuard:
    """Oversized chat exports are saved but never indexed (#116)."""

    async def test_oversized_export_saved_not_indexed(
        self, isolated_app_state: Any
    ) -> None:
        """Content over max_document_size answers indexed=False with a reason."""
        from ai_assistant.features.rag.handlers import save_chat
        from ai_assistant.features.rag.schemas import SaveChatRequest

        isolated_app_state.config.rag.index_chat_exports = True
        isolated_app_state.config.vector_store.max_document_size = 10

        req = SaveChatRequest(
            namespace="test", filename="big.md", content="x" * 100
        )
        response: dict[str, Any] = await save_chat(req, isolated_app_state)
        assert response["saved"] is True
        assert response["indexed"] is False
        assert "max_document_size" in response["reason"]
        # The document never reached the store.
        isolated_app_state.vector_store.upsert.assert_not_awaited()


class TestTargetedReadScope:
    """A targeted reindex reads only the target namespace's files (#8, #118)."""

    async def test_targeted_reindex_skips_other_namespaces(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Files of non-target namespaces are never read from disk."""
        calls: list[str] = []
        real_read = indexing._read_file_sync

        def counting_read(path: Path) -> str | None:
            calls.append(path.name)
            return real_read(path)

        monkeypatch.setattr(indexing, "_read_file_sync", counting_read)

        sources = []
        for ns in ("ns1", "ns2"):
            ns_dir = tmp_path / ns
            ns_dir.mkdir()
            (ns_dir / f"{ns}.md").write_text(
                "alpha beta gamma delta", encoding="utf-8"
            )
            sources.append(
                SourceConfig(
                    namespace=ns,
                    path=str(ns_dir),
                    include=["*.md"],
                    recursive=True,
                )
            )
        store = _make_store(tmp_path)
        result: dict[str, Any] = await index_folder(
            target_namespace="ns1",
            clear=False,
            chunker=SimpleChunker(ChunkerConfigData()),
            embedder=MockEmbedder(EmbedderConfigData()),
            vector_store=store,
            sources=sources,
            index_path=store.index_path,
        )
        assert result["success"] is True
        assert result["results"]["ns1"]["indexed"] == 1
        assert calls == ["ns1.md"]

    async def test_unknown_target_fails_fast_without_reads(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A namespace absent from sources fails before any file is read."""
        calls: list[str] = []
        real_read = indexing._read_file_sync

        def counting_read(path: Path) -> str | None:
            calls.append(path.name)
            return real_read(path)

        monkeypatch.setattr(indexing, "_read_file_sync", counting_read)

        ns_dir = tmp_path / "ns1"
        ns_dir.mkdir()
        (ns_dir / "a.md").write_text("alpha beta gamma delta", encoding="utf-8")
        sources = [
            SourceConfig(
                namespace="ns1",
                path=str(ns_dir),
                include=["*.md"],
                recursive=True,
            )
        ]
        store = _make_store(tmp_path)
        result: dict[str, Any] = await index_folder(
            target_namespace="missing",
            clear=False,
            chunker=SimpleChunker(ChunkerConfigData()),
            embedder=MockEmbedder(EmbedderConfigData()),
            vector_store=store,
            sources=sources,
            index_path=store.index_path,
        )
        assert result["success"] is False
        assert result["errors"] == [
            "Namespace 'missing' not found in configured sources"
        ]
        assert calls == []

    async def test_empty_target_namespace_is_failed_run(
        self, tmp_path: Path
    ) -> None:
        """An emptied target namespace fails like the watcher path (#113 parity)."""
        ns1 = tmp_path / "ns1"
        ns1.mkdir()
        ns2 = tmp_path / "ns2"
        ns2.mkdir()
        (ns2 / "b.md").write_text("alpha beta gamma delta", encoding="utf-8")
        sources = []
        for ns, ns_dir in (("ns1", ns1), ("ns2", ns2)):
            sources.append(
                SourceConfig(
                    namespace=ns,
                    path=str(ns_dir),
                    include=["*.md"],
                    recursive=True,
                )
            )
        store = _make_store(tmp_path)
        result: dict[str, Any] = await index_folder(
            target_namespace="ns1",
            clear=False,
            chunker=SimpleChunker(ChunkerConfigData()),
            embedder=MockEmbedder(EmbedderConfigData()),
            vector_store=store,
            sources=sources,
            index_path=store.index_path,
        )
        assert result["success"] is False
        assert result["errors"] == ["No documents found"]
