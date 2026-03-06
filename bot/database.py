"""Async SQLite persistence layer."""

from __future__ import annotations

import time
from typing import Any

import aiosqlite


def utc_ts() -> int:
    return int(time.time())


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.execute("PRAGMA synchronous=NORMAL;")
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        return self._conn

    async def init_schema(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_bot INTEGER DEFAULT 0,
                preferred_expiry INTEGER,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS files (
                file_id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                telegram_file_id TEXT NOT NULL,
                telegram_unique_id TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                mime_type TEXT,
                file_size INTEGER NOT NULL,
                local_path TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(owner_id) REFERENCES users(user_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS links (
                link_id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                file_id INTEGER NOT NULL,
                link_type TEXT NOT NULL,
                expires_at INTEGER NOT NULL,
                hit_count INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL,
                FOREIGN KEY(file_id) REFERENCES files(file_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_files_owner_id ON files(owner_id);
            CREATE INDEX IF NOT EXISTS idx_links_file_id ON links(file_id);
            CREATE INDEX IF NOT EXISTS idx_links_expires_at ON links(expires_at);
            """
        )
        await self.conn.commit()

    async def upsert_user(
        self,
        user_id: int,
        username: str | None,
        first_name: str | None,
        is_bot: bool = False,
    ) -> None:
        now = utc_ts()
        await self.conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, is_bot, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id)
            DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                is_bot = excluded.is_bot,
                updated_at = excluded.updated_at
            """,
            (user_id, username, first_name, int(is_bot), now, now),
        )
        await self.conn.commit()

    async def set_user_expiry(self, user_id: int, expiry_seconds: int | None) -> None:
        await self.conn.execute(
            "UPDATE users SET preferred_expiry = ?, updated_at = ? WHERE user_id = ?",
            (expiry_seconds, utc_ts(), user_id),
        )
        await self.conn.commit()

    async def get_user_expiry(self, user_id: int) -> int | None:
        cursor = await self.conn.execute(
            "SELECT preferred_expiry FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if not row:
            return None
        return row["preferred_expiry"]

    async def get_file_by_unique_id(self, unique_id: str) -> dict[str, Any] | None:
        cursor = await self.conn.execute(
            "SELECT * FROM files WHERE telegram_unique_id = ?",
            (unique_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return dict(row) if row else None

    async def get_file(self, file_id: int) -> dict[str, Any] | None:
        cursor = await self.conn.execute(
            "SELECT * FROM files WHERE file_id = ?",
            (file_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        return dict(row) if row else None

    async def add_file(
        self,
        owner_id: int,
        telegram_file_id: str,
        telegram_unique_id: str,
        file_name: str,
        mime_type: str | None,
        file_size: int,
        local_path: str,
    ) -> int:
        cursor = await self.conn.execute(
            """
            INSERT INTO files (
                owner_id, telegram_file_id, telegram_unique_id, file_name, mime_type, file_size, local_path, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                telegram_file_id,
                telegram_unique_id,
                file_name,
                mime_type,
                file_size,
                local_path,
                utc_ts(),
            ),
        )
        await self.conn.commit()
        return int(cursor.lastrowid)

    async def update_file_path(self, file_id: int, local_path: str) -> None:
        await self.conn.execute(
            "UPDATE files SET local_path = ? WHERE file_id = ?",
            (local_path, file_id),
        )
        await self.conn.commit()

    async def add_link(self, token: str, file_id: int, link_type: str, expires_at: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO links (token, file_id, link_type, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (token, file_id, link_type, expires_at, utc_ts()),
        )
        await self.conn.commit()

    async def touch_link(self, token: str) -> None:
        await self.conn.execute(
            "UPDATE links SET hit_count = hit_count + 1 WHERE token = ?",
            (token,),
        )
        await self.conn.commit()

    async def get_stats(self) -> dict[str, int]:
        stats: dict[str, int] = {}

        cursor = await self.conn.execute("SELECT COUNT(*) AS c FROM users")
        stats["users"] = int((await cursor.fetchone())["c"])
        await cursor.close()

        cursor = await self.conn.execute("SELECT COUNT(*) AS c FROM files")
        stats["files"] = int((await cursor.fetchone())["c"])
        await cursor.close()

        cursor = await self.conn.execute("SELECT COUNT(*) AS c FROM links")
        stats["links"] = int((await cursor.fetchone())["c"])
        await cursor.close()

        cursor = await self.conn.execute("SELECT COALESCE(SUM(file_size), 0) AS c FROM files")
        stats["total_size_bytes"] = int((await cursor.fetchone())["c"])
        await cursor.close()

        return stats

    async def list_users(self, limit: int = 100) -> list[dict[str, Any]]:
        cursor = await self.conn.execute(
            """
            SELECT user_id, username, first_name, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [dict(row) for row in rows]

    async def all_user_ids(self) -> list[int]:
        cursor = await self.conn.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        await cursor.close()
        return [int(row["user_id"]) for row in rows]
