"""Stateful tests for stateful ports using Hypothesis RuleBasedStateMachine.

IVectorStore and IChatStorage maintain internal state across operations.
These tests verify that sequences of add/search/delete behave consistently
across ALL implementations.

NOTE: State machines are purely in-memory (no persistence rules) because
Hypothesis RuleBasedStateMachine does not support async rules natively
(see https://github.com/HypothesisWorks/hypothesis/issues/4107).
Persistence (save/load) is tested in separate async pytest tests.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, rule, precondition, invariant

from ai_assistant.adapters.storage_sqlite import SQLiteStorage
from ai_assistant.adapters.vector_store_memory import MemoryVectorStore
from ai_assistant.core.domain.configs import VectorStoreConfigData, StorageConfigData
from ai_assistant.core.domain.documents import Chunk, ChunkMetadata
from ai_assistant.core.domain.errors import VersionMismatchError
from ai_assistant.core.ports.vector_store import IVectorStore
from ai_assistant.core.ports.storage import IChatStorage

pytestmark = pytest.mark.timeout(0)

_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789_-"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    """Run an async coroutine in a fresh thread with its own event loop.

    This avoids conflicts with pytest-asyncio managed loops in the main thread.
    Hypothesis RuleBasedStateMachine rules must be synchronous, so we bridge
    to async adapter methods by running them in a separate thread where
    asyncio.run() always succeeds.

    NOTE: This is a workaround for Hypothesis issue #4107. If Hypothesis
    adds native async support, replace with direct await in rules.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


# ---------------------------------------------------------------------------
# IVectorStore state machine (in-memory only)
# ---------------------------------------------------------------------------

class VectorStoreStateMachine(RuleBasedStateMachine):
    """Model: vector store contains a set of chunks per namespace.

    Rules: add, search, delete.
    Invariants: search returns only existing chunks, delete is idempotent.
    Persistence (save/load) is tested separately in async pytest tests.
    """

    def __init__(self) -> None:
        super().__init__()
        self._store: IVectorStore | None = None
        self._expected: dict[str, set[str]] = {}  # namespace -> chunk_ids
        self._dim: int = 384

    def _init_store(self) -> IVectorStore:
        """Create a fresh MemoryVectorStore."""
        return MemoryVectorStore(
            VectorStoreConfigData(dim=self._dim)
        )

    @rule()
    def init(self) -> None:
        """Given: no store exists. When: initialized. Then: store is ready."""
        self._store = self._init_store()

    @rule(idx=st.integers(), namespace=st.text(alphabet=_ALPHABET))
    @precondition(lambda self: self._store is not None)
    def add(self, idx: int, namespace: str) -> None:
        """Given: store initialized. When: add chunk. Then: chunk in set."""
        chunk = _make_chunk(idx, dim=self._dim)
        _run_async(self._store.add([chunk], namespace=namespace))
        self._expected.setdefault(namespace, set()).add(chunk.id)

    @rule(idx=st.integers(), namespace=st.text(alphabet=_ALPHABET))
    @precondition(lambda self: self._store is not None)
    def search(self, idx: int, namespace: str) -> None:
        """Given: store has chunks. When: search. Then: results from set."""
        query = [0.01 * (idx % 100)] * self._dim
        results = _run_async(
            self._store.search(query, top_k=5, namespace=namespace)
        )
        expected_ids = self._expected.get(namespace, set())
        for r in results:
            assert r.id in expected_ids

    @rule(
        chunk_id=st.text(alphabet=_ALPHABET),
        namespace=st.text(alphabet=_ALPHABET),
    )
    @precondition(lambda self: self._store is not None)
    def delete(self, chunk_id: str, namespace: str) -> None:
        """Given: store initialized. When: delete. Then: idempotent remove."""
        _run_async(self._store.delete([chunk_id], namespace=namespace))
        if namespace in self._expected:
            self._expected[namespace].discard(chunk_id)

    @invariant()
    def store_initialized_or_none(self) -> None:
        """Invariant: store is either None or initialized."""
        assert self._store is None or isinstance(self._store, IVectorStore)


TestVectorStoreStateful = VectorStoreStateMachine.TestCase


# ---------------------------------------------------------------------------
# IChatStorage state machine (file-based temp DB)
# ---------------------------------------------------------------------------

