import discord
from discord.ext import commands

from cogs.admin_command_utils import AdminCommandBase, create_error_splash, create_success_splash
from services.booking_service import BookingService


class AdministratorCapRoleCog(AdminCommandBase):
    ACTIONS = {
        "a": "add",
        "add": "add",
        "them": "add",
        "thêm": "add",
        "cap": "add",
        "cấp": "add",
        "d": "remove",
        "r": "remove",
        "delete": "remove",
        "del": "remove",
        "rm": "remove",
        "remove": "remove",
        "xoa": "remove",
        "xóa": "remove",
        "go": "remove",
        "gỡ": "remove",
    }

    async def _resolve_role(self, ctx, raw_role: str) -> discord.Role | None:
        try:
            return await commands.RoleConverter().convert(ctx, raw_role)
        except Exception:
            await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy Role", "Hãy nhập role mention, tên role hoặc role ID hợp lệ."))
            return None

    async def _validate_role_action(self, ctx, role: discord.Role) -> bool:
        if role == ctx.guild.default_role:
            await ctx.send(embed=create_error_splash("❌ Role Không Hợp Lệ", "Không thể cấp hoặc gỡ role `@everyone`."))
            return False
        if role.managed:
            await ctx.send(embed=create_error_splash("❌ Role Không Hợp Lệ", "Không thể cấp hoặc gỡ role được quản lý bởi integration/bot khác."))
            return False

        bot_member = ctx.guild.me or ctx.guild.get_member(self.bot.user.id)
        if not bot_member:
            await ctx.send(embed=create_error_splash("❌ Lỗi Bot", "Không lấy được thông tin bot trong server."))
            return False
        if not bot_member.guild_permissions.manage_roles:
            await ctx.send(embed=create_error_splash("❌ Thiếu Quyền Discord", "Bot cần quyền `Manage Roles` để cấp/gỡ role."))
            return False
        if role >= bot_member.top_role:
            await ctx.send(embed=create_error_splash("❌ Sai Thứ Tự Role", f"Role {role.mention} phải thấp hơn role cao nhất của bot."))
            return False
        return True

    def _is_booking_system_role(self, ctx, role: discord.Role) -> bool:
        system_role = self.guild_settings.get_system_role(ctx.guild.id, "booking")
        return bool(system_role and int(system_role["role_id"]) == int(role.id))

    def _sync_booking_member_if_needed(self, ctx, member: discord.Member, role: discord.Role) -> str:
        if member.bot or not self._is_booking_system_role(ctx, role):
            return ""
        BookingService(ctx.guild.id).get_or_create_booking(member.id, member.display_name)
        return "\nĐã sync user vào `booking.db` vì role này là role `booking`."

    @commands.command(name="role")
    async def caprole(self, ctx, action: str = None, member: discord.Member = None, *, raw_role: str = None):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh `role` chỉ hoạt động trong server."))
            return
        if not await self.require_role_or_admin_ctx(ctx, "role"):
            return

        if not action or not member or not raw_role:
            await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `role a/add @user @role` để cấp hoặc `role r/rm/remove/d/delete @user @role` để gỡ."))
            return

        normalized_action = self.ACTIONS.get(action.strip().lower())
        if not normalized_action:
            await ctx.send(embed=create_error_splash("❌ Sai Hành Động", "Hành động hợp lệ: `a/add` để cấp role, `r/rm/remove/d/delete` để gỡ role."))
            return

        role = await self._resolve_role(ctx, raw_role)
        if not role:
            return
        if not await self._validate_role_action(ctx, role):
            return

        try:
            if normalized_action == "add":
                if role in member.roles:
                    await ctx.send(embed=create_error_splash("❌ Role Đã Có", f"{member.mention} đã có role {role.mention}."))
                    return
                await member.add_roles(role, reason=f"{ctx.author} dùng lệnh role a")
                sync_text = self._sync_booking_member_if_needed(ctx, member, role)
                await ctx.send(embed=create_success_splash("✅ Cấp Role Thành Công", f"Đã cấp {role.mention} cho {member.mention}.{sync_text}"))
            else:
                if role not in member.roles:
                    await ctx.send(embed=create_error_splash("❌ Chưa Có Role", f"{member.mention} chưa có role {role.mention}."))
                    return
                await member.remove_roles(role, reason=f"{ctx.author} dùng lệnh role r")
                await ctx.send(embed=create_success_splash("✅ Gỡ Role Thành Công", f"Đã gỡ {role.mention} khỏi {member.mention}."))
        except discord.Forbidden:
            await ctx.send(embed=create_error_splash("❌ Thiếu Quyền Discord", "Discord từ chối thao tác. Hãy kiểm tra quyền `Manage Roles` và thứ tự role của bot."))
        except discord.HTTPException as exc:
            await ctx.send(embed=create_error_splash("❌ Thao Tác Thất Bại", str(exc)))


async def setup(bot):
    await bot.add_cog(AdministratorCapRoleCog(bot))
