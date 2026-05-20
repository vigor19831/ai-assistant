"""SQLite storage adapter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from core.ports.storage import IChatStorage, ISettingsStorage
from core.registry import register


@register("storage", "sqlite")
class SQLiteStorage(IChatStorage, ISettingsStorage):
    """Combined chat and settings storage."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.db_path: str = config.db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.commit()

    async def save_message(self, conversation_id: str, message: dict[str, Any]) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
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
            conn.commit()

    async def get_history(
        self, conversation_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT role, content, metadata, created_at
                FROM chat_messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (conversation_id, limit),
            ).fetchall()
            return [
                {
                    "role": r["role"],
                    "content": r["content"],
                    "metadata": json.loads(r["metadata"]) if r["metadata"] else {},
                    "created_at": r["created_at"],
                }
                for r in reversed(rows)
            ]

    async def get(self, key: str, default: Any = None) -> Any:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            if row:
                return json.loads(row[0])
            return default

    async def set(self, key: str, value: Any) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = ?
                """,
                (key, json.dumps(value), json.dumps(value)),
            )
            conn.commit()
