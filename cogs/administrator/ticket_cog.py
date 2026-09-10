from __future__ import annotations

import importlib
import io
import logging
import re
import uuid
import asyncio
from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

import services.ticket_service as ticket_service_module
import ui.ticket.components as ticket_components_module
import ui.ticket.emoji as ticket_emoji_module
import ui.ticket.ui as ticket_ui_module

# Extension reload does not refresh imported service/UI modules automatically.
# Reload dependencies in order so `breload` picks up ticket menu changes.
importlib.reload(ticket_service_module)
importlib.reload(ticket_emoji_module)
importlib.reload(ticket_ui_module)
importlib.reload(ticket_components_module)

from cogs.admin_command_utils import AdminCommandBase
from config import DISCORD_OWNER_IDS
from services.ticket_service import TicketService
from ui.ticket.components import (
    TicketCloseConfirmView,
    TicketControlView,
    TicketCreateConfirmView,
    TicketLogView,
    TicketManageView,
    TicketManagerView,
    TicketPanelView,
    TicketTypeView,
)
from ui.ticket.emoji import TICKET_THEME_DEFAULTS, ticket_emoji
from ui.ticket.ui import (
    build_ticket_closed_embed,
    build_ticket_created_embed,
    build_ticket_error_embed,
    build_ticket_help_embed,
    build_ticket_info_embed,
    build_ticket_manager_embed,
    build_ticket_notice_embed,
    build_ticket_panel_embed,
    build_ticket_success_embed,
    defer_interaction,
    format_ticket_template,
    safe_interaction_send,
    ticket_types,
)


logger = logging.getLogger(__name__)


def make_ticket_code() -> str:
    return uuid.uuid4().hex[:6]


def build_ticket_channel_name(ticket_code: str) -> str:
    code = re.sub(r"[^a-zA-Z0-9]", "", str(ticket_code)).lower()[:8]
    return f"ticket-{code or make_ticket_code()}"[:95]


def build_transcript(messages: list[discord.Message]) -> str:
    lines = [
        "==================================================",
        "              TICKET TRANSCRIPT LOG",
        "==================================================",
        f"Time: {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"Messages: {len(messages)}",
        "==================================================",
    ]
    for message in reversed(messages):
        if not message.content and not message.attachments:
            continue
        created_at = message.created_at.strftime("%Y-%m-%d %H:%M")
        content = message.clean_content.replace("\n", "\n    ")
        lines.append(f"[{created_at}] {message.author}: {content}")
        if message.attachments:
            lines.append("    Files: " + " | ".join(attachment.url for attachment in message.attachments))
    return "\n".join(lines)


class ContextAdapter:
    def __init__(self, source):
        self.source = source
        self.is_interaction = isinstance(source, discord.Interaction)
        self.guild = source.guild
        self.channel = source.channel
        self.user = source.user if self.is_interaction else source.author

    async def send(self, *args, **kwargs):
        if self.is_interaction:
            content = args[0] if args else kwargs.pop("content", None)
            return await safe_interaction_send(self.source, content=content, **kwargs)
        kwargs.pop("ephemeral", None)
        return await self.source.send(*args, **kwargs)


