from __future__ import annotations

from utils import CogDatabase, get_timestamp


DEFAULT_PLAYER_THEME = {
    "accent_color": "#7f314d",
    "background_url": "",
    "title_text": "BLACK LOUS MUSIC",
    "card_requester": "Yêu cầu bởi: {requester}",
    "card_status_playing": "ĐANG PHÁT",
    "card_status_paused": "TẠM DỪNG",
    "card_duration": "THỜI LƯỢNG",
    "card_volume": "Âm lượng {volume}%",
    "card_loop": "Loop {status}",
    "card_autoplay": "Đề xuất YouTube {status}",
    "card_queue": "Queue {count}",
    "message_queue_added_title": "Đã thêm vào queue",
    "message_queue_added_body": "`{title}`\nVị trí: `{position}` • Số bài: `{count}` • Yêu cầu bởi: {requester}",
    "button_pause": "Pause / Resume",
    "button_stop": "Stop",
    "button_skip": "Skip",
    "button_loop": "Loop",
    "button_autoplay": "Đề xuất YouTube",
    "button_shuffle": "Shuffle",
    "button_queue": "Queue",
    "button_volume": "Âm lượng",
    "button_settings": "Settings",
    "button_leave": "Rời voice",
    "icon_pause": "⏯️",
    "icon_stop": "⏹️",
    "icon_skip": "⏭️",
    "icon_loop": "🔁",
    "icon_autoplay": "♾️",
    "icon_shuffle": "🔀",
    "icon_queue": "📋",
    "icon_volume": "🔊",
    "icon_settings": "⚙️",
    "icon_leave": "🚪",
    "icon_queue_added": "🎶",
    "reaction_success": "✅",
    "reaction_error": "❌",
}

DEFAULT_USER_PREFERENCES = {
    "volume": 65,
}


class MusicPlayerService:
    def __init__(self):
        self.db = CogDatabase("music_player")
        self.db.create_table(
            "player_theme",
            """
            guild_id INTEGER PRIMARY KEY,
            accent_color TEXT NOT NULL DEFAULT '#7f314d',
            background_url TEXT DEFAULT '',
            title_text TEXT NOT NULL DEFAULT 'BLACK LOUS MUSIC',
            updated_at TEXT
            """,
        )
        self._ensure_theme_columns()
        self.db.create_table(
            "user_preferences",
            """
            user_id INTEGER PRIMARY KEY,
            volume INTEGER NOT NULL DEFAULT 65,
            updated_at TEXT
            """,
        )

    def _ensure_theme_columns(self):
        columns = {row["name"] for row in self.db.fetch("PRAGMA table_info(player_theme)")}
        for key, default in DEFAULT_PLAYER_THEME.items():
            if key in columns or key in {"accent_color", "background_url", "title_text"}:
                continue
            escaped = str(default).replace("'", "''")
            self.db.execute(
                f"ALTER TABLE player_theme ADD COLUMN {key} TEXT DEFAULT '{escaped}'"
            )

    def get_theme(self, guild_id: int) -> dict:
        saved = self.db.select_one("player_theme", "guild_id = ?", (int(guild_id),)) or {}
        return {**DEFAULT_PLAYER_THEME, **saved}

    def set_theme(self, guild_id: int, **values) -> dict:
        guild_id = int(guild_id)
        allowed = {key: str(value) for key, value in values.items() if key in DEFAULT_PLAYER_THEME}
        if not allowed:
            return self.get_theme(guild_id)
        allowed["updated_at"] = get_timestamp()
        if self.db.select_one("player_theme", "guild_id = ?", (guild_id,)):
            self.db.update("player_theme", allowed, "guild_id = ?", (guild_id,))
        else:
            self.db.insert("player_theme", {"guild_id": guild_id, **DEFAULT_PLAYER_THEME, **allowed})
        return self.get_theme(guild_id)

    def reset_theme(self, guild_id: int) -> dict:
        self.db.delete("player_theme", "guild_id = ?", (int(guild_id),))
        return self.get_theme(guild_id)

    def reset_theme_value(self, guild_id: int, key: str) -> str:
        if key not in DEFAULT_PLAYER_THEME:
            return ""
        self.set_theme(guild_id, **{key: DEFAULT_PLAYER_THEME[key]})
        return DEFAULT_PLAYER_THEME[key]

    def get_user_preferences(self, user_id: int) -> dict:
        saved = self.db.select_one(
            "user_preferences",
            "user_id = ?",
            (int(user_id),),
        ) or {}
        preferences = {**DEFAULT_USER_PREFERENCES, **saved}
        preferences["volume"] = max(0, min(200, int(preferences["volume"])))
        return preferences

    def set_user_preferences(self, user_id: int, **values) -> dict:
        user_id = int(user_id)
        allowed = {}
        if "volume" in values:
            allowed["volume"] = max(0, min(200, int(values["volume"])))
        if not allowed:
            return self.get_user_preferences(user_id)

        allowed["updated_at"] = get_timestamp()
        if self.db.select_one("user_preferences", "user_id = ?", (user_id,)):
            self.db.update("user_preferences", allowed, "user_id = ?", (user_id,))
        else:
            self.db.insert(
                "user_preferences",
                {
                    "user_id": user_id,
                    **DEFAULT_USER_PREFERENCES,
                    **allowed,
                },
            )
        return self.get_user_preferences(user_id)
