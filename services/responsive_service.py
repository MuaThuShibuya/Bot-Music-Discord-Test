"""
Responsive / auto response service.
"""

from __future__ import annotations

from utils import CogDatabase, get_timestamp


class ResponsiveService:
    def __init__(self):
        self.db = CogDatabase("responsive")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "responsive_profiles",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            profile_key TEXT NOT NULL,
            profile_number INTEGER NOT NULL,
            description TEXT DEFAULT '',
            color_value TEXT,
            image_url TEXT,
            thumbnail_url TEXT,
            assigned_user_id INTEGER,
            assigned_username TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(guild_id, profile_key, profile_number)
            """,
        )
        self.db.create_table(
            "auto_responses",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            trigger_key TEXT NOT NULL,
            response_text TEXT NOT NULL,
            target_user_id INTEGER,
            target_username TEXT,
            image_url TEXT,
            thumbnail_url TEXT,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(guild_id, trigger_key)
            """,
        )
        self.db.create_table(
            "submitted_forms",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            form_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(guild_id, user_id)
            """,
        )
        self._ensure_schema_columns()

    def _ensure_schema_columns(self):
        response_columns = {row["name"] for row in self.db.fetch("PRAGMA table_info(auto_responses)")}
        response_required_columns = {
            "image_url": "TEXT",
            "thumbnail_url": "TEXT",
        }
        for column_name, column_sql in response_required_columns.items():
            if column_name not in response_columns:
                self.db.execute(f"ALTER TABLE auto_responses ADD COLUMN {column_name} {column_sql}")

    @staticmethod
    def normalize_key(key: str) -> str:
        cleaned = (key or "").strip().lower()
        if not cleaned:
            raise ValueError("Key không được để trống")
        return cleaned

    def upsert_profile(self, guild_id: int, key: str, number: int, created_by: int, description: str = "") -> bool:
        profile_key = self.normalize_key(key)
        if number < 0:
            raise ValueError("Số profile không được âm")
        existing = self.get_profile(guild_id, profile_key, number)
        payload = {
            "description": description.strip() if description else "",
            "updated_at": get_timestamp(),
        }
        if existing:
            return self.db.update(
                "responsive_profiles",
                payload,
                "guild_id = ? AND profile_key = ? AND profile_number = ?",
                (guild_id, profile_key, number),
            )
        return self.db.insert(
            "responsive_profiles",
            {
                "guild_id": guild_id,
                "profile_key": profile_key,
                "profile_number": number,
                "description": description.strip() if description else "",
                "color_value": None,
                "image_url": None,
                "thumbnail_url": None,
                "assigned_user_id": None,
                "assigned_username": None,
                "created_by": created_by,
                "created_at": get_timestamp(),
                "updated_at": get_timestamp(),
            },
        )

    def delete_profile(self, guild_id: int, key: str, number: int) -> bool:
        return self.db.delete(
            "responsive_profiles",
            "guild_id = ? AND profile_key = ? AND profile_number = ?",
            (guild_id, self.normalize_key(key), number),
        )

    def get_profile(self, guild_id: int, key: str, number: int) -> dict | None:
        return self.db.select_one(
            "responsive_profiles",
            "guild_id = ? AND profile_key = ? AND profile_number = ?",
            (guild_id, self.normalize_key(key), number),
        )

    def get_profiles_by_key(self, guild_id: int, key: str) -> list:
        return self.db.fetch(
            """
            SELECT *
            FROM responsive_profiles
            WHERE guild_id = ? AND profile_key = ?
            ORDER BY profile_number ASC
            """,
            (guild_id, self.normalize_key(key)),
        )

    def get_assigned_profile(self, guild_id: int, user_id: int) -> dict | None:
        return self.db.select_one(
            "responsive_profiles",
            "guild_id = ? AND assigned_user_id = ?",
            (guild_id, user_id),
        )

    def update_profile_field(self, guild_id: int, key: str, number: int, field: str, value: str | None) -> bool:
        allowed_fields = {"description", "color_value", "image_url", "thumbnail_url"}
        if field not in allowed_fields:
            raise ValueError("Trường profile không hợp lệ")
        if self.get_profile(guild_id, key, number) is None:
            raise ValueError("Profile chưa tồn tại")
        return self.db.update(
            "responsive_profiles",
            {field: value, "updated_at": get_timestamp()},
            "guild_id = ? AND profile_key = ? AND profile_number = ?",
            (guild_id, self.normalize_key(key), number),
        )

    def assign_profile(self, guild_id: int, key: str, number: int, user_id: int, username: str) -> bool:
        if self.get_profile(guild_id, key, number) is None:
            raise ValueError("Profile chưa tồn tại")
        return self.db.update(
            "responsive_profiles",
            {
                "assigned_user_id": user_id,
                "assigned_username": username,
                "updated_at": get_timestamp(),
            },
            "guild_id = ? AND profile_key = ? AND profile_number = ?",
            (guild_id, self.normalize_key(key), number),
        )

    def save_submitted_form(self, guild_id: int, user_id: int, username: str, form_text: str) -> bool:
        cleaned_form = (form_text or "").strip()
        if not cleaned_form:
            raise ValueError("Form không được trống")
        timestamp = get_timestamp()
        existing = self.get_submitted_form(guild_id, user_id)
        payload = {
            "username": username,
            "form_text": cleaned_form,
            "updated_at": timestamp,
        }
        if existing:
            return self.db.update(
                "submitted_forms",
                payload,
                "guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
        return self.db.insert(
            "submitted_forms",
            {
                "guild_id": guild_id,
                "user_id": user_id,
                **payload,
                "created_at": timestamp,
            },
        )

    def get_submitted_form(self, guild_id: int, user_id: int) -> dict | None:
        return self.db.select_one(
            "submitted_forms",
            "guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )

    def upsert_response(self, guild_id: int, trigger: str, response_text: str, created_by: int) -> bool:
        trigger_key = self.normalize_key(trigger)
        response_text = response_text.strip()
        existing = self.get_response(guild_id, trigger_key)
        payload = {"response_text": response_text, "updated_at": get_timestamp()}
        if existing:
            return self.db.update("auto_responses", payload, "guild_id = ? AND trigger_key = ?", (guild_id, trigger_key))
        return self.db.insert(
            "auto_responses",
            {
                "guild_id": guild_id,
                "trigger_key": trigger_key,
                "response_text": response_text,
                "target_user_id": None,
                "target_username": None,
                "image_url": None,
                "thumbnail_url": None,
                "created_by": created_by,
                "created_at": get_timestamp(),
                "updated_at": get_timestamp(),
            },
        )

    def delete_response(self, guild_id: int, trigger: str) -> bool:
        return self.db.delete("auto_responses", "guild_id = ? AND trigger_key = ?", (guild_id, self.normalize_key(trigger)))

    def get_response(self, guild_id: int, trigger: str) -> dict | None:
        return self.db.select_one("auto_responses", "guild_id = ? AND trigger_key = ?", (guild_id, self.normalize_key(trigger)))

    def update_response_field(self, guild_id: int, trigger: str, field: str, value: str | None) -> bool:
        allowed_fields = {"image_url", "thumbnail_url"}
        if field not in allowed_fields:
            raise ValueError("Trường auto res không hợp lệ")
        if self.get_response(guild_id, trigger) is None:
            raise ValueError("Auto res chưa tồn tại")
        return self.db.update(
            "auto_responses",
            {field: value, "updated_at": get_timestamp()},
            "guild_id = ? AND trigger_key = ?",
            (guild_id, self.normalize_key(trigger)),
        )

    def list_responses(self, guild_id: int) -> list:
        return self.db.fetch("SELECT * FROM auto_responses WHERE guild_id = ? ORDER BY trigger_key ASC", (guild_id,))

    def set_response_target(self, guild_id: int, trigger: str, user_id: int, username: str) -> bool:
        if self.get_response(guild_id, trigger) is None:
            raise ValueError("Auto res chưa tồn tại")
        return self.db.update(
            "auto_responses",
            {
                "target_user_id": user_id,
                "target_username": username,
                "updated_at": get_timestamp(),
            },
            "guild_id = ? AND trigger_key = ?",
            (guild_id, self.normalize_key(trigger)),
        )
