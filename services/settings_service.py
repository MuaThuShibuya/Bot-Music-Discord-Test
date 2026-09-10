"""Bot settings scoped theo từng Discord server."""

from __future__ import annotations

from config import BOT_PREFIX
from services.guild_scope_utils import get_single_configured_guild_id
from utils import CogDatabase, get_timestamp


class SettingsService:
    def __init__(self):
        self.db = CogDatabase("bot_settings")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "guild_settings",
            """
            guild_id INTEGER NOT NULL,
            setting_key TEXT NOT NULL,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, setting_key)
            """,
        )
        self._migrate_legacy_prefix()

    def _migrate_legacy_prefix(self):
        guild_id = get_single_configured_guild_id()
        if guild_id is None or self.db.select_one(
            "guild_settings", "guild_id = ? AND setting_key = ?", (guild_id, "prefix")
        ):
            return
        tables = {row["name"] for row in self.db.fetch("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "settings" not in tables:
            return
        legacy = self.db.select_one("settings", "setting_key = ?", ("prefix",))
        if legacy:
            self.set_prefix(guild_id, str(legacy["setting_value"]))

    def get_setting(self, guild_id: int, key: str, default: str | None = None) -> str | None:
        result = self.db.select_one(
            "guild_settings", "guild_id = ? AND setting_key = ?", (int(guild_id), key)
        )
        if not result:
            return default
        return result["setting_value"]

    def set_setting(self, guild_id: int, key: str, value: str) -> bool:
        guild_id = int(guild_id)
        existing = self.db.select_one(
            "guild_settings", "guild_id = ? AND setting_key = ?", (guild_id, key)
        )
        payload = {
            "setting_value": value,
            "updated_at": get_timestamp(),
        }
        if existing:
            return self.db.update(
                "guild_settings", payload, "guild_id = ? AND setting_key = ?", (guild_id, key)
            )
        return self.db.insert(
            "guild_settings",
            {
                "guild_id": guild_id,
                "setting_key": key,
                "setting_value": value,
                "updated_at": get_timestamp(),
            },
        )

    def get_prefix(self, guild_id: int | None = None) -> str:
        if guild_id is None:
            return BOT_PREFIX
        return str(self.get_setting(guild_id, "prefix", BOT_PREFIX))

    def set_prefix(self, guild_id: int, prefix: str) -> bool:
        prefix = prefix.strip()
        if not prefix:
            raise ValueError("Prefix không được để trống")
        return self.set_setting(guild_id, "prefix", prefix)
