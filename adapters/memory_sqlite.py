"""SQLite-based long-term memory."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from core.ports.memory import ILongTermMemory, MemoryEntry
from core.registry import register


def _sanitize_fts(query: str) -> str:
    """Sanitize user input for SQLite FTS5 phrase queries."""
    if not query:
        return '""'
    # Remove FTS5 special characters
    cleaned = re.sub(r"[*^~/\\()\[\]{}:]", "", query)
    # Remove SQL-like operators and injection patterns
    cleaned = re.sub(r"\b(OR|AND|NOT|NEAR)\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"--.*$", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\b\d+\s*=\s*\d+\b", "", cleaned)
    # Escape internal double quotes for FTS5 phrase syntax
    cleaned = cleaned.replace('"', '""')
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return f'"{cleaned}"'


@register("memory", "sqlite")
class SQLiteMemory(ILongTermMemory):
    """Persistent memory using SQLite with FTS5 full-text search."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.db_path: str = getattr(config, "db_path", "./data/memory.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._fts5_available = False

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT DEFAULT 'conversation',
                    importance REAL DEFAULT 1.0,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_user ON memories(user_id)
            """)
            try:
                await conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                        content, content='memories', content_rowid='id'
                    )
                """)
                await conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS memories_ai
                    AFTER INSERT ON memories BEGIN
                        INSERT INTO memories_fts(rowid, content)
                        VALUES (new.id, new.content);
                    END
                """)
                await conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS memories_ad
                    AFTER DELETE ON memories BEGIN
                        INSERT INTO memories_fts(
                            memories_fts, rowid, content
                        )
                        VALUES ('delete', old.id, old.content);
                    END
                """)
                await conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS memories_au
                    AFTER UPDATE ON memories BEGIN
                        INSERT INTO memories_fts(
                            memories_fts, rowid, content
                        )
                        VALUES ('delete', old.id, old.content);
                        INSERT INTO memories_fts(rowid, content)
                        VALUES (new.id, new.content);
                    END
                """)
                cur = await conn.execute("SELECT COUNT(*) FROM memories_fts")
                row = await cur.fetchone()
                if row and row[0] == 0:
                    await conn.execute(
                        "INSERT INTO memories_fts(rowid, content) "
                        "SELECT id, content FROM memories"
                    )
                self._fts5_available = True
            except sqlite3.OperationalError:
                self._fts5_available = False
            await conn.commit()

    async def add(self, user_id: str, entry: MemoryEntry) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                """INSERT INTO memories
                   (user_id, content, source, importance, tags, metadata)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    entry.content,
                    entry.source,
                    entry.importance,
                    json.dumps(entry.tags),
                    json.dumps(entry.metadata),
                ),
            )
            rowid = cursor.lastrowid
            if self._fts5_available:
                # Fallback: some aiosqlite builds don't fire triggers reliably
                cur = await conn.execute(
                    "SELECT COUNT(*) FROM memories_fts WHERE rowid = ?",
                    (rowid,),
                )
                if (await cur.fetchone())[0] == 0:
                    await conn.execute(
                        "INSERT INTO memories_fts(rowid, content) VALUES (?, ?)",
                        (rowid, entry.content),
                    )
            await conn.commit()

    async def get(
        self, user_id: str, query: str | None = None, limit: int = 20
    ) -> list[MemoryEntry]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows: list[sqlite3.Row] = []
            if query:
                if self._fts5_available:
                    try:
                        safe_query = _sanitize_fts(query)
                        cur = await conn.execute(
                            """SELECT m.* FROM memories m
                               JOIN memories_fts f ON m.id = f.rowid
                               WHERE m.user_id = ? AND f.content MATCH ?
                               ORDER BY m.importance DESC, m.created_at DESC
                               LIMIT ?""",
                            (user_id, safe_query, limit),
                        )
                        rows = list(await cur.fetchall())
                    except sqlite3.OperationalError:
                        cur = await conn.execute(
                            """SELECT * FROM memories
                               WHERE user_id = ? AND content LIKE ?
                               ORDER BY importance DESC, created_at DESC
                               LIMIT ?""",
                            (user_id, f"%{query}%", limit),
                        )
                        rows = list(await cur.fetchall())
                else:
                    cur = await conn.execute(
                        """SELECT * FROM memories
                           WHERE user_id = ? AND content LIKE ?
                           ORDER BY importance DESC, created_at DESC
                           LIMIT ?""",
                        (user_id, f"%{query}%", limit),
                    )
                rows = list(await cur.fetchall())
            else:
                cur = await conn.execute(
                    """SELECT * FROM memories
                       WHERE user_id = ?
                       ORDER BY importance DESC, created_at DESC
                       LIMIT ?""",
                    (user_id, limit),
                )
                rows = list(await cur.fetchall())

            return [
                MemoryEntry(
                    id=str(r["id"]),
                    content=r["content"],
                    source=r["source"],
                    importance=r["importance"],
                    tags=json.loads(r["tags"]) if r["tags"] else [],
                    created_at=r["created_at"],
                    metadata=json.loads(r["metadata"]) if r["metadata"] else {},
                )
                for r in rows
            ]

    async def forget(self, user_id: str, entry_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as conn:
            cursor = await conn.execute(
                "DELETE FROM memories WHERE user_id = ? AND id = ?",
                (user_id, entry_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def consolidate(self, user_id: str) -> None:
        """Remove old low-importance memories."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """DELETE FROM memories
                   WHERE user_id = ?
                   AND importance < 0.3
                   AND created_at < datetime('now', '-30 days')""",
                (user_id,),
            )
            await conn.commit()
