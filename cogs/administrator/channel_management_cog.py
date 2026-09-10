from __future__ import annotations

import discord
from discord.ext import commands

from cogs.admin_command_utils import AdminCommandBase, create_error_splash, create_success_splash


class ChannelManagementCog(AdminCommandBase):
    async def _set_channel_lock(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel | None,
        locked: bool,
    ):
        command_name = "lock" if locked else "unlock"
        if not await self.require_role_or_admin_ctx(ctx, command_name):
            return
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh này chỉ hoạt động trong server."))
            return
        target = channel or ctx.channel
        if not isinstance(target, discord.TextChannel):
            await ctx.send(embed=create_error_splash("❌ Kênh Không Hợp Lệ", "Chỉ có thể khoá text channel."))
            return

        overwrite = target.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False if locked else None
        try:
            await target.set_permissions(
                ctx.guild.default_role,
                overwrite=overwrite,
                reason=f"{command_name} bởi {ctx.author} ({ctx.author.id})",
            )
        except discord.Forbidden:
            await ctx.send(embed=create_error_splash("❌ Thiếu Quyền", "Bot cần quyền Manage Channels để thực hiện."))
            return
        except discord.HTTPException as exc:
            await ctx.send(embed=create_error_splash("❌ Thao Tác Thất Bại", str(exc)))
            return

        action = "khoá" if locked else "mở khoá"
        await ctx.send(embed=create_success_splash(f"✅ Đã {action.title()} Kênh", f"Đã {action} {target.mention}."))

    @commands.command(name="lock")
    @commands.guild_only()
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        await self._set_channel_lock(ctx, channel, True)

    @commands.command(name="unlock")
    @commands.guild_only()
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel | None = None):
        await self._set_channel_lock(ctx, channel, False)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelManagementCog(bot))
