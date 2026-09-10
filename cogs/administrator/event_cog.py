from __future__ import annotations

import asyncio
import re

import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin_command_utils import AdminCommandBase
from services.event_service import EventService
from ui.event.components import EventConfigView, EventManagerDashboard, LeaderboardView
from ui.event.ui import (
    build_event_dashboard_embed,
    build_leaderboard_embed,
    build_manager_selection_embed,
    event_theme_value,
    event_emoji,
)
from utils import create_error_splash, create_info_splash, create_success_splash


LEADERBOARD_PAGE_SIZE = 10


class EventCog(AdminCommandBase):
    event_group = app_commands.Group(name="event", description="Quản lý sự kiện thi ảnh/video/meme")

    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.service = EventService()

    def _is_url(self, text: str) -> bool:
        return bool(re.match(r"https?://", text.strip(), flags=re.IGNORECASE))

    def _is_entry_valid(self, message: discord.Message, filter_mode: str) -> bool:
        if filter_mode == "any":
            return True
        if filter_mode == "image":
            return bool(message.attachments and any(att.content_type.startswith("image/") for att in message.attachments))
        if filter_mode == "video":
            return bool(message.attachments and any(att.content_type.startswith("video/") for att in message.attachments))
        if filter_mode == "link":
            return self._is_url(message.content)
        return False

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        event = self.service.get_active_event_in_channel(message.guild.id, message.channel.id)
        if not event:
            return

        if not self._is_entry_valid(message, event.get("filter_mode", "image")):
            try:
                await message.delete()
                await message.channel.send(
                    f"❌ {message.author.mention}, bài dự thi không hợp lệ. Sự kiện này chỉ chấp nhận "
                    f"`{event.get('filter_mode', 'image')}`.",
                    delete_after=10,
                )
            except discord.HTTPException:
                pass
            return

        self.service.add_entry(event["event_id"], message.guild.id, message.channel.id, message.author.id, message.id)
        try:
            await message.add_reaction(event.get("reaction_emoji", "❤️"))
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        self.service.remove_entry_by_message(payload.message_id)

    async def show_event_manager(self, interaction: discord.Interaction):
        theme = self.service.get_theme(interaction.guild.id)
        events = self.service.list_events(interaction.guild.id)
        embed = build_manager_selection_embed(events, theme)
        view = EventManagerDashboard(self, events)
        if interaction.response.is_done():
            await interaction.edit_original_response(content=None, embed=embed, view=view)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def handle_create_event(self, interaction: discord.Interaction, name: str):
        event = self.service.create_event(interaction.guild.id, name, interaction.user.id)
        theme = self.service.get_theme(interaction.guild.id)
        await interaction.response.edit_message(
            embed=build_event_dashboard_embed(event, theme),
            view=EventConfigView(self, event),
        )

    async def handle_update_event_value(self, interaction: discord.Interaction, event: dict, key: str, value: any):
        self.service.update_event(event["event_id"], **{key: value})
        theme = self.service.get_theme(interaction.guild.id)
        updated_event = self.service.get_event(event["event_id"])
        await interaction.response.edit_message(
            embed=build_event_dashboard_embed(updated_event, theme),
            view=EventConfigView(self, updated_event),
        )

    async def handle_toggle_event_status(self, interaction: discord.Interaction, event: dict):
        if event["status"] == "active":
            new_status = "closed"
        else:
            if not event.get("channel_id"):
                await interaction.response.send_message("❌ Vui lòng set kênh sự kiện trước khi bắt đầu.", ephemeral=True)
                return
            new_status = "active"

        self.service.update_event(event["event_id"], status=new_status)
        theme = self.service.get_theme(interaction.guild.id)
        updated_event = self.service.get_event(event["event_id"])
        await interaction.response.edit_message(
            embed=build_event_dashboard_embed(updated_event, theme),
            view=EventConfigView(self, updated_event),
        )

    async def handle_delete_event(self, interaction: discord.Interaction, event: dict):
        self.service.delete_event(event["event_id"])
        # Bug Fix: Phải quay lại list menu thay vì để dashboard trắng
        await self.show_event_manager(interaction)
        
    async def handle_event_theme_submit(self, interaction: discord.Interaction, key: str, value: str):
        if not await self.require_role_or_admin_interaction(interaction, "event"):
            return
        value = value.strip().replace("\\n", "\n")
        if value.lower() in {"reset", "default"}:
            self.service.reset_theme_value(interaction.guild.id, key)
            message = f"✅ Đã reset mục `{key}`."
        else:
            self.service.set_theme_value(interaction.guild.id, key, value)
            message = f"✅ Đã lưu thay đổi cho `{key}`."
        await interaction.response.send_message(message, ephemeral=True)
        # Update Dashboard if currently viewed
        await self.show_event_manager(interaction)

    async def show_leaderboard_page(self, interaction: discord.Interaction, event: dict, page: int):
        # Bug Fix: Timeout UX Deadlock - Báo tiến trình cho người dùng
        theme = self.service.get_theme(interaction.guild.id)
        if interaction.response.is_done():
            progress_msg = await interaction.followup.send("⏳ Đang đồng bộ dữ liệu realtime từ Discord, vui lòng chờ...", ephemeral=True)
        else:
            await interaction.response.send_message("⏳ Đang đồng bộ dữ liệu realtime từ Discord, vui lòng chờ...", ephemeral=True)
            progress_msg = await interaction.original_response()
            
        entries = self.service.get_entries(event["event_id"])
        if not entries:
            await progress_msg.edit(content="❌ Chưa có bài dự thi nào hợp lệ.")
            return

        channel = self.bot.get_channel(event["channel_id"])
        if not isinstance(channel, discord.TextChannel):
            await progress_msg.edit(content="❌ Kênh sự kiện không còn tồn tại.")
            return

        scored_entries = []
        for index, entry in enumerate(entries):
            if index > 0 and index % 10 == 0:
                try:
                    await progress_msg.edit(content=f"⏳ Đang đồng bộ dữ liệu... {index}/{len(entries)}")
                except discord.HTTPException:
                    pass
            try:
                message = await channel.fetch_message(entry["message_id"])
                score = 0
                for r in message.reactions:
                    if str(r.emoji) == event["reaction_emoji"]:
                        score = r.count
                        break
                if score > 0:
                    scored_entries.append({**entry, "score": score})
            except discord.NotFound:
                self.service.invalidate_entry(entry["entry_id"])
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.1)

        scored_entries.sort(key=lambda x: x["score"], reverse=True)
        total_pages = (len(scored_entries) + LEADERBOARD_PAGE_SIZE - 1) // LEADERBOARD_PAGE_SIZE
        page = max(1, min(page, total_pages))
        start_index = (page - 1) * LEADERBOARD_PAGE_SIZE
        end_index = start_index + LEADERBOARD_PAGE_SIZE
        page_entries = scored_entries[start_index:end_index]

        embed = build_leaderboard_embed(event, page_entries, theme, page, total_pages)
        view = LeaderboardView(self, event, total_pages, page)
        await progress_msg.edit(content=None, embed=embed, view=view)

    @event_group.command(name="manager", description="Mở bảng quản lý sự kiện")
    async def slash_manager(self, interaction: discord.Interaction):
        if not await self.require_role_or_admin_interaction(interaction, "event"):
            return
        await self.show_event_manager(interaction)

    @event_group.command(name="leaderboard", description="Xem bảng xếp hạng của một sự kiện")
    async def slash_leaderboard(self, interaction: discord.Interaction):
        if not await self.require_role_or_admin_interaction(interaction, "event"):
            return

        events = self.service.list_events(interaction.guild.id, "active")
        if not events:
            await interaction.response.send_message("❌ Hiện không có sự kiện nào đang chạy.", ephemeral=True)
            return

        if len(events) > 1:
            await interaction.response.send_message(
                "⚠️ Có nhiều sự kiện đang chạy. Vui lòng dùng lệnh `/event manager`, chọn sự kiện cần xem và bấm nút **Leaderboard**.", 
                ephemeral=True
            )
        else:
            await self.show_leaderboard_page(interaction, events[0], 1)

    @commands.group(name="event", invoke_without_command=True)
    async def event(self, ctx: commands.Context, *, content: str = ""):
        if ctx.guild is None:
            return
        if not await self.require_role_or_admin_ctx(ctx, "event"):
            return

        first, _, rest = (content or "").partition(" ")
        if first.lower() in {"manager", "manage", "config"}:
            # Create a proxy interaction to reuse the slash command flow
            class InteractionProxy:
                def __init__(self, ctx):
                    self.guild = ctx.guild
                    self.user = ctx.author
                    self.response = self
                    self._ctx = ctx
                    self._sent = False

                def is_done(self):
                    return self._sent

                async def send_message(self, *args, **kwargs):
                    kwargs.pop("ephemeral", None)
                    self._sent = True
                    return await self._ctx.send(*args, **kwargs)

                async def edit_original_response(self, *args, **kwargs):
                    # This is a simplification; a real implementation would need to track the message
                    return await self._ctx.send(*args, **kwargs)

            await self.show_event_manager(InteractionProxy(ctx))
            return

        if first.lower() in {"leaderboard", "lb", "top"}:
            events = self.service.list_events(ctx.guild.id, "active")
            if not events:
                await ctx.send(embed=create_error_splash("Không có sự kiện", "Hiện không có sự kiện nào đang chạy."))
                return

            class InteractionProxy:
                def __init__(self, ctx):
                    self.guild = ctx.guild
                    self.user = ctx.author
                    self.response = self
                    self._ctx = ctx
                    self._sent = False
                    self._progress_msg = None

                def is_done(self):
                    return self._sent

                async def defer(self):
                    self._sent = True
                    self._progress_msg = await self._ctx.send("⏳ Đang chuẩn bị dữ liệu...")
                    return self._progress_msg

                async def send_message(self, *args, **kwargs):
                    kwargs.pop("ephemeral", None)
                    self._sent = True
                    self._progress_msg = await self._ctx.send(*args, **kwargs)

                async def original_response(self):
                    return self._progress_msg

                async def followup(self, *args, **kwargs):
                    kwargs.pop("ephemeral", None)
                    return await self._progress_msg.edit(*args, **kwargs) if self._progress_msg else await self._ctx.send(*args, **kwargs)

            if len(events) > 1:
                await ctx.send(
                    embed=create_error_splash("Nhiều Sự Kiện Đang Chạy", f"Có nhiều sự kiện. Vui lòng dùng lệnh `{ctx.prefix}event manager`, chọn sự kiện và bấm nút **Leaderboard**.")
                )
            else:
                await self.show_leaderboard_page(InteractionProxy(ctx), events[0], 1)
            return

        await ctx.send(
            embed=create_info_splash(
                f"{event_emoji('event')} Event",
                f"Dùng `{ctx.prefix}event manager` để quản lý sự kiện.\n"
                f"Dùng `{ctx.prefix}event leaderboard` để xem bảng xếp hạng.",
            )
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EventCog(bot))