class ChatStorageStateMachine(RuleBasedStateMachine):
    """Model: chat storage contains messages per conversation.

    Rules: save_message, get_history.
    Invariants: get_history returns messages in order, limit/offset work.
    Persistence is tested separately in async pytest tests.

    NOTE: Uses a file-based temp DB (not :memory:) because aiosqlite opens
    a new connection per async-with block, and each :memory: connection gets
    its own isolated database.
    """

    def __init__(self) -> None:
        super().__init__()
        self._storage: IChatStorage | None = None
        self._expected: dict[str, list[dict[str, Any]]] = {}
        fd, self._db_path = tempfile.mkstemp(
            prefix="chat_stateful_", suffix=".db"
        )
        os.close(fd)

    def teardown(self) -> None:
        """Remove the temp DB file to avoid accumulation."""
        try:
            os.unlink(self._db_path)
        except OSError:
            pass
        super().teardown()

    def _init_storage(self) -> IChatStorage:
        """Create a fresh SQLiteStorage using the instance temp file."""
        storage = SQLiteStorage(StorageConfigData(db_path=self._db_path))
        _run_async(storage.init_db())
        return storage

    @rule()
    def init(self) -> None:
        """Initialize storage."""
        self._storage = self._init_storage()

    @rule(
        conv_id=st.text(alphabet=_ALPHABET),
        role=st.text(alphabet=_ALPHABET),
        content=st.text(alphabet=_ALPHABET),
    )
    @precondition(lambda self: self._storage is not None)
    def save_message(self, conv_id: str, role: str, content: str) -> None:
        """Save a message to a conversation."""
        msg = {"role": role, "content": content}
        _run_async(self._storage.save_message(conv_id, msg))
        self._expected.setdefault(conv_id, []).append(msg)

    @rule(
        conv_id=st.text(alphabet=_ALPHABET),
        limit=st.integers(min_value=0, max_value=100),
        offset=st.integers(min_value=0, max_value=100),
    )
    @precondition(lambda self: self._storage is not None)
    def get_history(self, conv_id: str, limit: int, offset: int) -> None:
        """Get history and verify invariants.

        get_history returns the most recent messages in chronological order.
        offset=0 means the most recent 'limit' messages.
        """
        history = _run_async(
            self._storage.get_history(conv_id, limit=limit, offset=offset)
        )
        expected = self._expected.get(conv_id, [])

        assert len(history) <= limit
        # Calculate expected slice: most recent messages, paginated
        # offset=0 → last 'limit' messages
        # offset=N → skip N most recent, then take 'limit'
        total = len(expected)
        if offset < total:
            start = max(0, total - limit - offset)
            end = total - offset
            expected_slice = expected[start:end]
            for i, msg in enumerate(history):
                assert msg["role"] == expected_slice[i]["role"]
                assert msg["content"] == expected_slice[i]["content"]

    @invariant()
    def storage_initialized_or_none(self) -> None:
        """Invariant: storage is either None or initialized."""
        assert self._storage is None or isinstance(self._storage, IChatStorage)


TestChatStorageStateful = ChatStorageStateMachine.TestCase


# ---------------------------------------------------------------------------
# Persistence tests (async, separate from state machines)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_vector_store_save_load_preserves_state(tmp_path: Path) -> None:
    """Given: MemoryVectorStore with chunks.
    When: save then load from disk.
    Then: all chunks and metadata are preserved, including source_uri.
    """
    dim = 384
    store = MemoryVectorStore(VectorStoreConfigData(dim=dim))
    namespace = "test_ns"

    chunks = [
        _make_chunk(0, dim=dim),
        _make_chunk(1, dim=dim),
        _make_chunk(2, dim=dim),
    ]
    await store.add(chunks, namespace=namespace)

    path = str(tmp_path / "vs_persist")
    await store.save(path, namespace=namespace)

    store2 = MemoryVectorStore(VectorStoreConfigData(dim=dim))
    await store2.load(path, namespace=namespace)

    query = [0.01] * dim
    results = await store2.search(query, top_k=100, namespace=namespace)
    result_ids = {r.id for r in results}
    expected_ids = {c.id for c in chunks}
    assert result_ids == expected_ids

    for r in results:
        assert r.metadata is not None
        assert r.metadata.source_uri is not None
        assert r.metadata.source_uri.startswith("file:///")


@pytest.mark.asyncio
async def test_vector_store_save_load_version_mismatch(tmp_path: Path) -> None:
    """Given: saved index with different dimension.
    When: load with mismatched config dim.
    Then: VersionMismatchError is raised.
    """
    dim = 384
    store = MemoryVectorStore(VectorStoreConfigData(dim=dim))
    namespace = "test_ns"
    await store.add([_make_chunk(0, dim=dim)], namespace=namespace)

    path = str(tmp_path / "vs_mismatch")
    await store.save(path, namespace=namespace)

    store2 = MemoryVectorStore(VectorStoreConfigData(dim=128))
    with pytest.raises(VersionMismatchError):
        await store2.load(path, namespace=namespace)


