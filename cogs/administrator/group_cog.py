from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_error_splash,
    create_info_splash,
    create_success_splash,
    create_warning_splash,
)


INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord(?:\.gg|\.com/invite)/|discordapp\.com/invite/)([A-Za-z0-9-]+)",
    re.IGNORECASE,
)


class GroupInputModal(discord.ui.Modal):
    def __init__(self, cog: "AdministratorGroupCog", requester_id: int, mode: str):
        title = "Nhập link server" if mode == "join" else "Nhập server cần rời"
        super().__init__(title=title, timeout=300)
        self.cog = cog
        self.requester_id = int(requester_id)
        self.mode = mode
        self.server_text = discord.ui.TextInput(
            label="Link invite / server ID / tên server",
            placeholder="https://discord.gg/... hoặc 1234567890",
            required=True,
            max_length=300,
        )
        self.add_item(self.server_text)

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.cog.require_admin_interaction_user(interaction, self.requester_id):
            return

        value = str(self.server_text.value).strip()
        if self.mode == "join":
            await self.cog.handle_join_interaction(interaction, value)
        else:
            await self.cog.send_leave_list_interaction(interaction)


class GroupInputView(discord.ui.View):
    def __init__(self, cog: "AdministratorGroupCog", requester_id: int, mode: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.requester_id = int(requester_id)
        self.mode = mode

    @discord.ui.button(label="Nhập server", style=discord.ButtonStyle.primary, emoji="🔗")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.require_admin_interaction_user(interaction, self.requester_id):
            return
        await interaction.response.send_modal(GroupInputModal(self.cog, self.requester_id, self.mode))


class GuildLeaveSelect(discord.ui.Select):
    def __init__(self, cog: "AdministratorGroupCog", requester_id: int, guilds: list[discord.Guild]):
        self.cog = cog
        self.requester_id = int(requester_id)
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
            placeholder="Chọn server để bot rời...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.cog.require_admin_interaction_user(interaction, self.requester_id):
            return
        guild = self.cog.bot.get_guild(int(self.values[0]))
        if not guild:
            await interaction.response.send_message(
                embed=create_error_splash("❌ Không Tìm Thấy Server", "Bot không còn ở server này."),
                ephemeral=True,
            )
            return
        await self.cog.send_leave_confirm_interaction(interaction, guild)


class GuildLeaveListView(discord.ui.View):
    def __init__(self, cog: "AdministratorGroupCog", requester_id: int, guilds: list[discord.Guild]):
        super().__init__(timeout=300)
        self.add_item(GuildLeaveSelect(cog, requester_id, guilds))


class ConfirmLeaveView(discord.ui.View):
    def __init__(self, cog: "AdministratorGroupCog", requester_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.requester_id = int(requester_id)
        self.guild_id = int(guild_id)

    @discord.ui.button(label="Rời server", style=discord.ButtonStyle.danger, emoji="🚪")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.require_admin_interaction_user(interaction, self.requester_id):
            return

        guild = self.cog.bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.edit_message(
                embed=create_error_splash("❌ Không Tìm Thấy Server", "Bot không còn ở server này."),
                view=None,
            )
            return

        guild_name = guild.name
        guild_id = guild.id
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            embed=create_info_splash(
                "🚪 Đang Rời Server",
                f"Bot đang rời `{guild_name}` (`{guild_id}`).\nNếu server được chọn là server hiện tại, bot sẽ không thể chỉnh thêm tin nhắn sau khi rời.",
            ),
            view=self,
        )

        try:
            await guild.leave()
        except discord.HTTPException as exc:
            await interaction.edit_original_response(
                embed=create_error_splash("❌ Leave Thất Bại", str(exc)),
                view=None,
            )
            return

        success_embed = create_success_splash("✅ Đã Rời Server", f"Bot đã rời `{guild_name}` (`{guild_id}`).")
        try:
            await interaction.edit_original_response(embed=success_embed, view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

        try:
            await interaction.user.send(embed=success_embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.cog.require_admin_interaction_user(interaction, self.requester_id):
            return
        await interaction.response.edit_message(
            embed=create_info_splash("Đã Hủy", "Không rời server nào."),
            view=None,
        )


class InviteBotView(discord.ui.View):
    def __init__(self, invite_url: str):
        super().__init__(timeout=None)
        self.add_item(discord.ui.Button(label="Mời bot vào server", style=discord.ButtonStyle.link, url=invite_url, emoji="🔗"))


class AdministratorGroupCog(AdminCommandBase):
    JOIN_ACTIONS = {"join", "j", "vao", "vào", "add", "invite"}
    LEAVE_ACTIONS = {"leave", "leaev", "l", "out", "roi", "rời", "thoat", "thoát", "remove", "rm"}

    def is_admin_user(self, user_id: int, guild_id: int | None = None) -> bool:
        return self.admins.is_admin(int(user_id), guild_id)

    async def require_admin_ctx(self, ctx) -> bool:
        guild_id = ctx.guild.id if ctx.guild else None
        if self.is_admin_user(ctx.author.id, guild_id):
            return True
        await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ bot admin mới được dùng lệnh này."))
        return False

    async def require_admin_interaction_user(self, interaction: discord.Interaction, requester_id: int | None = None) -> bool:
        if requester_id is not None and int(interaction.user.id) != int(requester_id):
            await interaction.response.send_message(
                embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ người mở menu này mới được thao tác."),
                ephemeral=True,
            )
            return False
        guild_id = interaction.guild.id if interaction.guild else None
        if self.is_admin_user(interaction.user.id, guild_id):
            return True
        await interaction.response.send_message(
            embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ bot admin mới được dùng thao tác này."),
            ephemeral=True,
        )
        return False

    @staticmethod
    def _first_invite_text(text: str | None) -> str:
        raw = (text or "").strip()
        match = INVITE_RE.search(raw)
        return match.group(0) if match else raw

    async def _reply_text(self, ctx) -> str:
        reference = getattr(ctx.message, "reference", None)
        if not reference:
            return ""
        message = getattr(reference, "resolved", None)
        if message is None and reference.message_id:
            try:
                message = await ctx.channel.fetch_message(reference.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return ""
        return getattr(message, "content", "") or ""

    def _oauth_url(self, guild_id: int | None = None) -> str:
        permissions = discord.Permissions(administrator=True)
        kwargs = {
            "permissions": permissions,
            "scopes": ("bot", "applications.commands"),
        }
        if guild_id:
            kwargs["guild"] = discord.Object(id=int(guild_id))
            kwargs["disable_guild_select"] = True
        return discord.utils.oauth_url(self.bot.user.id, **kwargs)

    async def _target_guild_from_invite(self, invite_text: str) -> tuple[int | None, str | None]:
        if not INVITE_RE.search(invite_text or ""):
            return None, None
        try:
            invite = await self.bot.fetch_invite(invite_text, with_counts=False, with_expiration=False)
        except discord.HTTPException:
            return None, "Không đọc được invite này, mình sẽ tạo link mời bot dạng chọn server thủ công."

        invite_guild = getattr(invite, "guild", None)
        if invite_guild:
            return int(invite_guild.id), f"Server từ invite: **{invite_guild.name}** (`{invite_guild.id}`)."
        return None, "Không lấy được server từ invite, mình sẽ tạo link mời bot dạng chọn server thủ công."

    async def _resolve_guild(self, raw_text: str, current_guild: discord.Guild | None = None) -> tuple[discord.Guild | None, str | None]:
        raw = self._first_invite_text(raw_text)
        lowered = raw.strip().lower()
        if lowered in {"this", "here", "current", "day", "đây", "server nay", "server này"} and current_guild:
            return current_guild, None

        if raw.isdigit():
            guild = self.bot.get_guild(int(raw))
            if guild:
                return guild, None
            return None, f"Bot không ở server ID `{raw}`."

        invite_guild_id, invite_note = await self._target_guild_from_invite(raw)
        if invite_guild_id:
            guild = self.bot.get_guild(invite_guild_id)
            if guild:
                return guild, None
            return None, f"Bot chưa ở server trong invite này. {invite_note or ''}".strip()

        exact_matches = [guild for guild in self.bot.guilds if guild.name.lower() == lowered]
        if len(exact_matches) == 1:
            return exact_matches[0], None
        if len(exact_matches) > 1:
            ids = ", ".join(f"`{guild.id}`" for guild in exact_matches[:8])
            return None, f"Có nhiều server trùng tên. Hãy dùng ID: {ids}"

        contains_matches = [guild for guild in self.bot.guilds if lowered and lowered in guild.name.lower()]
        if len(contains_matches) == 1:
            return contains_matches[0], None
        if len(contains_matches) > 1:
            names = ", ".join(f"`{guild.name}` (`{guild.id}`)" for guild in contains_matches[:8])
            return None, f"Có nhiều server gần giống: {names}. Hãy dùng ID."

        return None, "Không tìm thấy server. Hãy nhập server ID, tên server bot đang ở, hoặc invite link."

    async def send_join_result_ctx(self, ctx, server_text: str):
        embed, view = await self.build_join_response(server_text)
        await ctx.send(embed=embed, view=view)

    async def handle_join_interaction(self, interaction: discord.Interaction, server_text: str):
        embed, view = await self.build_join_response(server_text)
        await interaction.response.send_message(embed=embed, view=view)

    async def build_join_response(self, server_text: str) -> tuple[discord.Embed, discord.ui.View]:
        target_text = self._first_invite_text(server_text)
        guild_id, note = await self._target_guild_from_invite(target_text)
        if guild_id and self.bot.get_guild(guild_id):
            guild = self.bot.get_guild(guild_id)
            embed = create_info_splash("Bot Đã Ở Server", f"Bot hiện đã ở `{guild.name}` (`{guild.id}`).")
            return embed, InviteBotView(self._oauth_url())

        invite_url = self._oauth_url(guild_id)
        detail = (
            "Discord không cho bot tự join server bằng invite link như user.\n"
            "Hãy bấm nút bên dưới để mở OAuth và add bot vào server."
        )
        if note:
            detail += f"\n{note}"
        embed = create_info_splash("🔗 Link Mời Bot", detail)
        embed.add_field(name="OAuth", value=f"[Mời bot vào server]({invite_url})", inline=False)
        return embed, InviteBotView(invite_url)

    async def send_join_input_ctx(self, ctx):
        await ctx.send(
            embed=create_info_splash("🔗 Nhập Link Server", "Bấm nút bên dưới rồi nhập invite/server link để tạo link mời bot."),
            view=GroupInputView(self, ctx.author.id, "join"),
        )

    async def send_join_input_interaction(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            embed=create_info_splash("🔗 Nhập Link Server", "Bấm nút bên dưới rồi nhập invite/server link để tạo link mời bot."),
            view=GroupInputView(self, interaction.user.id, "join"),
        )

    async def send_leave_list_ctx(self, ctx):
        guilds = sorted(self.bot.guilds, key=lambda guild: guild.name.lower())
        if not guilds:
            await ctx.send(embed=create_info_splash("Không Có Server", "Bot hiện không ở server nào."))
            return

        embed = create_info_splash(
            "🚪 Chọn Server Để Rời",
            "Chọn server bot đang join trong menu bên dưới. Bot sẽ hiện splash xác nhận trước khi rời.",
        )
        await ctx.send(embed=embed, view=GuildLeaveListView(self, ctx.author.id, guilds))

    async def send_leave_list_interaction(self, interaction: discord.Interaction):
        guilds = sorted(self.bot.guilds, key=lambda guild: guild.name.lower())
        if not guilds:
            await interaction.response.send_message(embed=create_info_splash("Không Có Server", "Bot hiện không ở server nào."))
            return

        embed = create_info_splash(
            "🚪 Chọn Server Để Rời",
            "Chọn server bot đang join trong menu bên dưới. Bot sẽ hiện splash xác nhận trước khi rời.",
        )
        await interaction.response.send_message(embed=embed, view=GuildLeaveListView(self, interaction.user.id, guilds))

    async def send_leave_confirm_ctx(self, ctx, guild: discord.Guild):
        embed = create_warning_splash(
            "⚠️ Xác Nhận Rời Server",
            f"Bot sẽ rời `{guild.name}` (`{guild.id}`).\nThao tác này không thể hoàn tác từ phía bot.",
        )
        await ctx.send(embed=embed, view=ConfirmLeaveView(self, ctx.author.id, guild.id))

    async def send_leave_confirm_interaction(self, interaction: discord.Interaction, guild: discord.Guild):
        embed = create_warning_splash(
            "⚠️ Xác Nhận Rời Server",
            f"Bot sẽ rời `{guild.name}` (`{guild.id}`).\nThao tác này không thể hoàn tác từ phía bot.",
        )
        await interaction.response.send_message(embed=embed, view=ConfirmLeaveView(self, interaction.user.id, guild.id))

    @commands.command(name="group", aliases=["g"])
    async def group(self, ctx, action: str = None, *, server_text: str = None):
        if not await self.require_admin_ctx(ctx):
            return

        normalized_action = (action or "").strip().lower()
        if not normalized_action:
            await ctx.send(
                embed=create_info_splash(
                    "Group Manager",
                    "Dùng `group join|j [invite]` để lấy link mời bot, hoặc `group leave|l [server]` để bot rời server.",
                )
            )
            return

        server_text = (server_text or "").strip() or await self._reply_text(ctx)
        if normalized_action in self.JOIN_ACTIONS:
            if not server_text:
                await self.send_join_input_ctx(ctx)
                return
            await self.send_join_result_ctx(ctx, server_text)
            return

        if normalized_action in self.LEAVE_ACTIONS:
            await self.send_leave_list_ctx(ctx)
            return

        await ctx.send(embed=create_error_splash("❌ Sai Hành Động", "Hành động hợp lệ: `join/j` hoặc `leave/l`."))

    @app_commands.command(name="group", description="Quản lý bot join/leave server")
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.choices(
        action=[
            app_commands.Choice(name="join", value="join"),
            app_commands.Choice(name="leave", value="leave"),
        ]
    )
    @app_commands.describe(action="Chọn join hoặc leave", server="Invite/link server nếu join")
    async def slash_group(self, interaction: discord.Interaction, action: str, server: str = ""):
        if not await self.require_admin_interaction_user(interaction):
            return

        normalized_action = (action or "").strip().lower()
        if normalized_action == "join":
            server_text = (server or "").strip()
            if not server_text:
                await self.send_join_input_interaction(interaction)
                return
            await self.handle_join_interaction(interaction, server_text)
            return
        await self.send_leave_list_interaction(interaction)


async def setup(bot):
    await bot.add_cog(AdministratorGroupCog(bot))
