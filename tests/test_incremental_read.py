"""Incremental read (drift #106), pre-flight max_chunks (stage 1),
run success semantics, watcher visibility (#113), namespace order (#114),
index save timeouts (#115), chat export size guard (#116),
targeted read scope (#118), reindex restore symmetry (#119),
typed-field precedence in list_by_filter (#120)."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from ai_assistant.adapters.chunker_simple import SimpleChunker
from ai_assistant.adapters.embedder_mock import MockEmbedder
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.config import SourceConfig
from ai_assistant.core.domain.configs import (
    ChunkerConfigData,
    EmbedderConfigData,
    VectorStoreConfigData,
)
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.features.rag import indexing
from ai_assistant.features.rag.indexing import index_folder


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

        def counting_read(path: Path, encodings: list[str] | None = None) -> str | None:
            calls["n"] += 1
            return real_read(path, encodings)

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

        def counting_read(path: Path, encodings: list[str] | None = None) -> str | None:
            calls["n"] += 1
            return real_read(path, encodings)

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
        assert indexing._read_file_sync(target, ["utf-8-sig"]) is None

    async def test_collect_unreadable_keeps_uri(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unreadable file stays in the disk inventory — not an orphan."""
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "a.md").write_text("content", encoding="utf-8")

        def unreadable(path: Path, encodings: list[str] | None = None) -> str | None:
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

        def unreadable(path: Path, encodings: list[str] | None = None) -> str | None:
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

        def counting_read(path: Path, encodings: list[str] | None = None) -> str | None:
            calls.append(path.name)
            return real_read(path, encodings)

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

        def counting_read(path: Path, encodings: list[str] | None = None) -> str | None:
            calls.append(path.name)
            return real_read(path, encodings)

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


