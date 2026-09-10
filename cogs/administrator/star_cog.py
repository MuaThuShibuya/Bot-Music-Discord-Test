import discord
from discord.ext import commands

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_success_splash,
    create_warning_splash,
)


class AdministratorStarCog(AdminCommandBase):
    @commands.command(name="addstar")
    async def addstar(self, ctx, member: discord.Member, amount: int):
        await self.send_stat_update(ctx, member, amount, "star", "Cộng star")

    @commands.command(name="substar")
    async def substar(self, ctx, member: discord.Member, amount: int):
        await self.send_stat_update(ctx, member, amount, "star", "Trừ star")

    @commands.command(name="topstar")
    async def topstar(self, ctx, limit: int = 10):
        if not self.can_use_role_or_admin(ctx, "topstar"):
            await ctx.send(embed=create_warning_splash("❌ Quyền Bị Từ Chối", "Chỉ admin hoặc role trong DB mới xem được bảng xếp hạng này."))
            return
        if limit < 1:
            limit = 10
        if limit > 25:
            limit = 25
        rows = self.users.get_top_stars(limit)
        if not rows:
            await ctx.send(embed=create_warning_splash("⚠️ Top Star", "Chưa có dữ liệu star nào trong database."))
            return
        description = [f"**#{index}** `{row['username']}` - `{int(row['star']):,}` star" for index, row in enumerate(rows, 1)]
        await ctx.send(embed=create_success_splash(f"⭐ Top Star ({len(rows)})", "\n".join(description)))


async def setup(bot):
    await bot.add_cog(AdministratorStarCog(bot))
