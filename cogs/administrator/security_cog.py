from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin_command_utils import AdminCommandBase
from utils import create_error_splash, create_success_splash


RAID_JOIN_LIMIT = 6
RAID_WINDOW_SECONDS = 12
NUKE_ACTION_LIMIT = 4
NUKE_WINDOW_SECONDS = 20
AUDIT_LOOKBACK_SECONDS = 35

ON_VALUES = {"on", "bat", "bật", "true", "1", "enable", "enabled"}
OFF_VALUES = {"off", "tat", "tắt", "false", "0", "disable", "disabled"}


class AdministratorSecurityCog(AdminCommandBase):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self._join_windows: dict[int, deque[float]] = defaultdict(deque)
        self._nuke_windows: dict[tuple[int, int], deque[float]] = defaultdict(deque)

    def _resolve_mode(self, raw_mode: str | None, current_enabled: bool) -> bool:
        if raw_mode is None:
            return not current_enabled
        cleaned = raw_mode.strip().lower()
        if cleaned in ON_VALUES:
            return True
        if cleaned in OFF_VALUES:
            return False
        raise ValueError("Chỉ dùng `on/off` hoặc gõ lại lệnh để bật/tắt.")

    async def _send_status_ctx(self, ctx: commands.Context, feature_name: str, enabled: bool):
        status_text = "đã bật" if enabled else "đã tắt"
        await ctx.send(
            embed=create_success_splash(
                f"{feature_name} {status_text}",
                f"{feature_name} {status_text} cho server **{ctx.guild.name}**.",
            )
        )

    async def _send_status_interaction(self, interaction: discord.Interaction, feature_name: str, enabled: bool):
        status_text = "đã bật" if enabled else "đã tắt"
        await interaction.response.send_message(
            embed=create_success_splash(
                f"{feature_name} {status_text}",
                f"{feature_name} {status_text} cho server **{interaction.guild.name}**.",
            ),
            ephemeral=True,
        )

    @commands.command(name="antiraid")
    async def antiraid_prefix(self, ctx: commands.Context, mode: str | None = None):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("Lệnh này chỉ dùng trong server."))
            return
        if not await self.require_role_or_admin_ctx(ctx, "antiraid"):
            return

        try:
            enabled = self._resolve_mode(mode, self.guild_settings.is_antiraid_enabled(ctx.guild.id))
        except ValueError as exc:
            await ctx.send(embed=create_error_splash(str(exc)))
            return
        self.guild_settings.set_antiraid(ctx.guild.id, enabled)
        await self._send_status_ctx(ctx, "Anti Raid", enabled)

    @commands.command(name="antinuke")
    async def antinuke_prefix(self, ctx: commands.Context, mode: str | None = None):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("Lệnh này chỉ dùng trong server."))
            return
        if not await self.require_role_or_admin_ctx(ctx, "antinuke"):
            return

        try:
            enabled = self._resolve_mode(mode, self.guild_settings.is_antinuke_enabled(ctx.guild.id))
        except ValueError as exc:
            await ctx.send(embed=create_error_splash(str(exc)))
            return
        self.guild_settings.set_antinuke(ctx.guild.id, enabled)
        await self._send_status_ctx(ctx, "Anti Nuke", enabled)

    @app_commands.command(name="antiraid", description="Bật/tắt chống raid trong server")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def antiraid_slash(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Lệnh này chỉ dùng trong server.", ephemeral=True)
            return
        if not await self.require_role_or_admin_interaction(interaction, "antiraid"):
            return
        enabled = mode.value == "on"
        self.guild_settings.set_antiraid(interaction.guild.id, enabled)
        await self._send_status_interaction(interaction, "Anti Raid", enabled)

    @app_commands.command(name="antinuke", description="Bật/tắt chống nuke trong server")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="on", value="on"),
            app_commands.Choice(name="off", value="off"),
        ]
    )
    async def antinuke_slash(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Lệnh này chỉ dùng trong server.", ephemeral=True)
            return
        if not await self.require_role_or_admin_interaction(interaction, "antinuke"):
            return
        enabled = mode.value == "on"
        self.guild_settings.set_antinuke(interaction.guild.id, enabled)
        await self._send_status_interaction(interaction, "Anti Nuke", enabled)

    async def _notify_security(self, guild: discord.Guild, title: str, description: str, color: discord.Color):
        if guild.me is None:
            return
        channel = guild.system_channel
        if channel is None or not channel.permissions_for(guild.me).send_messages:
            channel = next(
                (
                    text_channel
                    for text_channel in guild.text_channels
                    if text_channel.permissions_for(guild.me).send_messages
                    and text_channel.permissions_for(guild.me).embed_links
                ),
                None,
            )
        if channel is None:
            return
        embed = discord.Embed(title=title, description=description, color=color)
        embed.set_footer(text="Security")
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    async def _find_audit_actor(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int | None = None,
    ) -> Optional[discord.abc.User]:
        if guild.me is None or not guild.me.guild_permissions.view_audit_log:
            return None
        now = datetime.now(timezone.utc)
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                if (now - entry.created_at).total_seconds() > AUDIT_LOOKBACK_SECONDS:
                    continue
                if target_id is not None and getattr(entry.target, "id", None) != target_id:
                    continue
                return entry.user
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    def _can_punish_actor(self, guild: discord.Guild, actor: discord.abc.User | None) -> bool:
        if actor is None or actor.bot:
            return False
        if actor.id == guild.owner_id:
            return False
        if self.admins.is_hard_admin(actor.id):
            return False
        return True

    async def _register_nuke_action(
        self,
        guild: discord.Guild,
        actor: discord.abc.User | None,
        action_text: str,
    ):
        if not self.guild_settings.is_antinuke_enabled(guild.id):
            return
        if not self._can_punish_actor(guild, actor):
            return

        now = datetime.now(timezone.utc).timestamp()
        key = (guild.id, actor.id)
        window = self._nuke_windows[key]
        window.append(now)
        while window and now - window[0] > NUKE_WINDOW_SECONDS:
            window.popleft()
        if len(window) < NUKE_ACTION_LIMIT:
            return

        window.clear()
        member = guild.get_member(actor.id)
        description = (
            f"{actor.mention} vừa thao tác quá nhanh: **{action_text}**.\n"
            f"Ngưỡng: `{NUKE_ACTION_LIMIT}` hành động / `{NUKE_WINDOW_SECONDS}s`."
        )
        punished = False
        if (
            member is not None
            and guild.me is not None
            and guild.me.guild_permissions.ban_members
            and member.top_role < guild.me.top_role
        ):
            try:
                await guild.ban(member, reason="Anti Nuke: thao tác phá server quá nhanh")
                punished = True
            except (discord.Forbidden, discord.HTTPException):
                punished = False

        if punished:
            description += "\nBot đã ban user này để chặn nuke."
            color = discord.Color.red()
        else:
            description += "\nBot chưa thể ban user này. Hãy kiểm tra quyền `Ban Members` và thứ tự role."
            color = discord.Color.orange()
        await self._notify_security(guild, "🛡️ Anti Nuke", description, color)

    async def _handle_audit_action(
        self,
        guild: discord.Guild,
        audit_action: discord.AuditLogAction,
        action_text: str,
        target_id: int | None = None,
    ):
        actor = await self._find_audit_actor(guild, audit_action, target_id)
        await self._register_nuke_action(guild, actor, action_text)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if not self.guild_settings.is_antiraid_enabled(guild.id):
            return

        now = datetime.now(timezone.utc).timestamp()
        window = self._join_windows[guild.id]
        window.append(now)
        while window and now - window[0] > RAID_WINDOW_SECONDS:
            window.popleft()
        if len(window) < RAID_JOIN_LIMIT:
            return

        description = (
            f"Server đang có `{len(window)}` lượt join trong `{RAID_WINDOW_SECONDS}s`.\n"
            f"User mới nhất: {member.mention} (`{member.id}`)."
        )
        kicked = False
        if guild.me and guild.me.guild_permissions.kick_members:
            try:
                await member.kick(reason="Anti Raid: join quá nhanh")
                kicked = True
            except (discord.Forbidden, discord.HTTPException):
                kicked = False
        if kicked:
            description += "\nBot đã kick user mới nhất để giảm tốc raid."
        else:
            description += "\nBot chưa kick được user mới nhất. Hãy kiểm tra quyền `Kick Members`."
        await self._notify_security(guild, "🚨 Anti Raid", description, discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await self._handle_audit_action(channel.guild, discord.AuditLogAction.channel_create, "Tạo channel", channel.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await self._handle_audit_action(channel.guild, discord.AuditLogAction.channel_delete, "Xoá channel", channel.id)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if before.name == after.name and getattr(before, "position", None) == getattr(after, "position", None):
            return
        await self._handle_audit_action(after.guild, discord.AuditLogAction.channel_update, "Sửa channel", after.id)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await self._handle_audit_action(role.guild, discord.AuditLogAction.role_create, "Tạo role", role.id)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._handle_audit_action(role.guild, discord.AuditLogAction.role_delete, "Xoá role", role.id)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if before.name == after.name and before.permissions == after.permissions and before.position == after.position:
            return
        await self._handle_audit_action(after.guild, discord.AuditLogAction.role_update, "Sửa role", after.id)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self._handle_audit_action(guild, discord.AuditLogAction.ban, "Ban member", user.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        before_roles = {role.id for role in before.roles}
        after_roles = {role.id for role in after.roles}
        if before_roles == after_roles:
            return
        await self._handle_audit_action(after.guild, discord.AuditLogAction.member_role_update, "Sửa role member", after.id)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if before.name == after.name and before.icon == after.icon and before.banner == after.banner:
            return
        await self._handle_audit_action(after, discord.AuditLogAction.guild_update, "Sửa server", after.id)


async def setup(bot):
    await bot.add_cog(AdministratorSecurityCog(bot))
