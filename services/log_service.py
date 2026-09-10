from __future__ import annotations

from typing import Any

from utils import CogDatabase, get_timestamp


LOG_CHANNEL_FIELDS = {
    "chat": "chat_channel_id",
    "voice": "voice_channel_id",
    "channel": "channel_channel_id",
    "server": "server_channel_id",
    "member": "member_channel_id",
    "cash": "cash_channel_id",
}


class LogService:
    def __init__(self):
        self.db = CogDatabase("log_system")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "log_config",
            """
            guild_id INTEGER PRIMARY KEY,
            chat_channel_id INTEGER,
            voice_channel_id INTEGER,
            channel_channel_id INTEGER,
            server_channel_id INTEGER,
            member_channel_id INTEGER,
            cash_channel_id INTEGER,
            voice_announce_channel_id INTEGER,
            voice_join_template TEXT DEFAULT '{username} vừa vào kênh {channel_name}.',
            voice_leave_template TEXT DEFAULT '{username} đã rời kênh {channel_name}.',
            voice_announce_embed INTEGER DEFAULT 0,
            voice_room_announce INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT
            """,
        )
        self._ensure_schema()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        cols = {row["name"] for row in self.db.fetch(f"PRAGMA table_info({table})")}
        if column not in cols:
            self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _ensure_schema(self):
        self._ensure_column("log_config", "channel_channel_id", "INTEGER")
        self._ensure_column("log_config", "cash_channel_id", "INTEGER")
        self._ensure_column("log_config", "voice_announce_channel_id", "INTEGER")
        self._ensure_column("log_config", "voice_join_template", "TEXT DEFAULT '{username} vừa vào kênh {channel_name}.'")
        self._ensure_column("log_config", "voice_leave_template", "TEXT DEFAULT '{username} đã rời kênh {channel_name}.'")
        self._ensure_column("log_config", "voice_announce_embed", "INTEGER DEFAULT 0")
        self._ensure_column("log_config", "voice_room_announce", "INTEGER DEFAULT 0")
        self._ensure_column("log_config", "created_at", "TEXT")
        self._ensure_column("log_config", "updated_at", "TEXT")
        self.db.execute(
            """
            UPDATE log_config
            SET voice_join_template = '{username} vừa vào kênh {channel_name}.'
            WHERE voice_join_template IS NULL
               OR voice_join_template = ''
               OR voice_join_template = 'Dạ em chào đại ca {user} ạ'
            """
        )
        self.db.execute(
            """
            UPDATE log_config
            SET voice_leave_template = '{username} đã rời kênh {channel_name}.'
            WHERE voice_leave_template IS NULL
               OR voice_leave_template = ''
               OR voice_leave_template = '{user} vừa rời voice {channel}.'
            """
        )

    def ensure_config(self, guild_id: int) -> dict:
        config = self.get_config(guild_id)
        if config:
            return config
        now = get_timestamp()
        self.db.insert(
            "log_config",
            {
                "guild_id": guild_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        return self.get_config(guild_id) or {"guild_id": guild_id}

    def get_config(self, guild_id: int) -> dict | None:
        return self.db.select_one("log_config", "guild_id = ?", (guild_id,))

    def set_channel(self, guild_id: int, category: str, channel_id: int | None) -> bool:
        field = LOG_CHANNEL_FIELDS.get(category)
        if not field:
            raise ValueError("Loại log không hợp lệ")
        self.ensure_config(guild_id)
        return self.db.update(
            "log_config",
            {field: channel_id, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def set_all_channels(self, guild_id: int, channel_id: int | None) -> bool:
        self.ensure_config(guild_id)
        payload: dict[str, Any] = {field: channel_id for field in LOG_CHANNEL_FIELDS.values()}
        payload["updated_at"] = get_timestamp()
        return self.db.update("log_config", payload, "guild_id = ?", (guild_id,))

    def get_channel_id(self, guild_id: int, category: str) -> int | None:
        field = LOG_CHANNEL_FIELDS.get(category)
        if not field:
            return None
        config = self.get_config(guild_id)
        if not config or not config.get(field):
            return None
        return int(config[field])

    def set_voice_announce_channel(self, guild_id: int, channel_id: int | None) -> bool:
        self.ensure_config(guild_id)
        return self.db.update(
            "log_config",
            {"voice_announce_channel_id": channel_id, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def set_voice_template(self, guild_id: int, template_type: str, template: str) -> bool:
        field = {
            "join": "voice_join_template",
            "leave": "voice_leave_template",
        }.get(template_type)
        if not field:
            raise ValueError("Loại template voice không hợp lệ")
        self.ensure_config(guild_id)
        return self.db.update(
            "log_config",
            {field: template, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def set_voice_announce_embed(self, guild_id: int, enabled: bool) -> bool:
        self.ensure_config(guild_id)
        return self.db.update(
            "log_config",
            {"voice_announce_embed": 1 if enabled else 0, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def set_voice_room_announce(self, guild_id: int, enabled: bool) -> bool:
        self.ensure_config(guild_id)
        return self.db.update(
            "log_config",
            {"voice_room_announce": 1 if enabled else 0, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )
