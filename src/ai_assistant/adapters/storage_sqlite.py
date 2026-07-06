"""SQLite storage adapter."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

import aiosqlite

from ai_assistant.adapters._registry import register
from ai_assistant.core.domain.configs import StorageConfigData
from ai_assistant.core.domain.errors import AdapterError
from ai_assistant.core.logger import get_logger
from ai_assistant.core.ports.storage import IChatStorage, ISettingsStorage

_logger = get_logger("adapters.storage_sqlite")

__all__ = ["SQLiteStorage"]

# Current schema version. Increment when schema changes and add migration.
_SCHEMA_VERSION = 1

# Migration registry: version -> list of SQL statements.
# Migrations are applied sequentially from current_version + 1.
_MIGRATIONS: dict[int, list[str]] = {}


def _safe_json_loads(value: str | None, default: Any) -> Any:
    """Parse JSON with fallback to *default* on any failure.

    Returns *default* for None, empty string, or any parse error.
    """
    if not value:
        return default
    try:
        result = json.loads(value)
        # Treat JSON null as "missing" so callers always get a usable dict.
        return default if result is None else result
    except (json.JSONDecodeError, TypeError, ValueError):
        _logger.warning(
            "JSON decode failed in storage",
            extra={"error": str(value)[:200]},
        )
        return default


@register("storage", "sqlite")
class SQLiteStorage(IChatStorage, ISettingsStorage):
    """Combined chat and settings storage."""

    def __init__(self, config: StorageConfigData) -> None:
        super().__init__(config)
        self.db_path: str = config.db_path

    async def init_db(self) -> None:
        await asyncio.to_thread(
            Path(self.db_path).parent.mkdir, parents=True, exist_ok=True
        )
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("PRAGMA busy_timeout=5000")

            # Attempt WAL mode and verify it took effect.
            row = await conn.execute("PRAGMA journal_mode=WAL")
            result = await row.fetchone()
            actual_mode = result[0] if result else ""
            if actual_mode.lower() != "wal":
                _logger.warning(
                    "WAL mode not enabled",
                    extra={"db_path": self.db_path, "actual_mode": actual_mode},
                )

            # Base schema (version 0).
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

            # Schema versioning via built-in PRAGMA user_version.
            current_version = await self._get_schema_version(conn)

            if current_version < _SCHEMA_VERSION:
                _logger.info(
                    "Migrating schema",
                    extra={
                        "db_path": self.db_path,
                        "from": current_version,
                        "to": _SCHEMA_VERSION,
                    },
                )
                for version in range(current_version + 1, _SCHEMA_VERSION + 1):
                    stmts = _MIGRATIONS.get(version)
                    if stmts:
                        for stmt in stmts:
                            await conn.execute(stmt)
                        _logger.info(
                            "Applied migration",
                            extra={
                                "db_path": self.db_path,
                                "version": version,
                            },
                        )
                await self._set_schema_version(conn, _SCHEMA_VERSION)

            await conn.commit()

    async def _get_schema_version(self, conn: aiosqlite.Connection) -> int:
        """Return current PRAGMA user_version, or 0 if never initialized."""
        cur = await conn.execute("PRAGMA user_version")
        row = await cur.fetchone()
        return row[0] if row else 0

    async def _set_schema_version(
        self, conn: aiosqlite.Connection, version: int
    ) -> None:
        await conn.execute(f"PRAGMA user_version = {version}")

    async def save_message(
        self, conversation_id: str, message: dict[str, Any]
    ) -> None:
        try:
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
        except (sqlite3.Error, aiosqlite.Error) as exc:
            _logger.exception(
                "save_message failed", extra={"db_path": self.db_path}
            )
            raise AdapterError(f"save_message failed: {exc}") from exc

    async def get_history(
        self, conversation_id: str, limit: int = 50, offset: int = 0
    ) -> list[dict[str, Any]]:
        try:
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
        except (sqlite3.Error, aiosqlite.Error) as exc:
            _logger.exception(
                "get_history failed", extra={"db_path": self.db_path}
            )
            raise AdapterError(f"get_history failed: {exc}") from exc

    async def get(self, key: str, default: Any = None) -> Any:
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                cur = await conn.execute(
                    "SELECT value FROM settings WHERE key = ?",
                    (key,),
                )
                row = await cur.fetchone()
                if row:
                    return _safe_json_loads(row[0], default)
                return default
        except (sqlite3.Error, aiosqlite.Error) as exc:
            _logger.exception("get failed", extra={"db_path": self.db_path})
            raise AdapterError(f"get failed: {exc}") from exc

    async def set(self, key: str, value: Any) -> None:
        try:
            payload = json.dumps(value)
        except (TypeError, ValueError) as exc:
            _logger.exception(
                "set failed: value not JSON-serializable",
                extra={"db_path": self.db_path, "key": key},
            )
            raise AdapterError(
                f"set failed: value not JSON-serializable: {exc}"
            ) from exc

        try:
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
        except (sqlite3.Error, aiosqlite.Error) as exc:
            _logger.exception("set failed", extra={"db_path": self.db_path})
            raise AdapterError(f"set failed: {exc}") from exc

    async def shutdown(self) -> None:
        """Flush WAL to disk and truncate WAL files for clean shutdown.

        Errors are logged but not raised so that shutdown degradation is
        visible without aborting the lifespan cleanup sequence.
        """
        if not await asyncio.to_thread(Path(self.db_path).exists):
            _logger.debug(
                "shutdown skipped: database file does not exist",
                extra={"db_path": self.db_path},
            )
            return

        conn: aiosqlite.Connection | None = None
        try:
            conn = await aiosqlite.connect(self.db_path)
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            _logger.info(
                "WAL checkpoint completed", extra={"db_path": self.db_path}
            )
        except sqlite3.OperationalError as exc:
            _logger.warning(
                "WAL checkpoint failed (database may be locked)",
                extra={"db_path": self.db_path, "error": str(exc)},
            )
        except Exception:
            _logger.exception(
                "Unexpected error during WAL checkpoint",
                extra={"db_path": self.db_path},
            )
        finally:
            if conn is not None:
                try:
                    await conn.close()
                except Exception:
                    _logger.exception(
                        "Failed to close SQLite connection during shutdown"
                    )
