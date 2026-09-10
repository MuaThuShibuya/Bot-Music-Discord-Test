import sqlite3
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from config import DATABASE_DIR

# Tạo folder database nếu chưa tồn tại
os.makedirs(DATABASE_DIR, exist_ok=True)

class CogDatabase:
    """
    Hàm dùng chung để quản lý database cho mỗi cog.
    Tự động tạo file database và table khi khởi tạo.
    """
    
    def __init__(self, cog_name: str):
        """
        Khởi tạo database cho một cog
        
        Args:
            cog_name: Tên của cog (sẽ dùng làm tên file database)
        """
        self.cog_name = cog_name
        self.db_path = os.path.join(DATABASE_DIR, f'{cog_name}.db')
        self.conn = None
        self.connect()
    
    def connect(self):
        """Kết nối đến database"""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row  # Để dữ liệu có dạng dict
            print(f'✅ Kết nối database: {self.db_path}')
        except Exception as e:
            print(f'❌ Lỗi kết nối database: {e}')
            raise

    def _ensure_connection(self):
        """Mở lại kết nối nếu cog reload đã đóng connection cũ."""
        if self.conn is None:
            self.connect()
            return
        try:
            self.conn.execute('SELECT 1')
        except sqlite3.ProgrammingError:
            self.connect()
    
    def create_table(self, table_name: str, schema: str) -> bool:
        """
        Tạo bảng trong database
        
        Args:
            table_name: Tên bảng
            schema: SQL schema (ví dụ: 'id INTEGER PRIMARY KEY, name TEXT')
        
        Returns:
            True nếu thành công, False nếu thất bại
        """
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            sql = f'CREATE TABLE IF NOT EXISTS {table_name} ({schema})'
            cursor.execute(sql)
            self.conn.commit()
            print(f'✅ Tạo bảng: {table_name}')
            return True
        except Exception as e:
            print(f'❌ Lỗi tạo bảng {table_name}: {e}')
            return False
    
    def insert(self, table_name: str, data: Dict[str, Any]) -> bool:
        """
        Insert một dòng dữ liệu
        
        Args:
            table_name: Tên bảng
            data: Dict {column: value}
        
        Returns:
            True nếu thành công
        """
        try:
            self._ensure_connection()
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['?' for _ in data])
            sql = f'INSERT INTO {table_name} ({columns}) VALUES ({placeholders})'
            cursor = self.conn.cursor()
            cursor.execute(sql, tuple(data.values()))
            self.conn.commit()
            return True
        except Exception as e:
            print(f'❌ Lỗi insert vào {table_name}: {e}')
            return False
    
    def select(self, table_name: str, where: str = '', params: tuple = ()) -> List[Dict]:
        """
        Lấy dữ liệu từ bảng
        
        Args:
            table_name: Tên bảng
            where: Điều kiện WHERE (ví dụ: 'id = ?')
            params: Tham số cho WHERE clause
        
        Returns:
            Danh sách dict chứa dữ liệu
        """
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            sql = f'SELECT * FROM {table_name}'
            if where:
                sql += f' WHERE {where}'
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f'❌ Lỗi select từ {table_name}: {e}')
            return []
    
    def select_one(self, table_name: str, where: str = '', params: tuple = ()) -> Optional[Dict]:
        """Lấy một dòng dữ liệu"""
        results = self.select(table_name, where, params)
        return results[0] if results else None
    
    def update(self, table_name: str, data: Dict[str, Any], where: str = '', params: tuple = ()) -> bool:
        """
        Cập nhật dữ liệu
        
        Args:
            table_name: Tên bảng
            data: Dict {column: new_value}
            where: Điều kiện WHERE
            params: Tham số cho WHERE
        
        Returns:
            True nếu thành công
        """
        try:
            self._ensure_connection()
            set_clause = ', '.join([f'{k} = ?' for k in data.keys()])
            sql = f'UPDATE {table_name} SET {set_clause}'
            if where:
                sql += f' WHERE {where}'
            
            values = tuple(data.values()) + params
            cursor = self.conn.cursor()
            cursor.execute(sql, values)
            self.conn.commit()
            return True
        except Exception as e:
            print(f'❌ Lỗi update {table_name}: {e}')
            return False
    
    def delete(self, table_name: str, where: str = '', params: tuple = ()) -> bool:
        """
        Xóa dữ liệu
        
        Args:
            table_name: Tên bảng
            where: Điều kiện WHERE
            params: Tham số cho WHERE
        
        Returns:
            True nếu thành công
        """
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            sql = f'DELETE FROM {table_name}'
            if where:
                sql += f' WHERE {where}'
            cursor.execute(sql, params)
            self.conn.commit()
            return True
        except Exception as e:
            print(f'❌ Lỗi delete từ {table_name}: {e}')
            return False
    
    def execute(self, sql: str, params: tuple = ()) -> bool:
        """
        Thực thi SQL query tùy chỉnh
        
        Args:
            sql: SQL query
            params: Tham số
        
        Returns:
            True nếu thành công
        """
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            self.conn.commit()
            return True
        except Exception as e:
            print(f'❌ Lỗi execute SQL: {e}')
            return False
    
    def fetch(self, sql: str, params: tuple = ()) -> List[Dict]:
        """Thực thi SQL query và lấy kết quả"""
        try:
            self._ensure_connection()
            cursor = self.conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            print(f'❌ Lỗi fetch: {e}')
            return []
    
    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[Dict]:
        """Thực thi SQL query và lấy một kết quả"""
        results = self.fetch(sql, params)
        return results[0] if results else None
    
    def close(self):
        """Đóng kết nối"""
        if self.conn:
            try:
                self.conn.close()
                print(f'✅ Đóng database: {self.cog_name}')
            finally:
                self.conn = None
    
    def __del__(self):
        """Tự động đóng khi object bị xóa"""
        self.close()


