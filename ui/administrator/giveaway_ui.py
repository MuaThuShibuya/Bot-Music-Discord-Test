from __future__ import annotations

import discord

from ui.administrator.giveaway_emoji import (
    GIVEAWAY_THEME_DEFAULTS,
    giveaway_icon,
    giveaway_theme_value,
)


GIVEAWAY_CONFIG_FIELDS = {
    "entry_emoji": ("Emoji tham gia", "🎉", "Reaction để user tham gia"),
    "title_start": ("Tiêu đề bắt đầu", "{start} GIVEAWAY BẮT ĐẦU {start}", "Biến: {start}"),
    "title_ended": ("Tiêu đề kết thúc", "{ended} GIVEAWAY ĐÃ KẾT THÚC {ended}", "Biến: {ended}"),
    "text_join": ("Nội dung tham gia", "Nhấn vào {emoji} để tham gia", "Biến: {emoji}"),
    "text_ended": ("Nội dung kết thúc", "Giveaway đã đóng", "Có thể để trống"),
    "label_winner": ("Nhãn người thắng", "Người thắng", "Tên field winner"),
    "label_time": ("Nhãn thời gian", "Đếm ngược", "Tên field thời gian"),
    "label_host": ("Nhãn host", "Tổ chức bởi", "Tên field host"),
    "label_selected": ("Nhãn winner chọn sẵn", "Winner đã chọn", "Tên field winner chỉ định"),
    "label_package": ("Nhãn gói", "Gói", "Tên field số lượng"),
    "label_template": ("Nhãn template", "Template", "Tên field template"),
    "dm_winner": ("DM người thắng", "{dm} Chúc mừng {reward} tại {guild}", "Biến: {dm}, {action}, {reward}, {guild}"),
    "result_winner": ("Kết quả winner", "{icon} {winners} đã trúng {reward}", "Biến: {icon}, {winners}, {reward}"),
    "result_reroll": ("Kết quả reroll", "{icon} Reroll {round}: {winners}", "Thêm biến: {round}"),
    "result_no_winner": ("Không có winner", "{icon} Không có người tham gia", "Biến: {icon}, {reward}"),
    "icon_start": ("Icon bắt đầu", "🌸", "Emoji tiêu đề bắt đầu"),
    "icon_ended": ("Icon kết thúc", "🏁", "Emoji tiêu đề kết thúc"),
    "icon_winner": ("Icon winner", "🏆", "Emoji người thắng"),
    "icon_time": ("Icon thời gian", "⏳", "Emoji thời gian"),
    "icon_host": ("Icon host", "👑", "Emoji host"),
    "icon_selected": ("Icon winner chọn sẵn", "🎯", "Emoji winner chỉ định"),
    "icon_package": ("Icon gói", "🎁", "Emoji gói"),
    "icon_template": ("Icon template", "📝", "Emoji template"),
    "icon_dm": ("Icon DM", "🎉", "Emoji DM winner"),
    "icon_result": ("Icon kết quả", "🎉", "Emoji kết quả"),
    "icon_reroll": ("Icon reroll", "🔄", "Emoji khi reroll"),
    "icon_random": ("Icon random", "🎲", "Emoji nút random winner"),
    "icon_config": ("Icon config", "🎉", "Emoji thông báo config"),
    "icon_created": ("Icon đã tạo", "🎉", "Emoji thông báo tạo giveaway"),
    "icon_set": ("Icon chọn winner", "🎯", "Emoji thông báo set winner"),
}

GIVEAWAY_CONTENT_FIELDS = {
    key: value
    for key, value in GIVEAWAY_CONFIG_FIELDS.items()
    if key != "entry_emoji" and not key.startswith("icon_")
}
GIVEAWAY_ICON_FIELDS = {
    key: value
    for key, value in GIVEAWAY_CONFIG_FIELDS.items()
    if key == "entry_emoji" or key.startswith("icon_")
}


def build_giveaway_config_embed(entry_emoji: str, theme: dict) -> discord.Embed:
    changed = sum(1 for key in GIVEAWAY_THEME_DEFAULTS if key in theme)
    embed = discord.Embed(
        title="Giveaway Config",
        description=(
            "Chọn một mục trong menu để sửa. Ví dụ nằm ngay trong từng lựa chọn.\n"
            "Nhập `reset` để đưa riêng mục đã chọn về mặc định."
        ),
        color=discord.Color.from_rgb(255, 136, 190),
    )
    embed.add_field(name="Emoji tham gia", value=entry_emoji, inline=True)
    embed.add_field(name="Mục đã tùy chỉnh", value=f"`{changed}`", inline=True)
    embed.add_field(
        name="Biến thường dùng",
        value="`{emoji}` `{start}` `{ended}` `{winners}` `{reward}` `{guild}` `{round}`",
        inline=False,
    )
    return embed


