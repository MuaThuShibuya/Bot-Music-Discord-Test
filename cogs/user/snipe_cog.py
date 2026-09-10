from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

import discord
from discord.ext import commands

from services.snipe_service import SnipeService


MAX_SNIPES_PER_CHANNEL = 500
SNIPES_PER_PAGE = 10


@dataclass
class DeletedMessage:
    author_id: int
    author_name: str
    author_avatar: str
    content: str
    channel_id: int
    channel_name: str
    deleted_at: datetime
    attachments: list[str]


class SnipeHistoryView(discord.ui.View):
    def __init__(self, entries: list[DeletedMessage], requester_id: int):
        super().__init__(timeout=None)
        self.entries = entries
        self.requester_id = requester_id
        self.page = 0
        self._sync_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("❌ Menu này không phải của bạn.", ephemeral=True)
            return False
        return True

    def _sync_buttons(self):
        last_index = len(self.entries) - 1
        self.first_page.disabled = self.page <= 0
        self.previous_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= last_index
        self.last_page.disabled = self.page >= last_index

    def build_embed(self) -> discord.Embed:
        entry = self.entries[self.page]
        description = entry.content.strip() if entry.content.strip() else "*Tin nhắn không có nội dung text.*"
        if len(description) > 3900:
            description = description[:3897] + "..."

        embed = discord.Embed(
            title="🕵️ Snipe",
            description=description,
            color=discord.Color.from_rgb(46, 48, 53),
            timestamp=entry.deleted_at,
        )
        embed.set_author(name=entry.author_name, icon_url=entry.author_avatar)
        embed.add_field(name="Kênh", value=f"<#{entry.channel_id}>", inline=True)
        embed.add_field(name="Trang", value=f"`{self.page + 1}/{len(self.entries)}`", inline=True)
        embed.add_field(name="Đã xoá lúc", value=f"<t:{int(entry.deleted_at.timestamp())}:R>", inline=True)

        image_url = next((url for url in entry.attachments if _is_image_url(url)), None)
        if image_url:
            embed.set_image(url=image_url)
        other_attachments = [url for url in entry.attachments if url != image_url]
        if other_attachments:
            links = "\n".join(f"[File {index}]({url})" for index, url in enumerate(other_attachments[:8], 1))
            embed.add_field(name="File đính kèm", value=links, inline=False)

        embed.set_footer(text="Tin mới xoá nhất nằm ở trang 1")
        return embed

    async def _update(self, interaction: discord.Interaction):
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Đầu", style=discord.ButtonStyle.secondary, emoji="⏮️")
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        await self._update(interaction)

    @discord.ui.button(label="Lùi", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self._update(interaction)

    @discord.ui.button(label="Tiếp", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(len(self.entries) - 1, self.page + 1)
        await self._update(interaction)

    @discord.ui.button(label="Cuối", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = len(self.entries) - 1
        await self._update(interaction)


class SnipeListView(discord.ui.View):
    def __init__(self, entries: list[DeletedMessage], requester_id: int):
        super().__init__(timeout=None)
        self.entries = entries
        self.requester_id = requester_id
        self.page = 0
        self._sync_buttons()

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.entries) + SNIPES_PER_PAGE - 1) // SNIPES_PER_PAGE)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("❌ Menu này không phải của bạn.", ephemeral=True)
            return False
        return True

    def _sync_buttons(self):
        last_index = self.total_pages - 1
        self.first_page.disabled = self.page <= 0
        self.previous_page.disabled = self.page <= 0
        self.next_page.disabled = self.page >= last_index
        self.last_page.disabled = self.page >= last_index

    @staticmethod
    def _short_content(content: str) -> str:
        cleaned = " ".join((content or "").split())
        if not cleaned:
            return "*Không có nội dung text*"
        return cleaned[:117] + "..." if len(cleaned) > 120 else cleaned

    def build_embed(self) -> discord.Embed:
        start = self.page * SNIPES_PER_PAGE
        chunk = self.entries[start:start + SNIPES_PER_PAGE]
        lines = []
        for index, entry in enumerate(chunk, start + 1):
            content = self._short_content(entry.content)
            attachment_note = " 📎" if entry.attachments else ""
            lines.append(
                f"**{index}.** `{entry.author_name}` • <t:{int(entry.deleted_at.timestamp())}:R>{attachment_note}\n"
                f"{content}"
            )

        embed = discord.Embed(
            title="🕵️ Snipe",
            description="\n\n".join(lines) if lines else "*Không có dữ liệu.*",
            color=discord.Color.from_rgb(46, 48, 53),
            timestamp=self.entries[0].deleted_at if self.entries else None,
        )
        first_entry = self.entries[0]
        embed.set_author(name=first_entry.author_name, icon_url=first_entry.author_avatar)
        embed.add_field(name="Kênh", value=f"<#{first_entry.channel_id}>", inline=True)
        embed.add_field(name="Trang", value=f"`{self.page + 1}/{self.total_pages}`", inline=True)
        embed.add_field(name="Tổng tin", value=f"`{len(self.entries)}`", inline=True)
        embed.set_footer(text="Tin mới xoá nhất nằm ở trang 1")
        return embed

    async def _update(self, interaction: discord.Interaction):
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Đầu", style=discord.ButtonStyle.secondary, emoji="⏮️")
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = 0
        await self._update(interaction)

    @discord.ui.button(label="Lùi", style=discord.ButtonStyle.secondary, emoji="◀️")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self._update(interaction)

    @discord.ui.button(label="Tiếp", style=discord.ButtonStyle.secondary, emoji="▶️")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.total_pages - 1, self.page + 1)
        await self._update(interaction)

    @discord.ui.button(label="Cuối", style=discord.ButtonStyle.secondary, emoji="⏭️")
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = self.total_pages - 1
        await self._update(interaction)


