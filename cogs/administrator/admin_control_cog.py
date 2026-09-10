from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin_command_utils import AdminCommandBase
from utils import create_error_splash, create_success_splash


class AdminGuildSelect(discord.ui.Select):
    def __init__(self, cog: "AdminControlCog", requester_id: int, locked: bool, guilds: list[discord.Guild]):
        self.cog = cog
        self.requester_id = int(requester_id)
        self.locked = bool(locked)
        action_text = "khoá" if locked else "mở"
        options = [
            discord.SelectOption(
                label=guild.name[:100],
                value=str(guild.id),
                description=f"ID {guild.id} • {guild.member_count or 0} members"[:100],
                emoji="🏠",
            )
            for guild in guilds[:25]
        ]
        super().__init__(
            placeholder=f"Chọn server để {action_text} quyền dùng lệnh...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message(
                embed=create_error_splash("Menu này không phải của bạn."),
                ephemeral=True,
            )
            return
        if not self.cog._is_hard_admin(interaction.user):
            await interaction.response.send_message(
                embed=create_error_splash("Chỉ hard admin mới dùng được lệnh này."),
                ephemeral=True,
            )
            return

        guild = self.cog.bot.get_guild(int(self.values[0]))
        if guild is None:
            await interaction.response.edit_message(
                embed=create_error_splash("Bot không còn ở server này."),
                view=None,
            )
            return

        self.cog.guild_settings.set_commands_locked(guild.id, self.locked)
        await interaction.response.edit_message(
            embed=self.cog.create_command_lock_embed(guild, self.locked),
            view=None,
        )


class AdminGuildSelectView(discord.ui.View):
    def __init__(self, cog: "AdminControlCog", requester_id: int, locked: bool, guilds: list[discord.Guild]):
        super().__init__(timeout=300)
        self.add_item(AdminGuildSelect(cog, requester_id, locked, guilds))


class AdminControlCog(AdminCommandBase):
    admin_group = app_commands.Group(name="admin", description="Quản trị bot")

    def _is_hard_admin(self, user: discord.abc.User) -> bool:
        return self.admins.is_hard_admin(user.id)

    def create_command_lock_embed(self, guild: discord.Guild, locked: bool) -> discord.Embed:
        if locked:
            title = "Đã khoá quyền dùng lệnh"
            description = (
                f"Server **{guild.name}** đã khoá command.\n"
                "Non-hardadmin sẽ không dùng được command cho tới khi bật lại."
            )
        else:
            title = "Đã mở quyền dùng lệnh"
            description = f"Command đã hoạt động lại cho server **{guild.name}**."
        return create_success_splash(title, description)

    @admin_group.command(name="command", description="Bật/tắt quyền dùng lệnh")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def command_lock(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        if not self._is_hard_admin(interaction.user):
            await interaction.response.send_message(
                embed=create_error_splash("Chỉ hard admin mới dùng được lệnh này."),
                ephemeral=True,
            )
            return

        locked = mode.value == "off"
        if interaction.guild is not None:
            self.guild_settings.set_commands_locked(interaction.guild.id, locked)
            await interaction.response.send_message(
                embed=self.create_command_lock_embed(interaction.guild, locked),
                ephemeral=True,
            )
            return

        guilds = sorted(self.bot.guilds, key=lambda guild: guild.name.casefold())
        if not guilds:
            await interaction.response.send_message(
                embed=create_error_splash("Bot chưa tham gia server nào để chọn."),
                ephemeral=True,
            )
            return

        action_text = "khoá" if locked else "mở"
        description = f"Chọn server bot đang tham gia để {action_text} quyền dùng lệnh."
        if len(guilds) > 25:
            description += "\nDiscord chỉ cho hiện tối đa 25 server trong một menu."

        await interaction.response.send_message(
            embed=create_success_splash("Chọn server", description),
            view=AdminGuildSelectView(self, interaction.user.id, locked, guilds),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminControlCog(bot))