# Hàm helper khác
def get_timestamp() -> str:
    """Lấy timestamp hiện tại"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def discord_timestamp_text(dt: datetime | None = None, style: str = "f") -> str:
    """Tạo timestamp Discord để mỗi user thấy đúng timezone của họ."""
    value = dt or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return f"<t:{int(value.timestamp())}:{style}>"


VIETNAM_TIMEZONE = timezone(timedelta(hours=7))


def vietnamese_footer_time(dt: datetime | None = None) -> str:
    """Format embed footer time consistently in Vietnam time."""
    value = dt or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local_value = value.astimezone(VIETNAM_TIMEZONE)
    today = datetime.now(VIETNAM_TIMEZONE).date()
    if local_value.date() == today:
        day_label = "Hôm nay"
    elif local_value.date() == today - timedelta(days=1):
        day_label = "Hôm qua"
    else:
        day_label = local_value.strftime("%d/%m/%Y")
    return f"{day_label} • {local_value:%H:%M} • {local_value:%d/%m/%Y}"


def append_discord_timestamp(embed, dt: datetime | None = None, style: str = "f"):
    """Put a consistent Vietnam-time label in the embed's small footer."""
    del style  # Kept for backwards compatibility with existing callers.
    stamp = vietnamese_footer_time(dt)
    footer_text = getattr(getattr(embed, "footer", None), "text", None)
    footer_icon = getattr(getattr(embed, "footer", None), "icon_url", None)
    text = f"{footer_text}\n{stamp}" if footer_text else stamp
    embed.set_footer(text=text, icon_url=footer_icon or None)
    return embed


def log_to_file(message: str, filename: str = 'bot.log'):
    """Ghi log vào file"""
    from config import LOGS_DIR
    log_path = os.path.join(LOGS_DIR, filename)
    with open(log_path, 'a', encoding='utf-8') as f:
        f.write(f'[{get_timestamp()}] {message}\n')