class TestReindexRestore:
    """Interrupted reindex restores memory from disk (#7, #119)."""

    @staticmethod
    def _patch_hanging_reindex(
        isolated_app_state: Any,
        monkeypatch: pytest.MonkeyPatch,
    ) -> tuple[list[Any], asyncio.Event]:
        """Patch spawn to capture the coroutine; hang index_folder until cancelled."""
        spawned: list[Any] = []
        hang_event = asyncio.Event()
        hang_started = asyncio.Event()

        def _capture_spawn(fn: Any, trace_id: str, name: str) -> None:
            spawned.append(fn())

        monkeypatch.setattr(
            isolated_app_state.task_registry, "spawn", _capture_spawn
        )

        async def hanging_index_folder(**kwargs: Any) -> dict[str, Any]:
            hang_started.set()
            await hang_event.wait()
            # Unreachable unless the test releases the stand-in —
            # but it must honor index_folder's return contract.
            return {"success": True, "results": {}, "errors": []}

        monkeypatch.setattr(
            "ai_assistant.features.rag.handlers.index_folder",
            AsyncMock(side_effect=hanging_index_folder),
        )
        monkeypatch.setattr(
            "ai_assistant.features.rag.handlers.REINDEX_TASK_TIMEOUT", 0.05
        )
        return spawned, hang_started

    async def test_timeout_restores_namespaces(
        self,
        isolated_app_state: Any,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A timed-out reindex reloads the affected namespace from disk."""
        from ai_assistant.features.rag.handlers import reindex_documents
        from ai_assistant.features.rag.schemas import ReindexRequest

        spawned, _hang_started = self._patch_hanging_reindex(
            isolated_app_state, monkeypatch
        )

        req = ReindexRequest(target_namespace=None, clear=False)
        started = await reindex_documents(req, isolated_app_state)
        assert started["status"] == "started"

        result = await spawned[0]
        assert "timed out" in result["error"]

        # Memory restored: the source namespace reloaded from disk.
        load_calls = isolated_app_state.vector_store.load.await_args_list
        assert [c.kwargs["namespace"] for c in load_calls] == ["default"]

        info = await isolated_app_state.rag_state.get_status(started["task_id"])
        assert info is not None
        assert info["status"] == "failed"

    async def test_cancel_restores_namespaces(
        self,
        isolated_app_state: Any,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Cancellation still restores from disk (regression guard)."""
        from ai_assistant.features.rag.handlers import reindex_documents
        from ai_assistant.features.rag.schemas import ReindexRequest

        spawned, hang_started = self._patch_hanging_reindex(
            isolated_app_state, monkeypatch
        )

        req = ReindexRequest(target_namespace=None, clear=False)
        started = await reindex_documents(req, isolated_app_state)
        assert started["status"] == "started"

        task = asyncio.create_task(spawned[0])
        # Deterministic handoff: wait until the stand-in is inside its
        # hang, then cancel — no timer races (#119, §15 DETERMINISM).
        await hang_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        load_calls = isolated_app_state.vector_store.load.await_args_list
        assert [c.kwargs["namespace"] for c in load_calls] == ["default"]

    async def test_restore_extends_chat_namespaces_on_full_clear(
        self, isolated_app_state: Any
    ) -> None:
        """clear=True without a target also restores chat namespaces."""
        from ai_assistant.features.rag.handlers import _restore_reindex_namespaces

        isolated_app_state.vector_store.list_namespaces = AsyncMock(
            return_value=["default", "chat_default"]
        )
        await _restore_reindex_namespaces(
            isolated_app_state, target_namespace=None, clear=True
        )
        namespaces = [
            c.kwargs["namespace"]
            for c in isolated_app_state.vector_store.load.await_args_list
        ]
        assert "default" in namespaces
        assert "chat_default" in namespaces
        assert "chat_chat_default" not in namespaces


class TestListByFilterPrecedence:
    """Typed metadata fields win over same-named custom keys (#15, #120)."""

    @staticmethod
    def _conflicting_chunk() -> Chunk:
        return Chunk(
            id="c-custom",
            text="hello world",
            embedding=[0.1] * 384,
            metadata=ChunkMetadata(
                source="real-source",
                index=0,
                total_chunks=1,
                custom={"source": "fake-source", "source_uri": "fake/uri"},
                source_uri="real/uri",
            ),
        )

    async def test_memory_typed_fields_win(self, tmp_path: Path) -> None:
        """MemoryVectorStore: a custom 'source' key cannot shadow the typed one."""
        store = MemoryVectorStore(
            VectorStoreConfigData(dim=384, index_path=str(tmp_path / "mem"))
        )
        await store.add([self._conflicting_chunk()], namespace="ns")
        listed = await store.list_by_filter({}, namespace="ns")
        assert len(listed) == 1
        _cid, meta = listed[0]
        assert meta["source"] == "real-source"
        assert meta["source_uri"] == "real/uri"
        shadows = await store.list_by_filter(
            {"source": "fake-source"}, namespace="ns"
        )
        assert shadows == []
        hits = await store.list_by_filter(
            {"source": "real-source"}, namespace="ns"
        )
        assert len(hits) == 1

    async def test_faiss_typed_fields_win(self, tmp_path: Path) -> None:
        """FaissVectorStore: same contract after the merge-order fix."""
        pytest.importorskip("faiss")
        from ai_assistant.adapters.vector_store_faiss import FaissVectorStore

        store = FaissVectorStore(
            VectorStoreConfigData(dim=384, index_path=str(tmp_path / "faiss"))
        )
        await store.add([self._conflicting_chunk()], namespace="ns")
        listed = await store.list_by_filter({}, namespace="ns")
        assert len(listed) == 1
        _cid, meta = listed[0]
        assert meta["source"] == "real-source"
        assert meta["source_uri"] == "real/uri"
        shadows = await store.list_by_filter(
            {"source": "fake-source"}, namespace="ns"
        )
        assert shadows == []
        hits = await store.list_by_filter(
            {"source": "real-source"}, namespace="ns"
        )
        assert len(hits) == 1




class TestFileEncodingsWiring:
    """Drift #155: the encoding chain must actually reach the file
    reader — a custom chain decides how files decode; the default
    chain being similar is not the same as the custom one working."""

    def test_custom_chain_reads_cp1251(self, tmp_path) -> None:
        from ai_assistant.features.rag.indexing import _read_file_sync

        (tmp_path / "doc.md").write_bytes("Мой любимый город".encode("cp1251"))

        # Custom chain, cp1251 first: decodes correctly.
        content = _read_file_sync(tmp_path / "doc.md", ["cp1251", "utf-8-sig"])
        assert content == "Мой любимый город"

        # Strict chain (utf-8-sig only) on the same file: exhausts —
        # empty result, the owner's explicit choice, never mojibake.
        strict = _read_file_sync(tmp_path / "doc.md", ["utf-8-sig"])
        assert strict == ""

    def test_chain_reaches_collect_files(self, tmp_path) -> None:
        """The chain passes through _collect_files_sync (the real
        ingestion path) — not just the reader in isolation."""
        from ai_assistant.core.config import SourceConfig
        from ai_assistant.features.rag.indexing import _collect_files_sync

        (tmp_path / "note.md").write_bytes("Мой любимый город".encode("cp1251"))
        source = SourceConfig(
            namespace="ns", path=str(tmp_path), include=["*.md"]
        )

        docs, _uris = _collect_files_sync(source, encodings=["cp1251"])
        assert docs and docs[0]["content"] == "Мой любимый город"
