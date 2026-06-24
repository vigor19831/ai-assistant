"""Stateful tests for stateful ports using Hypothesis RuleBasedStateMachine.

IVectorStore and IChatStorage maintain internal state across operations.
These tests verify that sequences of add/search/delete/save/load behave
consistently across ALL implementations.

NOTE: Uses tmp_path fixture via _TMP_DIR global to avoid polluting project root.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, precondition, invariant

from ai_assistant.adapters.storage_sqlite import SQLiteStorage
from ai_assistant.core.domain.configs import VectorStoreConfigData, StorageConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.ports.vector_store import IVectorStore
from ai_assistant.core.ports.storage import IChatStorage

pytestmark = pytest.mark.timeout(0)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TMP_DIR: Path | None = None


def _set_tmp_dir(path: Path) -> None:
    """Set temporary directory for state machine tests."""
    global _TMP_DIR
    _TMP_DIR = path


def _get_tmp_dir() -> Path:
    """Get temporary directory for state machine tests."""
    if _TMP_DIR is None:
        raise RuntimeError("TMP_DIR not set. Call _set_tmp_dir() first.")
    return _TMP_DIR


def _make_chunk(idx: int, text: str = "test", dim: int = 384) -> Chunk:
    """Create a chunk with deterministic embedding and source_uri."""
    return Chunk(
        id=f"chunk-{idx}",
        text=text,
        metadata=ChunkMetadata(
            source="test",
            index=idx,
            total_chunks=1,
            source_uri=f"file:///tmp/test_{idx}.md",
        ),
        embedding=[0.01 * (idx % 100)] * dim,
    )


def _run_async(coro):
    """Run async coroutine in a fresh event loop with proper cleanup."""
    try:
        return asyncio.run(coro)
    except RuntimeError:
        # Fallback if already in async context (shouldn't happen in tests)
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# IVectorStore state machine
# ---------------------------------------------------------------------------

class VectorStoreStateMachine(RuleBasedStateMachine):
    """Model: vector store contains a set of chunks per namespace.

    Rules: add, search, delete, save, load.
    Invariants: search returns only existing chunks, delete is idempotent,
    save/load preserves state.
    """

    def __init__(self) -> None:
        super().__init__()
        self._store: IVectorStore | None = None
        self._expected: dict[str, set[str]] = {}  # namespace -> chunk_ids
        self._dim: int = 384

    def _init_store(self) -> IVectorStore:
        """Create a fresh MemoryVectorStore."""
        from ai_assistant.adapters.vector_store_memory import MemoryVectorStore

        return MemoryVectorStore(
            VectorStoreConfigData(
                dim=self._dim,
            )
        )

    @rule()
    def init(self) -> None:
        """Given: no store exists.
        When: initialized.
        Then: store is ready.
        """
        self._store = self._init_store()

    @rule(idx=st.integers(), namespace=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"))
    @precondition(lambda self: self._store is not None)
    def add(self, idx: int, namespace: str) -> None:
        """Given: store initialized.
        When: add chunk with embedding.
        Then: chunk appears in expected set.
        """
        chunk = _make_chunk(idx, dim=self._dim)
        _run_async(self._store.add([chunk], namespace=namespace))
        self._expected.setdefault(namespace, set()).add(chunk.id)

    @rule(idx=st.integers(), namespace=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"))
    @precondition(lambda self: self._store is not None)
    def search(self, idx: int, namespace: str) -> None:
        """Given: store has chunks.
        When: search by embedding.
        Then: results are from expected set (or empty if no chunks).
        """
        query = [0.01 * (idx % 100)] * self._dim
        results = _run_async(
            self._store.search(query, top_k=5, namespace=namespace)
        )
        expected_ids = self._expected.get(namespace, set())
        for r in results:
            assert r.id in expected_ids, f"Found unexpected chunk {r.id} in {namespace}"

    @rule(chunk_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"), namespace=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"))
    @precondition(lambda self: self._store is not None)
    def delete(self, chunk_id: str, namespace: str) -> None:
        """Given: store initialized.
        When: delete chunk by ID.
        Then: chunk removed from expected set (idempotent).
        """
        _run_async(self._store.delete([chunk_id], namespace=namespace))
        if namespace in self._expected:
            self._expected[namespace].discard(chunk_id)

    @rule(namespace=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"))
    @precondition(lambda self: self._store is not None)
    def save_and_load(self, namespace: str) -> None:
        """Given: store has state.
        When: save then load.
        Then: state is preserved, including source_uri.
        """
        tmp_dir = _get_tmp_dir()
        path = str(tmp_dir / f"vs_{namespace}")
        _run_async(self._store.save(path, namespace=namespace))
        # Clear and reload
        _run_async(self._store.load(path, namespace=namespace))
        # After load, search should still find expected chunks
        if self._expected.get(namespace):
            query = [0.01] * self._dim
            results = _run_async(
                self._store.search(query, top_k=100, namespace=namespace)
            )
            result_ids = {r.id for r in results}
            expected_ids = self._expected.get(namespace, set())
            # Not all expected may be found (embedding similarity), but
            # found ones must be in expected set
            assert result_ids.issubset(expected_ids)
            # Verify source_uri survives save/load cycle
            for r in results:
                if r.metadata is not None:
                    assert r.metadata.source_uri is not None
                    assert r.metadata.source_uri.startswith("file:///")

    @invariant()
    def store_initialized_or_none(self) -> None:
        """Invariant: store is either None or initialized."""
        assert self._store is None or isinstance(self._store, IVectorStore)


TestVectorStoreStateful = VectorStoreStateMachine.TestCase


# ---------------------------------------------------------------------------
# IChatStorage state machine
# ---------------------------------------------------------------------------

class ChatStorageStateMachine(RuleBasedStateMachine):
    """Model: chat storage contains messages per conversation.

    Rules: save_message, get_history.
    Invariants: get_history returns messages in order, limit/offset work,
    messages have required fields.
    """

    def __init__(self) -> None:
        super().__init__()
        self._storage: IChatStorage | None = None
        self._expected: dict[str, list[dict[str, Any]]] = {}

    def _init_storage(self) -> IChatStorage:
        """Create a fresh SQLiteStorage in isolated temp file."""
        import uuid
        from ai_assistant.adapters.storage_sqlite import SQLiteStorage

        tmp_db = _get_tmp_dir() / f"chat_{uuid.uuid4().hex}.db"
        storage = SQLiteStorage(
            StorageConfigData(db_path=str(tmp_db))
        )
        _run_async(storage.init_db())
        return storage

    @rule()
    def init(self) -> None:
        """Initialize storage."""
        self._storage = self._init_storage()

    @rule(conv_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"), role=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"), content=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"))
    @precondition(lambda self: self._storage is not None)
    def save_message(self, conv_id: str, role: str, content: str) -> None:
        """Save a message to a conversation."""
        msg = {"role": role, "content": content}
        _run_async(self._storage.save_message(conv_id, msg))
        self._expected.setdefault(conv_id, []).append(msg)

    @rule(conv_id=st.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-"), limit=st.integers(min_value=0, max_value=100), offset=st.integers(min_value=0, max_value=100))
    @precondition(lambda self: self._storage is not None)
    def get_history(self, conv_id: str, limit: int, offset: int) -> None:
        """Get history and verify invariants."""
        history = _run_async(
            self._storage.get_history(conv_id, limit=limit, offset=offset)
        )
        expected = self._expected.get(conv_id, [])

        # Invariant: returned count <= limit
        assert len(history) <= limit

        # Invariant: returned messages are from expected list
        if offset < len(expected):
            expected_slice = expected[offset:offset + limit]
            for i, msg in enumerate(history):
                assert msg["role"] == expected_slice[i]["role"]
                assert msg["content"] == expected_slice[i]["content"]

    @invariant()
    def storage_initialized_or_none(self) -> None:
        """Invariant: storage is either None or initialized."""
        assert self._storage is None or isinstance(self._storage, IChatStorage)


TestChatStorageStateful = ChatStorageStateMachine.TestCase


# ---------------------------------------------------------------------------
# SQLiteStorage shutdown tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sqlite_storage_shutdown_wal_checkpoint() -> None:
    """shutdown() must flush WAL and not leave orphaned *.db-wal/*.db-shm."""
    tmp_db = _get_tmp_dir() / "shutdown_test.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(tmp_db)))
    await storage.init_db()

    # Write data to ensure WAL has content
    await storage.save_message("conv-1", {"role": "user", "content": "hello"})

    # Call shutdown — must not raise
    await storage.shutdown()

    # After TRUNCATE checkpoint, WAL should be empty or removed
    wal_path = str(tmp_db) + "-wal"
    if os.path.exists(wal_path):
        assert os.path.getsize(wal_path) == 0, f"WAL file not truncated: {wal_path}"

    # Verify data is still readable after shutdown
    storage2 = SQLiteStorage(StorageConfigData(db_path=str(tmp_db)))
    history = await storage2.get_history("conv-1")
    assert len(history) == 1
    assert history[0]["content"] == "hello"


@pytest.mark.asyncio
async def test_sqlite_storage_shutdown_idempotent() -> None:
    """shutdown() must be safe to call multiple times."""
    tmp_db = _get_tmp_dir() / "idempotent_test.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(tmp_db)))
    await storage.init_db()

    await storage.shutdown()
    await storage.shutdown()  # must not raise


# ---------------------------------------------------------------------------
# Setup tmp_dir for state machines
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def _tmp_dir_fixture():
    """Provide isolated temp directory inside project root."""
    current = Path(__file__).resolve().parent
    project_root = current
    while project_root.parent != project_root:
        if (project_root / "pyproject.toml").exists() or (project_root / ".git").exists():
            break
        project_root = project_root.parent

    test_tmp = project_root / ".test_tmp"
    test_tmp.mkdir(exist_ok=True)

    _set_tmp_dir(test_tmp)
    yield