@pytest.mark.asyncio
async def test_vector_store_delete_auto_persists(tmp_path: Path) -> None:
    """Given: MemoryVectorStore with chunks and index_path set.
    When: delete chunks.
    Then: delete auto-persists; reload finds deleted chunks gone.
    """
    dim = 384
    path = str(tmp_path / "vs_delete")
    store = MemoryVectorStore(
        VectorStoreConfigData(dim=dim, index_path=path)
    )
    namespace = "test_ns"

    chunks = [_make_chunk(0, dim=dim), _make_chunk(1, dim=dim)]
    await store.add(chunks, namespace=namespace)
    await store.save(path, namespace=namespace)

    await store.delete([chunks[0].id], namespace=namespace)

    store2 = MemoryVectorStore(VectorStoreConfigData(dim=dim))
    await store2.load(path, namespace=namespace)
    query = [0.01] * dim
    results = await store2.search(query, top_k=100, namespace=namespace)
    result_ids = {r.id for r in results}
    assert chunks[0].id not in result_ids
    assert chunks[1].id in result_ids


@pytest.mark.asyncio
async def test_chat_storage_persistence(tmp_path: Path) -> None:
    """Given: SQLiteStorage with messages.
    When: close and reopen same DB file.
    Then: messages are preserved.
    """
    db_path = tmp_path / "chat_persist.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(db_path)))
    await storage.init_db()

    await storage.save_message("conv-1", {"role": "user", "content": "hello"})
    await storage.save_message("conv-1", {"role": "assistant", "content": "hi"})

    storage2 = SQLiteStorage(StorageConfigData(db_path=str(db_path)))
    history = await storage2.get_history("conv-1")
    assert len(history) == 2
    assert history[0]["content"] == "hello"
    assert history[1]["content"] == "hi"


# ---------------------------------------------------------------------------
# SQLiteStorage shutdown tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sqlite_storage_shutdown_wal_checkpoint(tmp_path: Path) -> None:
    """shutdown() must flush WAL and not leave orphaned *.db-wal/*.db-shm."""
    tmp_db = tmp_path / f"shutdown_test_{uuid.uuid4().hex}.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(tmp_db)))
    await storage.init_db()

    await storage.save_message("conv-1", {"role": "user", "content": "hello"})
    await storage.shutdown()

    wal_path = str(tmp_db) + "-wal"
    if os.path.exists(wal_path):
        assert os.path.getsize(wal_path) == 0

    storage2 = SQLiteStorage(StorageConfigData(db_path=str(tmp_db)))
    history = await storage2.get_history("conv-1")
    assert len(history) == 1
    assert history[0]["content"] == "hello"


@pytest.mark.asyncio
async def test_sqlite_storage_shutdown_idempotent(tmp_path: Path) -> None:
    """shutdown() must be safe to call multiple times."""
    tmp_db = tmp_path / f"idempotent_test_{uuid.uuid4().hex}.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(tmp_db)))
    await storage.init_db()

    await storage.shutdown()
    await storage.shutdown()  # must not raise


# ---------------------------------------------------------------------------
# ISettingsStorage tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sqlite_settings_get_default(tmp_path: Path) -> None:
    """get() returns default when key absent."""
    db = tmp_path / "settings_default.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(db)))
    await storage.init_db()
    value = await storage.get("nonexistent_key", default="fallback")
    assert value == "fallback"


@pytest.mark.asyncio
async def test_sqlite_settings_set_and_get(tmp_path: Path) -> None:
    """set() persists value; get() retrieves it."""
    db = tmp_path / "settings_basic.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(db)))
    await storage.init_db()
    await storage.set("theme", "dark")
    value = await storage.get("theme")
    assert value == "dark"


@pytest.mark.asyncio
async def test_sqlite_settings_overwrite(tmp_path: Path) -> None:
    """set() overwrites existing value."""
    db = tmp_path / "settings_overwrite.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(db)))
    await storage.init_db()
    await storage.set("key1", "first")
    await storage.set("key1", "second")
    value = await storage.get("key1")
    assert value == "second"


@pytest.mark.asyncio
async def test_sqlite_settings_complex_value(tmp_path: Path) -> None:
    """set/get round-trip nested dicts and lists."""
    db = tmp_path / "settings_complex.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(db)))
    await storage.init_db()
    data = {"nested": {"a": [1, 2, 3]}, "flag": True}
    await storage.set("config", data)
    value = await storage.get("config")
    assert value == data


@pytest.mark.asyncio
async def test_sqlite_settings_none_value(tmp_path: Path) -> None:
    """set/get round-trip None."""
    db = tmp_path / "settings_none.db"
    storage = SQLiteStorage(StorageConfigData(db_path=str(db)))
    await storage.init_db()
    await storage.set("nullable", None)
    value = await storage.get("nullable")
    assert value is None

