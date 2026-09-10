# File: services/ticket_service.py
# Purpose: Chịu trách nhiệm tương tác Database cho hệ thống Ticket.
# Notes:
# - Tái sử dụng CogDatabase hiện tại, tự tạo bảng nếu chưa có.
# - Giữ ACID logic/Status check ở level DB.

import time
import logging
from typing import Dict, List, Optional, Any
from utils import CogDatabase, get_timestamp

logger = logging.getLogger(__name__)

ALLOWED_CONFIG_KEYS = {
    "panel_channel_id", "ticket_category_id", "log_channel_id",
    "transcript_channel_id", "archive_category_id", "panel_message_id",
    "max_open_tickets", "cooldown_seconds", "close_mode", "transcript_limit"
}

class TicketService:
    def __init__(self):
        self.db = CogDatabase('ticket_system')
        self._init_database()

    def _init_database(self):
        self.db.create_table('ticket_config', '''
            guild_id INTEGER PRIMARY KEY,
            panel_channel_id INTEGER,
            ticket_category_id INTEGER,
            staff_role_id INTEGER,
            log_channel_id INTEGER,
            transcript_channel_id INTEGER,
            archive_category_id INTEGER,
            panel_message_id INTEGER,
            max_open_tickets INTEGER DEFAULT 1,
            cooldown_seconds INTEGER DEFAULT 60,
            close_mode TEXT DEFAULT 'archive',
            transcript_limit INTEGER DEFAULT 500,
            created_at TEXT,
            updated_at TEXT
        ''')
        self.db.create_table('tickets', '''
            ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER UNIQUE NOT NULL,
            owner_user_id INTEGER NOT NULL,
            ticket_type TEXT,
            status TEXT NOT NULL,
            claimed_by_user_id INTEGER,
            created_at TEXT NOT NULL,
            last_activity_at REAL NOT NULL
        ''')
        self.db.create_table('ticket_events', '''
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            actor_user_id INTEGER,
            target_user_id INTEGER,
            message TEXT,
            created_at TEXT NOT NULL
        ''')
        self.db.create_table('ticket_theme', '''
            guild_id INTEGER NOT NULL,
            theme_key TEXT NOT NULL,
            theme_value TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, theme_key)
        ''')
        self.db.create_table('ticket_type_mentions', '''
            guild_id INTEGER NOT NULL,
            ticket_type TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, ticket_type, target_type, target_id)
        ''')
        self._ensure_schema()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        try:
            cols = {row['name'] for row in self.db.fetch(f"PRAGMA table_info({table})")}
            if column not in cols:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        except Exception as e:
            logger.exception(f"Ticket config schema migration failed for column {column} in table {table}: {e}")

    def _ensure_schema(self):
        self._ensure_column("tickets", "claimed_by_username", "TEXT")
        self._ensure_column("tickets", "close_reason", "TEXT")
        self._ensure_column("tickets", "ticket_code", "TEXT")
        self._ensure_column("tickets", "deleted_at", "TEXT")
        self._ensure_column("tickets", "delete_reason", "TEXT")
        
        self._ensure_column("ticket_config", "archive_category_id", "INTEGER")
        self._ensure_column("ticket_config", "panel_message_id", "INTEGER")
        self._ensure_column("ticket_config", "transcript_channel_id", "INTEGER")
        self._ensure_column("ticket_config", "max_open_tickets", "INTEGER DEFAULT 1")
        self._ensure_column("ticket_config", "cooldown_seconds", "INTEGER DEFAULT 60")
        self._ensure_column("ticket_config", "close_mode", "TEXT DEFAULT 'archive'")
        self._ensure_column("ticket_config", "transcript_limit", "INTEGER DEFAULT 500")
        self._ensure_column("ticket_config", "created_at", "TEXT")
        self._ensure_column("ticket_config", "updated_at", "TEXT")
                
        try:
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_tickets_guild_channel ON tickets(guild_id, channel_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_tickets_owner_status ON tickets(guild_id, owner_user_id, status)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_ticket_events_ticket_id ON ticket_events(ticket_id)")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_ticket_type_mentions ON ticket_type_mentions(guild_id, ticket_type)")
        except Exception as e:
            logger.exception(f"Ticket Index creation failed: {e}")
            
    def get_config(self, guild_id: int) -> Optional[Dict]:
        return self.db.select_one('ticket_config', 'guild_id = ?', (guild_id,))

    def save_config(self, guild_id: int, panel_id: int, category_id: int, log_id: Optional[int], max_tickets: int = 1, transcript_id: Optional[int] = 0, close_mode: str = 'archive', archive_cat_id: Optional[int] = 0):
        existing = self.get_config(guild_id)
        if existing:
            self.db.execute('''
                UPDATE ticket_config 
                SET panel_channel_id=?, ticket_category_id=?, log_channel_id=?, transcript_channel_id=?, archive_category_id=?, close_mode=?, max_open_tickets=?, updated_at=?
                WHERE guild_id=?
            ''', (panel_id, category_id, log_id, transcript_id, archive_cat_id, close_mode, max_tickets, get_timestamp(), guild_id))
            return True
        else:
            return self.db.insert('ticket_config', {
                'guild_id': guild_id,
                'panel_channel_id': panel_id,
                'ticket_category_id': category_id,
                'log_channel_id': log_id,
                'transcript_channel_id': transcript_id,
                'archive_category_id': archive_cat_id,
                'close_mode': close_mode,
                'max_open_tickets': max_tickets,
                'created_at': get_timestamp(),
                'updated_at': get_timestamp()
            })
            
    def ensure_config(self, guild_id: int) -> dict:
        config = self.get_config(guild_id)
        if config:
            return config
        now = get_timestamp()
        self.db.insert('ticket_config', {
            'guild_id': guild_id,
            'max_open_tickets': 1,
            'cooldown_seconds': 60,
            'close_mode': 'archive',
            'created_at': now,
            'updated_at': now
        })
        return self.get_config(guild_id)

    def update_single_config(self, guild_id: int, key: str, value: Any) -> bool:
        if key not in ALLOWED_CONFIG_KEYS:
            raise ValueError(f"Invalid ticket config key: {key}")
        self.ensure_config(guild_id)
        logger.debug("[TICKET_DB] update key=%s value=%s guild=%s", key, value, guild_id)
        ok = self.db.update('ticket_config', {key: value, 'updated_at': get_timestamp()}, 'guild_id = ?', (guild_id,))
        logger.debug("[TICKET_DB] update_config result ok=%s rowcount=%s", ok, getattr(self.db.conn, "total_changes", "N/A"))
        return ok

    def get_theme(self, guild_id: int) -> dict:
        rows = self.db.fetch(
            "SELECT theme_key, theme_value FROM ticket_theme WHERE guild_id = ?",
            (int(guild_id),),
        )
        return {str(row["theme_key"]): str(row["theme_value"]) for row in rows}

    def set_theme_value(self, guild_id: int, key: str, value: str):
        existing = self.db.select_one(
            "ticket_theme",
            "guild_id = ? AND theme_key = ?",
            (int(guild_id), str(key)),
        )
        data = {"theme_value": str(value), "updated_at": get_timestamp()}
        if existing:
            self.db.update(
                "ticket_theme",
                data,
                "guild_id = ? AND theme_key = ?",
                (int(guild_id), str(key)),
            )
        else:
            self.db.insert(
                "ticket_theme",
                {"guild_id": int(guild_id), "theme_key": str(key), **data},
            )

    def reset_theme_value(self, guild_id: int, key: str):
        self.db.delete(
            "ticket_theme",
            "guild_id = ? AND theme_key = ?",
            (int(guild_id), str(key)),
        )

    def get_type_mentions(self, guild_id: int, ticket_type: str) -> List[Dict]:
        return self.db.fetch(
            """
            SELECT target_type, target_id
            FROM ticket_type_mentions
            WHERE guild_id = ? AND ticket_type = ?
            ORDER BY target_type, target_id
            """,
            (int(guild_id), str(ticket_type)),
        )

    def replace_type_mentions(
        self,
        guild_id: int,
        ticket_type: str,
        target_type: str,
        target_ids: List[int],
    ) -> None:
        if target_type not in {"role", "user"}:
            raise ValueError(f"Invalid ticket mention target type: {target_type}")
        guild_id = int(guild_id)
        ticket_type = str(ticket_type)
        self.db.delete(
            "ticket_type_mentions",
            "guild_id = ? AND ticket_type = ? AND target_type = ?",
            (guild_id, ticket_type, target_type),
        )
        for target_id in dict.fromkeys(int(value) for value in target_ids):
            self.db.insert(
                "ticket_type_mentions",
                {
                    "guild_id": guild_id,
                    "ticket_type": ticket_type,
                    "target_type": target_type,
                    "target_id": target_id,
                    "created_at": get_timestamp(),
                },
            )

    def set_type_mentions(
        self,
        guild_id: int,
        ticket_type: str,
        *,
        role_ids: List[int],
        user_ids: List[int],
    ) -> None:
        self.replace_type_mentions(guild_id, ticket_type, "role", role_ids)
        self.replace_type_mentions(guild_id, ticket_type, "user", user_ids)

    def clear_type_mentions(self, guild_id: int, ticket_type: str) -> None:
        self.db.delete(
            "ticket_type_mentions",
            "guild_id = ? AND ticket_type = ?",
            (int(guild_id), str(ticket_type)),
        )

    def get_user_active_tickets(self, guild_id: int, user_id: int) -> List[Dict]:
        # Status open hoặc claimed được coi là active
        return self.db.fetch('''
            SELECT * FROM tickets 
            WHERE guild_id = ? AND owner_user_id = ? AND status IN ('open', 'claimed')
        ''', (guild_id, user_id))

    def create_ticket(self, guild_id: int, channel_id: int, owner_id: int, ticket_type: str, ticket_code: str) -> bool:
        return self.db.insert('tickets', {
            'guild_id': guild_id,
            'channel_id': channel_id,
            'owner_user_id': owner_id,
            'ticket_type': ticket_type,
            'ticket_code': ticket_code,
            'status': 'open',
            'created_at': get_timestamp(),
            'last_activity_at': time.time()
        })

    def get_ticket(self, channel_id: int) -> Optional[Dict]:
        return self.db.select_one('tickets', 'channel_id = ?', (channel_id,))

    def claim_ticket(self, channel_id: int, staff_id: int, staff_username: str = "") -> bool:
        ticket = self.get_ticket(channel_id)
        if not ticket or ticket['status'] != 'open':
            return False
        cursor = self.db.conn.cursor()
        cursor.execute('''
            UPDATE tickets SET status = 'claimed', claimed_by_user_id = ?, claimed_by_username = ?, last_activity_at = ?
            WHERE channel_id = ? AND status = 'open'
        ''', (staff_id, staff_username, time.time(), channel_id))
        self.db.conn.commit()
        return cursor.rowcount > 0

    def transfer_ticket(self, channel_id: int, new_staff_id: int, new_staff_username: str) -> bool:
        cursor = self.db.conn.cursor()
        cursor.execute('''
            UPDATE tickets SET status = 'claimed', claimed_by_user_id = ?, claimed_by_username = ?, last_activity_at = ?
            WHERE channel_id = ? AND status IN ('open', 'claimed')
        ''', (new_staff_id, new_staff_username, time.time(), channel_id))
        self.db.conn.commit()
        return cursor.rowcount > 0

    def unclaim_ticket(self, channel_id: int) -> bool:
        cursor = self.db.conn.cursor()
        cursor.execute('''
            UPDATE tickets SET status = 'open', claimed_by_user_id = NULL, claimed_by_username = NULL, last_activity_at = ?
            WHERE channel_id = ? AND status = 'claimed'
        ''', (time.time(), channel_id))
        self.db.conn.commit()
        return cursor.rowcount > 0

    def log_event(self, ticket_id: int, guild_id: int, channel_id: int, event_type: str, actor_id: int, target_id: Optional[int] = None, message: str = "") -> bool:
        return self.db.insert('ticket_events', {
            'ticket_id': ticket_id,
            'guild_id': guild_id,
            'channel_id': channel_id,
            'event_type': event_type,
            'actor_user_id': actor_id,
            'target_user_id': target_id,
            'message': message,
            'created_at': get_timestamp()
        })

    def set_ticket_status(self, channel_id: int, new_status: str, required_current_statuses: List[str], close_reason: str = "") -> bool:
        """Update atomic chống double click."""
        placeholders = ','.join(['?']*len(required_current_statuses))
        if new_status == 'closed':
            query = f'''UPDATE tickets SET status = ?, close_reason = ?, last_activity_at = ? WHERE channel_id = ? AND status IN ({placeholders})'''
            args = [new_status, close_reason, time.time(), channel_id] + required_current_statuses
        else:
            query = f'''UPDATE tickets SET status = ?, last_activity_at = ? WHERE channel_id = ? AND status IN ({placeholders})'''
            args = [new_status, time.time(), channel_id] + required_current_statuses
            
        cursor = self.db.conn.cursor()
        cursor.execute(query, args)
        self.db.conn.commit()
        return cursor.rowcount > 0
        
    def get_cooldown(self, guild_id: int, user_id: int, cooldown_seconds: int) -> int:
        # Lấy ticket gần nhất để check cooldown
        last_tickets = self.db.fetch('SELECT last_activity_at FROM tickets WHERE guild_id = ? AND owner_user_id = ? ORDER BY last_activity_at DESC LIMIT 1', (guild_id, user_id))
        if not last_tickets: return 0
        elapsed = time.time() - float(last_tickets[0]['last_activity_at'])
        return max(0, int(cooldown_seconds - elapsed))

    def get_all_active_tickets(self, guild_id: int) -> List[Dict]:
        return self.db.fetch("SELECT * FROM tickets WHERE guild_id = ? AND status IN ('open', 'claimed', 'closing')", (guild_id,))

    def mark_ticket_deleted(self, channel_id: int, reason: str = "manual_delete_detected"):
        self.db.execute("UPDATE tickets SET status = 'deleted', deleted_at = ?, delete_reason = ? WHERE channel_id = ?", (get_timestamp(), reason, channel_id))
