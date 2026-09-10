"""
Guild Settings Service
- Lưu cài đặt riêng cho từng guild
"""

from __future__ import annotations

from utils import CogDatabase, get_timestamp


class GuildSettingsService:
    def __init__(self):
        self.db = CogDatabase("guild_settings")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "guild_settings",
            """
            guild_id INTEGER PRIMARY KEY,
            anti_raid_enabled INTEGER DEFAULT 0,
            anti_nuke_enabled INTEGER DEFAULT 0,
            commands_locked INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
            """,
        )
        self._ensure_guild_settings_columns()
        self.db.create_table(
            "guild_system_roles",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            role_key TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            role_name TEXT NOT NULL,
            updated_by INTEGER,
            updated_at TEXT NOT NULL,
            UNIQUE(guild_id, role_key)
            """,
        )

    def _ensure_guild_settings_columns(self):
        rows = self.db.fetch("PRAGMA table_info(guild_settings)")
        columns = {row["name"] for row in rows}
        if "anti_nuke_enabled" not in columns:
            self.db.execute("ALTER TABLE guild_settings ADD COLUMN anti_nuke_enabled INTEGER DEFAULT 0")
        if "commands_locked" not in columns:
            self.db.execute("ALTER TABLE guild_settings ADD COLUMN commands_locked INTEGER DEFAULT 0")

    def get_guild_settings(self, guild_id: int) -> dict:
        result = self.db.select_one("guild_settings", "guild_id = ?", (guild_id,))
        if result:
            return result
        self.db.insert(
            "guild_settings",
            {
                "guild_id": guild_id,
                "anti_raid_enabled": 0,
                "anti_nuke_enabled": 0,
                "commands_locked": 0,
                "updated_at": get_timestamp(),
            },
        )
        return self.db.select_one("guild_settings", "guild_id = ?", (guild_id,))

    def is_antiraid_enabled(self, guild_id: int) -> bool:
        settings = self.get_guild_settings(guild_id)
        return bool(settings and int(settings.get("anti_raid_enabled", 0)) == 1)

    def set_antiraid(self, guild_id: int, enabled: bool) -> bool:
        self.get_guild_settings(guild_id)
        self.db.update(
            "guild_settings",
            {
                "anti_raid_enabled": 1 if enabled else 0,
                "updated_at": get_timestamp(),
            },
            "guild_id = ?",
            (guild_id,),
        )
        return enabled

    def toggle_antiraid(self, guild_id: int) -> bool:
        enabled = not self.is_antiraid_enabled(guild_id)
        return self.set_antiraid(guild_id, enabled)

    def is_antinuke_enabled(self, guild_id: int) -> bool:
        settings = self.get_guild_settings(guild_id)
        return bool(settings and int(settings.get("anti_nuke_enabled", 0)) == 1)

    def set_antinuke(self, guild_id: int, enabled: bool) -> bool:
        self.get_guild_settings(guild_id)
        self.db.update(
            "guild_settings",
            {
                "anti_nuke_enabled": 1 if enabled else 0,
                "updated_at": get_timestamp(),
            },
            "guild_id = ?",
            (guild_id,),
        )
        return enabled

    def toggle_antinuke(self, guild_id: int) -> bool:
        enabled = not self.is_antinuke_enabled(guild_id)
        return self.set_antinuke(guild_id, enabled)

    def are_commands_locked(self, guild_id: int) -> bool:
        settings = self.get_guild_settings(guild_id)
        return bool(settings and int(settings.get("commands_locked", 0)) == 1)

    def set_commands_locked(self, guild_id: int, locked: bool) -> bool:
        self.get_guild_settings(guild_id)
        self.db.update(
            "guild_settings",
            {
                "commands_locked": 1 if locked else 0,
                "updated_at": get_timestamp(),
            },
            "guild_id = ?",
            (guild_id,),
        )
        return locked

    @staticmethod
    def normalize_role_key(role_key: str) -> str:
        cleaned = (role_key or "").strip().lower()
        if not cleaned:
            raise ValueError("Tên role hệ thống không được trống")
        return cleaned

    def set_system_role(self, guild_id: int, role_key: str, role_id: int, role_name: str, updated_by: int | None = None) -> bool:
        normalized_key = self.normalize_role_key(role_key)
        payload = {
            "role_id": role_id,
            "role_name": role_name,
            "updated_by": updated_by,
            "updated_at": get_timestamp(),
        }
        existing = self.db.select_one(
            "guild_system_roles",
            "guild_id = ? AND role_key = ?",
            (guild_id, normalized_key),
        )
        if existing:
            return self.db.update(
                "guild_system_roles",
                payload,
                "guild_id = ? AND role_key = ?",
                (guild_id, normalized_key),
            )
        return self.db.insert(
            "guild_system_roles",
            {
                "guild_id": guild_id,
                "role_key": normalized_key,
                **payload,
            },
        )

    def get_system_role(self, guild_id: int, role_key: str) -> dict | None:
        return self.db.select_one(
            "guild_system_roles",
            "guild_id = ? AND role_key = ?",
            (guild_id, self.normalize_role_key(role_key)),
        )

    def user_has_system_role(self, guild_id: int, user_role_ids: list[int], role_key: str) -> bool:
        system_role = self.get_system_role(guild_id, role_key)
        return bool(system_role and int(system_role["role_id"]) in user_role_ids)
