from __future__ import annotations

import re

import discord
from discord.ui import Button, ChannelSelect, Modal, RoleSelect, Select, TextInput, UserSelect, View

from ui.ticket.emoji import (
    TICKET_CONTENT_FIELDS,
    TICKET_ICON_FIELDS,
    ticket_emoji,
    ticket_theme_value,
)
from ui.ticket.ui import (
    build_ticket_close_cancelled_embed,
    build_ticket_close_progress_embed,
    build_ticket_create_cancelled_embed,
    build_ticket_create_progress_embed,
    build_ticket_guide_embed,
    safe_interaction_send,
    ticket_types,
)


class TicketTypeSelect(Select):
    def __init__(self, cog, guild_id: int | None = None):
        theme = cog.service.get_theme(guild_id) if guild_id else {}
        options = [
            discord.SelectOption(label=label, value=value, emoji=ticket_emoji(value, theme))
            for value, label in ticket_types(theme).items()
        ]
        super().__init__(
            placeholder="Chọn loại yêu cầu hỗ trợ...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ticket:type",
        )
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        await self.cog.handle_ticket_type_selected(interaction, self.values[0])


class TicketTypeView(View):
    def __init__(self, cog, guild_id: int | None = None):
        super().__init__(timeout=120)
        self.add_item(TicketTypeSelect(cog, guild_id))


class TicketCreateConfirmView(View):
    def __init__(self, cog, ticket_type: str, owner_id: int, guild_id: int | None = None):
        super().__init__(timeout=120)
        self.cog = cog
        self.ticket_type = ticket_type
        self.owner_id = owner_id
        theme = cog.service.get_theme(guild_id) if guild_id else {}
        for child in self.children:
            if child.label == "Xác nhận":
                child.label = ticket_theme_value(theme, "button_confirm")
                child.emoji = ticket_emoji("confirm", theme)
            elif child.label == "Hủy":
                child.label = ticket_theme_value(theme, "button_cancel")
                child.emoji = ticket_emoji("cancel", theme)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await safe_interaction_send(
            interaction,
            content=f"{ticket_emoji('error')} Chỉ người mở ticket mới được xác nhận.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Xác nhận", style=discord.ButtonStyle.success, emoji=ticket_emoji("confirm"))
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            embed=build_ticket_create_progress_embed(),
            view=None,
        )
        await self.cog.handle_create_ticket(interaction, self.ticket_type)

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary, emoji=ticket_emoji("cancel"))
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            embed=build_ticket_create_cancelled_embed(),
            view=None,
        )


class TicketPanelView(View):
    def __init__(self, cog, guild_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        theme = cog.service.get_theme(guild_id) if guild_id else {}
        for child in self.children:
            if child.custom_id == "ticket:open":
                child.label = ticket_theme_value(theme, "button_open")
                child.emoji = ticket_emoji("ticket", theme)
            elif child.custom_id == "ticket:guide":
                child.label = ticket_theme_value(theme, "button_guide")
                child.emoji = ticket_emoji("log", theme)

    @discord.ui.button(
        label="Mở Ticket",
        style=discord.ButtonStyle.primary,
        emoji=ticket_emoji("ticket"),
        custom_id="ticket:open",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: Button):
        await self.cog.handle_panel_open(interaction)

    @discord.ui.button(
        label="Hướng dẫn",
        style=discord.ButtonStyle.secondary,
        emoji=ticket_emoji("log"),
        custom_id="ticket:guide",
    )
    async def guide(self, interaction: discord.Interaction, button: Button):
        theme = self.cog.service.get_theme(interaction.guild.id)
        await safe_interaction_send(interaction, embed=build_ticket_guide_embed(theme), ephemeral=True)


class TicketCloseConfirmView(View):
    def __init__(self, cog, reason: str):
        super().__init__(timeout=120)
        self.cog = cog
        self.reason = reason

    @discord.ui.button(label="Xác nhận đóng", style=discord.ButtonStyle.danger, emoji=ticket_emoji("close"))
    async def confirm(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            embed=build_ticket_close_progress_embed(),
            view=None,
        )
        await self.cog.handle_confirm_close(interaction, self.reason)

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.secondary, emoji=ticket_emoji("cancel"))
    async def cancel(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(
            embed=build_ticket_close_cancelled_embed(),
            view=None,
        )


class TicketRenameModal(Modal, title="Đổi tên Ticket"):
    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        self.name_input = TextInput(label="Tên mới", required=True, max_length=50)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.core_rename(self.cog.context_adapter(interaction), self.name_input.value)


class TicketManageView(View):
    def __init__(self, cog):
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.select(cls=UserSelect, placeholder="Thêm thành viên...")
    async def add_user(self, interaction: discord.Interaction, select: UserSelect):
        await self.cog.core_add_user(self.cog.context_adapter(interaction), select.values[0])

    @discord.ui.select(cls=UserSelect, placeholder="Xóa thành viên...")
    async def remove_user(self, interaction: discord.Interaction, select: UserSelect):
        await self.cog.core_remove_user(self.cog.context_adapter(interaction), select.values[0])

    @discord.ui.select(cls=UserSelect, placeholder="Chuyển ticket cho người quản trị...")
    async def transfer(self, interaction: discord.Interaction, select: UserSelect):
        await self.cog.core_transfer(self.cog.context_adapter(interaction), select.values[0])

    @discord.ui.button(label="Đổi tên", style=discord.ButtonStyle.secondary, emoji=ticket_emoji("rename"))
    async def rename(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TicketRenameModal(self.cog))

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.secondary)
    async def unclaim(self, interaction: discord.Interaction, button: Button):
        await self.cog.core_unclaim(self.cog.context_adapter(interaction))

    @discord.ui.button(label="Thông tin", style=discord.ButtonStyle.primary)
    async def info(self, interaction: discord.Interaction, button: Button):
        await self.cog.core_info(self.cog.context_adapter(interaction))


