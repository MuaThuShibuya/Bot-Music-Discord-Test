from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin_command_utils import AdminCommandBase
from services.command_toggle_service import ChannelCommandToggleService, normalize_channel_command
from utils import create_error_splash


ACTION_ENABLE = {"enable", "on", "bat", "bật", "mo", "mở"}
ACTION_DISABLE = {"disable", "off", "tat", "tắt", "khoa", "khóa"}


class CommandToggleCog(AdminCommandBase):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.channel_commands = ChannelCommandToggleService()

    def cog_unload(self):
        self.channel_commands.close()

    def _canonical_command(self, raw_command: str) -> str | None:
        normalized = normalize_channel_command(raw_command)
        if not normalized:
            return None
        parts = normalized.split(" ")
        command = self.bot.get_command(parts[0])
        if command is None:
            slash_names = {item.name.lower() for item in self.bot.tree.get_commands()}
            if parts[0] not in slash_names:
                return None
            canonical_root = parts[0]
        else:
            canonical_root = command.root_parent.name if command.root_parent else command.name
        return " ".join([canonical_root.lower(), *parts[1:]])

    async def _change_prefix(self, ctx: commands.Context, action: str, raw_command: str):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Bật/tắt lệnh theo kênh chỉ dùng trong server."))
            return
        if not await self.require_role_or_admin_ctx(ctx, "command"):
            return

        command_name = self._canonical_command(raw_command)
        if not command_name:
            await ctx.send(embed=create_error_splash("❌ Lệnh Không Tồn Tại", f"Không tìm thấy lệnh `{raw_command}`."))
            return

        if action in ACTION_DISABLE:
            self.channel_commands.disable(ctx.guild.id, ctx.channel.id, command_name, ctx.author.id)
            await ctx.send(f"⛔ | Lệnh ||{command_name}|| đã bị tắt trong {ctx.channel.mention}.")
            return

        removed = self.channel_commands.enable(ctx.guild.id, ctx.channel.id, command_name)
        if removed:
            await ctx.send(f"✅ | Lệnh ||{command_name}|| đã được bật trong {ctx.channel.mention}.")
        else:
            await ctx.send(f"✅ | Lệnh ||{command_name}|| vốn đang được bật trong {ctx.channel.mention}.")

    @commands.command(name="command", aliases=["cmd"])
    async def command_toggle(self, ctx: commands.Context, action: str | None = None, *, command_name: str = ""):
        cleaned_action = str(action or "").strip().lower()
        if cleaned_action not in ACTION_ENABLE | ACTION_DISABLE or not command_name.strip():
            await ctx.send("Dùng: `command enable <lệnh>` hoặc `command disable <lệnh>`. Có thể dùng trực tiếp `enable/disable <lệnh>`.")
            return
        await self._change_prefix(ctx, cleaned_action, command_name)

    @commands.command(name="enable")
    async def enable_command(self, ctx: commands.Context, *, command_name: str):
        await self._change_prefix(ctx, "enable", command_name)

    @commands.command(name="disable")
    async def disable_command(self, ctx: commands.Context, *, command_name: str):
        await self._change_prefix(ctx, "disable", command_name)

    @app_commands.command(name="command", description="Bật hoặc tắt một lệnh trong channel hiện tại")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="enable", value="enable"),
            app_commands.Choice(name="disable", value="disable"),
        ]
    )
    @app_commands.describe(action="Chọn bật hoặc tắt", command_name="Tên lệnh, ví dụ ga hoặc level setup")
    async def command_slash(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        command_name: str,
    ):
        if interaction.guild is None or interaction.channel is None:
            await interaction.response.send_message("❌ Lệnh này chỉ dùng trong server.", ephemeral=True)
            return
        if not await self.require_role_or_admin_interaction(interaction, "command"):
            return

        canonical = self._canonical_command(command_name)
        if not canonical:
            await interaction.response.send_message(f"❌ Không tìm thấy lệnh `{command_name}`.", ephemeral=True)
            return

        if action.value == "disable":
            self.channel_commands.disable(interaction.guild.id, interaction.channel.id, canonical, interaction.user.id)
            message = f"⛔ | Lệnh ||{canonical}|| đã bị tắt trong {interaction.channel.mention}."
        else:
            removed = self.channel_commands.enable(interaction.guild.id, interaction.channel.id, canonical)
            state = "đã được bật" if removed else "vốn đang được bật"
            message = f"✅ | Lệnh ||{canonical}|| {state} trong {interaction.channel.mention}."
        await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CommandToggleCog(bot))
