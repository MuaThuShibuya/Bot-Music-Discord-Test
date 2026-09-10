from __future__ import annotations

import json
from datetime import datetime, timezone

from utils import CogDatabase, get_timestamp


class SnipeService:
    """Lưu lịch sử tin nhắn bị xoá để snipe không phụ thuộc RAM."""

    MAX_PER_CHANNEL = 500

    def __init__(self):
        self.db = CogDatabase("snipe")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "deleted_messages",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            channel_name TEXT,
            author_id INTEGER NOT NULL,
            author_name TEXT NOT NULL,
            author_avatar TEXT,
            content TEXT,
            attachments TEXT DEFAULT '[]',
            deleted_at TEXT NOT NULL,
            created_at TEXT NOT NULL
            """,
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS idx_snipe_channel_time "
            "ON deleted_messages(guild_id, channel_id, deleted_at DESC, id DESC)"
        )

    @staticmethod
    def _to_iso(value: datetime | None = None) -> str:
        dt = value or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()

    def add_deleted_message(
        self,
        *,
        guild_id: int,
        channel_id: int,
        channel_name: str,
        author_id: int,
        author_name: str,
        author_avatar: str,
        content: str,
        attachments: list[str],
        deleted_at: datetime | None = None,
    ) -> None:
        self.db.insert(
            "deleted_messages",
            {
                "guild_id": guild_id,
                "channel_id": channel_id,
                "channel_name": channel_name,
                "author_id": author_id,
                "author_name": author_name,
                "author_avatar": author_avatar,
                "content": content or "",
                "attachments": json.dumps(attachments or [], ensure_ascii=False),
                "deleted_at": self._to_iso(deleted_at),
                "created_at": get_timestamp(),
            },
        )
        self._trim_channel(guild_id, channel_id)

    def _trim_channel(self, guild_id: int, channel_id: int) -> None:
        self.db.execute(
            """
            DELETE FROM deleted_messages
            WHERE guild_id = ? AND channel_id = ?
              AND id NOT IN (
                SELECT id
                FROM deleted_messages
                WHERE guild_id = ? AND channel_id = ?
                ORDER BY deleted_at DESC, id DESC
                LIMIT ?
              )
            """,
            (guild_id, channel_id, guild_id, channel_id, self.MAX_PER_CHANNEL),
        )

    def get_recent(self, guild_id: int, channel_id: int, limit: int) -> list[dict]:
        safe_limit = max(1, min(int(limit), self.MAX_PER_CHANNEL))
        return self.db.fetch(
            """
            SELECT *
            FROM deleted_messages
            WHERE guild_id = ? AND channel_id = ?
            ORDER BY deleted_at DESC, id DESC
            LIMIT ?
            """,
            (guild_id, channel_id, safe_limit),
        )