class RolePermissionManager:
    """
    Quản lý quyền hạn commands theo role
    
    Ví dụ:
        manager = RolePermissionManager()
        await manager.add_permission(guild_id=123, role_id=456, command='ban')
        → Role 456 được dùng lệnh 'ban' trong server 123
        
        can_use = manager.can_use_command(guild_id=123, user_roles=[456], command='ban')
        → Nếu user có role 456, return True
    """
    
    def __init__(self):
        self.db = CogDatabase('command_role')
        self._init_database()
    
    def _init_database(self):
        """Khởi tạo database schema"""
        # Table lưu quyền commands theo role
        self.db.create_table('command_permissions', '''
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            role_id INTEGER,
            role_name TEXT,
            command_name TEXT NOT NULL,
            is_allowed BOOLEAN DEFAULT 1,
            created_by INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(guild_id, role_id, command_name)
        ''')
        
        # Table lưu default permissions cho commands
        self.db.create_table('command_defaults', '''
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command_name TEXT UNIQUE NOT NULL,
            default_permission TEXT DEFAULT 'everyone',
            description TEXT,
            created_at TEXT NOT NULL
        ''')
        
        # Table lưu role hierarchy (cấp độ role)
        self.db.create_table('role_hierarchy', '''
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            role_name TEXT,
            hierarchy_level INTEGER,
            created_at TEXT NOT NULL,
            UNIQUE(guild_id, role_id)
        ''')
        self._ensure_schema_columns()

    def _ensure_schema_columns(self):
        columns = {row['name'] for row in self.db.fetch('PRAGMA table_info(command_permissions)')}
        if 'role_name' not in columns:
            self.db.execute('ALTER TABLE command_permissions ADD COLUMN role_name TEXT')
        self.db.execute('''
            UPDATE command_permissions
            SET role_name = (
                SELECT rh.role_name
                FROM role_hierarchy rh
                WHERE rh.guild_id = command_permissions.guild_id
                  AND rh.role_id = command_permissions.role_id
                LIMIT 1
            )
            WHERE role_name IS NULL OR role_name = ''
        ''')
    
    def add_permission(self, guild_id: int, role_id: int, command_name: str, 
                       created_by: int = None, role_name: str | None = None) -> bool:
        """
        Thêm quyền cho role sử dụng command
        
        Args:
            guild_id: Server ID
            role_id: Role ID (None = @everyone)
            command_name: Tên command
            created_by: User ID người tạo
        
        Returns:
            True nếu thành công
        
        Ví dụ:
            manager.add_permission(guild_id=123, role_id=456, command='ban', created_by=789)
            → Role 456 được dùng lệnh 'ban'
        """
        try:
            timestamp = get_timestamp()
            success = self.db.execute('''
                INSERT INTO command_permissions
                (guild_id, role_id, role_name, command_name, is_allowed, created_by, created_at)
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(guild_id, role_id, command_name)
                DO UPDATE SET
                    is_allowed = 1,
                    role_name = COALESCE(excluded.role_name, command_permissions.role_name),
                    created_by = excluded.created_by,
                    created_at = excluded.created_at
            ''', (guild_id, role_id, role_name, command_name, created_by, timestamp))
            if not success:
                return False
            print(f'✅ Thêm quyền: Role {role_id} → Command "{command_name}" (Server {guild_id})')
            return True
        except Exception as e:
            print(f'❌ Lỗi add_permission: {e}')
            return False
    
    def remove_permission(self, guild_id: int, role_id: int, command_name: str) -> bool:
        """
        Xóa quyền cho role sử dụng command
        
        Args:
            guild_id: Server ID
            role_id: Role ID
            command_name: Tên command
        
        Returns:
            True nếu thành công
        
        Ví dụ:
            manager.remove_permission(guild_id=123, role_id=456, command='ban')
            → Role 456 không được dùng lệnh 'ban'
        """
        try:
            self.db.delete('command_permissions',
                'guild_id = ? AND role_id = ? AND command_name = ?',
                (guild_id, role_id, command_name)
            )
            print(f'✅ Xóa quyền: Role {role_id} → Command "{command_name}" (Server {guild_id})')
            return True
        except Exception as e:
            print(f'❌ Lỗi remove_permission: {e}')
            return False
    
    def can_use_command(self, guild_id: int, user_roles: List[int], command_name: str) -> bool:
        """
        Check xem user có thể dùng command không
        
        Args:
            guild_id: Server ID
            user_roles: List các role ID của user
            command_name: Tên command
        
        Returns:
            True nếu có ít nhất 1 role có quyền
        
        Ví dụ:
            user_roles = [123, 456, 789]  # User có 3 roles
            can_use = manager.can_use_command(guild_id=100, user_roles=user_roles, command='ban')
            → Nếu role 456 có quyền 'ban' thì return True
        """
        if not user_roles:
            # Không có role, check @everyone permission
            perm = self.db.select_one('command_permissions',
                'guild_id = ? AND role_id IS NULL AND command_name = ?',
                (guild_id, command_name)
            )
            return perm is not None
        
        # Check xem có role nào có quyền không
        for role_id in user_roles:
            perm = self.db.select_one('command_permissions',
                'guild_id = ? AND role_id = ? AND command_name = ? AND is_allowed = 1',
                (guild_id, role_id, command_name)
            )
            if perm:
                return True
        
        return False
    
    def get_roles_for_command(self, guild_id: int, command_name: str) -> List[Dict]:
        """
        Lấy danh sách roles có quyền dùng command
        
        Args:
            guild_id: Server ID
            command_name: Tên command
        
        Returns:
            Danh sách dict chứa role_id, role_name
        
        Ví dụ:
            roles = manager.get_roles_for_command(guild_id=123, command='ban')
            → [{'role_id': 456, 'role_name': 'Moderator'}, ...]
        """
        return self.db.fetch('''
            SELECT cp.role_id, COALESCE(cp.role_name, rh.role_name, 'Role ' || cp.role_id) AS role_name
            FROM command_permissions cp
            LEFT JOIN role_hierarchy rh ON cp.guild_id = rh.guild_id AND cp.role_id = rh.role_id
            WHERE cp.guild_id = ? AND cp.command_name = ? AND cp.is_allowed = 1
        ''', (guild_id, command_name))
    
    def get_commands_for_role(self, guild_id: int, role_id: int) -> List[str]:
        """
        Lấy danh sách commands mà role có thể dùng
        
        Args:
            guild_id: Server ID
            role_id: Role ID
        
        Returns:
            Danh sách tên commands
        
        Ví dụ:
            commands = manager.get_commands_for_role(guild_id=123, role_id=456)
            → ['ban', 'kick', 'mute']
        """
        results = self.db.fetch(
            'SELECT DISTINCT command_name FROM command_permissions WHERE guild_id = ? AND role_id = ? AND is_allowed = 1',
            (guild_id, role_id)
        )
        return [r['command_name'] for r in results]
    
    def set_command_default(self, command_name: str, default_permission: str = 'everyone', 
                           description: str = None) -> bool:
        """
        Set default permission cho command
        
        Args:
            command_name: Tên command
            default_permission: 'everyone', 'admin', 'moderator'
            description: Mô tả command
        
        Returns:
            True nếu thành công
        
        Ví dụ:
            manager.set_command_default('ban', 'admin', 'Cấm user')
            → Lệnh 'ban' mặc định chỉ admin có thể dùng
        """
        try:
            self.db.execute('''
                INSERT OR REPLACE INTO command_defaults 
                (command_name, default_permission, description, created_at)
                VALUES (?, ?, ?, ?)
            ''', (command_name, default_permission, description, get_timestamp()))
            print(f'✅ Set default: Command "{command_name}" → {default_permission}')
            return True
        except Exception as e:
            print(f'❌ Lỗi set_command_default: {e}')
            return False
    
    def add_role_hierarchy(self, guild_id: int, role_id: int, role_name: str, 
                          hierarchy_level: int) -> bool:
        """
        Thêm role vào hierarchy
        
        Args:
            guild_id: Server ID
            role_id: Role ID
            role_name: Tên role
            hierarchy_level: Cấp độ (0=thấp nhất, 10=cao nhất)
        
        Returns:
            True nếu thành công
        """
        try:
            existing = self.db.select_one(
                'role_hierarchy',
                'guild_id = ? AND role_id = ?',
                (guild_id, role_id),
            )
            payload = {
                'role_name': role_name,
                'hierarchy_level': hierarchy_level,
                'created_at': get_timestamp(),
            }
            if existing:
                return self.db.update(
                    'role_hierarchy',
                    payload,
                    'guild_id = ? AND role_id = ?',
                    (guild_id, role_id),
                )
            return self.db.insert('role_hierarchy', {
                'guild_id': guild_id,
                'role_id': role_id,
                **payload,
            })
        except Exception as e:
            print(f'❌ Lỗi add_role_hierarchy: {e}')
            return False


