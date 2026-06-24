"""SQLite storage adapter."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import StorageConfigData
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.storage import IChatStorage, ISettingsStorage

_logger = get_logger("adapters.storage_sqlite")

__all__ = ["SQLiteStorage"]


def _safe_json_loads(value: str | None, default: Any) -> Any:
    if value is None:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        _logger.warning("JSON decode failed in storage", extra={"error": str(exc)})
        return default


@register("storage", "sqlite")
class SQLiteStorage(IChatStorage, ISettingsStorage):
    """Combined chat and settings storage."""

    def __init__(self, config: StorageConfigData) -> None:
        super().__init__(config)
        self.db_path: str = config.db_path
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
        self, conversation_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = await conn.execute(
                """
                SELECT role, content, metadata, created_at
                FROM chat_messages
                WHERE conversation_id = ?
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (conversation_id, limit, offset),
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

    async def shutdown(self) -> None:
        """Flush WAL to disk and truncate WAL files for clean shutdown.

        Opens a dedicated connection to run PRAGMA wal_checkpoint(TRUNCATE),
        ensuring all WAL content is merged into the main database file and
        *.db-wal / *.db-shm are removed.  Errors are logged but not raised
        so that shutdown degradation is visible without aborting the
        lifespan cleanup sequence.
        """
        conn: aiosqlite.Connection | None = None
        try:
            conn = await aiosqlite.connect(self.db_path)
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            _logger.info("WAL checkpoint completed", extra={"db_path": self.db_path})
        except sqlite3.OperationalError as exc:
            _logger.warning(
                "WAL checkpoint failed (database may be locked by another process)",
                extra={"db_path": self.db_path, "error": str(exc)},
            )
        except Exception:
            _logger.exception("Unexpected error during WAL checkpoint", extra={"db_path": self.db_path})
        finally:
            if conn is not None:
                try:
                    await conn.close()
                except Exception:
                    _logger.exception("Failed to close SQLite connection during shutdown")
