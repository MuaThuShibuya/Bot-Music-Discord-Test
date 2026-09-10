"""
Bot Admin Service
- Quản lý admin mặc định từ env
- Quản lý admin mềm theo từng server
- Quản lý quyền cash riêng theo từng server
"""

from __future__ import annotations

from typing import List, Dict

from config import DISCORD_OWNER_IDS
from utils import CogDatabase, get_timestamp


class AdminService:
    def __init__(self):
        self.db = CogDatabase('bot_admins')
        self._init_database()

    def _init_database(self):
        self.db.create_table('admins', '''
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            added_by INTEGER NOT NULL,
            created_at TEXT NOT NULL
        ''')
        self.db.create_table('guild_admins', '''
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            added_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        ''')
        self.db.create_table('cash_admins', '''
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            added_by INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        ''')

    def is_hard_admin(self, user_id: int) -> bool:
        return user_id in DISCORD_OWNER_IDS

    def is_admin(self, user_id: int, guild_id: int | None = None) -> bool:
        if self.is_hard_admin(user_id):
            return True
        if guild_id is None:
            return False
        return self.db.select_one(
            'guild_admins',
            'guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        ) is not None

    def add_admin(self, user_id: int, added_by: int, guild_id: int | None = None) -> bool:
        if self.is_hard_admin(user_id):
            raise ValueError("User này đã có quyền quản trị.")
        if guild_id is None:
            raise ValueError("Thiếu server ID để cấp admin.")

        existing = self.db.select_one(
            'guild_admins',
            'guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )
        if existing:
            raise ValueError("User này đã là admin trong server này.")

        return self.db.insert('guild_admins', {
            'guild_id': guild_id,
            'user_id': user_id,
            'added_by': added_by,
            'created_at': get_timestamp(),
        })

    def remove_admin(self, user_id: int, guild_id: int | None = None) -> bool:
        if self.is_hard_admin(user_id):
            raise ValueError("Không thể xoá quyền quản trị mặc định.")
        if guild_id is None:
            raise ValueError("Thiếu server ID để xoá admin.")

        return self.db.delete(
            'guild_admins',
            'guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )

    def get_admins(self, guild_id: int | None = None) -> List[Dict]:
        if guild_id is None:
            return self.db.fetch('SELECT * FROM guild_admins ORDER BY created_at DESC')
        return self.db.fetch(
            'SELECT * FROM guild_admins WHERE guild_id = ? ORDER BY created_at DESC',
            (guild_id,),
        )

    def is_cash_admin(self, user_id: int, guild_id: int | None = None) -> bool:
        if self.is_hard_admin(user_id):
            return True
        if guild_id is None:
            return False
        return self.db.select_one(
            'cash_admins',
            'guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        ) is not None

    def add_cash_admin(self, user_id: int, added_by: int, guild_id: int | None = None) -> bool:
        if self.is_hard_admin(user_id):
            raise ValueError("User này đã là hard admin cash.")
        if guild_id is None:
            raise ValueError("Thiếu server ID để cấp quyền cash.")
        existing = self.db.select_one(
            'cash_admins',
            'guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )
        if existing:
            raise ValueError("User này đã có quyền cash trong server này.")
        return self.db.insert('cash_admins', {
            'guild_id': guild_id,
            'user_id': user_id,
            'added_by': added_by,
            'created_at': get_timestamp(),
        })

    def remove_cash_admin(self, user_id: int, guild_id: int | None = None) -> bool:
        if self.is_hard_admin(user_id):
            raise ValueError("Không thể xoá quyền cash mặc định.")
        if guild_id is None:
            raise ValueError("Thiếu server ID để xoá quyền cash.")
        return self.db.delete(
            'cash_admins',
            'guild_id = ? AND user_id = ?',
            (guild_id, user_id),
        )

    def get_cash_admins(self, guild_id: int | None = None) -> List[Dict]:
        if guild_id is None:
            return self.db.fetch('SELECT * FROM cash_admins ORDER BY created_at DESC')
        return self.db.fetch(
            'SELECT * FROM cash_admins WHERE guild_id = ? ORDER BY created_at DESC',
            (guild_id,),
        )