# ============================================
# PREFIX & CONFIGURATION HELPERS
# ============================================

def get_prefix(guild_id: int | None = None):
    """
    Lấy prefix hiện tại của bot
    
    Mặc định: !
    """
    global _SETTINGS_SERVICE_CACHE
    try:
        if "_SETTINGS_SERVICE_CACHE" not in globals():
            _SETTINGS_SERVICE_CACHE = None
        if _SETTINGS_SERVICE_CACHE is None:
            from services.settings_service import SettingsService

            _SETTINGS_SERVICE_CACHE = SettingsService()
        return _SETTINGS_SERVICE_CACHE.get_prefix(guild_id)
    except Exception:
        from config import BOT_PREFIX

        return BOT_PREFIX


def match_case_insensitive_prefix(content: str, prefix: str) -> str | None:
    """Trả về đúng phần prefix user đã gõ nếu khớp không phân biệt hoa thường."""
    if not prefix or len(content) < len(prefix):
        return None
    candidate = content[:len(prefix)]
    return candidate if candidate.casefold() == prefix.casefold() else None


def get_command_help(command_name: str, prefix: str = None) -> str:
    """
    Tạo cú pháp help cho command
    
    Args:
        command_name: Tên command (vd: 'addrole')
        prefix: Prefix (lấy từ .env nếu None)
    
    Returns:
        String cú pháp
    
    Ví dụ:
        help_text = get_command_help('addrole')
        → '!addrole'
    """
    if prefix is None:
        prefix = get_prefix()
    return f"{prefix}{command_name}"


