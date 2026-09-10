import discord
from discord.ext import commands

from cogs.admin_command_utils import AdminCommandBase, create_error_splash, create_success_splash, format_hours


class AdministratorTimeCog(AdminCommandBase):
    ACTIONS = {
        "a": "add",
        "add": "add",
        "d": "remove",
        "del": "remove",
        "delete": "remove",
        "r": "remove",
        "rm": "remove",
        "remove": "remove",
        "e": "edit",
        "edit": "edit",
    }

    @commands.command(name="addtime")
    async def addtime(self, ctx, *args):
        if len(args) == 2:
            action = "add"
            raw_member, raw_hours = args
        elif len(args) == 3:
            action = self.ACTIONS.get(args[0].lower())
            raw_member, raw_hours = args[1], args[2]
            if not action:
                await ctx.send(embed=create_error_splash("❌ Sai Hành Động", "Dùng `a/add`, `r/rm/remove/d/delete` hoặc `e/edit`."))
                return
        else:
            await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `addtime @user <hours>` hoặc `addtime a/r/e @user <hours>` (`r` có thể viết `rm/remove/d/delete`)."))
            return

        if not await self.require_role_or_admin_ctx(ctx, "addtime"):
            return

        try:
            member = await commands.MemberConverter().convert(ctx, raw_member)
            hours = float(str(raw_hours).replace(",", "."))
            if action == "edit":
                if hours < 0:
                    raise ValueError("Giờ không thể âm")
            elif hours <= 0:
                raise ValueError("Giờ phải lớn hơn 0")
            if action in {"add", "edit"}:
                self.users.get_or_create_user(member.id, member.display_name)
            if action == "add":
                self.users.add_hours(member.id, hours)
                title = "✅ Cộng Giờ Thành Công"
                detail = f"Đã cộng `{format_hours(hours)}` cho {member.mention}."
            elif action == "remove":
                self.users.remove_hours(member.id, hours)
                title = "✅ Trừ Giờ Thành Công"
                detail = f"Đã trừ `{format_hours(hours)}` của {member.mention}."
            else:
                self.users.set_hours(member.id, hours)
                title = "✅ Sửa Giờ Thành Công"
                detail = f"Đã set giờ của {member.mention} thành `{format_hours(hours)}`."
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Cập Nhật Thất Bại", str(exc)))
            return

        current_hours = self.users.get_user(member.id).total_hours
        await ctx.send(embed=create_success_splash(title, f"{detail}\nGiờ hiện tại: `{format_hours(current_hours)}`"))

    @commands.command(name="subtime")
    async def subtime(self, ctx, member: discord.Member, hours: float):
        await self.send_stat_update(ctx, member, hours, "total_hours", "Trừ giờ")


async def setup(bot):
    await bot.add_cog(AdministratorTimeCog(bot))
