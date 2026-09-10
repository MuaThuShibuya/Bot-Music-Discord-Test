from __future__ import annotations

import discord
from discord.ui import Button, ChannelSelect, Modal, Select, TextInput, View

from ui.event.emoji import EVENT_THEME_DEFAULTS, event_emoji, event_theme_value
from ui.event.ui import build_event_dashboard_embed

class EventThemeModal(Modal):
    def __init__(self, cog, guild_id: int, key: str, current: str):
        super().__init__(title=f"Sửa {key}"[:45])
        self.cog = cog
        self.guild_id = guild_id
        self.key = key
        self.value_input = TextInput(
            label=key[:45],
            placeholder=f"VD: {EVENT_THEME_DEFAULTS.get(key, '')}"[:100],
            default=current[:1000],
            style=discord.TextStyle.paragraph if len(current) > 80 else discord.TextStyle.short,
            max_length=1000,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_event_theme_submit(interaction, self.key, str(self.value_input.value))

class EventThemeSelect(Select):
    def __init__(self, cog, guild_id: int):
        self.cog = cog
        self.guild_id = guild_id
        options = [
            discord.SelectOption(
                label=key.replace("_", " ").title()[:100],
                value=key,
                description=f"VD: {example}"[:100],
                emoji="📝",
            )
            for key, example in EVENT_THEME_DEFAULTS.items()
        ]
        super().__init__(placeholder="Chọn nội dung cần sửa...", options=options)

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        theme = self.cog.service.get_theme(self.guild_id)
        await interaction.response.send_modal(EventThemeModal(self.cog, self.guild_id, key, event_theme_value(theme, key)))

class EventThemeView(View):
    def __init__(self, cog, guild_id: int):
        super().__init__(timeout=600)
        self.add_item(EventThemeSelect(cog, guild_id))

class EventNameModal(Modal):
    def __init__(self, cog, title: str, current_name: str = ""):
        super().__init__(title=title, timeout=300)
        self.cog = cog
        self.name_input = TextInput(
            label="Tên sự kiện",
            placeholder="Ví dụ: Thi ảnh đẹp 8/3",
            default=current_name,
            required=True,
            max_length=100,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        raise NotImplementedError


class CreateEventModal(EventNameModal):
    def __init__(self, cog):
        super().__init__(cog, "Tạo Sự kiện mới")

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_create_event(interaction, str(self.name_input.value))


class EditEventNameModal(EventNameModal):
    def __init__(self, cog, event: dict):
        super().__init__(cog, "Sửa tên sự kiện", event["name"])
        self.event = event

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_update_event_value(interaction, self.event, "name", str(self.name_input.value))


class EmojiModal(Modal, title="Sửa Emoji Vote"):
    def __init__(self, cog, event: dict):
        super().__init__()
        self.cog = cog
        self.event = event
        self.emoji_input = TextInput(label="Emoji", default=event["reaction_emoji"], required=True, max_length=50)
        self.add_item(self.emoji_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_update_event_value(interaction, self.event, "reaction_emoji", str(self.emoji_input.value))


class EventSelect(Select):
    def __init__(self, cog, events: list[dict]):
        self.cog = cog
        options = [
            discord.SelectOption(
                label=event["name"][:100],
                value=str(event["event_id"]),
                emoji="▶️" if event["status"] == "active" else "📝",
            )
            for event in events
        ]
        super().__init__(placeholder="Chọn sự kiện để quản lý...", options=options)

    async def callback(self, interaction: discord.Interaction):
        event = self.cog.service.get_event(int(self.values[0]))
        if not event:
            await interaction.response.edit_message(content="❌ Sự kiện không còn tồn tại.", embed=None, view=None)
            return
        theme = self.cog.service.get_theme(interaction.guild.id)
        await interaction.response.edit_message(
            embed=build_event_dashboard_embed(event, theme),
            view=EventConfigView(self.cog, event),
        )


class EventConfigView(View):
    def __init__(self, cog, event: dict):
        super().__init__(timeout=600)
        self.cog = cog
        self.event = event
        self._update_start_stop_button()

        theme = self.cog.service.get_theme(self.event["guild_id"])
        mapping = {
            "event_config:back": ("button_back", "back"),
            "event_config:edit_name": ("button_edit_name", "✏️"),
            "event_config:set_emoji": ("button_emoji", "emoji"),
            "event_config:delete": ("button_delete", "delete"),
            "event_config:view_lb": ("button_leaderboard", "leaderboard"),
        }
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.custom_id in mapping:
                child.emoji = event_emoji(mapping[child.custom_id][1], theme) if mapping[child.custom_id][1] != "✏️" else "✏️"

    def _update_start_stop_button(self):
        theme = self.cog.service.get_theme(self.event["guild_id"])
        start_stop_button = discord.utils.get(self.children, custom_id="event:start_stop")
        if not start_stop_button:
            return
        if self.event["status"] == "active":
            start_stop_button.label = event_theme_value(theme, "button_stop")
            start_stop_button.emoji = event_emoji("stop")
            start_stop_button.style = discord.ButtonStyle.danger
        else:
            start_stop_button.label = event_theme_value(theme, "button_start")
            start_stop_button.emoji = event_emoji("start")
            start_stop_button.style = discord.ButtonStyle.success

    @discord.ui.button(label="Back", style=discord.ButtonStyle.secondary, row=4, custom_id="event_config:back")
    async def back(self, interaction: discord.Interaction, button: Button):
        await self.cog.show_event_manager(interaction)

    @discord.ui.button(label="Tên", style=discord.ButtonStyle.secondary, emoji="✏️", custom_id="event_config:edit_name")
    async def edit_name(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(EditEventNameModal(self.cog, self.event))

    @discord.ui.select(cls=ChannelSelect, channel_types=[discord.ChannelType.text], placeholder="Chọn kênh sự kiện...")
    async def set_channel(self, interaction: discord.Interaction, select: ChannelSelect):
        await self.cog.handle_update_event_value(interaction, self.event, "channel_id", select.values[0].id)

    @discord.ui.button(label="Emoji", style=discord.ButtonStyle.secondary, custom_id="event_config:set_emoji")
    async def set_emoji(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(EmojiModal(self.cog, self.event))

    @discord.ui.select(
        placeholder="Chọn loại bài thi...",
        options=[
            discord.SelectOption(label="Tất cả", value="any", description="Cho phép mọi loại tin nhắn"),
            discord.SelectOption(label="Chỉ Ảnh", value="image", description="Chỉ chấp nhận tin nhắn có ảnh đính kèm"),
            discord.SelectOption(label="Chỉ Video", value="video", description="Chỉ chấp nhận tin nhắn có video đính kèm"),
            discord.SelectOption(label="Chỉ Link", value="link", description="Chỉ chấp nhận tin nhắn có link"),
        ],
    )
    async def set_filter(self, interaction: discord.Interaction, select: Select):
        await self.cog.handle_update_event_value(interaction, self.event, "filter_mode", select.values[0])

    @discord.ui.button(label="Bắt đầu sự kiện", style=discord.ButtonStyle.success, custom_id="event:start_stop")
    async def start_stop(self, interaction: discord.Interaction, button: Button):
        await self.cog.handle_toggle_event_status(interaction, self.event)

    @discord.ui.button(label="Leaderboard", style=discord.ButtonStyle.primary, row=4, custom_id="event_config:view_lb")
    async def view_lb(self, interaction: discord.Interaction, button: Button):
        await self.cog.show_leaderboard_page(interaction, self.event, 1)

    @discord.ui.button(label="Xóa", style=discord.ButtonStyle.danger, row=4, custom_id="event_config:delete")
    async def delete(self, interaction: discord.Interaction, button: Button):
        await self.cog.handle_delete_event(interaction, self.event)


class EventManagerDashboard(View):
    def __init__(self, cog, events: list[dict]):
        super().__init__(timeout=600)
        self.cog = cog
        if events:
            self.add_item(EventSelect(cog, events))

        theme = self.cog.service.get_theme(events[0]["guild_id"]) if events else {}
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == "event_manager:create":
                    child.label = event_theme_value(theme, "button_create")
                    child.emoji = event_emoji("create", theme)
                elif child.custom_id == "event_manager:theme":
                    child.label = event_theme_value(theme, "button_theme")
                    child.emoji = event_emoji("theme", theme)

    @discord.ui.button(label="Tạo Sự kiện", style=discord.ButtonStyle.success, custom_id="event_manager:create")
    async def create(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_modal(CreateEventModal(self.cog))

    @discord.ui.button(label="Giao diện (Theme)", style=discord.ButtonStyle.secondary, custom_id="event_manager:theme")
    async def config_theme(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message(content="Chọn mục text cần tùy chỉnh cấu hình:", view=EventThemeView(self.cog, interaction.guild.id), ephemeral=True)


class LeaderboardView(View):
    def __init__(self, cog, event: dict, total_pages: int, current_page: int = 1):
        super().__init__(timeout=900)
        self.cog = cog
        self.event = event
        self.total_pages = total_pages
        self.current_page = current_page
        self._update_buttons()

    def _update_buttons(self):
        self.children[0].disabled = self.current_page <= 1
        self.children[1].disabled = self.current_page >= self.total_pages

    @discord.ui.button(label="Trước", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def previous_page(self, interaction: discord.Interaction, button: Button):
        self.current_page -= 1
        await self.cog.show_leaderboard_page(interaction, self.event, self.current_page)

    @discord.ui.button(label="Sau", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def next_page(self, interaction: discord.Interaction, button: Button):
        self.current_page += 1
        await self.cog.show_leaderboard_page(interaction, self.event, self.current_page)