class TicketControlView(View):
    def __init__(self, cog, guild_id: int | None = None):
        super().__init__(timeout=None)
        self.cog = cog
        theme = cog.service.get_theme(guild_id) if guild_id else {}
        mapping = {
            "ticket:claim": ("button_claim", "claim"),
            "ticket:manage": ("button_manage", "manage"),
            "ticket:close": ("button_close", "close"),
        }
        for child in self.children:
            if child.custom_id in mapping:
                label_key, icon_key = mapping[child.custom_id]
                child.label = ticket_theme_value(theme, label_key)
                child.emoji = ticket_emoji(icon_key, theme)

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.success,
        emoji=ticket_emoji("claim"),
        custom_id="ticket:claim",
    )
    async def claim(self, interaction: discord.Interaction, button: Button):
        await self.cog.handle_claim(interaction)

    @discord.ui.button(
        label="Quản lý",
        style=discord.ButtonStyle.secondary,
        emoji=ticket_emoji("manage"),
        custom_id="ticket:manage",
    )
    async def manage(self, interaction: discord.Interaction, button: Button):
        await self.cog.handle_manage(interaction)

    @discord.ui.button(
        label="Đóng",
        style=discord.ButtonStyle.danger,
        emoji=ticket_emoji("close"),
        custom_id="ticket:close",
    )
    async def close(self, interaction: discord.Interaction, button: Button):
        await self.cog.core_close_request(self.cog.context_adapter(interaction), "")


class TicketConfigView(View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.cog.require_role_or_admin_interaction(interaction, "ticket")

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Chọn kênh Panel...")
    async def panel_channel(self, interaction: discord.Interaction, select: ChannelSelect):
        await self.cog.save_config_value(interaction, "panel_channel_id", select.values[0].id, "Kênh panel")

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.category], placeholder="Chọn danh mục Ticket...")
    async def ticket_category(self, interaction: discord.Interaction, select: ChannelSelect):
        await self.cog.save_config_value(interaction, "ticket_category_id", select.values[0].id, "Danh mục ticket")

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.category], placeholder="Chọn danh mục lưu trữ...")
    async def archive_category(self, interaction: discord.Interaction, select: ChannelSelect):
        self.cog.service.update_single_config(interaction.guild.id, "close_mode", "archive")
        await self.cog.save_config_value(interaction, "archive_category_id", select.values[0].id, "Danh mục lưu trữ")

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Chọn kênh Log...")
    async def log_channel(self, interaction: discord.Interaction, select: ChannelSelect):
        await self.cog.save_config_value(interaction, "log_channel_id", select.values[0].id, "Kênh log")

    @discord.ui.button(label="Tắt lưu trữ", style=discord.ButtonStyle.danger, row=4)
    async def disable_archive(self, interaction: discord.Interaction, button: Button):
        self.cog.service.update_single_config(interaction.guild.id, "archive_category_id", None)
        self.cog.service.update_single_config(interaction.guild.id, "close_mode", "delete")
        await safe_interaction_send(interaction, content="✅ Đã chuyển chế độ đóng ticket sang xóa kênh.", ephemeral=True)


