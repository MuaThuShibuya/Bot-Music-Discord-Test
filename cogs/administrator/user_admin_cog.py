from discord.ext import commands

from cogs.admin_command_utils import AdminCommandBase, create_error_splash, create_success_splash


class AdministratorUserAdminCog(AdminCommandBase):
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

    @commands.command(name="addpoints")
    async def add_points(self, ctx, *args):
        if not await self.require_role_or_admin_ctx(ctx, "addpoints"):
            return
        if len(args) == 2:
            action = "add"
            raw_member, raw_amount = args
        elif len(args) == 3:
            action = self.ACTIONS.get(args[0].lower())
            raw_member, raw_amount = args[1], args[2]
            if not action:
                await ctx.send(embed=create_error_splash("❌ Sai Hành Động", "Dùng `a/add`, `r/rm/remove/d/delete` hoặc `e/edit`."))
                return
        else:
            await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `addpoints @user <amount>` hoặc `addpoints a/r/e @user <amount>` (`r` có thể viết `rm/remove/d/delete`)."))
            return

        try:
            member = await commands.MemberConverter().convert(ctx, raw_member)
            amount = int(str(raw_amount).replace(",", "").replace(".", ""))
            if action == "edit":
                if amount < 0:
                    raise ValueError("Points không thể âm")
            elif amount <= 0:
                raise ValueError("Points phải lớn hơn 0")
            if action in {"add", "edit"}:
                self.users.get_or_create_user(member.id, member.display_name, ctx.guild.id)
            if action == "add":
                self.users.add_points(member.id, amount, ctx.guild.id)
                title = "✅ Cộng Points Thành Công"
                detail = f"Đã cộng `{amount:,}` points cho {member.mention}."
            elif action == "remove":
                self.users.remove_points(member.id, amount, ctx.guild.id)
                title = "✅ Trừ Points Thành Công"
                detail = f"Đã trừ `{amount:,}` points của {member.mention}."
            else:
                self.users.set_points(member.id, amount, ctx.guild.id)
                title = "✅ Sửa Points Thành Công"
                detail = f"Đã set points của {member.mention} thành `{amount:,}`."
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Cập Nhật Thất Bại", str(exc)))
            return

        current_points = self.users.get_user(member.id, ctx.guild.id).points
        await ctx.send(embed=create_success_splash(title, f"{detail}\nPoints hiện tại: `{int(current_points):,}`"))


async def setup(bot):
    await bot.add_cog(AdministratorUserAdminCog(bot))