# ============================================
# SPLASH & EMBED HELPERS
# ============================================

def create_splash_single(title: str, description: str = None, color = None, 
                        fields: Dict[str, str] = None, thumbnail_url: str = None,
                        footer_text: str = None) -> 'discord.Embed':
    """
    Tạo 1 embed splash (splash duy nhất)
    
    Args:
        title: Tiêu đề
        description: Mô tả (optional)
        color: Màu (discord.Color.blue())
        fields: Dict {name: value}
        thumbnail_url: URL ảnh
        footer_text: Footer text
    
    Returns:
        discord.Embed object
    
    Ví dụ:
        embed = create_splash_single(
            title="✅ Thành Công",
            description="Hành động hoàn tất",
            color=discord.Color.green(),
            fields={'User': 'JohnDoe', 'Action': 'Banned'}
        )
        await ctx.send(embed=embed)
    """
    import discord
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=color or discord.Color.blue()
    )
    
    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=True)
    
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)
    
    if footer_text:
        embed.set_footer(text=footer_text)
    
    return embed


def create_splash_double(title1: str, description1: str = None, 
                        title2: str = None, description2: str = None,
                        color1 = None, color2 = None,
                        fields1: Dict[str, str] = None, fields2: Dict[str, str] = None) -> tuple:
    """
    Tạo 2 embeds splash (splash kép)
    
    Args:
        title1: Tiêu đề embed 1
        description1: Mô tả embed 1
        title2: Tiêu đề embed 2
        description2: Mô tả embed 2
        color1: Màu embed 1
        color2: Màu embed 2
        fields1: Dict fields cho embed 1
        fields2: Dict fields cho embed 2
    
    Returns:
        (embed1, embed2) tuple
    
    Ví dụ:
        embed1, embed2 = create_splash_double(
            title1="📍 From",
            description1="JohnDoe",
            title2="📍 To",
            description2="JaneDoe"
        )
        await ctx.send(embed=embed1)
        await ctx.send(embed=embed2)
    """
    import discord
    
    embed1 = discord.Embed(
        title=title1,
        description=description1,
        color=color1 or discord.Color.blue()
    )
    
    if fields1:
        for name, value in fields1.items():
            embed1.add_field(name=name, value=value, inline=True)
    
    embed2 = discord.Embed(
        title=title2 or title1,
        description=description2 or description1,
        color=color2 or discord.Color.green()
    )
    
    if fields2:
        for name, value in fields2.items():
            embed2.add_field(name=name, value=value, inline=True)
    
    return (embed1, embed2)