def _is_image_url(url: str) -> bool:
    lowered = url.lower().split("?")[0]
    return lowered.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp"))


def _entry_from_row(row: dict) -> DeletedMessage:
    try:
        attachments = json.loads(row.get("attachments") or "[]")
    except (TypeError, json.JSONDecodeError):
        attachments = []
    deleted_at = datetime.fromisoformat(row["deleted_at"])
    if deleted_at.tzinfo is None:
        deleted_at = deleted_at.replace(tzinfo=timezone.utc)
    return DeletedMessage(
        author_id=int(row["author_id"]),
        author_name=row.get("author_name") or str(row["author_id"]),
        author_avatar=row.get("author_avatar") or "",
        content=row.get("content") or "",
        channel_id=int(row["channel_id"]),
        channel_name=row.get("channel_name") or str(row["channel_id"]),
        deleted_at=deleted_at,
        attachments=list(attachments),
    )


class SnipeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = SnipeService()

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author == self.bot.user:
            return

        attachments = [attachment.url for attachment in message.attachments]
        self.service.add_deleted_message(
            guild_id=message.guild.id,
            channel_id=message.channel.id,
            channel_name=getattr(message.channel, "name", str(message.channel.id)),
            author_id=message.author.id,
            author_name=getattr(message.author, "display_name", message.author.name),
            author_avatar=message.author.display_avatar.url,
            content=message.content or "",
            attachments=attachments,
            deleted_at=datetime.now(timezone.utc),
        )

    @commands.command(name="snipe", aliases=["sn"])
    async def snipe(self, ctx: commands.Context, amount: str = "1"):
        if ctx.guild is None:
            await ctx.send("❌ Lệnh này chỉ dùng trong server.")
            return

        amount_text = str(amount or "1").strip().lower()
        if amount_text == "all":
            limit = MAX_SNIPES_PER_CHANNEL
        else:
            try:
                limit = int(amount_text)
            except ValueError:
                await ctx.send("❌ Dùng: `snipe [số|all]`, ví dụ `sn`, `sn 10`, `sn all`.")
                return
            if limit <= 0:
                await ctx.send("❌ Số lượng phải lớn hơn 0.")
                return

        rows = self.service.get_recent(ctx.guild.id, ctx.channel.id, min(limit, MAX_SNIPES_PER_CHANNEL))
        entries = [_entry_from_row(row) for row in rows]
        if not entries:
            await ctx.send("❌ Chưa có tin nhắn nào bị xoá trong kênh này.")
            return

        view = SnipeHistoryView(entries, ctx.author.id) if limit == 1 else SnipeListView(entries, ctx.author.id)
        await ctx.send(embed=view.build_embed(), view=view, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(SnipeCog(bot))
