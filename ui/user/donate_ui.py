from __future__ import annotations

import discord


MODE_LABELS = {
    "bank": "Bank / QR",
    "cash": "Cash",
}


class DonateModal(discord.ui.Modal):
    def __init__(self, controller, mode: str):
        mode = "cash" if mode == "cash" else "bank"
        super().__init__(title=f"Donate bằng {MODE_LABELS[mode]}")
        self.controller = controller
        self.mode = mode
        self.amount = discord.ui.TextInput(
            label="Số tiền donate",
            placeholder="Ví dụ: 10k, 100000",
            min_length=1,
            max_length=30,
            required=True,
        )
        self.message = discord.ui.TextInput(
            label="Nội dung donate",
            placeholder="Lời nhắn gửi tới server (không bắt buộc)",
            style=discord.TextStyle.paragraph,
            max_length=500,
            required=False,
        )
        self.add_item(self.amount)
        self.add_item(self.message)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await self.controller.process_donation(
            interaction,
            self.mode,
            str(self.amount.value),
            str(self.message.value or ""),
        )


class DonateModeView(discord.ui.View):
    def __init__(self, controller, author_id: int):
        super().__init__(timeout=180)
        self.controller = controller
        self.author_id = int(author_id)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("❌ Chỉ người gọi lệnh mới dùng được menu này.", ephemeral=True)
        return False

    @discord.ui.button(label="Bank / QR", emoji="🏦", style=discord.ButtonStyle.primary)
    async def bank(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DonateModal(self.controller, "bank"))

    @discord.ui.button(label="Cash", emoji="💰", style=discord.ButtonStyle.success)
    async def cash(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DonateModal(self.controller, "cash"))


class DonateFormLauncherView(discord.ui.View):
    def __init__(self, controller, author_id: int, mode: str):
        super().__init__(timeout=180)
        self.controller = controller
        self.author_id = int(author_id)
        self.mode = "cash" if mode == "cash" else "bank"
        label = f"Mở biểu mẫu {MODE_LABELS[self.mode]}"
        emoji = "💰" if self.mode == "cash" else "🏦"
        button = discord.ui.Button(label=label, emoji=emoji, style=discord.ButtonStyle.primary)
        button.callback = self.open_modal
        self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("❌ Chỉ người gọi lệnh mới mở được biểu mẫu này.", ephemeral=True)
        return False

    async def open_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DonateModal(self.controller, self.mode))