def create_error_splash(error_message: str, footer_text: str = None) -> 'discord.Embed':
    """
    Tạo embed lỗi (splash error)
    
    Args:
        error_message: Nội dung lỗi
        footer_text: Footer text (optional)
    
    Returns:
        discord.Embed object (màu đỏ)
    
    Ví dụ:
        embed = create_error_splash("User không tồn tại!")
        await ctx.send(embed=embed)
    """
    import discord
    
    embed = discord.Embed(
        title="❌ Lỗi",
        description=error_message,
        color=discord.Color.red()
    )
    
    if footer_text:
        embed.set_footer(text=footer_text)
    
    return embed


def create_success_splash(title: str, description: str = None, 
                         fields: Dict[str, str] = None) -> 'discord.Embed':
    """
    Tạo embed thành công (splash success)
    
    Args:
        title: Tiêu đề
        description: Mô tả
        fields: Dict fields
    
    Returns:
        discord.Embed object (màu xanh)
    
    Ví dụ:
        embed = create_success_splash(
            title="✅ Tạo Người Dùng",
            description="Người dùng JohnDoe đã được tạo",
            fields={'ID': '12345', 'Role': 'user'}
        )
        await ctx.send(embed=embed)
    """
    import discord
    
    embed = discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=discord.Color.green()
    )
    
    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=True)
    
    return embed


def create_info_splash(title: str, description: str = None,
                      fields: Dict[str, str] = None) -> 'discord.Embed':
    """
    Tạo embed thông tin (splash info)
    
    Args:
        title: Tiêu đề
        description: Mô tả
        fields: Dict fields
    
    Returns:
        discord.Embed object (màu xanh dương)
    
    Ví dụ:
        embed = create_info_splash(
            title="📋 Danh Sách Quyền",
            description="Permissions của command ban",
            fields={'Role 1': 'Admin', 'Role 2': 'Moderator'}
        )
        await ctx.send(embed=embed)
    """
    import discord
    
    embed = discord.Embed(
        title=f"📋 {title}",
        description=description,
        color=discord.Color.blue()
    )
    
    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=True)
    
    return embed


def create_warning_splash(title: str, description: str = None,
                         fields: Dict[str, str] = None) -> 'discord.Embed':
    """
    Tạo embed cảnh báo (splash warning)
    
    Args:
        title: Tiêu đề
        description: Mô tả
        fields: Dict fields
    
    Returns:
        discord.Embed object (màu cam)
    
    Ví dụ:
        embed = create_warning_splash(
            title="Không Tìm Thấy",
            description="User không tồn tại trong database",
            fields={'User ID': '12345', 'Status': 'Not Found'}
        )
        await ctx.send(embed=embed)
    """
    import discord
    
    embed = discord.Embed(
        title=f"⚠️ {title}",
        description=description,
        color=discord.Color.orange()
    )
    
    if fields:
        for name, value in fields.items():
            embed.add_field(name=name, value=value, inline=True)
    
    return embed
