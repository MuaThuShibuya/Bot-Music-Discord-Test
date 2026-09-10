"""
Giveaway Service Layer
- Luu giveaway va nguoi tham gia vao database/giveaway.db
"""

from __future__ import annotations

import json
import time

from utils import CogDatabase, get_timestamp
from ui.administrator.giveaway_emoji import GIVEAWAY_DEFAULT_ENTRY_EMOJI


class GiveawayService:
    def __init__(self):
        self.db = CogDatabase("giveaway")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "giveaways",
            f"""
            giveaway_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL,
            reward TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            winners_count INTEGER NOT NULL,
            quantity_total INTEGER DEFAULT 1,
            quantity_index INTEGER DEFAULT 1,
            template TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            ends_at INTEGER NOT NULL,
            ended_at INTEGER,
            winner_ids TEXT DEFAULT '[]',
            selected_winner_ids TEXT DEFAULT '[]',
            entry_emoji TEXT DEFAULT '{GIVEAWAY_DEFAULT_ENTRY_EMOJI}',
            reroll_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
            """,
        )
        self.db.create_table(
            "giveaway_settings",
            f"""
            guild_id INTEGER PRIMARY KEY,
            entry_emoji TEXT DEFAULT '{GIVEAWAY_DEFAULT_ENTRY_EMOJI}',
            updated_at TEXT NOT NULL
            """,
        )
        self.db.create_table(
            "giveaway_theme",
            """
            guild_id INTEGER NOT NULL,
            theme_key TEXT NOT NULL,
            theme_value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, theme_key)
            """,
        )
        self.db.create_table(
            "giveaway_participants",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            giveaway_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            joined_at TEXT NOT NULL,
            UNIQUE(giveaway_id, user_id)
            """,
        )
        self._ensure_schema_columns()

    def _ensure_schema_columns(self):
        columns = {row["name"] for row in self.db.fetch("PRAGMA table_info(giveaways)")}
        required_columns = {
            "quantity_total": "INTEGER DEFAULT 1",
            "quantity_index": "INTEGER DEFAULT 1",
            "template": "TEXT DEFAULT ''",
            "selected_winner_ids": "TEXT DEFAULT '[]'",
            "entry_emoji": f"TEXT DEFAULT '{GIVEAWAY_DEFAULT_ENTRY_EMOJI}'",
            "reroll_count": "INTEGER DEFAULT 0",
        }
        for column_name, column_sql in required_columns.items():
            if column_name not in columns:
                self.db.execute(f"ALTER TABLE giveaways ADD COLUMN {column_name} {column_sql}")

    def create_giveaway(
        self,
        giveaway_id: int,
        guild_id: int,
        channel_id: int,
        message_id: int,
        creator_id: int,
        reward: str,
        duration_seconds: int,
        winners_count: int,
        ends_at: int,
        quantity_total: int = 1,
        quantity_index: int = 1,
        template: str = "",
        entry_emoji: str = GIVEAWAY_DEFAULT_ENTRY_EMOJI,
    ):
        self.db.insert(
            "giveaways",
            {
                "giveaway_id": giveaway_id,
                "guild_id": guild_id,
                "channel_id": channel_id,
                "message_id": message_id,
                "creator_id": creator_id,
                "reward": reward,
                "duration_seconds": int(duration_seconds),
                "winners_count": int(winners_count),
                "quantity_total": int(quantity_total),
                "quantity_index": int(quantity_index),
                "template": template or "",
                "status": "active",
                "ends_at": int(ends_at),
                "ended_at": None,
                "winner_ids": "[]",
                "selected_winner_ids": "[]",
                "entry_emoji": entry_emoji or GIVEAWAY_DEFAULT_ENTRY_EMOJI,
                "reroll_count": 0,
                "created_at": get_timestamp(),
                "updated_at": get_timestamp(),
            },
        )

    def get_giveaway(self, giveaway_id: int) -> dict | None:
        return self.db.select_one("giveaways", "giveaway_id = ?", (giveaway_id,))

    def get_giveaway_by_message_id(self, message_id: int) -> dict | None:
        return self.db.select_one("giveaways", "message_id = ?", (message_id,))

    def get_active_giveaways(self) -> list[dict]:
        return self.db.fetch(
            """
            SELECT *
            FROM giveaways
            WHERE status = 'active'
            ORDER BY ends_at ASC
            """
        )

    def add_participant(self, giveaway_id: int, user_id: int, username: str) -> tuple[bool, str]:
        giveaway = self.get_giveaway(giveaway_id)
        if not giveaway:
            return False, "Giveaway không tồn tại."
        if giveaway["status"] != "active":
            return False, "Giveaway đã kết thúc."

        return self.sync_participant(giveaway_id, user_id, username)

    def sync_participant(self, giveaway_id: int, user_id: int, username: str) -> tuple[bool, str]:
        """Dong bo nguoi tham gia tu reaction, khong phu thuoc dong ho VPS."""

        existing = self.db.select_one(
            "giveaway_participants",
            "giveaway_id = ? AND user_id = ?",
            (giveaway_id, user_id),
        )
        if existing:
            if str(existing.get("username") or "") != str(username):
                self.db.update(
                    "giveaway_participants",
                    {"username": str(username)},
                    "giveaway_id = ? AND user_id = ?",
                    (giveaway_id, user_id),
                )
            return False, "Bạn đã tham gia giveaway này rồi."

        self.db.insert(
            "giveaway_participants",
            {
                "giveaway_id": giveaway_id,
                "user_id": user_id,
                "username": username,
                "joined_at": get_timestamp(),
            },
        )
        return True, "Đã tham gia giveaway."

    def get_participants(self, giveaway_id: int) -> list[dict]:
        return self.db.fetch(
            """
            SELECT *
            FROM giveaway_participants
            WHERE giveaway_id = ?
            ORDER BY joined_at ASC
            """,
            (giveaway_id,),
        )

    def remove_participant(self, giveaway_id: int, user_id: int) -> bool:
        return self.db.delete(
            "giveaway_participants",
            "giveaway_id = ? AND user_id = ?",
            (giveaway_id, user_id),
        )

    def participant_count(self, giveaway_id: int) -> int:
        row = self.db.fetch_one(
            "SELECT COUNT(*) AS total FROM giveaway_participants WHERE giveaway_id = ?",
            (giveaway_id,),
        )
        return int(row["total"]) if row else 0

    def mark_ended(self, giveaway_id: int, winner_ids: list[int]):
        self.db.update(
            "giveaways",
            {
                "status": "ended",
                "ended_at": int(time.time()),
                "winner_ids": json.dumps([int(user_id) for user_id in winner_ids]),
                "updated_at": get_timestamp(),
            },
            "giveaway_id = ?",
            (giveaway_id,),
        )

    def claim_ending(self, giveaway_id: int) -> bool:
        """Atomically reserve an active giveaway for final payout."""
        try:
            self.db._ensure_connection()
            cursor = self.db.conn.cursor()
            cursor.execute(
                """
                UPDATE giveaways
                SET status = 'ending',
                    updated_at = ?
                WHERE giveaway_id = ?
                  AND status = 'active'
                """,
                (get_timestamp(), int(giveaway_id)),
            )
            self.db.conn.commit()
            return cursor.rowcount == 1
        except Exception as exc:
            print(f"❌ Lỗi claim ending giveaway {giveaway_id}: {exc}")
            return False

    def update_ends_at(self, giveaway_id: int, ends_at: int):
        self.db.update(
            "giveaways",
            {
                "ends_at": int(ends_at),
                "updated_at": get_timestamp(),
            },
            "giveaway_id = ?",
            (int(giveaway_id),),
        )

    def update_winners(self, giveaway_id: int, winner_ids: list[int], reroll_count: int | None = None):
        values = {
            "winner_ids": json.dumps([int(user_id) for user_id in winner_ids]),
            "updated_at": get_timestamp(),
        }
        if reroll_count is not None:
            values["reroll_count"] = int(reroll_count)
        self.db.update(
            "giveaways",
            values,
            "giveaway_id = ?",
            (giveaway_id,),
        )

    def set_selected_winners(self, giveaway_id: int, winner_ids: list[int]):
        self.db.update(
            "giveaways",
            {
                "selected_winner_ids": json.dumps([int(user_id) for user_id in winner_ids]),
                "updated_at": get_timestamp(),
            },
            "giveaway_id = ?",
            (giveaway_id,),
        )

    def clear_selected_winners(self, giveaway_id: int):
        self.set_selected_winners(giveaway_id, [])

    @staticmethod
    def decode_winner_ids(giveaway: dict | None) -> list[int]:
        if not giveaway:
            return []
        try:
            return [int(user_id) for user_id in json.loads(giveaway.get("winner_ids") or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    @staticmethod
    def decode_selected_winner_ids(giveaway: dict | None) -> list[int]:
        if not giveaway:
            return []
        try:
            return [int(user_id) for user_id in json.loads(giveaway.get("selected_winner_ids") or "[]")]
        except (TypeError, ValueError, json.JSONDecodeError):
            return []

    def get_settings(self, guild_id: int) -> dict:
        row = self.db.select_one("giveaway_settings", "guild_id = ?", (guild_id,))
        if row:
            return row
        self.db.insert(
            "giveaway_settings",
            {
                "guild_id": int(guild_id),
                "entry_emoji": GIVEAWAY_DEFAULT_ENTRY_EMOJI,
                "updated_at": get_timestamp(),
            },
        )
        return self.db.select_one("giveaway_settings", "guild_id = ?", (guild_id,))

    def get_entry_emoji(self, guild_id: int) -> str:
        settings = self.get_settings(guild_id)
        return str(settings.get("entry_emoji") or GIVEAWAY_DEFAULT_ENTRY_EMOJI)

    def set_entry_emoji(self, guild_id: int, emoji: str):
        self.get_settings(guild_id)
        self.db.update(
            "giveaway_settings",
            {"entry_emoji": str(emoji), "updated_at": get_timestamp()},
            "guild_id = ?",
            (int(guild_id),),
        )

    def get_theme(self, guild_id: int) -> dict[str, str]:
        rows = self.db.fetch(
            """
            SELECT theme_key, theme_value
            FROM giveaway_theme
            WHERE guild_id = ?
            """,
            (int(guild_id),),
        )
        return {str(row["theme_key"]): str(row["theme_value"]) for row in rows}

    def set_theme_value(self, guild_id: int, theme_key: str, theme_value: str):
        guild_id = int(guild_id)
        theme_key = str(theme_key)
        existing = self.db.select_one(
            "giveaway_theme",
            "guild_id = ? AND theme_key = ?",
            (guild_id, theme_key),
        )
        data = {
            "theme_value": str(theme_value),
            "updated_at": get_timestamp(),
        }
        if existing:
            self.db.update(
                "giveaway_theme",
                data,
                "guild_id = ? AND theme_key = ?",
                (guild_id, theme_key),
            )
            return
        self.db.insert(
            "giveaway_theme",
            {
                "guild_id": guild_id,
                "theme_key": theme_key,
                **data,
            },
        )

    def reset_theme_value(self, guild_id: int, theme_key: str):
        self.db.delete(
            "giveaway_theme",
            "guild_id = ? AND theme_key = ?",
            (int(guild_id), str(theme_key)),
        )
