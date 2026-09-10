"""
User Service Layer
- Chứa business logic cho user
- Giao tiếp với Database Layer
"""

from utils import CogDatabase, get_timestamp
from models.user_model import User, UserRole
from services.guild_scope_utils import get_single_configured_guild_id

class UserService:
    """Service xử lý user operations"""
    
    def __init__(self):
        self.db = CogDatabase('users')
        self._init_database()
    
    def _init_database(self):
        """Khởi tạo database schema"""
        self.db.create_table('users', '''
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            username TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            points INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            cash INTEGER DEFAULT 0,
            luong INTEGER DEFAULT 0,
            star INTEGER DEFAULT 0,
            total_hours REAL DEFAULT 0,
            total_donate INTEGER DEFAULT 0,
            total_money INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        ''')
        self.db.create_table('guild_user_stats', '''
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            points INTEGER DEFAULT 0,
            luong INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (guild_id, user_id)
        ''')
        self.db.create_table('guild_stats_migrations', '''
            migration_key TEXT PRIMARY KEY,
            migrated_at TEXT NOT NULL
        ''')
        self._ensure_schema_columns()
        self._migrate_legacy_guild_stats()

    def _migrate_legacy_guild_stats(self):
        migration_key = 'legacy_points_luong_to_single_guild_v1'
        if self.db.select_one('guild_stats_migrations', 'migration_key = ?', (migration_key,)):
            return
        guild_id = get_single_configured_guild_id()
        if guild_id is None:
            return
        for row in self.db.fetch('SELECT user_id, username, points, luong FROM users WHERE points != 0 OR luong != 0'):
            stats = self._get_or_create_guild_stats(guild_id, row['user_id'], row['username'])
            if int(stats['points']) == 0 and int(stats['luong']) == 0:
                self.db.update(
                    'guild_user_stats',
                    {'points': int(row['points']), 'luong': int(row['luong']), 'updated_at': get_timestamp()},
                    'guild_id = ? AND user_id = ?',
                    (guild_id, int(row['user_id'])),
                )
        self.db.insert('guild_stats_migrations', {
            'migration_key': migration_key,
            'migrated_at': get_timestamp(),
        })

    def _ensure_schema_columns(self):
        """Đảm bảo các cột mới tồn tại cho database cũ"""
        columns = {row['name'] for row in self.db.fetch('PRAGMA table_info(users)')}
        required_columns = {
            'total_hours': 'REAL DEFAULT 0',
            'total_donate': 'INTEGER DEFAULT 0',
            'total_money': 'INTEGER DEFAULT 0',
            'cash': 'INTEGER DEFAULT 0',
            'luong': 'INTEGER DEFAULT 0',
            'star': 'INTEGER DEFAULT 0',
        }

        for column_name, column_sql in required_columns.items():
            if column_name not in columns:
                self.db.execute(f'ALTER TABLE users ADD COLUMN {column_name} {column_sql}')
    
    def get_or_create_user(self, user_id: int, username: str, guild_id: int | None = None) -> User:
        """Lấy user hoặc tạo mới"""
        user = self.get_user(user_id)
        
        if not user:
            user = User(
                user_id=user_id,
                username=username,
                role=UserRole.USER,
                points=0,
                level=1,
                cash=0,
                luong=0,
                star=0,
                total_hours=0,
                total_donate=0,
                total_money=0,
            )
            user.validate()
            self.create_user(user)
        
        if guild_id is not None:
            self._get_or_create_guild_stats(guild_id, user_id, username)
            return self.get_user(user_id, guild_id)
        return user

    def _get_or_create_guild_stats(self, guild_id: int, user_id: int, username: str | None = None) -> dict:
        guild_id, user_id = int(guild_id), int(user_id)
        row = self.db.select_one(
            'guild_user_stats', 'guild_id = ? AND user_id = ?', (guild_id, user_id)
        )
        safe_username = str(username or (row or {}).get('username') or user_id).strip() or str(user_id)
        if row:
            if row['username'] != safe_username:
                self.db.update(
                    'guild_user_stats',
                    {'username': safe_username, 'updated_at': get_timestamp()},
                    'guild_id = ? AND user_id = ?',
                    (guild_id, user_id),
                )
            return self.db.select_one('guild_user_stats', 'guild_id = ? AND user_id = ?', (guild_id, user_id))
        self.db.insert('guild_user_stats', {
            'guild_id': guild_id,
            'user_id': user_id,
            'username': safe_username,
            'points': 0,
            'luong': 0,
            'created_at': get_timestamp(),
            'updated_at': get_timestamp(),
        })
        return self.db.select_one('guild_user_stats', 'guild_id = ? AND user_id = ?', (guild_id, user_id))

    def touch_user(self, user_id: int, username: str) -> User:
        """Tạo user nếu chưa có, hoặc cập nhật username mới nhất."""
        safe_username = str(username or user_id).strip() or str(user_id)
        user = self.get_user(user_id)
        if not user:
            return self.get_or_create_user(user_id, safe_username)

        if user.username != safe_username:
            self.db.update(
                'users',
                {'username': safe_username, 'updated_at': get_timestamp()},
                'user_id = ?',
                (user_id,)
            )
            user.username = safe_username
        return user
    
    def get_user(self, user_id: int, guild_id: int | None = None) -> User:
        """Lấy user từ database"""
        result = self.db.select_one('users', 'user_id = ?', (user_id,))
        
        if not result:
            return None
        
        guild_stats = None
        if guild_id is not None:
            guild_stats = self.db.select_one(
                'guild_user_stats', 'guild_id = ? AND user_id = ?', (int(guild_id), int(user_id))
            )
        return User(
            user_id=result['user_id'],
            username=result['username'],
            role=UserRole(result['role']),
            points=guild_stats['points'] if guild_stats else 0,
            level=result['level'],
            cash=result['cash'] if 'cash' in result.keys() else 0,
            luong=guild_stats['luong'] if guild_stats else 0,
            star=result['star'] if 'star' in result.keys() else 0,
            total_hours=result['total_hours'] if 'total_hours' in result.keys() else 0,
            total_donate=result['total_donate'] if 'total_donate' in result.keys() else 0,
            total_money=result['total_money'] if 'total_money' in result.keys() else 0,
        )
    
    def create_user(self, user: User):
        """Tạo user mới"""
        user.validate()
        
        self.db.insert('users', {
            'user_id': user.user_id,
            'username': user.username,
            'role': user.role.value,
            'points': user.points,
            'level': user.level,
            'cash': user.cash,
            'luong': user.luong,
            'star': user.star,
            'total_hours': user.total_hours,
            'total_donate': user.total_donate,
            'total_money': user.total_money,
            'created_at': get_timestamp(),
            'updated_at': get_timestamp()
        })
    
    def add_points(self, user_id: int, amount: int, guild_id: int):
        """Thêm points cho user"""
        self._get_or_create_guild_stats(guild_id, user_id)
        user = self.get_user(user_id, guild_id)
        if not user:
            raise ValueError(f"User {user_id} không tồn tại")
        
        user.add_points(amount)
        
        self.db.update('guild_user_stats',
            {'points': user.points, 'updated_at': get_timestamp()},
            'guild_id = ? AND user_id = ?',
            (int(guild_id), user_id)
        )

    def remove_points(self, user_id: int, amount: int, guild_id: int):
        self._update_guild_numeric_field(guild_id, user_id, 'points', -amount)

    def set_points(self, user_id: int, amount: int, guild_id: int):
        self._set_guild_numeric_field(guild_id, user_id, 'points', amount)

    def _update_guild_numeric_field(self, guild_id: int, user_id: int, field_name: str, amount: int):
        row = self._get_or_create_guild_stats(guild_id, user_id)
        new_value = int(row[field_name]) + int(amount)
        if new_value < 0:
            raise ValueError(f"{field_name} không thể âm")
        self.db.update('guild_user_stats', {field_name: new_value, 'updated_at': get_timestamp()},
                       'guild_id = ? AND user_id = ?', (int(guild_id), int(user_id)))

    def _set_guild_numeric_field(self, guild_id: int, user_id: int, field_name: str, value: int):
        if value < 0:
            raise ValueError(f"{field_name} không thể âm")
        self._get_or_create_guild_stats(guild_id, user_id)
        self.db.update('guild_user_stats', {field_name: int(value), 'updated_at': get_timestamp()},
                       'guild_id = ? AND user_id = ?', (int(guild_id), int(user_id)))

    def _update_numeric_field(self, user_id: int, field_name: str, amount: float):
        user = self.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} không tồn tại")

        current_value = getattr(user, field_name)
        new_value = current_value + amount

        if field_name == 'total_hours':
            if new_value < 0:
                raise ValueError("Hours không thể âm")
        else:
            # Cash âm từ casino được giữ nguyên và có thể nạp để bù nợ.
            # Các thao tác chi tiêu ở bot tổng không được tự tạo thêm nợ.
            if new_value < 0 and not (field_name == 'cash' and amount > 0):
                raise ValueError(f"{field_name} không thể âm")

        setattr(user, field_name, new_value)
        self.db.update('users',
            {
                field_name: new_value,
                'updated_at': get_timestamp()
            },
            'user_id = ?',
            (user_id,)
        )

    def _set_numeric_field(self, user_id: int, field_name: str, value: float):
        user = self.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} không tồn tại")
        if value < 0 and field_name != 'cash':
            raise ValueError(f"{field_name} không thể âm")

        self.db.update('users',
            {
                field_name: value,
                'updated_at': get_timestamp()
            },
            'user_id = ?',
            (user_id,)
        )

    def add_cash(self, user_id: int, amount: int):
        self._update_numeric_field(user_id, 'cash', amount)

    def remove_cash(self, user_id: int, amount: int):
        self._update_numeric_field(user_id, 'cash', -amount)

    def set_cash(self, user_id: int, amount: int):
        self._set_numeric_field(user_id, 'cash', amount)

    def add_total_money(self, user_id: int, amount: int):
        self._update_numeric_field(user_id, 'total_money', amount)

    def remove_total_money(self, user_id: int, amount: int):
        self._update_numeric_field(user_id, 'total_money', -amount)

    def set_total_money(self, user_id: int, amount: int):
        self._set_numeric_field(user_id, 'total_money', amount)

    def add_total_donate(self, user_id: int, amount: int):
        self._update_numeric_field(user_id, 'total_donate', amount)

    def remove_total_donate(self, user_id: int, amount: int):
        self._update_numeric_field(user_id, 'total_donate', -amount)

    def set_total_donate(self, user_id: int, amount: int):
        self._set_numeric_field(user_id, 'total_donate', amount)

    def transfer_cash(self, from_user_id: int, from_username: str, to_user_id: int, to_username: str, amount: int):
        if amount <= 0:
            raise ValueError("Số tiền phải lớn hơn 0")

        sender = self.get_user(from_user_id)
        if not sender:
            raise ValueError(f"User {from_user_id} không tồn tại")
        receiver = self.get_user(to_user_id)
        if not receiver:
            raise ValueError(f"User {to_user_id} không tồn tại")

        if sender.cash < amount:
            raise ValueError("Không đủ cash để chuyển")

        self.remove_cash(from_user_id, amount)
        self.add_cash(to_user_id, amount)

        return {
            "sender_cash": self.get_user(from_user_id).cash,
            "receiver_cash": self.get_user(to_user_id).cash,
        }

    def add_luong(self, user_id: int, amount: int, guild_id: int):
        self._update_guild_numeric_field(guild_id, user_id, 'luong', amount)

    def remove_luong(self, user_id: int, amount: int, guild_id: int):
        self._update_guild_numeric_field(guild_id, user_id, 'luong', -amount)

    def set_luong(self, user_id: int, amount: int, guild_id: int):
        self._set_guild_numeric_field(guild_id, user_id, 'luong', amount)

    def get_users_with_luong(self, guild_id: int) -> list:
        return self.db.fetch(
            'SELECT * FROM guild_user_stats WHERE guild_id = ? AND luong > 0 ORDER BY luong DESC, username ASC',
            (int(guild_id),)
        )

    def pay_user_luong(self, user_id: int, guild_id: int) -> dict:
        user = self.get_user(user_id, guild_id)
        if not user:
            raise ValueError(f"User {user_id} không tồn tại")

        paid_amount = int(user.luong)
        if paid_amount <= 0:
            raise ValueError("Người này không còn lương cần trả")

        before = {
            "user_id": user.user_id,
            "username": user.username,
            "luong": paid_amount,
        }
        self.set_luong(user_id, 0, guild_id)
        after_user = self.get_user(user_id, guild_id)
        return {
            "source": "users",
            "before": before,
            "after": {
                "user_id": after_user.user_id,
                "username": after_user.username,
                "luong": int(after_user.luong),
            },
            "paid_amount": paid_amount,
        }

    def add_star(self, user_id: int, amount: int):
        self._update_numeric_field(user_id, 'star', amount)

    def remove_star(self, user_id: int, amount: int):
        self._update_numeric_field(user_id, 'star', -amount)

    def set_star(self, user_id: int, amount: int):
        self._set_numeric_field(user_id, 'star', amount)

    def add_hours(self, user_id: int, hours: float):
        self._update_numeric_field(user_id, 'total_hours', hours)

    def remove_hours(self, user_id: int, hours: float):
        self._update_numeric_field(user_id, 'total_hours', -hours)

    def set_hours(self, user_id: int, hours: float):
        self._set_numeric_field(user_id, 'total_hours', hours)

    def get_users_by_stat(self, field_name: str, limit: int = 25, guild_id: int | None = None) -> list:
        allowed_fields = {"cash", "luong", "star", "points", "total_hours", "total_donate", "total_money"}
        if field_name not in allowed_fields:
            raise ValueError("Trường thống kê không hợp lệ")
        safe_limit = max(1, min(int(limit), 100))
        if field_name in {'points', 'luong'}:
            if guild_id is None:
                raise ValueError('guild_id là bắt buộc cho points/lương')
            return self.db.fetch(
                f'SELECT * FROM guild_user_stats WHERE guild_id = ? ORDER BY {field_name} DESC, username ASC LIMIT ?',
                (int(guild_id), safe_limit),
            )
        return self.db.fetch(
            f'SELECT * FROM users ORDER BY {field_name} DESC, username ASC LIMIT ?',
            (safe_limit,)
        )

    def get_top_users(self, limit: int = 10, guild_id: int | None = None) -> list:
        """Lấy top users theo points"""
        if guild_id is None:
            raise ValueError('guild_id là bắt buộc cho bảng xếp hạng points')
        return self.db.fetch(
            '''
            SELECT stats.*, COALESCE(users.level, 1) AS level
            FROM guild_user_stats AS stats
            LEFT JOIN users ON users.user_id = stats.user_id
            WHERE stats.guild_id = ?
            ORDER BY stats.points DESC, stats.username ASC
            LIMIT ?
            ''',
            (int(guild_id), limit),
        )

    def get_top_stars(self, limit: int = 10) -> list:
        """Lấy top users theo star"""
        return self.db.fetch(
            'SELECT * FROM users ORDER BY star DESC, points DESC LIMIT ?',
            (limit,)
        )

    def get_total_luong(self, guild_id: int) -> int:
        """Lấy tổng lương của toàn bộ users"""
        result = self.db.fetch_one('SELECT COALESCE(SUM(luong), 0) AS total_luong FROM guild_user_stats WHERE guild_id = ?', (int(guild_id),))
        return int(result['total_luong']) if result else 0

    def set_user_role(self, user_id: int, role: UserRole):
        """Thay đổi role user"""
        user = self.get_user(user_id)
        if not user:
            raise ValueError(f"User {user_id} không tồn tại")
        
        self.db.update('users',
            {'role': role.value, 'updated_at': get_timestamp()},
            'user_id = ?',
            (user_id,)
        )
