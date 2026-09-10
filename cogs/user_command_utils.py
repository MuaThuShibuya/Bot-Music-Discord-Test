from discord.ext import commands

from services.admin_service import AdminService
from services.role_permission_service import RolePermissionService
from services.user_service import UserService
from utils import create_error_splash


class UserCommandBase(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._service = None
        self._admins = None
        self._role_permissions = None

    @property
    def service(self) -> UserService:
        if self._service is None:
            self._service = UserService()
        return self._service

    @property
    def admins(self) -> AdminService:
        if self._admins is None:
            self._admins = AdminService()
        return self._admins

    @property
    def role_permissions(self) -> RolePermissionService:
        if self._role_permissions is None:
            self._role_permissions = RolePermissionService()
        return self._role_permissions

    def can_view_other_profile(self, ctx) -> bool:
        if ctx.guild is None:
            return False
        if self.admins.is_admin(ctx.author.id, ctx.guild.id):
            return True
        user_role_ids = [role.id for role in ctx.author.roles if role.name != "@everyone"]
        return self.role_permissions.user_can_use(ctx.guild.id, user_role_ids, "profile")

    def can_manage_cash(self, target) -> bool:
        guild = getattr(target, "guild", None)
        user = getattr(target, "author", None) or getattr(target, "user", None)
        if guild is None or user is None:
            return False
        if self.admins.is_cash_admin(user.id, guild.id):
            return True
        roles = getattr(user, "roles", [])
        user_role_ids = [role.id for role in roles if role.name != "@everyone"]
        return self.role_permissions.user_can_use(guild.id, user_role_ids, "cash")

    async def require_admin_ctx(self, ctx, message: str = "Chỉ bot admin mới được dùng lệnh này.") -> bool:
        guild_id = ctx.guild.id if ctx.guild else None
        if self.admins.is_admin(ctx.author.id, guild_id):
            return True
        await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", message))
        return False
