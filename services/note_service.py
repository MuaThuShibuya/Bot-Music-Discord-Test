"""
Note Service Layer
- Luu ghi chu ca nhan theo tung server vao database/notes.db
"""

from __future__ import annotations

from utils import CogDatabase, get_timestamp


class NoteService:
    def __init__(self):
        self.db = CogDatabase("notes")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "notes",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            content TEXT NOT NULL,
            amount INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
            """,
        )
        self.db.create_table(
            "note_settings",
            """
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            is_public INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
            """,
        )
        self._ensure_schema_columns()

    def _ensure_schema_columns(self):
        columns = {row["name"] for row in self.db.fetch("PRAGMA table_info(notes)")}
        migrations = {
            "author_user_id": "INTEGER",
            "author_name": "TEXT",
            "title": "TEXT",
            "kind": "TEXT DEFAULT 'plain'",
            "edit_count": "INTEGER DEFAULT 0",
            "last_editor_user_id": "INTEGER",
            "last_editor_name": "TEXT",
            "source_url": "TEXT",
            "source_message_id": "INTEGER",
        }
        for column_name, column_sql in migrations.items():
            if column_name not in columns:
                self.db.execute(f"ALTER TABLE notes ADD COLUMN {column_name} {column_sql}")

        self.db.execute("UPDATE notes SET author_user_id = user_id WHERE author_user_id IS NULL")
        self.db.execute("UPDATE notes SET author_name = '' WHERE author_name IS NULL")
        self.db.execute("UPDATE notes SET title = '' WHERE title IS NULL")
        self.db.execute("UPDATE notes SET kind = 'plain' WHERE kind IS NULL OR kind = ''")
        self.db.execute("UPDATE notes SET edit_count = 0 WHERE edit_count IS NULL")
        self.db.execute("UPDATE notes SET last_editor_name = '' WHERE last_editor_name IS NULL")
        self.db.execute("UPDATE notes SET source_url = '' WHERE source_url IS NULL")

    @staticmethod
    def _scope_guild_id(guild_id: int | None) -> int:
        return int(guild_id or 0)

    def add_note(
        self,
        guild_id: int | None,
        user_id: int,
        content: str,
        amount: int | None = None,
        *,
        author_user_id: int | None = None,
        author_name: str = "",
        title: str = "",
        kind: str = "plain",
        source_url: str = "",
        source_message_id: int | None = None,
    ) -> dict | None:
        now = get_timestamp()
        self.db.insert(
            "notes",
            {
                "guild_id": self._scope_guild_id(guild_id),
                "user_id": int(user_id),
                "content": content.strip(),
                "amount": int(amount) if amount is not None else None,
                "author_user_id": int(author_user_id if author_user_id is not None else user_id),
                "author_name": str(author_name or "").strip(),
                "title": str(title or "").strip(),
                "kind": kind if kind in {"plain", "txt"} else "plain",
                "edit_count": 0,
                "last_editor_user_id": None,
                "last_editor_name": "",
                "source_url": str(source_url or "").strip(),
                "source_message_id": int(source_message_id) if source_message_id is not None else None,
                "created_at": now,
                "updated_at": now,
            },
        )
        return self.db.fetch_one("SELECT * FROM notes WHERE rowid = last_insert_rowid()")

    def list_notes(self, guild_id: int | None, user_id: int) -> list[dict]:
        return self.db.fetch(
            """
            SELECT * FROM notes
            WHERE guild_id = ? AND user_id = ?
            ORDER BY id ASC
            """,
            (self._scope_guild_id(guild_id), int(user_id)),
        )

    def get_note_at(self, guild_id: int | None, user_id: int, position: int) -> dict | None:
        notes = self.list_notes(guild_id, user_id)
        if position < 1 or position > len(notes):
            return None
        note = notes[position - 1].copy()
        note["position"] = position
        return note

    def update_note_at(
        self,
        guild_id: int | None,
        user_id: int,
        position: int,
        content: str,
        amount: int | None = None,
        *,
        title: str = "",
        kind: str = "plain",
        editor_user_id: int | None = None,
        editor_name: str = "",
    ) -> dict | None:
        note = self.get_note_at(guild_id, user_id, position)
        if not note:
            return None
        self.db.update(
            "notes",
            {
                "content": content.strip(),
                "amount": int(amount) if amount is not None else None,
                "title": str(title or "").strip(),
                "kind": kind if kind in {"plain", "txt"} else "plain",
                "edit_count": int(note.get("edit_count") or 0) + 1,
                "last_editor_user_id": int(editor_user_id) if editor_user_id is not None else None,
                "last_editor_name": str(editor_name or "").strip(),
                "updated_at": get_timestamp(),
            },
            "id = ? AND guild_id = ? AND user_id = ?",
            (note["id"], self._scope_guild_id(guild_id), int(user_id)),
        )
        return self.get_note_at(guild_id, user_id, position)

    def delete_positions(self, guild_id: int | None, user_id: int, positions: list[int]) -> list[dict]:
        notes = self.list_notes(guild_id, user_id)
        deleted: list[dict] = []
        for position in sorted(set(positions), reverse=True):
            if position < 1 or position > len(notes):
                continue
            note = notes[position - 1]
            deleted.append({**note, "position": position})
            self.db.delete("notes", "id = ? AND guild_id = ? AND user_id = ?", (note["id"], self._scope_guild_id(guild_id), int(user_id)))
        return sorted(deleted, key=lambda row: row["position"])

    def adjust_amount(self, guild_id: int | None, user_id: int, position: int, delta: int) -> dict | None:
        note = self.get_note_at(guild_id, user_id, position)
        if not note:
            return None
        current_amount = int(note["amount"] or 0)
        new_amount = current_amount + int(delta)
        self.db.update(
            "notes",
            {"amount": new_amount, "updated_at": get_timestamp()},
            "id = ? AND guild_id = ? AND user_id = ?",
            (note["id"], self._scope_guild_id(guild_id), int(user_id)),
        )
        updated = self.get_note_at(guild_id, user_id, position)
        return updated

    def set_public(self, guild_id: int | None, user_id: int, is_public: bool) -> bool:
        now = get_timestamp()
        return self.db.execute(
            """
            INSERT INTO note_settings (guild_id, user_id, is_public, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                is_public = excluded.is_public,
                updated_at = excluded.updated_at
            """,
            (self._scope_guild_id(guild_id), int(user_id), 1 if is_public else 0, now),
        )

    def is_public(self, guild_id: int | None, user_id: int) -> bool:
        row = self.db.fetch_one(
            "SELECT is_public FROM note_settings WHERE guild_id = ? AND user_id = ?",
            (self._scope_guild_id(guild_id), int(user_id)),
        )
        return bool(row and int(row["is_public"] or 0))

    def get_setting(self, guild_id: int | None, user_id: int) -> dict:
        row = self.db.fetch_one(
            "SELECT * FROM note_settings WHERE guild_id = ? AND user_id = ?",
            (self._scope_guild_id(guild_id), int(user_id)),
        )
        if row:
            return row
        return {
            "guild_id": self._scope_guild_id(guild_id),
            "user_id": int(user_id),
            "is_public": 0,
            "updated_at": "",
        }

    def close(self):
        self.db.close()