class TicketLimitModal(Modal, title="Cấu hình Ticket"):
    def __init__(self, cog, config: dict):
        super().__init__()
        self.cog = cog
        self.max_open = TextInput(
            label="Số ticket tối đa mỗi người",
            default=str(config.get("max_open_tickets", 1)),
            required=True,
        )
        self.cooldown = TextInput(
            label="Cooldown tạo ticket (giây)",
            default=str(config.get("cooldown_seconds", 60)),
            required=True,
        )
        self.add_item(self.max_open)
        self.add_item(self.cooldown)

    async def on_submit(self, interaction: discord.Interaction):
        if not await self.cog.require_role_or_admin_interaction(interaction, "ticket"):
            return
        try:
            max_open = int(self.max_open.value)
            cooldown = int(self.cooldown.value)
            if not 1 <= max_open <= 10 or cooldown < 0:
                raise ValueError
        except ValueError:
            await safe_interaction_send(
                interaction,
                content=f"{ticket_emoji('error')} Max ticket phải từ 1-10 và cooldown không được âm.",
                ephemeral=True,
            )
            return
        self.cog.service.update_single_config(interaction.guild.id, "max_open_tickets", max_open)
        self.cog.service.update_single_config(interaction.guild.id, "cooldown_seconds", cooldown)
        await safe_interaction_send(interaction, content="✅ Đã lưu giới hạn Ticket.", ephemeral=True)