class TicketCog(AdminCommandBase):
    ticket_group = app_commands.Group(name="ticket", description="Quản lý hệ thống Ticket")
    context_adapter = staticmethod(ContextAdapter)

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.service = TicketService()
        bot.add_view(TicketPanelView(self))
        bot.add_view(TicketControlView(self))
        bot.add_view(TicketLogView(self))

    def member_can_manage(self, member: discord.Member) -> bool:
        if self.admins.is_admin(member.id, member.guild.id):
            return True
        role_ids = [role.id for role in member.roles if role.name != "@everyone"]
        return self.role_permissions.user_can_use(member.guild.id, role_ids, "ticket")

    def command_roles(self, guild: discord.Guild) -> list[discord.Role]:
        rows = self.role_permissions.get_roles_for_command(guild.id, "ticket")
        roles_by_id = {}
        for row in rows:
            role = guild.get_role(int(row["role_id"]))
            if role:
                roles_by_id[role.id] = role
        return list(roles_by_id.values())

    def admin_members(self, guild: discord.Guild) -> list[discord.Member]:
        admin_ids = {int(user_id) for user_id in DISCORD_OWNER_IDS}
        admin_ids.update(int(row["user_id"]) for row in self.admins.get_admins())
        return [
            member
            for user_id in admin_ids
            if (member := guild.get_member(user_id)) is not None
        ]

    def ticket_mention_config_text(self, guild: discord.Guild, ticket_type: str) -> str:
        theme = self.service.get_theme(guild.id)
        label = ticket_types(theme).get(ticket_type, ticket_type)
        targets = self.service.get_type_mentions(guild.id, ticket_type)
        role_mentions = [
            f"<@&{int(row['target_id'])}>"
            for row in targets
            if row["target_type"] == "role"
        ]
        user_mentions = [
            f"<@{int(row['target_id'])}>"
            for row in targets
            if row["target_type"] == "user"
        ]
        return (
            f"**Mục:** {label}\n"
            f"**Role:** {', '.join(role_mentions) if role_mentions else 'Chưa cài'}\n"
            f"**User:** {', '.join(user_mentions) if user_mentions else 'Chưa cài'}\n\n"
            "Chọn role/user sẽ thay danh sách cùng loại. Nút **Nhập ID** thay toàn bộ role và user của mục."
        )

    async def handle_ticket_mention_select(
        self,
        interaction: discord.Interaction,
        ticket_type: str,
        target_type: str,
        target_ids: list[int],
    ):
        if not await self.require_role_or_admin_interaction(interaction, "ticket"):
            return
        self.service.replace_type_mentions(
            interaction.guild.id,
            ticket_type,
            target_type,
            target_ids,
        )
        await safe_interaction_send(
            interaction,
            content=(
                f"✅ Đã lưu `{len(target_ids)}` "
                f"{'role' if target_type == 'role' else 'user'} cho mục này.\n"
                f"{self.ticket_mention_config_text(interaction.guild, ticket_type)}"
            ),
            ephemeral=True,
        )

    async def handle_ticket_mention_ids(
        self,
        interaction: discord.Interaction,
        ticket_type: str,
        raw_ids: str,
    ):
        if not await self.require_role_or_admin_interaction(interaction, "ticket"):
            return
        ids = list(dict.fromkeys(int(value) for value in re.findall(r"\d{15,25}", raw_ids)))
        role_ids = []
        user_ids = []
        unknown_ids = []
        for target_id in ids:
            if interaction.guild.get_role(target_id):
                role_ids.append(target_id)
            elif interaction.guild.get_member(target_id):
                user_ids.append(target_id)
            else:
                unknown_ids.append(target_id)
        if not role_ids and not user_ids:
            await safe_interaction_send(
                interaction,
                content="❌ Không tìm thấy role hoặc thành viên nào từ ID đã nhập trong server này.",
                ephemeral=True,
            )
            return
        self.service.set_type_mentions(
            interaction.guild.id,
            ticket_type,
            role_ids=role_ids,
            user_ids=user_ids,
        )
        warning = (
            "\n⚠️ Bỏ qua ID không tồn tại trong server: "
            + ", ".join(f"`{value}`" for value in unknown_ids)
            if unknown_ids
            else ""
        )
        await safe_interaction_send(
            interaction,
            content=(
                f"✅ Đã lưu `{len(role_ids)}` role và `{len(user_ids)}` user.\n"
                f"{self.ticket_mention_config_text(interaction.guild, ticket_type)}"
                f"{warning}"
            ),
            ephemeral=True,
        )

    def ticket_notify_targets(
        self,
        guild: discord.Guild,
        ticket_type: str,
    ) -> tuple[list[discord.Role], list[discord.Member], bool]:
        rows = self.service.get_type_mentions(guild.id, ticket_type)
        configured = bool(rows)
        roles = []
        members = []
        for row in rows:
            target_id = int(row["target_id"])
            if row["target_type"] == "role":
                role = guild.get_role(target_id)
                if role:
                    roles.append(role)
            elif row["target_type"] == "user":
                member = guild.get_member(target_id)
                if member:
                    members.append(member)
        return roles, members, configured

    async def save_config_value(
        self,
        interaction: discord.Interaction,
        key: str,
        value: int | None,
        label: str,
    ):
        self.service.update_single_config(interaction.guild.id, key, value)
        await safe_interaction_send(interaction, content=f"✅ {label} đã được cập nhật.", ephemeral=True)

    async def handle_ticket_theme_submit(
        self,
        interaction: discord.Interaction,
        key: str,
        value: str,
    ):
        if not await self.require_role_or_admin_interaction(interaction, "ticket"):
            return
        if key not in TICKET_THEME_DEFAULTS:
            await safe_interaction_send(interaction, content="❌ Mục cấu hình không hợp lệ.", ephemeral=True)
            return
        value = value.strip().replace("\\n", "\n")
        if value.lower() in {"reset", "default"}:
            self.service.reset_theme_value(interaction.guild.id, key)
            message = f"✅ Đã reset `{key}`."
        else:
            self.service.set_theme_value(interaction.guild.id, key, value)
            message = f"✅ Đã lưu `{key}`."
        await safe_interaction_send(interaction, content=message, ephemeral=True)

    @ticket_group.command(name="manager", description="Mở bảng quản lý Ticket")
    async def slash_manager(self, interaction: discord.Interaction):
        if not await self.require_role_or_admin_interaction(interaction, "ticket"):
            return
        await safe_interaction_send(
            interaction,
            embed=build_ticket_manager_embed(self, interaction.guild),
            view=TicketManagerView(self),
            ephemeral=False,
        )

    @ticket_group.command(name="info", description="Xem thông tin ticket hiện tại")
    async def slash_info(self, interaction: discord.Interaction):
        await self.core_info(ContextAdapter(interaction))

    @ticket_group.command(name="close", description="Đóng ticket hiện tại")
    @app_commands.describe(reason="Lý do đóng ticket")
    async def slash_close(self, interaction: discord.Interaction, reason: str = ""):
        await self.core_close_request(ContextAdapter(interaction), reason)

    @commands.group(name="ticket", invoke_without_command=True)
    async def ticket(self, ctx):
        await ctx.send(embed=build_ticket_help_embed(ctx.clean_prefix))

    @ticket.command(name="manager", aliases=["setup"])
    async def ticket_manager(self, ctx):
        if not await self.require_role_or_admin_ctx(ctx, "ticket"):
            return
        await ctx.send(embed=build_ticket_manager_embed(self, ctx.guild), view=TicketManagerView(self))

    @ticket.command(name="config", aliases=["cfg"])
    async def ticket_config(self, ctx):
        if not await self.require_role_or_admin_ctx(ctx, "ticket"):
            return
        await ctx.send(embed=build_ticket_manager_embed(self, ctx.guild), view=TicketManagerView(self))

    @ticket.command(name="panel")
    async def ticket_panel(self, ctx):
        if not await self.require_role_or_admin_ctx(ctx, "ticket"):
            return
        await self.send_or_refresh_panel(ctx.guild, ctx.send)

    @ticket.command(name="add")
    async def ticket_add(self, ctx, member: discord.Member):
        await self.core_add_user(ContextAdapter(ctx), member)

    @ticket.command(name="remove", aliases=["rm"])
    async def ticket_remove(self, ctx, member: discord.Member):
        await self.core_remove_user(ContextAdapter(ctx), member)

    @ticket.command(name="rename")
    async def ticket_rename(self, ctx, *, name: str):
        await self.core_rename(ContextAdapter(ctx), name)

    @ticket.command(name="transfer")
    async def ticket_transfer(self, ctx, member: discord.Member):
        await self.core_transfer(ContextAdapter(ctx), member)

    @ticket.command(name="unclaim")
    async def ticket_unclaim(self, ctx):
        await self.core_unclaim(ContextAdapter(ctx))

    @ticket.command(name="info")
    async def ticket_info(self, ctx):
        await self.core_info(ContextAdapter(ctx))

    @ticket.command(name="close")
    async def ticket_close(self, ctx, *, reason: str = ""):
        await self.core_close_request(ContextAdapter(ctx), reason)

    async def handle_send_panel(self, interaction: discord.Interaction):
        if not await self.require_role_or_admin_interaction(interaction, "ticket"):
            return
        await defer_interaction(interaction, ephemeral=True)

        async def sender(*args, **kwargs):
            return await interaction.followup.send(*args, ephemeral=True, **kwargs)

        await self.send_or_refresh_panel(interaction.guild, sender)

    async def send_or_refresh_panel(self, guild: discord.Guild, sender):
        config = self.service.get_config(guild.id)
        if not config or not config.get("panel_channel_id") or not config.get("ticket_category_id"):
            await sender(embed=build_ticket_error_embed("Thiếu Cấu Hình", "Cần chọn kênh panel và danh mục ticket."))
            return
        channel = guild.get_channel(int(config["panel_channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            await sender(embed=build_ticket_error_embed("Kênh Không Hợp Lệ", "Kênh panel không còn tồn tại."))
            return

        theme = self.service.get_theme(guild.id)
        embed = build_ticket_panel_embed(config, theme)
        message_id = config.get("panel_message_id")
        if message_id:
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(embed=embed, view=TicketPanelView(self, guild.id))
                await sender(embed=build_ticket_success_embed("Refresh Panel", "Đã cập nhật panel hiện tại."))
                return
            except (discord.NotFound, discord.HTTPException):
                pass
        message = await channel.send(embed=embed, view=TicketPanelView(self, guild.id))
        self.service.update_single_config(guild.id, "panel_message_id", message.id)
        await sender(embed=build_ticket_success_embed("Đã Gửi Panel", f"Panel đã gửi ở {channel.mention}."))

    async def handle_panel_open(self, interaction: discord.Interaction):
        theme = self.service.get_theme(interaction.guild.id)
        await safe_interaction_send(
            interaction,
            embed=build_ticket_notice_embed(
                "ticket",
                "Chọn Loại Ticket",
                theme.get("type_prompt") or TICKET_THEME_DEFAULTS["type_prompt"],
            ),
            view=TicketTypeView(self, interaction.guild.id),
            ephemeral=True,
        )

    async def handle_ticket_type_selected(self, interaction: discord.Interaction, ticket_type: str):
        theme = self.service.get_theme(interaction.guild.id)
        label = ticket_types(theme).get(ticket_type, ticket_type)
        prompt = format_ticket_template(theme, "confirm_prompt", type=label)
        await interaction.response.edit_message(
            embed=build_ticket_notice_embed("ticket", "Xác Nhận", prompt),
            view=TicketCreateConfirmView(self, ticket_type, interaction.user.id, interaction.guild.id),
        )

    async def handle_create_ticket(self, interaction: discord.Interaction, ticket_type: str):
        config = self.service.get_config(interaction.guild.id)
        if not config or not config.get("ticket_category_id"):
            await safe_interaction_send(interaction, content="❌ Server chưa cấu hình danh mục Ticket.", ephemeral=True)
            return
        active = self.service.get_user_active_tickets(interaction.guild.id, interaction.user.id)
        if len(active) >= int(config.get("max_open_tickets", 1)):
            await safe_interaction_send(interaction, content="❌ Bạn đã đạt giới hạn ticket đang mở.", ephemeral=True)
            return
        cooldown = self.service.get_cooldown(
            interaction.guild.id,
            interaction.user.id,
            int(config.get("cooldown_seconds", 60)),
        )
        if cooldown > 0:
            await safe_interaction_send(interaction, content=f"❌ Hãy chờ `{cooldown}` giây trước khi tạo ticket mới.", ephemeral=True)
            return
        category = interaction.guild.get_channel(int(config["ticket_category_id"]))
        if not isinstance(category, discord.CategoryChannel):
            await safe_interaction_send(interaction, content="❌ Danh mục Ticket không hợp lệ.", ephemeral=True)
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True,
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                send_messages=True,
                manage_channels=True,
                manage_permissions=True,
            ),
        }
        manager_roles = self.command_roles(interaction.guild)
        for role in manager_roles:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                read_message_history=True,
            )
        for admin_member in self.admin_members(interaction.guild):
            overwrites[admin_member] = discord.PermissionOverwrite(
                view_channel=True,
                read_messages=True,
                send_messages=True,
                manage_messages=True,
                manage_channels=True,
                read_message_history=True,
            )

        notify_roles, notify_members, mentions_configured = self.ticket_notify_targets(
            interaction.guild,
            ticket_type,
        )
        for role in notify_roles:
            if role not in overwrites:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    read_message_history=True,
                )
        for member in notify_members:
            if member not in overwrites:
                overwrites[member] = discord.PermissionOverwrite(
                    view_channel=True,
                    read_messages=True,
                    send_messages=True,
                    attach_files=True,
                    read_message_history=True,
                )

        ticket_code = make_ticket_code()
        try:
            channel = await interaction.guild.create_text_channel(
                name=build_ticket_channel_name(ticket_code),
                category=category,
                overwrites=overwrites,
                reason=f"Ticket của {interaction.user}",
            )
        except discord.Forbidden:
            await safe_interaction_send(interaction, content="❌ Bot thiếu quyền tạo kênh Ticket.", ephemeral=True)
            return

        if not self.service.create_ticket(
            interaction.guild.id,
            channel.id,
            interaction.user.id,
            ticket_type,
            ticket_code,
        ):
            try:
                await channel.delete(reason="Không ghi được ticket vào database")
            except discord.HTTPException:
                logger.warning(f"Could not delete orphaned ticket channel {channel.id}")
            await safe_interaction_send(interaction, content="❌ Không ghi được Ticket vào database.", ephemeral=True)
            return

        mention_roles = notify_roles if mentions_configured else manager_roles
        mention_targets = [
            interaction.user.mention,
            *(role.mention for role in mention_roles),
            *(member.mention for member in notify_members),
        ]
        theme = self.service.get_theme(interaction.guild.id)
        await channel.send(
            content=" ".join(dict.fromkeys(mention_targets)),
            embed=build_ticket_created_embed(interaction.user, ticket_type, theme),
            view=TicketControlView(self, interaction.guild.id),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True),
        )
        await safe_interaction_send(interaction, content=f"✅ Đã tạo ticket: {channel.mention}", ephemeral=True)

    async def handle_claim(self, interaction: discord.Interaction):
        if not self.member_can_manage(interaction.user):
            await safe_interaction_send(interaction, content="❌ Bạn không có quyền quản trị Ticket.", ephemeral=True)
            return
        ticket = self.service.get_ticket(interaction.channel.id)
        if not ticket:
            await safe_interaction_send(interaction, content="❌ Đây không phải kênh Ticket.", ephemeral=True)
            return
        if self.service.claim_ticket(interaction.channel.id, interaction.user.id, interaction.user.display_name):
            self.service.log_event(ticket["ticket_id"], interaction.guild.id, interaction.channel.id, "claimed", interaction.user.id)
            await safe_interaction_send(interaction, content=f"👋 {interaction.user.mention} đã nhận Ticket này.", ephemeral=False)
            return
        await safe_interaction_send(interaction, content="❌ Ticket đã có người nhận hoặc đã đóng.", ephemeral=True)

    async def handle_manage(self, interaction: discord.Interaction):
        if not self.member_can_manage(interaction.user):
            await safe_interaction_send(interaction, content="❌ Bạn không có quyền quản trị Ticket.", ephemeral=True)
            return
        await safe_interaction_send(interaction, content="Bảng quản lý Ticket:", view=TicketManageView(self), ephemeral=True)

    async def verify_ticket(self, adapter: ContextAdapter, require_manager: bool = True):
        if not adapter.guild or not adapter.channel:
            return None
        ticket = self.service.get_ticket(adapter.channel.id)
        if not ticket or ticket["status"] not in {"open", "claimed"}:
            await adapter.send(
                embed=build_ticket_error_embed("Ticket Không Hợp Lệ", "Kênh này không phải ticket đang mở."),
                ephemeral=True,
            )
            return None
        if require_manager and not self.member_can_manage(adapter.user):
            await adapter.send(
                embed=build_ticket_error_embed("Quyền Bị Từ Chối", "Bạn không có quyền `ticket` trong role database."),
                ephemeral=True,
            )
            return None
        return ticket

    async def core_add_user(self, adapter: ContextAdapter, member: discord.Member):
        ticket = await self.verify_ticket(adapter)
        if not ticket:
            return
        if member.bot or member.id == int(ticket["owner_user_id"]):
            await adapter.send(content="❌ Không thể thêm bot hoặc chủ ticket.", ephemeral=True)
            return
        overwrite = adapter.channel.overwrites_for(member)
        if overwrite.view_channel is True:
            await adapter.send(content="❌ Thành viên này đã có trong ticket.", ephemeral=True)
            return
            
        new_overwrite = discord.PermissionOverwrite(
            view_channel=True,
            read_messages=True,
            send_messages=True,
            attach_files=True,
            read_message_history=True,
            embed_links=True,
            use_external_emojis=True,
        )
        await adapter.channel.set_permissions(member, overwrite=new_overwrite)
        self.service.log_event(ticket["ticket_id"], adapter.guild.id, adapter.channel.id, "user_added", adapter.user.id, member.id)
        await adapter.send(content=f"✅ Đã thêm {member.mention} vào ticket.")

    async def core_remove_user(self, adapter: ContextAdapter, member: discord.Member):
        ticket = await self.verify_ticket(adapter)
        if not ticket:
            return
        if member.bot or member.id == int(ticket["owner_user_id"]) or self.member_can_manage(member):
            await adapter.send(content="❌ Không thể xóa bot, chủ ticket hoặc người quản trị Ticket.", ephemeral=True)
            return
        await adapter.channel.set_permissions(member, overwrite=None)
        self.service.log_event(ticket["ticket_id"], adapter.guild.id, adapter.channel.id, "user_removed", adapter.user.id, member.id)
        await adapter.send(content=f"✅ Đã xóa {member.mention} khỏi ticket.")

    async def core_rename(self, adapter: ContextAdapter, raw_name: str):
        ticket = await self.verify_ticket(adapter)
        if not ticket:
            return
        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "", raw_name.lower().replace(" ", "-")).strip("-")
        if not safe_name:
            await adapter.send(content="❌ Tên ticket không hợp lệ.", ephemeral=True)
            return
        final_name = safe_name[:100]
        await adapter.channel.edit(name=final_name, reason=f"Đổi bởi {adapter.user}")
        self.service.log_event(ticket["ticket_id"], adapter.guild.id, adapter.channel.id, "renamed", adapter.user.id, message=final_name)
        await adapter.send(content=f"✅ Đã đổi tên kênh thành `{final_name}`.")

    async def core_transfer(self, adapter: ContextAdapter, member: discord.Member):
        ticket = await self.verify_ticket(adapter)
        if not ticket:
            return
        if member.bot or not self.member_can_manage(member):
            await adapter.send(content="❌ Người nhận phải có quyền `ticket` trong role database.", ephemeral=True)
            return
        if self.service.transfer_ticket(adapter.channel.id, member.id, member.display_name):
            self.service.log_event(ticket["ticket_id"], adapter.guild.id, adapter.channel.id, "transferred", adapter.user.id, member.id)
            await adapter.send(content=f"✅ Đã chuyển Ticket cho {member.mention}.")
            return
        await adapter.send(content="❌ Không thể chuyển Ticket.", ephemeral=True)

    async def core_unclaim(self, adapter: ContextAdapter):
        ticket = await self.verify_ticket(adapter)
        if not ticket:
            return
        if ticket["status"] != "claimed":
            await adapter.send(content="❌ Ticket chưa có người nhận.", ephemeral=True)
            return
        if int(ticket.get("claimed_by_user_id") or 0) != adapter.user.id and not self.admins.is_admin(adapter.user.id, adapter.guild.id):
            await adapter.send(content="❌ Bạn không thể unclaim Ticket của người khác.", ephemeral=True)
            return
        if self.service.unclaim_ticket(adapter.channel.id):
            self.service.log_event(ticket["ticket_id"], adapter.guild.id, adapter.channel.id, "unclaimed", adapter.user.id)
            await adapter.send(content="✅ Ticket đã trở về trạng thái chờ.")

    async def core_info(self, adapter: ContextAdapter):
        ticket = await self.verify_ticket(adapter, require_manager=False)
        if not ticket:
            return
        if int(ticket["owner_user_id"]) != adapter.user.id and not self.member_can_manage(adapter.user):
            await adapter.send(content="❌ Bạn không có quyền xem Ticket này.", ephemeral=True)
            return
        await adapter.send(embed=build_ticket_info_embed(ticket))

    async def core_close_request(self, adapter: ContextAdapter, reason: str):
        ticket = await self.verify_ticket(adapter, require_manager=False)
        if not ticket:
            return
        if int(ticket["owner_user_id"]) != adapter.user.id and not self.member_can_manage(adapter.user):
            await adapter.send(content="❌ Bạn không có quyền đóng Ticket này.", ephemeral=True)
            return
        self.service.log_event(
            ticket["ticket_id"],
            adapter.guild.id,
            adapter.channel.id,
            "close_requested",
            adapter.user.id,
            message=reason,
        )
        await adapter.send(
            embed=build_ticket_notice_embed("confirm", "Xác Nhận Đóng", f"Lý do: {reason or 'Không có'}"),
            view=TicketCloseConfirmView(self, reason),
        )

    async def handle_confirm_close(self, interaction: discord.Interaction, reason: str):
        # Ngăn lỗi "Interaction Failed" do tải history (Transcript) tốn nhiều thời gian
        if not interaction.response.is_done():
            await interaction.response.defer()
            
        ticket = self.service.get_ticket(interaction.channel.id)
        if not ticket:
            return
        if not self.service.set_ticket_status(interaction.channel.id, "closing", ["open", "claimed"]):
            await safe_interaction_send(interaction, content="❌ Ticket đã được xử lý trước đó.", ephemeral=True)
            return
        config = self.service.get_config(interaction.guild.id) or {}
        transcript_limit = int(config.get("transcript_limit", 500))
        try:
            messages = [message async for message in interaction.channel.history(limit=transcript_limit)]
            transcript = build_transcript(messages)
        except discord.HTTPException:
            transcript = "Không thể tải transcript."

        log_channel_id = config.get("log_channel_id")
        log_channel = interaction.guild.get_channel(int(log_channel_id)) if log_channel_id else None
        if isinstance(log_channel, discord.TextChannel):
            try:
                created_at = datetime.strptime(ticket["created_at"], "%Y-%m-%d %H:%M:%S")
                opened_text = f"<t:{int(created_at.timestamp())}:F>"
            except (TypeError, ValueError):
                opened_text = str(ticket.get("created_at", "Không rõ"))
            file = discord.File(io.BytesIO(transcript.encode("utf-8")), filename=f"transcript-{ticket['ticket_id']}.txt")
            await log_channel.send(
                embed=build_ticket_closed_embed(ticket, interaction.user, opened_text, reason),
                file=file,
                view=TicketLogView(self),
            )

        self.service.set_ticket_status(interaction.channel.id, "closed", ["closing"], close_reason=reason)
        self.service.log_event(ticket["ticket_id"], interaction.guild.id, interaction.channel.id, "closed", interaction.user.id, message=reason)

        archive_id = config.get("archive_category_id")
        archive = interaction.guild.get_channel(int(archive_id)) if archive_id else None
        try:
            if config.get("close_mode", "archive") == "archive" and isinstance(archive, discord.CategoryChannel):
                overwrites = interaction.channel.overwrites
                owner = interaction.guild.get_member(int(ticket["owner_user_id"]))
                if owner in overwrites:
                    del overwrites[owner]
                await interaction.channel.edit(
                    name=f"closed-{ticket['ticket_id']}",
                    category=archive,
                    overwrites=overwrites,
                    reason="Ticket đã đóng",
                )
                self.service.log_event(ticket["ticket_id"], interaction.guild.id, interaction.channel.id, "archived", interaction.user.id)
            else:
                await interaction.channel.delete(reason="Ticket đã đóng")
                self.service.log_event(ticket["ticket_id"], interaction.guild.id, interaction.channel.id, "deleted", interaction.user.id)
        except discord.HTTPException:
            logger.exception("Không thể archive/delete ticket channel %s", interaction.channel.id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not isinstance(channel, discord.TextChannel):
            return
        ticket = self.service.get_ticket(channel.id)
        if ticket and ticket["status"] not in {"closed", "deleted", "archived"}:
            self.service.mark_ticket_deleted(channel.id)
            self.service.log_event(
                ticket["ticket_id"],
                channel.guild.id,
                channel.id,
                "deleted_manually",
                getattr(self.bot.user, "id", 0),
            )

    # ---------------------------------------------------------
    # Thêm lệnh thao tác nhanh (fast alias) ở cấp root
    # ---------------------------------------------------------
    @commands.command(name="tickclose", aliases=["tclose"], description="Đóng nhanh ticket hiện tại")
    async def close_root_command(self, ctx, *, reason: str = ""):
        await self.core_close_request(ContextAdapter(ctx), reason)
        
    @commands.command(name="ticksetname", aliases=["trename"], description="Đổi tên nhanh ticket hiện tại")
    async def rename_root_command(self, ctx, *, name: str):
        await self.core_rename(ContextAdapter(ctx), name)
        
    @commands.command(name="tickremind", aliases=["tremind"], description="Nhắc nhở người dùng đóng tất cả ticket đang mở")
    async def remind_root_command(self, ctx):
        if not await self.require_role_or_admin_ctx(ctx, "ticket"):
            return
            
        active_tickets = self.service.get_all_active_tickets(ctx.guild.id)
        remind_tickets = [t for t in active_tickets if t["status"] in {"open", "claimed"}]
        
        if not remind_tickets:
            await ctx.send(embed=build_ticket_error_embed("Không Có Ticket", "Hiện không có ticket nào đang hoạt động để nhắc nhở."))
            return

        prefix = ctx.clean_prefix
        count = 0
        
        msg = await ctx.send(embed=build_ticket_notice_embed("ticket", "Đang Gửi Lời Nhắc", f"Đang tiến hành gửi lời nhắc cho `{len(remind_tickets)}` ticket..."))

        for ticket in remind_tickets:
            channel = ctx.guild.get_channel(int(ticket["channel_id"]))
            if channel and isinstance(channel, discord.TextChannel):
                mentions = []
                owner_id = ticket.get("owner_user_id")
                if owner_id:
                    mentions.append(f"<@{owner_id}>")

                if ticket.get("status") == "claimed":
                    claimer_id = ticket.get("claimed_by_user_id")
                    if claimer_id:
                        mentions.append(f"<@{claimer_id}>")
                
                content_to_send = " ".join(list(dict.fromkeys(mentions)))
                if not content_to_send:
                    continue
                try:
                    embed = build_ticket_notice_embed("ticket", "Nhắc nhở đóng Ticket", f"Nếu vấn đề của bạn đã được giải quyết xong, xin hãy sử dụng lệnh `{prefix}tickclose` để đóng ticket này nhé! Cảm ơn bạn rất nhiều.")
                    await channel.send(content=content_to_send, embed=embed)
                    count += 1
                    await asyncio.sleep(0.5)
                except discord.HTTPException:
                    pass
                    
        await msg.edit(embed=build_ticket_success_embed("Gửi Thành Công", f"Đã gửi lời nhắc vào `{count}/{len(remind_tickets)}` ticket đang hoạt động."))

async def setup(bot):
    await bot.add_cog(TicketCog(bot))
