from discord.ext import commands

from services.admin_service import AdminService
from services.guild_settings_service import GuildSettingsService
from services.role_permission_service import RolePermissionService, normalize_permission_key
from utils import create_error_splash


class RoleCommandBase(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._service = None
        self._admins = None
        self._guild_settings = None

    @property
    def service(self) -> RolePermissionService:
        if self._service is None:
            self._service = RolePermissionService()
        return self._service

    @property
    def admins(self) -> AdminService:
        if self._admins is None:
            self._admins = AdminService()
        return self._admins

    @property
    def guild_settings(self) -> GuildSettingsService:
        if self._guild_settings is None:
            self._guild_settings = GuildSettingsService()
        return self._guild_settings

    def is_admin(self, target) -> bool:
        user = getattr(target, "author", None) or getattr(target, "user", None)
        guild = getattr(target, "guild", None)
        guild_id = guild.id if guild else None
        return bool(user and self.admins.is_admin(user.id, guild_id))

    def can_use_role_or_admin(self, ctx, command_name: str) -> bool:
        resolved_command = normalize_permission_key(command_name)
        if resolved_command == "cash":
            if ctx.guild is None:
                return False
            if self.admins.is_cash_admin(ctx.author.id, ctx.guild.id):
                return True
            user_roles = [role.id for role in ctx.author.roles if role.name != "@everyone"]
            return self.service.user_can_use(ctx.guild.id, user_roles, "cash")
        if self.is_admin(ctx):
            return True
        if ctx.guild is None:
            return False
        user_roles = [role.id for role in ctx.author.roles if role.name != "@everyone"]
        return self.service.user_can_use(ctx.guild.id, user_roles, resolved_command)

    async def require_admin_ctx(self, ctx, message: str = "Chỉ bot admin mới được dùng lệnh này.") -> bool:
        if self.is_admin(ctx):
            return True
        await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", message))
        return False

    async def require_role_or_admin_ctx(self, ctx, command_name: str | None = None) -> bool:
        resolved_command = normalize_permission_key(command_name or getattr(ctx.command, "name", "") or "")
        if self.can_use_role_or_admin(ctx, resolved_command):
            return True
        await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", f"Chỉ bot admin hoặc role có quyền `{resolved_command}` trong DB mới dùng được lệnh này."))
        return False
