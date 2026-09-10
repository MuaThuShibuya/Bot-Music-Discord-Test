from __future__ import annotations

import time

from utils import CogDatabase


class AfkService:
    def __init__(self):
        self.db = CogDatabase("afk")
        self.db.create_table(
            "afk_status",
            """
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            reason TEXT NOT NULL,
            started_at INTEGER NOT NULL,
            PRIMARY KEY (guild_id, user_id)
            """,
        )
        self.db.create_table(
            "random_overrides",
            """
            user_id INTEGER PRIMARY KEY,
            result INTEGER NOT NULL,
            set_by INTEGER NOT NULL,
            created_at INTEGER NOT NULL
            """,
        )

    def set_afk(self, guild_id: int, user_id: int, reason: str) -> dict | None:
        started_at = int(time.time())
        self.db.execute(
            """
            INSERT INTO afk_status (guild_id, user_id, reason, started_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                reason = excluded.reason,
                started_at = excluded.started_at
            """,
            (int(guild_id), int(user_id), reason.strip(), started_at),
        )
        return self.get_afk(guild_id, user_id)

    def get_afk(self, guild_id: int, user_id: int) -> dict | None:
        return self.db.fetch_one(
            "SELECT * FROM afk_status WHERE guild_id = ? AND user_id = ?",
            (int(guild_id), int(user_id)),
        )

    def remove_afk(self, guild_id: int, user_id: int) -> dict | None:
        status = self.get_afk(guild_id, user_id)
        if status:
            self.db.delete(
                "afk_status",
                "guild_id = ? AND user_id = ?",
                (int(guild_id), int(user_id)),
            )
        return status

    def set_random_override(self, user_id: int, result: int, set_by: int) -> bool:
        return self.db.execute(
            """
            INSERT INTO random_overrides (user_id, result, set_by, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                result = excluded.result,
                set_by = excluded.set_by,
                created_at = excluded.created_at
            """,
            (int(user_id), int(result), int(set_by), int(time.time())),
        )

    def get_random_override(self, user_id: int) -> dict | None:
        return self.db.fetch_one(
            "SELECT * FROM random_overrides WHERE user_id = ?",
            (int(user_id),),
        )

    def remove_random_override(self, user_id: int) -> bool:
        return self.db.delete("random_overrides", "user_id = ?", (int(user_id),))

    def close(self):
        self.db.close()
