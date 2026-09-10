from __future__ import annotations

import discord

from services.music_player_service import DEFAULT_PLAYER_THEME


PLAY_CONTENT_FIELDS = {
    key: value
    for key, value in DEFAULT_PLAYER_THEME.items()
    if not key.startswith(("icon_", "reaction_"))
    and key not in {"accent_color", "background_url"}
}
PLAY_ICON_FIELDS = {
    key: value
    for key, value in DEFAULT_PLAYER_THEME.items()
    if key.startswith(("icon_", "reaction_"))
}


def build_play_config_embed(theme: dict) -> discord.Embed:
    return discord.Embed(
        title="Music Player Config",
        description=(
            "Dùng các nút bên dưới để sửa giao diện, nội dung, icon nút hoặc reaction.\n"
            "Trong menu, mỗi mục đều hiện ví dụ. Nhập `reset` để trả riêng mục đó về mặc định."
        ),
        color=discord.Color.from_str(str(theme.get("accent_color") or "#7f314d")),
    )


class PlayerThemeModal(discord.ui.Modal, title="Chỉnh giao diện Player"):
    accent = discord.ui.TextInput(
        label="Màu chính",
        placeholder="#7f314d",
        required=False,
        max_length=7,
    )
    title_text = discord.ui.TextInput(
        label="Tiêu đề nhỏ",
        placeholder="BLACK LOUS MUSIC",
        required=False,
        max_length=40,
    )
    background_url = discord.ui.TextInput(
        label="URL ảnh nền",
        placeholder="https://... hoặc để trống để dùng ảnh trong UI",
        required=False,
        max_length=500,
    )

    def __init__(self, controller, guild_id: int, theme: dict):
        super().__init__()
        self.controller = controller
        self.guild_id = guild_id
        self.accent.default = str(theme.get("accent_color") or "#7f314d")
        self.title_text.default = str(theme.get("title_text") or "BLACK LOUS MUSIC")
        self.background_url.default = str(theme.get("background_url") or "")

    async def on_submit(self, interaction: discord.Interaction):
        await self.controller.handle_player_theme_submit(
            interaction,
            self.guild_id,
            accent=str(self.accent.value),
            title_text=str(self.title_text.value),
            background_url=str(self.background_url.value),
        )


class PlayThemeModal(discord.ui.Modal):
    def __init__(self, controller, guild_id: int, key: str, current: str):
        super().__init__(title=f"Sửa {key}"[:45])
        self.controller = controller
        self.guild_id = guild_id
        self.key = key
        example = DEFAULT_PLAYER_THEME.get(key, "")
        max_length = 4000
        if key.startswith("button_"):
            max_length = 80
        elif key.startswith(("icon_", "reaction_")):
            max_length = 100
        elif key == "title_text":
            max_length = 40
        elif key.startswith("card_"):
            max_length = 120
        elif key.startswith("message_"):
            max_length = 1900
        self.value_input = discord.ui.TextInput(
            label=key[:45],
            placeholder=f"VD: {example}"[:100],
            default=str(current)[:max_length],
            style=discord.TextStyle.paragraph if len(str(current)) > 80 else discord.TextStyle.short,
            max_length=max_length,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.controller.handle_play_theme_submit(
            interaction,
            self.guild_id,
            self.key,
            str(self.value_input.value),
        )


class PlayThemeSelect(discord.ui.Select):
    def __init__(self, controller, guild_id: int, mode: str):
        self.controller = controller
        self.guild_id = guild_id
        fields = PLAY_ICON_FIELDS if mode == "icon" else PLAY_CONTENT_FIELDS
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
            placeholder="Chọn icon/reaction cần sửa..." if mode == "icon" else "Chọn nội dung cần sửa...",
            options=options[:25],
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.controller.check_player_settings_interaction(interaction, self.guild_id):
            return
        key = self.values[0]
        theme = self.controller.player_service.get_theme(self.guild_id)
        await interaction.response.send_modal(
            PlayThemeModal(self.controller, self.guild_id, key, theme.get(key, ""))
        )


class PlayThemeView(discord.ui.View):
    def __init__(self, controller, guild_id: int, mode: str):
        super().__init__(timeout=600)
        self.add_item(PlayThemeSelect(controller, guild_id, mode))


class PlayConfigMenu(discord.ui.View):
    def __init__(self, controller, guild_id: int):
        super().__init__(timeout=600)
        self.controller = controller
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.controller.check_player_settings_interaction(interaction, self.guild_id)

    @discord.ui.button(label="Giao diện", emoji="🎨", style=discord.ButtonStyle.primary)
    async def appearance(self, interaction: discord.Interaction, button: discord.ui.Button):
        theme = self.controller.player_service.get_theme(self.guild_id)
        await interaction.response.send_modal(
            self.controller.player_theme_modal(self.guild_id, theme)
        )

    @discord.ui.button(label="Nội dung", emoji="📝", style=discord.ButtonStyle.secondary)
    async def content(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Chọn nội dung card/message/nút cần sửa:",
            view=PlayThemeView(self.controller, self.guild_id, "content"),
            ephemeral=True,
        )

    @discord.ui.button(label="Icon & React", emoji="✨", style=discord.ButtonStyle.secondary)
    async def icons(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Chọn icon nút hoặc reaction cần sửa:",
            view=PlayThemeView(self.controller, self.guild_id, "icon"),
            ephemeral=True,
        )

    @discord.ui.button(label="Xem trước", emoji="🖼️", style=discord.ButtonStyle.secondary)
    async def preview(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.send_player_preview(interaction, self.guild_id)

    @discord.ui.button(label="Reset tất cả", emoji="↩️", style=discord.ButtonStyle.danger)
    async def reset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.reset_player_theme(interaction, self.guild_id)
