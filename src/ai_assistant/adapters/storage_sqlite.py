"""SQLite storage adapter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from ai_assistant.core.ports.storage import IChatStorage, ISettingsStorage
from ai_assistant.core.registry import register

__all__ = ["SQLiteStorage"]


def _safe_json_loads(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


@register("storage", "sqlite")
class SQLiteStorage(IChatStorage, ISettingsStorage):
    """Combined chat and settings storage."""

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        self.db_path: str = getattr(config, "db_path", "./data/storage.db")
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    async def init_db(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_conv
                ON chat_messages(conversation_id)
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
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
            rows = list(await cur.fetchall())
            return [
                {
                    "role": r["role"],
                    "content": r["content"],
                    "metadata": _safe_json_loads(r["metadata"], {}),
                    "created_at": r["created_at"],
                }
                for r in reversed(rows)
            ]

    async def get(self, key: str, default: Any = None) -> Any:
        async with aiosqlite.connect(self.db_path) as conn:
            cur = await conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            )
            row = await cur.fetchone()
            if row:
                return _safe_json_loads(row[0], default)
            return default

    async def set(self, key: str, value: Any) -> None:
        payload = json.dumps(value)
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?
                """,
                (key, payload, payload),
            )
            await conn.commit()
