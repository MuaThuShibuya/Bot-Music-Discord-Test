from __future__ import annotations

import math
from datetime import datetime

from utils import CogDatabase, get_timestamp


class LevelService:
    MESSAGE_XP_DEFAULT = 10
    VOICE_XP_PER_MINUTE_DEFAULT = 5
    XP_MODE_BASE = {
        "easy": 60,
        "normal": 100,
        "hard": 180,
    }

    def __init__(self):
        self.db = CogDatabase("level")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "level_settings",
            """
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            announce_channel_id INTEGER,
            message_xp INTEGER DEFAULT 10,
            voice_xp_per_minute INTEGER DEFAULT 5,
            xp_mode TEXT DEFAULT 'normal',
            xp_base INTEGER DEFAULT 100,
            announce_template TEXT,
            updated_at TEXT NOT NULL
            """,
        )
        self.db.create_table(
            "level_users",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            total_xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            total_messages INTEGER DEFAULT 0,
            total_voice_seconds INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(guild_id, user_id)
            """,
        )
        self.db.create_table(
            "level_events",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            event_type TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            xp INTEGER DEFAULT 0,
            day_key TEXT NOT NULL,
            week_key TEXT NOT NULL,
            month_key TEXT NOT NULL,
            created_at TEXT NOT NULL
            """,
        )
        self.db.create_table(
            "level_rewards",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            role_name TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(guild_id, level, role_id)
            """,
        )
        self.db.create_table(
            "level_voice_sessions",
            """
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            channel_id INTEGER,
            joined_at INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(guild_id, user_id)
            """,
        )
        self.db.create_table(
            "level_requirements",
            """
            guild_id INTEGER NOT NULL,
            level INTEGER NOT NULL,
            xp_required INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(guild_id, level)
            """,
        )
        self._ensure_schema_columns()
        self._ensure_indexes()

    def _ensure_schema_columns(self):
        rows = self.db.fetch("PRAGMA table_info(level_settings)")
        columns = {row["name"] for row in rows}
        if "xp_mode" not in columns:
            self.db.execute("ALTER TABLE level_settings ADD COLUMN xp_mode TEXT DEFAULT 'normal'")
        if "announce_template" not in columns:
            self.db.execute("ALTER TABLE level_settings ADD COLUMN announce_template TEXT")
        if "xp_base" not in columns:
            self.db.execute("ALTER TABLE level_settings ADD COLUMN xp_base INTEGER DEFAULT 100")

    def _ensure_indexes(self):
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_level_events_guild_period ON level_events(guild_id, day_key, week_key, month_key)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_level_events_user ON level_events(guild_id, user_id)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_level_users_rank ON level_users(guild_id, total_xp DESC)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_level_requirements_guild ON level_requirements(guild_id, level)")

    @staticmethod
    def now_ts() -> int:
        return int(datetime.now().timestamp())

    @staticmethod
    def period_keys(dt: datetime | None = None) -> dict:
        dt = dt or datetime.now().astimezone()
        iso_year, iso_week, _ = dt.isocalendar()
        return {
            "day_key": dt.strftime("%Y-%m-%d"),
            "week_key": f"{iso_year}-W{iso_week:02d}",
            "month_key": dt.strftime("%Y-%m"),
        }

    @staticmethod
    def xp_for_level(level: int, base: int = 100) -> int:
        level = max(0, int(level))
        base = max(1, int(base))
        return base * level * level

    @classmethod
    def level_from_xp(cls, xp: int, base: int = 100) -> int:
        return int(math.sqrt(max(0, int(xp)) / max(1, int(base))))

    @classmethod
    def normalize_xp_mode(cls, mode: str | None) -> str:
        normalized = (mode or "normal").strip().lower()
        aliases = {
            "easy": "easy",
            "it": "easy",
            "ít": "easy",
            "low": "easy",
            "normal": "normal",
            "medium": "normal",
            "vua": "normal",
            "vừa": "normal",
            "hard": "hard",
            "nhieu": "hard",
            "nhiều": "hard",
            "manual": "manual",
            "tay": "manual",
            "custom": "custom",
            "tuỳ": "custom",
            "tuy": "custom",
        }
        return aliases.get(normalized, "normal")

    @classmethod
    def xp_base_from_settings(cls, settings: dict) -> int:
        mode = cls.normalize_xp_mode(settings.get("xp_mode"))
        if mode in cls.XP_MODE_BASE:
            return cls.XP_MODE_BASE[mode]
        return max(1, int(settings.get("xp_base") or cls.XP_MODE_BASE["normal"]))

    def get_xp_for_level(self, guild_id: int, level: int) -> int:
        level = max(0, int(level))
        if level <= 0:
            return 0
        settings = self.get_settings(guild_id)
        mode = self.normalize_xp_mode(settings.get("xp_mode"))
        if mode == "manual":
            row = self.db.fetch_one(
                "SELECT xp_required FROM level_requirements WHERE guild_id = ? AND level = ?",
                (guild_id, level),
            )
            if row:
                return max(0, int(row["xp_required"] or 0))
        return self.xp_for_level(level, self.xp_base_from_settings(settings))

    def level_from_total_xp(self, guild_id: int, xp: int) -> int:
        xp = max(0, int(xp))
        settings = self.get_settings(guild_id)
        mode = self.normalize_xp_mode(settings.get("xp_mode"))
        if mode != "manual":
            return self.level_from_xp(xp, self.xp_base_from_settings(settings))

        level = 0
        while level < 10000 and xp >= self.get_xp_for_level(guild_id, level + 1):
            level += 1
        return level

    def get_xp_mode_info(self, guild_id: int) -> dict:
        settings = self.get_settings(guild_id)
        mode = self.normalize_xp_mode(settings.get("xp_mode"))
        return {
            "mode": mode,
            "base": self.xp_base_from_settings(settings),
            "message_xp": int(settings.get("message_xp") or 0),
            "voice_xp_per_minute": int(settings.get("voice_xp_per_minute") or 0),
        }

    def set_xp_mode(self, guild_id: int, mode: str, xp_base: int | None = None):
        self.get_settings(guild_id)
        normalized = self.normalize_xp_mode(mode)
        if normalized in self.XP_MODE_BASE:
            base = self.XP_MODE_BASE[normalized]
        else:
            base = max(1, int(xp_base or self.XP_MODE_BASE["normal"]))
        self.db.update(
            "level_settings",
            {"xp_mode": normalized, "xp_base": base, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )
        self.recalculate_levels(guild_id)

    def recalculate_levels(self, guild_id: int):
        rows = self.db.fetch(
            "SELECT user_id, total_xp FROM level_users WHERE guild_id = ?",
            (guild_id,),
        )
        for row in rows:
            self.db.update(
                "level_users",
                {"level": self.level_from_total_xp(guild_id, int(row["total_xp"] or 0)), "updated_at": get_timestamp()},
                "guild_id = ? AND user_id = ?",
                (guild_id, int(row["user_id"])),
            )

    def set_manual_level_xp(self, guild_id: int, level: int, xp_required: int):
        self.get_settings(guild_id)
        level = max(1, int(level))
        xp_required = max(0, int(xp_required))
        self.db.execute(
            """
            INSERT INTO level_requirements (guild_id, level, xp_required, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, level)
            DO UPDATE SET xp_required = excluded.xp_required, updated_at = excluded.updated_at
            """,
            (guild_id, level, xp_required, get_timestamp()),
        )
        self.set_xp_mode(guild_id, "manual", self.get_xp_mode_info(guild_id)["base"])

    def get_manual_requirements(self, guild_id: int, limit: int = 20) -> list[dict]:
        return self.db.fetch(
            """
            SELECT * FROM level_requirements
            WHERE guild_id = ?
            ORDER BY level ASC
            LIMIT ?
            """,
            (guild_id, max(1, min(50, int(limit)))),
        )

    def get_settings(self, guild_id: int) -> dict:
        settings = self.db.select_one("level_settings", "guild_id = ?", (guild_id,))
        if settings:
            return settings
        self.db.insert(
            "level_settings",
            {
                "guild_id": guild_id,
                "enabled": 1,
                "announce_channel_id": None,
                "message_xp": self.MESSAGE_XP_DEFAULT,
                "voice_xp_per_minute": self.VOICE_XP_PER_MINUTE_DEFAULT,
                "xp_mode": "normal",
                "xp_base": self.XP_MODE_BASE["normal"],
                "announce_template": None,
                "updated_at": get_timestamp(),
            },
        )
        return self.db.select_one("level_settings", "guild_id = ?", (guild_id,))

    def set_announce_channel(self, guild_id: int, channel_id: int | None):
        self.get_settings(guild_id)
        self.db.update(
            "level_settings",
            {"announce_channel_id": channel_id, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def set_announce_template(self, guild_id: int, template: str):
        self.get_settings(guild_id)
        self.db.update(
            "level_settings",
            {"announce_template": template, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def set_enabled(self, guild_id: int, enabled: bool):
        self.get_settings(guild_id)
        self.db.update(
            "level_settings",
            {"enabled": 1 if enabled else 0, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def set_xp_rates(
        self,
        guild_id: int,
        message_xp: int | None = None,
        voice_xp_per_minute: int | None = None,
    ):
        self.get_settings(guild_id)
        payload = {"updated_at": get_timestamp()}
        if message_xp is not None:
            payload["message_xp"] = max(0, int(message_xp))
        if voice_xp_per_minute is not None:
            payload["voice_xp_per_minute"] = max(0, int(voice_xp_per_minute))
        self.db.update("level_settings", payload, "guild_id = ?", (guild_id,))

    def get_or_create_user(self, guild_id: int, user_id: int, username: str) -> dict:
        row = self.db.select_one("level_users", "guild_id = ? AND user_id = ?", (guild_id, user_id))
        if row:
            if username and row.get("username") != username:
                self.db.update(
                    "level_users",
                    {"username": username, "updated_at": get_timestamp()},
                    "guild_id = ? AND user_id = ?",
                    (guild_id, user_id),
                )
                row = self.db.select_one("level_users", "guild_id = ? AND user_id = ?", (guild_id, user_id))
            return row
        self.db.insert(
            "level_users",
            {
                "guild_id": guild_id,
                "user_id": user_id,
                "username": username,
                "total_xp": 0,
                "level": 0,
                "total_messages": 0,
                "total_voice_seconds": 0,
                "created_at": get_timestamp(),
                "updated_at": get_timestamp(),
            },
        )
        return self.db.select_one("level_users", "guild_id = ? AND user_id = ?", (guild_id, user_id))

    def add_message_activity(self, guild_id: int, user_id: int, username: str) -> dict:
        settings = self.get_settings(guild_id)
        if not int(settings.get("enabled", 1)):
            return {"changed": False}
        return self._apply_activity(
            guild_id=guild_id,
            user_id=user_id,
            username=username,
            event_type="message",
            amount=1,
            xp=int(settings.get("message_xp") or self.MESSAGE_XP_DEFAULT),
        )

    def add_voice_activity(self, guild_id: int, user_id: int, username: str, seconds: int) -> dict:
        seconds = max(0, int(seconds))
        if seconds <= 0:
            return {"changed": False}
        settings = self.get_settings(guild_id)
        if not int(settings.get("enabled", 1)):
            return {"changed": False}
        voice_minutes = seconds // 60
        xp = int(voice_minutes * int(settings.get("voice_xp_per_minute") or self.VOICE_XP_PER_MINUTE_DEFAULT))
        return self._apply_activity(
            guild_id=guild_id,
            user_id=user_id,
            username=username,
            event_type="voice",
            amount=seconds,
            xp=xp,
        )

    def _apply_activity(self, guild_id: int, user_id: int, username: str, event_type: str, amount: int, xp: int) -> dict:
        row = self.get_or_create_user(guild_id, user_id, username)
        old_level = int(row["level"])
        new_total_xp = max(0, int(row["total_xp"]) + int(xp))
        new_level = self.level_from_total_xp(guild_id, new_total_xp)
        messages_delta = int(amount) if event_type == "message" else 0
        voice_delta = int(amount) if event_type == "voice" else 0

        self.db.execute(
            """
            UPDATE level_users
            SET username = ?,
                total_xp = ?,
                level = ?,
                total_messages = total_messages + ?,
                total_voice_seconds = total_voice_seconds + ?,
                updated_at = ?
            WHERE guild_id = ? AND user_id = ?
            """,
            (
                username,
                new_total_xp,
                new_level,
                messages_delta,
                voice_delta,
                get_timestamp(),
                guild_id,
                user_id,
            ),
        )

        keys = self.period_keys()
        self.db.insert(
            "level_events",
            {
                "guild_id": guild_id,
                "user_id": user_id,
                "username": username,
                "event_type": event_type,
                "amount": int(amount),
                "xp": int(xp),
                **keys,
                "created_at": get_timestamp(),
            },
        )
        updated = self.get_or_create_user(guild_id, user_id, username)
        return {
            "changed": True,
            "old_level": old_level,
            "new_level": new_level,
            "leveled_up": new_level > old_level,
            "stats": updated,
        }

    def get_user(self, guild_id: int, user_id: int) -> dict | None:
        return self.db.select_one("level_users", "guild_id = ? AND user_id = ?", (guild_id, user_id))

    def get_user_period_stats(self, guild_id: int, user_id: int, period: str = "total", username: str | None = None) -> dict:
        total = self.get_or_create_user(guild_id, user_id, username or str(user_id))
        if period == "total":
            return {
                "total_xp": int(total["total_xp"]),
                "level": int(total["level"]),
                "messages": int(total["total_messages"]),
                "voice_seconds": int(total["total_voice_seconds"]),
            }

        key_column, key_value = self._period_filter(period)
        row = self.db.fetch_one(
            f"""
            SELECT
                COALESCE(SUM(xp), 0) AS total_xp,
                COALESCE(SUM(CASE WHEN event_type = 'message' THEN amount ELSE 0 END), 0) AS messages,
                COALESCE(SUM(CASE WHEN event_type = 'voice' THEN amount ELSE 0 END), 0) AS voice_seconds
            FROM level_events
            WHERE guild_id = ? AND user_id = ? AND {key_column} = ?
            """,
            (guild_id, user_id, key_value),
        )
        return {
            "total_xp": int(row["total_xp"] or 0),
            "level": int(total["level"]),
            "messages": int(row["messages"] or 0),
            "voice_seconds": int(row["voice_seconds"] or 0),
        }

    def _period_filter(self, period: str) -> tuple[str, str]:
        keys = self.period_keys()
        if period == "day":
            return "day_key", keys["day_key"]
        if period == "week":
            return "week_key", keys["week_key"]
        if period == "month":
            return "month_key", keys["month_key"]
        raise ValueError("Period không hợp lệ")

    def get_leaderboard(self, guild_id: int, period: str = "total", metric: str = "xp", limit: int = 10) -> list[dict]:
        limit = max(1, min(25, int(limit)))
        if period == "total":
            metric_sql = {
                "xp": "total_xp",
                "messages": "total_messages",
                "voice": "total_voice_seconds",
                "level": "level",
            }.get(metric, "total_xp")
            return self.db.fetch(
                f"""
                SELECT user_id, username, total_xp, level, total_messages AS messages, total_voice_seconds AS voice_seconds,
                       {metric_sql} AS score
                FROM level_users
                WHERE guild_id = ?
                ORDER BY {metric_sql} DESC, total_xp DESC, username ASC
                LIMIT ?
                """,
                (guild_id, limit),
            )

        key_column, key_value = self._period_filter(period)
        score_sql = {
            "xp": "SUM(xp)",
            "messages": "SUM(CASE WHEN event_type = 'message' THEN amount ELSE 0 END)",
            "voice": "SUM(CASE WHEN event_type = 'voice' THEN amount ELSE 0 END)",
        }.get(metric, "SUM(xp)")
        return self.db.fetch(
            f"""
            SELECT user_id, MAX(username) AS username,
                   COALESCE(SUM(xp), 0) AS total_xp,
                   0 AS level,
                   COALESCE(SUM(CASE WHEN event_type = 'message' THEN amount ELSE 0 END), 0) AS messages,
                   COALESCE(SUM(CASE WHEN event_type = 'voice' THEN amount ELSE 0 END), 0) AS voice_seconds,
                   COALESCE({score_sql}, 0) AS score
            FROM level_events
            WHERE guild_id = ? AND {key_column} = ?
            GROUP BY user_id
            ORDER BY score DESC, total_xp DESC, username ASC
            LIMIT ?
            """,
            (guild_id, key_value, limit),
        )

    def get_server_count(self, guild_id: int, period: str = "total") -> dict:
        if period == "total":
            row = self.db.fetch_one(
                """
                SELECT COUNT(*) AS users,
                       COALESCE(SUM(total_xp), 0) AS total_xp,
                       COALESCE(SUM(total_messages), 0) AS messages,
                       COALESCE(SUM(total_voice_seconds), 0) AS voice_seconds
                FROM level_users
                WHERE guild_id = ?
                """,
                (guild_id,),
            )
        else:
            key_column, key_value = self._period_filter(period)
            row = self.db.fetch_one(
                f"""
                SELECT COUNT(DISTINCT user_id) AS users,
                       COALESCE(SUM(xp), 0) AS total_xp,
                       COALESCE(SUM(CASE WHEN event_type = 'message' THEN amount ELSE 0 END), 0) AS messages,
                       COALESCE(SUM(CASE WHEN event_type = 'voice' THEN amount ELSE 0 END), 0) AS voice_seconds
                FROM level_events
                WHERE guild_id = ? AND {key_column} = ?
                """,
                (guild_id, key_value),
            )
        return {
            "users": int(row["users"] or 0),
            "total_xp": int(row["total_xp"] or 0),
            "messages": int(row["messages"] or 0),
            "voice_seconds": int(row["voice_seconds"] or 0),
        }

    def get_rank(self, guild_id: int, user_id: int, metric: str = "xp") -> int | None:
        column = {
            "xp": "total_xp",
            "level": "level",
            "messages": "total_messages",
            "voice": "total_voice_seconds",
        }.get(metric, "total_xp")
        row = self.db.fetch_one(
            f"""
            SELECT rank FROM (
                SELECT user_id, ROW_NUMBER() OVER (ORDER BY {column} DESC, total_xp DESC, username ASC) AS rank
                FROM level_users
                WHERE guild_id = ?
            )
            WHERE user_id = ?
            """,
            (guild_id, user_id),
        )
        return int(row["rank"]) if row and row.get("rank") is not None else None

    def manual_update(self, guild_id: int, user_id: int, username: str, field: str, mode: str, value: int) -> dict:
        row = self.get_or_create_user(guild_id, user_id, username)
        column = {
            "xp": "total_xp",
            "messages": "total_messages",
            "voice": "total_voice_seconds",
            "level": "level",
        }[field]

        current = int(row[column])
        if mode == "add":
            new_value = current + int(value)
        elif mode == "remove":
            new_value = current - int(value)
        else:
            new_value = int(value)
        new_value = max(0, new_value)

        payload = {column: new_value, "username": username, "updated_at": get_timestamp()}
        if field == "xp":
            payload["level"] = self.level_from_total_xp(guild_id, new_value)
        elif field == "level":
            payload["total_xp"] = self.get_xp_for_level(guild_id, new_value)
        self.db.update("level_users", payload, "guild_id = ? AND user_id = ?", (guild_id, user_id))
        updated = self.get_or_create_user(guild_id, user_id, username)
        keys = self.period_keys()
        event_type = f"manual_{field}"
        event_amount = 0
        event_xp = 0
        if field == "messages":
            event_amount = new_value - current if mode != "edit" else 0
        elif field == "voice":
            event_amount = new_value - current if mode != "edit" else 0
        elif field in {"xp", "level"}:
            event_xp = int(updated["total_xp"]) - int(row["total_xp"])
        self.db.insert(
            "level_events",
            {
                "guild_id": guild_id,
                "user_id": user_id,
                "username": username,
                "event_type": event_type,
                "amount": int(event_amount),
                "xp": int(event_xp),
                **keys,
                "created_at": get_timestamp(),
            },
        )
        return updated

    def add_reward(self, guild_id: int, level: int, role_id: int, role_name: str, created_by: int):
        self.db.execute(
            """
            INSERT INTO level_rewards (guild_id, level, role_id, role_name, created_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, level, role_id)
            DO UPDATE SET role_name = excluded.role_name, created_by = excluded.created_by, created_at = excluded.created_at
            """,
            (guild_id, int(level), int(role_id), role_name, created_by, get_timestamp()),
        )

    def remove_reward(self, guild_id: int, level: int, role_id: int | None = None):
        if role_id:
            return self.db.delete("level_rewards", "guild_id = ? AND level = ? AND role_id = ?", (guild_id, int(level), int(role_id)))
        return self.db.delete("level_rewards", "guild_id = ? AND level = ?", (guild_id, int(level)))

    def get_rewards(self, guild_id: int) -> list[dict]:
        return self.db.fetch(
            "SELECT * FROM level_rewards WHERE guild_id = ? ORDER BY level ASC, role_name ASC",
            (guild_id,),
        )

    def get_rewards_between(self, guild_id: int, old_level: int, new_level: int) -> list[dict]:
        return self.db.fetch(
            """
            SELECT * FROM level_rewards
            WHERE guild_id = ? AND level > ? AND level <= ?
            ORDER BY level ASC
            """,
            (guild_id, int(old_level), int(new_level)),
        )

    def start_voice_session(self, guild_id: int, user_id: int, username: str, channel_id: int, joined_at: int | None = None):
        self.db.execute(
            """
            INSERT INTO level_voice_sessions (guild_id, user_id, username, channel_id, joined_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id)
            DO UPDATE SET username = excluded.username, channel_id = excluded.channel_id, joined_at = excluded.joined_at
            """,
            (guild_id, user_id, username, channel_id, joined_at or self.now_ts(), get_timestamp()),
        )

    def get_active_voice_sessions(self, guild_id: int | None = None) -> list[dict]:
        if guild_id is None:
            return self.db.fetch("SELECT * FROM level_voice_sessions")
        return self.db.fetch("SELECT * FROM level_voice_sessions WHERE guild_id = ?", (guild_id,))

    def end_voice_session(self, guild_id: int, user_id: int, ended_at: int | None = None) -> dict | None:
        row = self.db.select_one("level_voice_sessions", "guild_id = ? AND user_id = ?", (guild_id, user_id))
        if not row:
            return None
        self.db.delete("level_voice_sessions", "guild_id = ? AND user_id = ?", (guild_id, user_id))
        seconds = max(0, int(ended_at or self.now_ts()) - int(row["joined_at"]))
        return {**row, "seconds": seconds}

    def finish_voice_session(self, guild_id: int, user_id: int, username: str | None = None, ended_at: int | None = None) -> dict | None:
        session = self.end_voice_session(guild_id, user_id, ended_at)
        if not session:
            return None
        activity = self.add_voice_activity(
            guild_id=guild_id,
            user_id=user_id,
            username=username or session.get("username") or str(user_id),
            seconds=int(session["seconds"]),
        )
        return {**session, "activity": activity}