class GiveawayConfigModal(discord.ui.Modal):
    def __init__(self, controller, guild_id: int, key: str, current: str):
        label, example, help_text = GIVEAWAY_CONFIG_FIELDS[key]
        super().__init__(title=f"Sửa {label}"[:45])
        self.controller = controller
        self.guild_id = guild_id
        self.key = key
        placeholder = f"VD: {example} | {help_text}"[:100]
        max_length = 100 if key == "entry_emoji" or key.startswith("icon_") else 4000
        if key.startswith("title_"):
            max_length = 256
        elif key.startswith("label_"):
            max_length = 256
        elif key.startswith("result_") or key == "dm_winner":
            max_length = 1900
        self.value_input = discord.ui.TextInput(
            label=label[:45],
            placeholder=placeholder,
            default=current[:max_length],
            style=discord.TextStyle.paragraph if len(current) > 80 or key.startswith(("result_", "dm_")) else discord.TextStyle.short,
            required=key != "text_ended",
            max_length=max_length,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.controller.handle_giveaway_config_submit(
            interaction,
            self.guild_id,
            self.key,
            str(self.value_input.value),
        )


class GiveawayConfigSelect(discord.ui.Select):
    def __init__(self, controller, guild_id: int, mode: str):
        self.controller = controller
        self.guild_id = guild_id
        fields = GIVEAWAY_ICON_FIELDS if mode == "icon" else GIVEAWAY_CONTENT_FIELDS
        options = [
            discord.SelectOption(
                label=label[:100],
                value=key,
                description=f"VD: {example}"[:100],
                emoji="✨" if mode == "icon" else "📝",
            )
            for key, (label, example, _) in fields.items()
        ]
        super().__init__(
            placeholder="Chọn icon/reaction cần sửa..." if mode == "icon" else "Chọn nội dung cần sửa...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.controller.require_role_or_admin_interaction(interaction, "giveaway"):
            return
        key = self.values[0]
        theme = self.controller.service.get_theme(self.guild_id)
        current = (
            self.controller.get_entry_emoji(self.guild_id)
            if key == "entry_emoji"
            else giveaway_theme_value(theme, key)
        )
        await interaction.response.send_modal(
            GiveawayConfigModal(self.controller, self.guild_id, key, current)
        )


class GiveawayConfigSelectView(discord.ui.View):
    def __init__(self, controller, guild_id: int, mode: str):
        super().__init__(timeout=600)
        self.add_item(GiveawayConfigSelect(controller, guild_id, mode))


class GiveawayConfigView(discord.ui.View):
    def __init__(self, controller, guild_id: int):
        super().__init__(timeout=600)
        self.controller = controller
        self.guild_id = guild_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.controller.require_role_or_admin_interaction(interaction, "giveaway")

    @discord.ui.button(label="Nội dung", emoji="📝", style=discord.ButtonStyle.primary)
    async def content(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Chọn nội dung giveaway cần sửa. Mỗi mục có ví dụ ngay trong menu.",
            view=GiveawayConfigSelectView(self.controller, self.guild_id, "content"),
            ephemeral=True,
        )

    @discord.ui.button(label="Icon & Reaction", emoji="✨", style=discord.ButtonStyle.secondary)
    async def icons(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "Chọn icon hoặc reaction tham gia cần sửa.",
            view=GiveawayConfigSelectView(self.controller, self.guild_id, "icon"),
            ephemeral=True,
        )


class GiveawayWinnerSelect(discord.ui.Select):
    def __init__(self, controller, giveaway: dict, participants: list[dict]):
        self.controller = controller
        self.giveaway = giveaway
        winners_count = int(giveaway["winners_count"])
        options = [
            discord.SelectOption(
                label=str(row["username"])[:100],
                value=str(row["user_id"]),
                description=f"ID {row['user_id']}"[:100],
            )
            for row in participants[:25]
        ]
        selected_count = max(1, min(winners_count, len(options)))
        super().__init__(
            placeholder=f"Chọn {selected_count} winner thủ công...",
            min_values=selected_count,
            max_values=selected_count,
            options=options,
            custom_id=f"giveaway:set_winner:{giveaway['giveaway_id']}",
        )

    async def callback(self, interaction: discord.Interaction):
        winner_ids = [int(value) for value in self.values]
        await self.controller._save_selected_winners_interaction(
            interaction,
            int(self.giveaway["giveaway_id"]),
            winner_ids,
        )


class GiveawayManualSetView(discord.ui.View):
    def __init__(self, controller, giveaway: dict, participants: list[dict]):
        super().__init__(timeout=900)
        self.controller = controller
        self.giveaway = giveaway
        if participants:
            self.add_item(GiveawayWinnerSelect(controller, giveaway, participants))

    @discord.ui.button(
        label="Random winner",
        style=discord.ButtonStyle.primary,
        emoji=giveaway_icon("random"),
        custom_id="giveaway:manual_random",
    )
    async def random_winner(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller._random_winners_interaction(
            interaction,
            int(self.giveaway["giveaway_id"]),
        )
