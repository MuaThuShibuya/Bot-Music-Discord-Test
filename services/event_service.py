from __future__ import annotations

from utils import CogDatabase, get_timestamp


class EventService:
    """Service layer for event contest management."""

    def __init__(self):
        self.db = CogDatabase("event_system")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "events",
            """
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            channel_id INTEGER,
            status TEXT DEFAULT 'draft',
            reaction_emoji TEXT DEFAULT '❤️',
            filter_mode TEXT DEFAULT 'image',
            anti_cheat_mode INTEGER DEFAULT 0,
            created_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
            """,
        )
        self.db.create_table(
            "event_entries",
            """
            entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            is_valid INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            FOREIGN KEY (event_id) REFERENCES events(event_id) ON DELETE CASCADE
            """,
        )
        self.db.create_table(
            "event_theme",
            """
            guild_id INTEGER NOT NULL,
            theme_key TEXT NOT NULL,
            theme_value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, theme_key)
            """,
        )
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_events_guild_status ON events(guild_id, status)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_event_entries_event ON event_entries(event_id)")

    def create_event(self, guild_id: int, name: str, created_by: int) -> dict:
        """Creates a new event in draft status."""
        now = get_timestamp()
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO events (guild_id, name, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, name.strip(), created_by, now, now),
        )
        self.db.conn.commit()
        return self.get_event(cursor.lastrowid)

    def get_event(self, event_id: int) -> dict | None:
        """Gets a single event by its ID."""
        return self.db.select_one("events", "event_id = ?", (event_id,))

    def list_events(self, guild_id: int, status: str | None = None) -> list[dict]:
        """Lists events in a guild, optionally filtered by status."""
        if status:
            return self.db.fetch(
                "SELECT * FROM events WHERE guild_id = ? AND status = ? ORDER BY created_at DESC",
                (guild_id, status),
            )
        return self.db.fetch(
            "SELECT * FROM events WHERE guild_id = ? ORDER BY created_at DESC",
            (guild_id,),
        )

    def get_active_event_in_channel(self, guild_id: int, channel_id: int) -> dict | None:
        """Finds the active event for a specific channel."""
        return self.db.select_one(
            "events",
            "guild_id = ? AND channel_id = ? AND status = 'active'",
            (guild_id, channel_id),
        )

    def update_event(self, event_id: int, **kwargs) -> bool:
        """Updates an event's configuration."""
        allowed_keys = {"name", "channel_id", "status", "reaction_emoji", "filter_mode", "anti_cheat_mode"}
        payload = {key: value for key, value in kwargs.items() if key in allowed_keys}
        if not payload:
            return False
        payload["updated_at"] = get_timestamp()
        return self.db.update("events", payload, "event_id = ?", (event_id,))

    def delete_event(self, event_id: int) -> bool:
        """Deletes an event and all its entries."""
        self.db.delete("event_entries", "event_id = ?", (event_id,))
        return self.db.delete("events", "event_id = ?", (event_id,))

    def add_entry(
        self,
        event_id: int,
        guild_id: int,
        channel_id: int,
        user_id: int,
        message_id: int,
    ) -> dict | None:
        """Adds a new entry for an event."""
        now = get_timestamp()
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO event_entries (event_id, guild_id, channel_id, user_id, message_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (event_id, guild_id, channel_id, user_id, message_id, now),
        )
        self.db.conn.commit()
        return self.db.fetch_one("SELECT * FROM event_entries WHERE entry_id = ?", (cursor.lastrowid,))

    def get_entries(self, event_id: int) -> list[dict]:
        """Gets all entries for a specific event."""
        return self.db.fetch(
            "SELECT * FROM event_entries WHERE event_id = ? AND is_valid = 1 ORDER BY created_at ASC",
            (event_id,),
        )

    def invalidate_entry(self, entry_id: int) -> bool:
        """Marks an entry as invalid (e.g., message deleted)."""
        return self.db.update("event_entries", {"is_valid": 0}, "entry_id = ?", (entry_id,))

    def remove_entry_by_message(self, message_id: int) -> bool:
        """Removes an entry by its message ID."""
        return self.db.delete("event_entries", "message_id = ?", (message_id,))

    def get_theme(self, guild_id: int) -> dict[str, str]:
        rows = self.db.fetch(
            "SELECT theme_key, theme_value FROM event_theme WHERE guild_id = ?",
            (int(guild_id),),
        )
        return {str(row["theme_key"]): str(row["theme_value"]) for row in rows}

    def set_theme_value(self, guild_id: int, key: str, value: str):
        existing = self.db.select_one(
            "event_theme",
            "guild_id = ? AND theme_key = ?",
            (int(guild_id), str(key)),
        )
        data = {"theme_value": str(value), "updated_at": get_timestamp()}
        if existing:
            self.db.update("event_theme", data, "guild_id = ? AND theme_key = ?", (int(guild_id), str(key)))
        else:
            self.db.insert("event_theme", {"guild_id": int(guild_id), "theme_key": str(key), **data})

    def reset_theme_value(self, guild_id: int, key: str):
        self.db.delete(
            "event_theme",
            "guild_id = ? AND theme_key = ?",
            (int(guild_id), str(key)),
        )