class TicketThemeModal(Modal):
    def __init__(self, cog, guild_id: int, key: str, current: str):
        super().__init__(title=f"Sửa {key}"[:45])
        self.cog = cog
        self.guild_id = guild_id
        self.key = key
        example = (
            TICKET_ICON_FIELDS.get(key)
            if key.startswith("icon_")
            else TICKET_CONTENT_FIELDS.get(key)
        ) or ""
        max_length = 4000
        if key.startswith("icon_"):
            max_length = 100
        elif key.startswith("button_"):
            max_length = 80
        elif key.startswith("type_"):
            max_length = 100
        elif key.endswith("_title"):
            max_length = 256
        self.value_input = TextInput(
            label=key[:45],
            placeholder=f"VD: {example}"[:100],
            default=current[:max_length],
            style=discord.TextStyle.paragraph if len(current) > 80 else discord.TextStyle.short,
            max_length=max_length,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_ticket_theme_submit(
            interaction,
            self.key,
            str(self.value_input.value),
        )


class TicketThemeSelect(Select):
    def __init__(self, cog, guild_id: int, mode: str):
        self.cog = cog
        self.guild_id = guild_id
        fields = TICKET_ICON_FIELDS if mode == "icon" else TICKET_CONTENT_FIELDS
        options = [
            discord.SelectOption(
                label=key.replace("_", " ").title()[:100],
                value=key,
                description=f"VD: {example}"[:100],
                emoji="✨" if mode == "icon" else "📝",
            )
            for key, example in fields.items()
        ]
        super().__init__(
            placeholder="Chọn icon cần sửa..." if mode == "icon" else "Chọn nội dung cần sửa...",
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.cog.require_role_or_admin_interaction(interaction, "ticket"):
            return
        key = self.values[0]
        theme = self.cog.service.get_theme(self.guild_id)
        await interaction.response.send_modal(
            TicketThemeModal(
                self.cog,
                self.guild_id,
                key,
                ticket_theme_value(theme, key),
            )
        )


class TicketThemeView(View):
    def __init__(self, cog, guild_id: int, mode: str):
        super().__init__(timeout=600)
        self.add_item(TicketThemeSelect(cog, guild_id, mode))


class TicketMentionIdModal(Modal, title="Nhập ID cần tag"):
    def __init__(self, cog, ticket_type: str):
        super().__init__()
        self.cog = cog
        self.ticket_type = ticket_type
        self.target_ids = TextInput(
            label="Role ID hoặc User ID",
            placeholder="VD: 123456789012345678, 987654321098765432",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
        )
        self.add_item(self.target_ids)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_ticket_mention_ids(
            interaction,
            self.ticket_type,
            str(self.target_ids.value),
        )


class TicketMentionTargetView(View):
    def __init__(self, cog, ticket_type: str):
        super().__init__(timeout=600)
        self.cog = cog
        self.ticket_type = ticket_type

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.cog.require_role_or_admin_interaction(interaction, "ticket")

    @discord.ui.select(
        cls=RoleSelect,
        placeholder="Chọn role cần tag cho mục này...",
        min_values=1,
        max_values=10,
    )
    async def roles(self, interaction: discord.Interaction, select: RoleSelect):
        await self.cog.handle_ticket_mention_select(
            interaction,
            self.ticket_type,
            "role",
            [role.id for role in select.values],
        )

    @discord.ui.select(
        cls=UserSelect,
        placeholder="Chọn user cần tag cho mục này...",
        min_values=1,
        max_values=10,
    )
    async def users(self, interaction: discord.Interaction, select: UserSelect):
        await self.cog.handle_ticket_mention_select(
            interaction,
            self.ticket_type,
            "user",
            [user.id for user in select.values],
        )

    @discord.ui.button(label="Nhập ID", emoji="🆔", style=discord.ButtonStyle.secondary)
    async def ids(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(TicketMentionIdModal(self.cog, self.ticket_type))

    @discord.ui.button(label="Xóa tag mục này", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def clear(self, interaction: discord.Interaction, button: Button):
        self.cog.service.clear_type_mentions(interaction.guild.id, self.ticket_type)
        await safe_interaction_send(
            interaction,
            content="✅ Đã xóa toàn bộ role/user tag của mục này.",
            ephemeral=True,
        )


class TicketMentionTypeSelect(Select):
    def __init__(self, cog, guild_id: int):
        self.cog = cog
        self.guild_id = guild_id
        theme = cog.service.get_theme(guild_id)
        options = [
            discord.SelectOption(
                label=label[:100],
                value=value,
                emoji=ticket_emoji(value, theme),
            )
            for value, label in ticket_types(theme).items()
        ]
        super().__init__(
            placeholder="Chọn mục Ticket cần cài tag...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.cog.require_role_or_admin_interaction(interaction, "ticket"):
            return
        ticket_type = self.values[0]
        await safe_interaction_send(
            interaction,
            content=self.cog.ticket_mention_config_text(interaction.guild, ticket_type),
            view=TicketMentionTargetView(self.cog, ticket_type),
            ephemeral=True,
        )


class TicketMentionTypeView(View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=600)
        self.add_item(TicketMentionTypeSelect(cog, guild_id))


class TicketAutoResponseSelect(Select):
    def __init__(self, cog, guild_id: int):
        self.cog = cog
        self.guild_id = guild_id
        theme = cog.service.get_theme(guild_id)
        options = [
            discord.SelectOption(
                label=label[:100],
                value=f"autoresponse_{value}",
                description="Sửa lời yêu cầu tự động cho mục này...",
                emoji=ticket_emoji(value, theme),
            )
            for value, label in ticket_types(theme).items()
        ]
        super().__init__(
            placeholder="Chọn mục Ticket để sửa Auto-res...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.cog.require_role_or_admin_interaction(interaction, "ticket"):
            return
        key = self.values[0]
        theme = self.cog.service.get_theme(self.guild_id)
        await interaction.response.send_modal(TicketThemeModal(self.cog, self.guild_id, key, ticket_theme_value(theme, key)))


class TicketAutoResponseView(View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=600)
        self.add_item(TicketAutoResponseSelect(cog, guild_id))


class TicketManagerView(View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.cog.require_role_or_admin_interaction(interaction, "ticket")

    @discord.ui.button(label="Cấu hình kênh", style=discord.ButtonStyle.primary, emoji=ticket_emoji("channel"))
    async def channels(self, interaction: discord.Interaction, button: Button):
        await safe_interaction_send(
            interaction,
            content="Chọn kênh hoặc danh mục cần cấu hình:",
            view=TicketConfigView(self.cog),
            ephemeral=True,
        )

    @discord.ui.button(label="Giới hạn", style=discord.ButtonStyle.secondary, emoji=ticket_emoji("settings"))
    async def limits(self, interaction: discord.Interaction, button: Button):
        config = self.cog.service.ensure_config(interaction.guild.id)
        await interaction.response.send_modal(TicketLimitModal(self.cog, config))

    @discord.ui.button(label="Nội dung", style=discord.ButtonStyle.secondary, emoji="📝")
    async def content(self, interaction: discord.Interaction, button: Button):
        await safe_interaction_send(
            interaction,
            content="Chọn nội dung Ticket cần tùy chỉnh. Modal sẽ có ví dụ trong ô nhập.",
            view=TicketThemeView(self.cog, interaction.guild.id, "content"),
            ephemeral=True,
        )

    @discord.ui.button(label="Yêu cầu tự động (Auto-res)", style=discord.ButtonStyle.secondary, emoji="💬")
    async def auto_responses(self, interaction: discord.Interaction, button: Button):
        await safe_interaction_send(
            interaction,
            content="Chọn mục Ticket để cài đặt lời yêu cầu tự động (vd: xin bill, xin ảnh oxp/olvl...):",
            view=TicketAutoResponseView(self.cog, interaction.guild.id),
            ephemeral=True,
        )

    @discord.ui.button(label="Icon", style=discord.ButtonStyle.secondary, emoji="✨")
    async def icons(self, interaction: discord.Interaction, button: Button):
        await safe_interaction_send(
            interaction,
            content="Chọn icon Ticket cần tùy chỉnh.",
            view=TicketThemeView(self.cog, interaction.guild.id, "icon"),
            ephemeral=True,
        )

    @discord.ui.button(label="Tag theo mục", style=discord.ButtonStyle.secondary, emoji="🏷️")
    async def mentions(self, interaction: discord.Interaction, button: Button):
        await safe_interaction_send(
            interaction,
            content="Chọn mục Ticket để cài role/user được tag và cấp quyền xem kênh:",
            view=TicketMentionTypeView(self.cog, interaction.guild.id),
            ephemeral=True,
        )

    @discord.ui.button(label="Gửi / Refresh Panel", style=discord.ButtonStyle.success, emoji=ticket_emoji("refresh"))
    async def panel(self, interaction: discord.Interaction, button: Button):
        await self.cog.handle_send_panel(interaction)


class TicketLogReasonModal(Modal, title="Sửa lý do đóng Ticket"):
    def __init__(self, cog, ticket_id: int, current_reason: str):
        super().__init__()
        self.cog = cog
        self.ticket_id = ticket_id
        self.reason = TextInput(
            label="Lý do",
            style=discord.TextStyle.paragraph,
            default=current_reason,
            required=True,
            max_length=1000,
        )
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        self.cog.service.db.execute(
            "UPDATE tickets SET close_reason = ? WHERE ticket_id = ?",
            (self.reason.value.strip(), self.ticket_id),
        )
        embed = interaction.message.embeds[0]
        for index, field in enumerate(embed.fields):
            if "Lý do" in field.name:
                embed.set_field_at(index, name=field.name, value=self.reason.value.strip(), inline=field.inline)
                break
        await interaction.response.edit_message(embed=embed)


class TicketLogView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.cog.require_role_or_admin_interaction(interaction, "ticket")

    @discord.ui.button(
        label="Sửa lý do",
        style=discord.ButtonStyle.secondary,
        emoji=ticket_emoji("rename"),
        custom_id="ticket:log_reason",
    )
    async def edit_reason(self, interaction: discord.Interaction, button: Button):
        if not interaction.message.embeds:
            return
        embed = interaction.message.embeds[0]
        ticket_id = None
        current_reason = ""
        for field in embed.fields:
            if "Ticket ID" in field.name:
                match = re.search(r"\d+", field.value)
                ticket_id = int(match.group()) if match else None
            if "Lý do" in field.name:
                current_reason = field.value
        if ticket_id is None:
            await safe_interaction_send(
                interaction,
                content=f"{ticket_emoji('error')} Không tìm thấy Ticket ID.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(TicketLogReasonModal(self.cog, ticket_id, current_reason))
