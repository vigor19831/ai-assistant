"""SQLite storage adapter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from core.ports.storage import IChatStorage, ISettingsStorage
from core.registry import register


@register("storage", "sqlite")
class SQLiteStorage(IChatStorage, ISettingsStorage):
    """Combined chat and settings storage."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.db_path: str = config.db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            await conn.commit()

    async def save_message(self, conversation_id: str, message: dict[str, Any]) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO chat_messages
                (conversation_id, role, content, metadata)
                VALUES (?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    message.get("role", ""),
                    message.get("content", ""),
                    json.dumps(message.get("metadata", {})),
                ),
            )
            await conn.commit()

    async def get_history(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = await conn.execute(
                """
                SELECT role, content, metadata, created_at
                FROM chat_messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            )
            rows = await cur.fetchall()
            return [
                {
                    "role": r["role"],
                    "content": r["content"],
                    "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                    "created_at": r["created_at"],
                }
                for r in reversed(list(rows))
            ]

    async def get(self, key: str, default: Any = None) -> Any:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = await cur.fetchone()
            if row:
                return json.loads(row[0])
            return default

    async def set(self, key: str, value: Any) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?
                """,
                (key, json.dumps(value), json.dumps(value)),
            )
            await conn.commit()
