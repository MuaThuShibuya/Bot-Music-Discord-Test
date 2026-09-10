"""
Role Permission Service
- Quản lý quyền commands theo role
- Sử dụng RolePermissionManager từ utils.py
"""

from utils import RolePermissionManager
from typing import List, Dict


ROLE_PERMISSION_GROUP = {
    "role",
    "addrole",
    "addadmin",
    "addcashadmin",
    "themrole",
    "removerole",
    "rmadmin",
    "rmcashadmin",
    "rmrole",
    "xoarole",
    "setrole",
    "perms",
    "myroles",
    "rolescommands",
}


def normalize_permission_key(command_name: str | None) -> str:
    """Chuẩn hóa command key, hỗ trợ cả subcommand dạng `level setup`."""
    return " ".join(str(command_name or "").strip().lower().split())


def permission_parent_keys(command_name: str) -> list[str]:
    """Trả về các key cha gần nhất, ví dụ `level setup xp` -> [`level setup`, `level`]."""
    parts = normalize_permission_key(command_name).split()
    return [" ".join(parts[:index]) for index in range(len(parts) - 1, 0, -1)]


class RolePermissionService:
    """Service quản lý quyền commands theo role"""
    
    def __init__(self):
        self.manager = RolePermissionManager()
    
    def add_command_role(
        self,
        guild_id: int,
        role_id: int,
        command_name: str,
        created_by: int,
        role_name: str | None = None,
    ) -> bool:
        """
        Thêm role cho command
        
        Args:
            guild_id: Server ID
            role_id: Role ID
            command_name: Tên command
            created_by: User ID người tạo
        
        Returns:
            True nếu thành công
        
        Ví dụ:
            service.add_command_role(123456, 987654, 'ban', 111111)
            → Role 987654 được dùng lệnh 'ban' trên server 123456
        """
        normalized_command = normalize_permission_key(command_name)
        if normalized_command in ROLE_PERMISSION_GROUP:
            normalized_command = "role"

        return self.manager.add_permission(
            guild_id=guild_id,
            role_id=role_id,
            command_name=normalized_command,
            created_by=created_by,
            role_name=role_name,
        )

    def save_role(self, guild_id: int, role_id: int, role_name: str, hierarchy_level: int = 0) -> bool:
        """Lưu tên role để các lệnh kiểm tra quyền hiển thị dễ đọc hơn."""
        return self.manager.add_role_hierarchy(
            guild_id=guild_id,
            role_id=role_id,
            role_name=role_name,
            hierarchy_level=hierarchy_level,
        )
    
    def remove_command_role(self, guild_id: int, role_id: int, command_name: str) -> bool:
        """
        Xóa role khỏi command
        
        Args:
            guild_id: Server ID
            role_id: Role ID
            command_name: Tên command
        
        Returns:
            True nếu thành công
        
        Ví dụ:
            service.remove_command_role(123456, 987654, 'ban')
            → Role 987654 không được dùng lệnh 'ban' nữa
        """
        normalized_command = normalize_permission_key(command_name)
        if normalized_command in ROLE_PERMISSION_GROUP:
            success = True
            for grouped_command in ROLE_PERMISSION_GROUP:
                success = self.manager.remove_permission(guild_id, role_id, grouped_command) and success
            return success

        return self.manager.remove_permission(
            guild_id=guild_id,
            role_id=role_id,
            command_name=normalized_command
        )
    
    def user_can_use(self, guild_id: int, user_roles: List[int], command_name: str) -> bool:
        """
        Check user có thể dùng command không
        
        Args:
            guild_id: Server ID
            user_roles: List role IDs của user
            command_name: Tên command
        
        Returns:
            True nếu user có ít nhất 1 role có quyền
        
        Ví dụ:
            user_roles = [123, 456, 789]
            can_use = service.user_can_use(100, user_roles, 'ban')
            → Nếu role 456 hoặc role nào có quyền 'ban' thì return True
        """
        normalized_command = normalize_permission_key(command_name)
        if normalized_command in ROLE_PERMISSION_GROUP:
            return any(
                self.manager.can_use_command(guild_id, user_roles, grouped_command)
                for grouped_command in ROLE_PERMISSION_GROUP
            )

        command_keys = [normalized_command] + permission_parent_keys(normalized_command)
        return any(
            self.manager.can_use_command(
                guild_id=guild_id,
                user_roles=user_roles,
                command_name=command_key,
            )
            for command_key in command_keys
        )

    def command_has_permission(self, guild_id: int, command_name: str) -> bool:
        """Check command key đã được set role trực tiếp trong DB chưa."""
        normalized_command = normalize_permission_key(command_name)
        return bool(self.manager.get_roles_for_command(guild_id, normalized_command))
    
    def get_roles_for_command(self, guild_id: int, command_name: str) -> List[Dict]:
        """
        Lấy danh sách roles có quyền dùng command
        
        Args:
            guild_id: Server ID
            command_name: Tên command
        
        Returns:
            List dict [{'role_id': 123, 'role_name': 'Admin'}, ...]
        """
        normalized_command = normalize_permission_key(command_name)
        if normalized_command in ROLE_PERMISSION_GROUP:
            roles_by_id = {}
            for grouped_command in ROLE_PERMISSION_GROUP:
                for role in self.manager.get_roles_for_command(guild_id, grouped_command):
                    roles_by_id[role["role_id"]] = role
            return list(roles_by_id.values())

        return self.manager.get_roles_for_command(guild_id, normalized_command)
    
    def get_commands_for_role(self, guild_id: int, role_id: int) -> List[str]:
        """
        Lấy danh sách commands mà role có quyền
        
        Args:
            guild_id: Server ID
            role_id: Role ID
        
        Returns:
            List tên commands
        """
        commands = self.manager.get_commands_for_role(guild_id, role_id)
        if any(command_name in ROLE_PERMISSION_GROUP for command_name in commands):
            commands = [command_name for command_name in commands if command_name not in ROLE_PERMISSION_GROUP]
            commands.insert(0, "role")
        return commands
