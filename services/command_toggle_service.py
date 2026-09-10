from __future__ import annotations

import re

from utils import CogDatabase, get_timestamp


def normalize_channel_command(command_name: str | None) -> str:
    value = re.sub(r"\s+", " ", str(command_name or "").strip().lower())
    return value.lstrip("/!?.-,").strip()


class ChannelCommandToggleService:
    """Lưu các command bị tắt theo từng channel của mỗi server."""

    def __init__(self):
        self.db = CogDatabase("command_toggle")
        self.db.create_table(
            "disabled_channel_commands",
            """
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            command_name TEXT NOT NULL,
            updated_by INTEGER,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, channel_id, command_name)
            """,
        )

    def disable(self, guild_id: int, channel_id: int, command_name: str, updated_by: int) -> bool:
        normalized = normalize_channel_command(command_name)
        if not normalized:
            raise ValueError("Tên lệnh không được để trống")
        self.db.execute(
            """
            INSERT OR REPLACE INTO disabled_channel_commands
                (guild_id, channel_id, command_name, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, channel_id, normalized, updated_by, get_timestamp()),
        )
        return True

    def enable(self, guild_id: int, channel_id: int, command_name: str) -> bool:
        normalized = normalize_channel_command(command_name)
        if not normalized:
            raise ValueError("Tên lệnh không được để trống")
        existing = self.db.select_one(
            "disabled_channel_commands",
            "guild_id = ? AND channel_id = ? AND command_name = ?",
            (guild_id, channel_id, normalized),
        )
        if not existing:
            return False
        return self.db.delete(
            "disabled_channel_commands",
            "guild_id = ? AND channel_id = ? AND command_name = ?",
            (guild_id, channel_id, normalized),
        )

    def find_disabled(self, guild_id: int, channel_id: int, candidates: list[str]) -> str | None:
        checked: set[str] = set()
        for candidate in candidates:
            normalized = normalize_channel_command(candidate)
            if not normalized or normalized in checked:
                continue
            checked.add(normalized)
            row = self.db.select_one(
                "disabled_channel_commands",
                "guild_id = ? AND channel_id = ? AND command_name = ?",
                (guild_id, channel_id, normalized),
            )
            if row:
                return normalized
        return None

    def list_disabled(self, guild_id: int, channel_id: int) -> list[dict]:
        return self.db.fetch(
            """
            SELECT * FROM disabled_channel_commands
            WHERE guild_id = ? AND channel_id = ?
            ORDER BY command_name ASC
            """,
            (guild_id, channel_id),
        )

    def close(self):
        self.db.close()
