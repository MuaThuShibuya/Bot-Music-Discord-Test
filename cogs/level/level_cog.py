from __future__ import annotations

import importlib
import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_error_splash,
    create_info_splash,
    create_success_splash,
    format_duration_seconds,
    parse_duration,
)

import services.level_service as level_service_module
importlib.reload(level_service_module)

from services.level_service import LevelService
from utils import append_discord_timestamp


PERIOD_ALIASES = {
    "total": "total",
    "tong": "total",
    "tổng": "total",
    "alltime": "total",
    "month": "month",
    "thang": "month",
    "tháng": "month",
    "week": "week",
    "tuan": "week",
    "tuần": "week",
    "day": "day",
    "ngay": "day",
    "ngày": "day",
}
PERIOD_LABELS = {
    "total": "Tổng",
    "month": "Tháng này",
    "week": "Tuần này",
    "day": "Hôm nay",
}
METRIC_ALIASES = {
    "xp": "xp",
    "level": "level",
    "lv": "level",
    "messages": "messages",
    "message": "messages",
    "msg": "messages",
    "tin": "messages",
    "tinnhan": "messages",
    "tin_nhan": "messages",
    "voice": "voice",
    "vc": "voice",
}
METRIC_LABELS = {
    "xp": "XP",
    "level": "Level",
    "messages": "Tin nhắn",
    "voice": "Voice",
}
FIELD_ALIASES = {
    "xp": "xp",
    "level": "level",
    "lv": "level",
    "messages": "messages",
    "message": "messages",
    "msg": "messages",
    "tin": "messages",
    "tinnhan": "messages",
    "voice": "voice",
    "vc": "voice",
}
ACTION_ALIASES = {
    "a": "add",
    "add": "add",
    "them": "add",
    "thêm": "add",
    "d": "remove",
    "del": "remove",
    "delete": "remove",
    "r": "remove",
    "rm": "remove",
    "remove": "remove",
    "xoa": "remove",
    "xoá": "remove",
    "e": "edit",
    "edit": "edit",
    "sua": "edit",
    "sửa": "edit",
}

PERIOD_CHOICES = [
    app_commands.Choice(name="Tổng", value="total"),
    app_commands.Choice(name="Tháng này", value="month"),
    app_commands.Choice(name="Tuần này", value="week"),
    app_commands.Choice(name="Hôm nay", value="day"),
]
METRIC_CHOICES = [
    app_commands.Choice(name="XP", value="xp"),
    app_commands.Choice(name="Level", value="level"),
    app_commands.Choice(name="Tin nhắn", value="messages"),
    app_commands.Choice(name="Voice", value="voice"),
]
FIELD_CHOICES = [
    app_commands.Choice(name="XP", value="xp"),
    app_commands.Choice(name="Level", value="level"),
    app_commands.Choice(name="Tin nhắn", value="messages"),
    app_commands.Choice(name="Voice", value="voice"),
]
MODE_CHOICES = [
    app_commands.Choice(name="Add", value="add"),
    app_commands.Choice(name="Remove", value="remove"),
    app_commands.Choice(name="Edit", value="edit"),
]
XP_MODE_LABELS = {
    "easy": "Ít XP",
    "normal": "Vừa XP",
    "hard": "Nhiều XP",
    "manual": "Thủ công",
    "custom": "Tùy chỉnh",
}
XP_MODE_CHOICES = [
    app_commands.Choice(name="Ít XP để lên level", value="easy"),
    app_commands.Choice(name="Vừa XP để lên level", value="normal"),
    app_commands.Choice(name="Nhiều XP để lên level", value="hard"),
    app_commands.Choice(name="Tự set mốc level", value="manual"),
    app_commands.Choice(name="Tùy chỉnh base XP", value="custom"),
]
LEVEL_ACTION_CHOICES = [
    app_commands.Choice(name="me", value="me"),
    app_commands.Choice(name="user", value="user"),
    app_commands.Choice(name="all", value="all"),
    app_commands.Choice(name="count", value="count"),
    app_commands.Choice(name="setup", value="setup"),
    app_commands.Choice(name="xp", value="xp"),
    app_commands.Choice(name="xp-level", value="xp-level"),
    app_commands.Choice(name="reward-add", value="reward-add"),
    app_commands.Choice(name="reward-remove", value="reward-remove"),
    app_commands.Choice(name="rewards", value="rewards"),
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove"),
    app_commands.Choice(name="edit", value="edit"),
]


def normalize_period(value: str | None, default: str = "total") -> str:
    if not value:
        return default
    return PERIOD_ALIASES.get(str(value).strip().lower(), default)


def normalize_metric(value: str | None, default: str = "xp") -> str:
    if not value:
        return default
    return METRIC_ALIASES.get(str(value).strip().lower(), default)


def normalize_field(value: str | None) -> str | None:
    if not value:
        return None
    return FIELD_ALIASES.get(str(value).strip().lower())


def format_xp(value: int) -> str:
    return f"{int(value):,} XP"


def progress_bar(percent: float, size: int = 12) -> str:
    percent = max(0.0, min(1.0, float(percent)))
    filled = round(percent * size)
    return "▰" * filled + "▱" * (size - filled)


def parse_stat_value(field: str, raw_value: str) -> int:
    if field == "voice":
        seconds = parse_duration(raw_value)
        if seconds is None:
            raise ValueError("Voice dùng dạng `30m`, `1h`, `90s` hoặc số phút.")
        return int(seconds)
    try:
        value = int(str(raw_value).replace(",", "").replace(".", "").strip())
    except ValueError as exc:
        raise ValueError(f"Giá trị `{raw_value}` không hợp lệ.") from exc
    if value < 0:
        raise ValueError("Giá trị không được âm.")
    return value


class LevelPeriodButton(discord.ui.Button):
    def __init__(self, cog: "LevelCog", member_id: int, period: str):
        super().__init__(
            label=PERIOD_LABELS[period],
            style=discord.ButtonStyle.secondary,
            custom_id=f"level:period:{member_id}:{period}",
        )
        self.cog = cog
        self.member_id = member_id
        self.period = period

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Chỉ dùng trong server.", ephemeral=True)
            return
        member = interaction.guild.get_member(self.member_id)
        if member is None:
            try:
                member = await interaction.guild.fetch_member(self.member_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                await interaction.response.send_message("❌ Không tìm thấy user.", ephemeral=True)
                return
        embed = self.cog.build_profile_embed(interaction.guild, member, self.period)
        await interaction.response.edit_message(embed=embed, view=LevelProfileView(self.cog, member.id, self.period))


class LevelProfileView(discord.ui.View):
    def __init__(self, cog: "LevelCog", member_id: int, active_period: str = "total"):
        super().__init__(timeout=300)
        for period in ("total", "month", "week", "day"):
            button = LevelPeriodButton(cog, member_id, period)
            if period == active_period:
                button.style = discord.ButtonStyle.primary
            self.add_item(button)


class LevelManualModal(discord.ui.Modal):
    def __init__(self, cog: "LevelCog", member: discord.Member, mode: str):
        mode_labels = {
            "add": "Add Level Stat",
            "remove": "Remove Level Stat",
            "edit": "Edit Level Stat",
        }
        super().__init__(title=mode_labels[mode], timeout=300)
        self.cog = cog
        self.member = member
        self.mode = mode

        self.xp = discord.ui.TextInput(
            label="XP",
            placeholder="Bỏ trống nếu không đổi",
            required=False,
            max_length=20,
        )
        self.level = discord.ui.TextInput(
            label="Level",
            placeholder="Bỏ trống nếu không đổi",
            required=False,
            max_length=20,
        )
        self.messages = discord.ui.TextInput(
            label="Messages",
            placeholder="Bỏ trống nếu không đổi",
            required=False,
            max_length=20,
        )
        self.voice = discord.ui.TextInput(
            label="Voice",
            placeholder="30m, 1h, 90s hoặc số phút",
            required=False,
            max_length=20,
        )
        self.add_item(self.xp)
        self.add_item(self.level)
        self.add_item(self.messages)
        self.add_item(self.voice)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Chỉ dùng trong server.", ephemeral=True)
            return
        if not self.cog.admins.is_hard_admin(interaction.user.id):
            await interaction.response.send_message(
                embed=create_error_splash("❌ Quyền Bị Từ Chối", "Bạn không có quyền dùng lệnh này."),
                ephemeral=True,
            )
            return

        raw_values = {
            "xp": str(self.xp.value or "").strip(),
            "level": str(self.level.value or "").strip(),
            "messages": str(self.messages.value or "").strip(),
            "voice": str(self.voice.value or "").strip(),
        }
        selected = [(field, value) for field, value in raw_values.items() if value]
        if not selected:
            await interaction.response.send_message(
                embed=create_error_splash("❌ Chưa Nhập Dữ Liệu", "Hãy nhập ít nhất một ô: XP, Level, Messages hoặc Voice."),
                ephemeral=True,
            )
            return

        before = self.cog.service.get_user_period_stats(
            interaction.guild.id,
            self.member.id,
            "total",
            self.member.display_name,
        )
        changes = []
        updated = None
        try:
            for field, raw_value in selected:
                parsed_value = parse_stat_value(field, raw_value)
                updated = self.cog.service.manual_update(
                    interaction.guild.id,
                    self.member.id,
                    self.member.display_name,
                    field,
                    self.mode,
                    parsed_value,
                )
                display_value = format_duration_seconds(parsed_value) if field == "voice" else f"{parsed_value:,}"
                changes.append(f"**{METRIC_LABELS.get(field, field)}:** `{display_value}`")
        except ValueError as exc:
            await interaction.response.send_message(embed=create_error_splash("❌ Giá Trị Không Hợp Lệ", str(exc)), ephemeral=True)
            return

        if updated and int(updated["level"]) > int(before["level"]):
            await self.cog.handle_level_up(self.member, int(before["level"]), int(updated["level"]))

        mode_text = {
            "add": "Đã cộng",
            "remove": "Đã trừ",
            "edit": "Đã set",
        }[self.mode]
        await interaction.response.send_message(
            embed=create_success_splash(
                "✅ Đã Cập Nhật Level",
                (
                    f"{mode_text} stat cho {self.member.mention}.\n"
                    + "\n".join(changes)
                    + f"\nLevel hiện tại: `{int(updated['level'])}`\n"
                    + f"XP hiện tại: `{format_xp(int(updated['total_xp']))}`"
                ),
            ),
            ephemeral=True,
        )


class LevelCog(AdminCommandBase):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.service = LevelService()
        self._voice_restored = False

    @commands.Cog.listener()
    async def on_ready(self):
        if self._voice_restored:
            return
        self._voice_restored = True
        for guild in self.bot.guilds:
            for channel in guild.voice_channels:
                for member in channel.members:
                    if member.bot:
                        continue
                    self.service.start_voice_session(
                        guild.id,
                        member.id,
                        member.display_name,
                        channel.id,
                    )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        member = message.author
        result = self.service.add_message_activity(
            message.guild.id,
            member.id,
            member.display_name,
        )
        if result.get("leveled_up"):
            await self.handle_level_up(
                member=member,
                old_level=int(result["old_level"]),
                new_level=int(result["new_level"]),
                fallback_channel=message.channel,
            )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        if member.bot or member.guild is None:
            return
        if before.channel is None and after.channel is not None:
            self.service.start_voice_session(member.guild.id, member.id, member.display_name, after.channel.id)
            return
        if before.channel is not None and after.channel is None:
            result = self.service.finish_voice_session(member.guild.id, member.id, member.display_name)
            activity = result.get("activity") if result else None
            if activity and activity.get("leveled_up"):
                await self.handle_level_up(
                    member=member,
                    old_level=int(activity["old_level"]),
                    new_level=int(activity["new_level"]),
                )
            return
        if before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
            return

    async def handle_level_up(
        self,
        member: discord.Member,
        old_level: int,
        new_level: int,
        fallback_channel: discord.abc.Messageable | None = None,
    ):
        granted_roles = await self.grant_level_roles(member, old_level, new_level)
        settings = self.service.get_settings(member.guild.id)
        channel = None
        if settings.get("announce_channel_id"):
            channel = member.guild.get_channel(int(settings["announce_channel_id"]))
        channel = channel or fallback_channel
        if channel is None:
            return

        template = settings.get("announce_template") or "🎉 {user} đã lên **Level {new_level}**! `{old_level}` → `{new_level}`"
        try:
            description = template.format(user=member.mention, old_level=old_level, new_level=new_level)
        except (KeyError, ValueError):
            description = f"🎉 {member.mention} đã lên **Level {new_level}**! `{old_level}` → `{new_level}`"
        if granted_roles:
            description += "\nNhận role: " + ", ".join(role.mention for role in granted_roles)
        await channel.send(description)

    async def grant_level_roles(self, member: discord.Member, old_level: int, new_level: int) -> list[discord.Role]:
        rewards = self.service.get_rewards_between(member.guild.id, old_level, new_level)
        if not rewards:
            return []
        me = member.guild.me
        if me is None or not me.guild_permissions.manage_roles:
            return []

        granted = []
        for reward in rewards:
            role = member.guild.get_role(int(reward["role_id"]))
            if role is None or role in member.roles or role >= me.top_role:
                continue
            try:
                await member.add_roles(role, reason=f"Level reward {reward['level']}")
                granted.append(role)
            except (discord.Forbidden, discord.HTTPException):
                continue
        return granted

    def build_profile_embed(self, guild: discord.Guild, member: discord.Member, period: str = "total") -> discord.Embed:
        period = normalize_period(period)
        stats = self.service.get_user_period_stats(guild.id, member.id, period, member.display_name)
        total = self.service.get_user_period_stats(guild.id, member.id, "total", member.display_name)
        level = int(total["level"])
        current_xp = int(total["total_xp"])
        current_level_xp = self.service.get_xp_for_level(guild.id, level)
        next_xp = self.service.get_xp_for_level(guild.id, level + 1)
        level_span = max(1, next_xp - current_level_xp)
        level_progress = max(0, current_xp - current_level_xp)
        percent = min(1.0, level_progress / level_span)
        missing_xp = max(0, next_xp - current_xp)
        rank = self.service.get_rank(guild.id, member.id, "xp")
        period_label = PERIOD_LABELS[period]
        mode_info = self.service.get_xp_mode_info(guild.id)
        mode_label = XP_MODE_LABELS.get(mode_info["mode"], mode_info["mode"])

        embed = discord.Embed(
            title="LEVEL PROFILE",
            description=(
                f"{member.mention}\n"
                f"**Level {level}** đang tiến tới **Level {level + 1}**\n"
                f"`{progress_bar(percent)}` **{percent * 100:.1f}%**\n"
                f"Còn thiếu `{format_xp(missing_xp)}`"
            ),
            color=discord.Color.from_rgb(104, 142, 255),
        )
        embed.set_author(name=f"{member.display_name} • {period_label}", icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="🏅 **Level**", value=f"`{level}`", inline=True)
        embed.add_field(name="🏆 **Rank**", value=f"`#{rank}`" if rank else "`Chưa có`", inline=True)
        embed.add_field(name="✨ **XP Tổng**", value=f"`{format_xp(current_xp)}`", inline=True)
        embed.add_field(
            name="📍 **Mốc kế tiếp**",
            value=f"`{format_xp(level_progress)} / {format_xp(level_span)}`",
            inline=False,
        )
        embed.add_field(name=f"🧾 **XP {period_label.lower()}**", value=f"`{format_xp(stats['total_xp'])}`", inline=True)
        embed.add_field(name="💬 **Tin nhắn**", value=f"`{int(stats['messages']):,}`", inline=True)
        embed.add_field(name="🎙️ **Voice**", value=f"`{format_duration_seconds(int(stats['voice_seconds']))}`", inline=True)
        embed.set_footer(text=f"XP mode: {mode_label}")
        append_discord_timestamp(embed)
        return embed

    def build_leaderboard_embed(self, guild: discord.Guild, period: str, metric: str, limit: int) -> discord.Embed:
        period = normalize_period(period)
        metric = normalize_metric(metric)
        rows = self.service.get_leaderboard(guild.id, period, metric, limit)
        title = f"🏆 Top Level - {PERIOD_LABELS[period]}"
        embed = discord.Embed(
            title=title,
            description=f"Sắp xếp theo **{METRIC_LABELS[metric]}**",
            color=discord.Color.from_rgb(255, 198, 92),
        )
        if not rows:
            embed.description = "Chưa có dữ liệu level trong kỳ này."
            append_discord_timestamp(embed)
            return embed

        lines = []
        for index, row in enumerate(rows, 1):
            username = row.get("username") or "Unknown"
            user_text = f"<@{int(row['user_id'])}> `{username}`"
            if metric == "voice":
                score_text = format_duration_seconds(int(row["score"] or 0))
            elif metric == "messages":
                score_text = f"{int(row['score'] or 0):,} tin"
            elif metric == "level":
                score_text = f"Level {int(row['score'] or 0):,}"
            else:
                score_text = format_xp(int(row["score"] or 0))
            lines.append(f"**#{index}** {user_text} - `{score_text}`")
        embed.add_field(name="Bảng xếp hạng", value="\n".join(lines), inline=False)
        embed.set_footer(text=f"{len(rows)} user")
        append_discord_timestamp(embed)
        return embed

    def build_count_embed(self, guild: discord.Guild, period: str) -> discord.Embed:
        period = normalize_period(period)
        count = self.service.get_server_count(guild.id, period)
        embed = discord.Embed(
            title="SERVER LEVEL COUNT",
            description=f"Thống kê **{PERIOD_LABELS[period]}** của server",
            color=discord.Color.from_rgb(74, 222, 128),
        )
        embed.add_field(name="👥 **User có dữ liệu**", value=f"`{count['users']:,}`", inline=True)
        embed.add_field(name="✨ **Tổng XP**", value=f"`{format_xp(count['total_xp'])}`", inline=True)
        embed.add_field(name="💬 **Tin nhắn**", value=f"`{count['messages']:,}`", inline=True)
        embed.add_field(name="🎙️ **Voice**", value=f"`{format_duration_seconds(count['voice_seconds'])}`", inline=True)
        append_discord_timestamp(embed)
        return embed

    def build_settings_embed(self, guild: discord.Guild) -> discord.Embed:
        settings = self.service.get_settings(guild.id)
        mode_info = self.service.get_xp_mode_info(guild.id)
        mode_label = XP_MODE_LABELS.get(mode_info["mode"], mode_info["mode"])
        channel_text = "Chưa set"
        if settings.get("announce_channel_id"):
            channel_text = f"<#{int(settings['announce_channel_id'])}>"
        rewards = self.service.get_rewards(guild.id)
        reward_text = "\n".join(
            f"Level `{int(row['level'])}` → <@&{int(row['role_id'])}>"
            for row in rewards[:20]
        ) or "Chưa có role reward."

        embed = create_info_splash(
            "📈 Level Setup",
            (
                f"Trạng thái: `{'Bật' if int(settings.get('enabled', 1)) else 'Tắt'}`\n"
                f"Kênh thông báo: {channel_text}\n"
                f"XP mỗi tin nhắn: `{int(settings.get('message_xp') or 0)}`\n"
                f"XP voice mỗi phút: `{int(settings.get('voice_xp_per_minute') or 0)}`\n"
                f"Kiểu lên level: `{mode_label}`\n"
                f"Base XP: `{int(mode_info['base']):,}`"
            ),
        )
        next_levels = "\n".join(
            f"Level `{level}` → `{format_xp(self.service.get_xp_for_level(guild.id, level))}`"
            for level in range(1, 6)
        )
        manual_rows = self.service.get_manual_requirements(guild.id, 10)
        manual_text = "\n".join(
            f"Level `{int(row['level'])}` → `{format_xp(int(row['xp_required']))}`"
            for row in manual_rows
        ) or "Chưa set mốc thủ công."
        embed.add_field(name="Mốc XP kế tiếp", value=next_levels, inline=False)
        embed.add_field(name="Mốc thủ công", value=manual_text, inline=False)
        embed.add_field(name="Role reward", value=reward_text, inline=False)
        return embed

    async def resolve_member_arg(self, ctx: commands.Context, raw_member: str) -> discord.Member | None:
        member = await self.resolve_member_target(ctx, raw_member)
        if member is None:
            await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy User", f"Không tìm thấy `{raw_member}` trong server."))
        return member

    async def require_level_root_if_locked_ctx(self, ctx: commands.Context) -> bool:
        """Nếu DB đã set quyền `level`, toàn bộ nhánh level sẽ bị khóa theo quyền đó."""
        if ctx.guild is None:
            return False
        if not self.role_permissions.command_has_permission(ctx.guild.id, "level"):
            return True
        return await self.require_role_or_admin_ctx(ctx, "level")

    async def require_level_key_if_locked_ctx(self, ctx: commands.Context, permission_key: str) -> bool:
        """Các nhánh public chỉ bị khóa khi chính key đó đã được add vào DB."""
        if ctx.guild is None:
            return False
        if not self.role_permissions.command_has_permission(ctx.guild.id, permission_key):
            return True
        return await self.require_role_or_admin_ctx(ctx, permission_key)

    async def require_level_root_if_locked_interaction(self, interaction: discord.Interaction) -> bool:
        """Slash cũng đi theo cùng cơ chế khóa cha của prefix."""
        if interaction.guild is None:
            return False
        if not self.role_permissions.command_has_permission(interaction.guild.id, "level"):
            return True
        return await self.require_role_or_admin_interaction(interaction, "level")

    async def require_level_key_if_locked_interaction(self, interaction: discord.Interaction, permission_key: str) -> bool:
        """Slash public subcommand cũng có thể khóa riêng nếu DB có key tương ứng."""
        if interaction.guild is None:
            return False
        if not self.role_permissions.command_has_permission(interaction.guild.id, permission_key):
            return True
        return await self.require_role_or_admin_interaction(interaction, permission_key)

    async def send_profile_ctx(self, ctx: commands.Context, member: discord.Member, period: str = "total"):
        embed = self.build_profile_embed(ctx.guild, member, period)
        await ctx.send(embed=embed, view=LevelProfileView(self, member.id, normalize_period(period)))

    async def handle_setup_ctx(self, ctx: commands.Context, args: tuple[str, ...]):
        if not await self.require_role_or_admin_ctx(ctx, "level setup"):
            return
        if not args:
            await ctx.send(embed=self.build_settings_embed(ctx.guild))
            return

        action = args[0].lower()
        if action in {"on", "enable", "bat", "bật"}:
            self.service.set_enabled(ctx.guild.id, True)
            await ctx.send(embed=create_success_splash("✅ Level Đã Bật", "Bot sẽ tiếp tục count tin nhắn và voice."))
            return
        if action in {"off", "disable", "tat", "tắt"}:
            self.service.set_enabled(ctx.guild.id, False)
            await ctx.send(embed=create_success_splash("✅ Level Đã Tắt", "Bot tạm ngưng count level trong server này."))
            return
        if action in {"template", "announce", "noidung", "nội dung"}:
            if len(args) < 2:
                await ctx.send(embed=create_error_splash("❌ Thiếu Nội Dung", "Dùng: `level setup template <nội dung>`.\nPlaceholder: `{user}`, `{old_level}`, `{new_level}`."))
                return
            template = " ".join(args[1:])
            self.service.set_announce_template(ctx.guild.id, template)
            await ctx.send(embed=create_success_splash("✅ Đã Set Template Level-up", f"Câu thông báo mới:\n{template}"))
            return
        if action in {"messagexp", "msgxp"} and len(args) >= 2:
            try:
                message_xp = int(args[1])
            except ValueError:
                await ctx.send(embed=create_error_splash("❌ XP Không Hợp Lệ", "XP mỗi tin nhắn phải là số."))
                return
            self.service.set_xp_rates(ctx.guild.id, message_xp=message_xp)
            await ctx.send(embed=create_success_splash("✅ Đã Set XP Tin Nhắn", f"Mỗi tin nhắn nhận `{message_xp}` XP."))
            return
        if action in {"voicexp", "vcxp"} and len(args) >= 2:
            try:
                voice_xp = int(args[1])
            except ValueError:
                await ctx.send(embed=create_error_splash("❌ XP Không Hợp Lệ", "XP mỗi phút voice phải là số."))
                return
            self.service.set_xp_rates(ctx.guild.id, voice_xp_per_minute=voice_xp)
            await ctx.send(embed=create_success_splash("✅ Đã Set XP Voice", f"Mỗi phút voice nhận `{voice_xp}` XP."))
            return
        if action in {"xp", "xpmode", "curve"} and len(args) >= 2:
            mode = LevelService.normalize_xp_mode(args[1])
            if mode == "manual" and len(args) >= 4:
                try:
                    level = int(args[2])
                    xp_required = int(args[3].replace(",", "").replace(".", ""))
                except ValueError:
                    await ctx.send(embed=create_error_splash("❌ Mốc XP Không Hợp Lệ", "Dùng: `level setup xp manual <level> <xp>`."))
                    return
                self.service.set_manual_level_xp(ctx.guild.id, level, xp_required)
                await ctx.send(embed=create_success_splash("✅ Đã Set Mốc Level", f"Level `{level}` cần `{format_xp(xp_required)}`."))
                return
            if mode == "custom":
                if len(args) < 3:
                    await ctx.send(embed=create_error_splash("❌ Thiếu Base XP", "Dùng: `level setup xp custom <base>`."))
                    return
                try:
                    xp_base = int(args[2].replace(",", "").replace(".", ""))
                except ValueError:
                    await ctx.send(embed=create_error_splash("❌ Base XP Không Hợp Lệ", "Base XP phải là số."))
                    return
                self.service.set_xp_mode(ctx.guild.id, "custom", xp_base)
            else:
                self.service.set_xp_mode(ctx.guild.id, mode)
            mode_info = self.service.get_xp_mode_info(ctx.guild.id)
            mode_label = XP_MODE_LABELS.get(mode_info["mode"], mode_info["mode"])
            await ctx.send(
                embed=create_success_splash(
                    "✅ Đã Set Kiểu XP",
                    f"Kiểu lên level: `{mode_label}`\nBase XP: `{int(mode_info['base']):,}`",
                )
            )
            return
        if action in {"levelxp", "lvxp", "require", "req", "manualxp"} and len(args) >= 3:
            try:
                level = int(args[1])
                xp_required = int(args[2].replace(",", "").replace(".", ""))
            except ValueError:
                await ctx.send(embed=create_error_splash("❌ Mốc XP Không Hợp Lệ", "Dùng: `level setup levelxp <level> <xp>`."))
                return
            self.service.set_manual_level_xp(ctx.guild.id, level, xp_required)
            await ctx.send(embed=create_success_splash("✅ Đã Set Mốc Level", f"Level `{level}` cần `{format_xp(xp_required)}`."))
            return
        if action in {"none", "clear", "xoa", "xoá"}:
            self.service.set_announce_channel(ctx.guild.id, None)
            await ctx.send(embed=create_success_splash("✅ Đã Xóa Kênh", "Level-up sẽ fallback về kênh chat khi có tin nhắn."))
            return

        try:
            channel = await commands.TextChannelConverter().convert(ctx, " ".join(args))
        except Exception:
            await ctx.send(
                embed=create_error_splash(
                    "❌ Sai Cú Pháp",
                    "Dùng: `level setup #channel`, `level setup on/off`, `level setup messagexp 10`, `level setup voicexp 5`, `level setup xp ...`, `level setup levelxp ...`, `level setup template ...`.",
                )
            )
            return
        self.service.set_announce_channel(ctx.guild.id, channel.id)
        await ctx.send(embed=create_success_splash("✅ Đã Set Kênh Level", f"Thông báo level-up sẽ gửi ở {channel.mention}."))

    async def handle_reward_ctx(self, ctx: commands.Context, args: tuple[str, ...]):
        if not await self.require_role_or_admin_ctx(ctx, "level role"):
            return
        if not args or args[0].lower() in {"list", "ls", "xem"}:
            rewards = self.service.get_rewards(ctx.guild.id)
            if not rewards:
                await ctx.send(embed=create_info_splash("Role Reward", "Chưa có role reward nào."))
                return
            lines = [f"Level `{int(row['level'])}` → <@&{int(row['role_id'])}>" for row in rewards]
            await ctx.send(embed=create_info_splash("🎁 Role Reward", "\n".join(lines)))
            return

        action = ACTION_ALIASES.get(args[0].lower())
        if action not in {"add", "remove"} or len(args) < 2:
            await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `level role add <level> @role`, `level role remove <level> [@role]`, `level role list`."))
            return
        try:
            level = int(args[1])
        except ValueError:
            await ctx.send(embed=create_error_splash("❌ Level Không Hợp Lệ", "Level phải là số."))
            return
        if level <= 0:
            await ctx.send(embed=create_error_splash("❌ Level Không Hợp Lệ", "Level reward phải lớn hơn 0."))
            return

        role = None
        if len(args) >= 3:
            try:
                role = await commands.RoleConverter().convert(ctx, " ".join(args[2:]))
            except Exception:
                await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy Role", "Không tìm thấy role cần set."))
                return
        if action == "add":
            if role is None:
                await ctx.send(embed=create_error_splash("❌ Thiếu Role", "Dùng: `level role add <level> @role`."))
                return
            self.service.add_reward(ctx.guild.id, level, role.id, role.name, ctx.author.id)
            await ctx.send(embed=create_success_splash("✅ Đã Thêm Role Reward", f"Level `{level}` sẽ nhận {role.mention}."))
            return

        self.service.remove_reward(ctx.guild.id, level, role.id if role else None)
        target = role.mention if role else f"mọi role ở level `{level}`"
        await ctx.send(embed=create_success_splash("✅ Đã Xóa Role Reward", f"Đã xóa reward {target}."))

    async def handle_manual_ctx(self, ctx: commands.Context, action: str, args: tuple[str, ...]):
        if not await self.require_role_or_admin_ctx(ctx, "level edit"):
            return
        await self.apply_manual_update_ctx(ctx, action, args)

    async def handle_hard_set_ctx(self, ctx: commands.Context, args: tuple[str, ...]):
        if not self.admins.is_hard_admin(ctx.author.id):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Bạn không có quyền dùng lệnh này."))
            return
        await self.apply_manual_update_ctx(ctx, "edit", args, title="✅ Đã Set Level")

    async def apply_manual_update_ctx(
        self,
        ctx: commands.Context,
        action: str,
        args: tuple[str, ...],
        title: str = "✅ Đã Cập Nhật Level",
    ):
        if len(args) < 3:
            await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `level a|r|e @user xp|level|messages|voice <value>`."))
            return
        member = await self.resolve_member_arg(ctx, args[0])
        if member is None:
            return
        field = normalize_field(args[1])
        if field is None:
            await ctx.send(embed=create_error_splash("❌ Trường Không Hợp Lệ", "Trường hợp lệ: `xp`, `level`, `messages`, `voice`."))
            return
        try:
            value = parse_stat_value(field, args[2])
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Giá Trị Không Hợp Lệ", str(exc)))
            return

        before = self.service.get_user_period_stats(ctx.guild.id, member.id, "total", member.display_name)
        updated = self.service.manual_update(ctx.guild.id, member.id, member.display_name, field, action, value)
        if int(updated["level"]) > int(before["level"]):
            await self.handle_level_up(member, int(before["level"]), int(updated["level"]), ctx.channel)

        action_text = {"add": "cộng", "remove": "trừ", "edit": "set"}[action]
        value_text = format_duration_seconds(value) if field == "voice" else f"{value:,}"
        await ctx.send(
            embed=create_success_splash(
                title,
                (
                    f"Đã {action_text} `{METRIC_LABELS.get(field, field)}` cho {member.mention}: `{value_text}`.\n"
                    f"Level hiện tại: `{int(updated['level'])}`\n"
                    f"XP hiện tại: `{format_xp(int(updated['total_xp']))}`"
                ),
            )
        )

    @commands.command(name="level", aliases=["lv"])
    async def level(self, ctx: commands.Context, *args: str):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Level chỉ hoạt động trong server."))
            return

        if not await self.require_level_root_if_locked_ctx(ctx):
            return

        if not args:
            await self.send_profile_ctx(ctx, ctx.author)
            return

        first = args[0].lower()
        if first in {"help", "h"}:
            await ctx.send(
                embed=create_info_splash(
                    "📈 Level Help",
                    (
                        "`level` - xem level của bạn\n"
                        "`level @user [total|month|week|day]` - xem user\n"
                        "`level all [period] [xp|level|messages|voice] [limit]` - bảng xếp hạng\n"
                        "`level count [period]` - tổng count server\n"
                        "`level setup #channel|on|off|messagexp|voicexp|xp|levelxp` - setup\n"
                        "`level role add/remove/list` - role reward"
                    ),
                )
            )
            return

        if first in {"all", "top", "leaderboard", "lb"}:
            if not await self.require_level_key_if_locked_ctx(ctx, "level all"):
                return
            period = "total"
            metric = "xp"
            limit = 10
            for token in args[1:]:
                lowered = token.lower()
                if lowered in PERIOD_ALIASES:
                    period = normalize_period(lowered)
                elif lowered in METRIC_ALIASES:
                    metric = normalize_metric(lowered)
                elif lowered.isdigit():
                    limit = max(1, min(25, int(lowered)))
            await ctx.send(embed=self.build_leaderboard_embed(ctx.guild, period, metric, limit))
            return

        if first in {"count", "c", "totalcount"}:
            if not await self.require_level_key_if_locked_ctx(ctx, "level count"):
                return
            period = normalize_period(args[1] if len(args) >= 2 else "total")
            await ctx.send(embed=self.build_count_embed(ctx.guild, period))
            return

        if first in {"setup", "config", "setting", "settings"}:
            await self.handle_setup_ctx(ctx, args[1:])
            return

        if first in {"role", "roles", "reward", "rewards"}:
            await self.handle_reward_ctx(ctx, args[1:])
            return

        if first == "set":
            await self.handle_hard_set_ctx(ctx, args[1:])
            return

        action = ACTION_ALIASES.get(first)
        if action:
            await self.handle_manual_ctx(ctx, action, args[1:])
            return

        if first in PERIOD_ALIASES:
            await self.send_profile_ctx(ctx, ctx.author, normalize_period(first))
            return

        member = await self.resolve_member_arg(ctx, args[0])
        if member is None:
            return
        period = normalize_period(args[1] if len(args) >= 2 else "total")
        await self.send_profile_ctx(ctx, member, period)

    @commands.command(name="lvlconfig")
    async def lvlconfig(self, ctx: commands.Context, *args: str):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Level chỉ hoạt động trong server."))
            return
        await self.handle_setup_ctx(ctx, args)

    async def open_manual_modal(self, interaction: discord.Interaction, member: discord.Member, mode: str):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Chỉ dùng trong server.", ephemeral=True)
            return
        if not self.admins.is_hard_admin(interaction.user.id):
            await interaction.response.send_message(
                embed=create_error_splash("❌ Quyền Bị Từ Chối", "Bạn không có quyền dùng lệnh này."),
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(LevelManualModal(self, member, mode))

    level_group = app_commands.Group(name="level", description="edit config")

    async def _handle_slash_level_action(
        self,
        interaction: discord.Interaction,
        action: str = "me",
        member: discord.Member | None = None,
        period: str = "total",
        metric: str = "xp",
        limit: app_commands.Range[int, 1, 25] = 10,
        channel: discord.TextChannel | None = None,
        xp_mode: str | None = None,
        base: int | None = None,
        level: int | None = None,
        xp_required: int | None = None,
        role: discord.Role | None = None,
    ):
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message("❌ Chỉ dùng trong server.", ephemeral=True)
            return

        action = (action or "me").strip().lower()
        if not await self.require_level_root_if_locked_interaction(interaction):
            return

        permission_key = {
            "setup": "level setup",
            "xp": "level setup",
            "xp-level": "level setup",
            "reward-add": "level role",
            "reward-remove": "level role",
            "rewards": "level role",
        }.get(action)
        if permission_key and not await self.require_role_or_admin_interaction(interaction, permission_key):
            return

        if action == "me":
            embed = self.build_profile_embed(interaction.guild, interaction.user, period)
            await interaction.response.send_message(embed=embed, view=LevelProfileView(self, interaction.user.id, period))
            return

        if action == "user":
            target = member or interaction.user
            embed = self.build_profile_embed(interaction.guild, target, period)
            await interaction.response.send_message(embed=embed, view=LevelProfileView(self, target.id, period))
            return

        if action == "all":
            if not await self.require_level_key_if_locked_interaction(interaction, "level all"):
                return
            await interaction.response.send_message(embed=self.build_leaderboard_embed(interaction.guild, period, metric, int(limit)))
            return

        if action == "count":
            if not await self.require_level_key_if_locked_interaction(interaction, "level count"):
                return
            await interaction.response.send_message(embed=self.build_count_embed(interaction.guild, period))
            return

        if action == "setup":
            if channel is None:
                await interaction.response.send_message(embed=self.build_settings_embed(interaction.guild), ephemeral=True)
                return
            self.service.set_announce_channel(interaction.guild.id, channel.id)
            await interaction.response.send_message(
                embed=create_success_splash("✅ Đã Set Kênh Level", f"Thông báo level-up sẽ gửi ở {channel.mention}."),
                ephemeral=True,
            )
            return

        if action == "xp":
            if not xp_mode:
                await interaction.response.send_message(
                    embed=create_error_splash("❌ Thiếu Kiểu XP", "Hãy chọn `xp_mode`: easy, normal, hard, manual hoặc custom."),
                    ephemeral=True,
                )
                return
            normalized = LevelService.normalize_xp_mode(xp_mode)
            if normalized == "custom" and base is None:
                await interaction.response.send_message(
                    embed=create_error_splash("❌ Thiếu Base XP", "Mode tùy chỉnh cần nhập thêm `base`."),
                    ephemeral=True,
                )
                return
            self.service.set_xp_mode(interaction.guild.id, normalized, base)
            mode_info = self.service.get_xp_mode_info(interaction.guild.id)
            mode_label = XP_MODE_LABELS.get(mode_info["mode"], mode_info["mode"])
            await interaction.response.send_message(
                embed=create_success_splash(
                    "✅ Đã Set Kiểu XP",
                    f"Kiểu lên level: `{mode_label}`\nBase XP: `{int(mode_info['base']):,}`",
                ),
                ephemeral=True,
            )
            return

        if action == "xp-level":
            if level is None or xp_required is None:
                await interaction.response.send_message(
                    embed=create_error_splash("❌ Thiếu Dữ Liệu", "Cần nhập `level` và `xp_required`."),
                    ephemeral=True,
                )
                return
            self.service.set_manual_level_xp(interaction.guild.id, int(level), int(xp_required))
            await interaction.response.send_message(
                embed=create_success_splash("✅ Đã Set Mốc Level", f"Level `{int(level)}` cần `{format_xp(int(xp_required))}`."),
                ephemeral=True,
            )
            return

        if action == "reward-add":
            if level is None or role is None:
                await interaction.response.send_message(
                    embed=create_error_splash("❌ Thiếu Dữ Liệu", "Cần nhập `level` và `role`."),
                    ephemeral=True,
                )
                return
            self.service.add_reward(interaction.guild.id, int(level), role.id, role.name, interaction.user.id)
            await interaction.response.send_message(
                embed=create_success_splash("✅ Đã Thêm Role Reward", f"Level `{int(level)}` sẽ nhận {role.mention}."),
                ephemeral=True,
            )
            return

        if action == "reward-remove":
            if level is None:
                await interaction.response.send_message(
                    embed=create_error_splash("❌ Thiếu Level", "Cần nhập `level`."),
                    ephemeral=True,
                )
                return
            self.service.remove_reward(interaction.guild.id, int(level), role.id if role else None)
            target = role.mention if role else f"mọi role ở level `{int(level)}`"
            await interaction.response.send_message(
                embed=create_success_splash("✅ Đã Xóa Role Reward", f"Đã xóa reward {target}."),
                ephemeral=True,
            )
            return

        if action == "rewards":
            rewards = self.service.get_rewards(interaction.guild.id)
            if not rewards:
                await interaction.response.send_message(embed=create_info_splash("Role Reward", "Chưa có role reward nào."), ephemeral=True)
                return
            lines = [f"Level `{int(row['level'])}` → <@&{int(row['role_id'])}>" for row in rewards]
            await interaction.response.send_message(embed=create_info_splash("🎁 Role Reward", "\n".join(lines)), ephemeral=True)
            return

        if action in {"add", "remove", "edit"}:
            await self.open_manual_modal(interaction, member or interaction.user, action)

    @level_group.command(name="me", description="Xem level của bạn")
    @app_commands.choices(period=PERIOD_CHOICES)
    @app_commands.describe(period="Kỳ thống kê")
    async def slash_level_me(self, interaction: discord.Interaction, period: str = "total"):
        await self._handle_slash_level_action(interaction, "me", period=period)

    @level_group.command(name="user", description="Xem level user")
    @app_commands.choices(period=PERIOD_CHOICES)
    @app_commands.describe(member="User cần xem", period="Kỳ thống kê")
    async def slash_level_user(self, interaction: discord.Interaction, member: discord.Member, period: str = "total"):
        await self._handle_slash_level_action(interaction, "user", member=member, period=period)

    @level_group.command(name="all", description="Bảng xếp hạng level/stat")
    @app_commands.choices(period=PERIOD_CHOICES, metric=METRIC_CHOICES)
    @app_commands.describe(period="Kỳ thống kê", metric="Loại top/stat", limit="Số dòng leaderboard")
    async def slash_level_all(
        self,
        interaction: discord.Interaction,
        period: str = "total",
        metric: str = "xp",
        limit: app_commands.Range[int, 1, 25] = 10,
    ):
        await self._handle_slash_level_action(interaction, "all", period=period, metric=metric, limit=limit)

    @level_group.command(name="count", description="Xem tổng count")
    @app_commands.choices(period=PERIOD_CHOICES)
    @app_commands.describe(period="Kỳ thống kê")
    async def slash_level_count(self, interaction: discord.Interaction, period: str = "total"):
        await self._handle_slash_level_action(interaction, "count", period=period)

    @level_group.command(name="setup", description="Set kênh thông báo level")
    @app_commands.describe(channel="Kênh thông báo level-up")
    async def slash_level_setup(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        await self._handle_slash_level_action(interaction, "setup", channel=channel)

    @level_group.command(name="xp", description="Set kiểu XP lên level")
    @app_commands.choices(xp_mode=XP_MODE_CHOICES)
    @app_commands.describe(xp_mode="Kiểu XP", base="Base XP nếu chọn custom")
    async def slash_level_xp(
        self,
        interaction: discord.Interaction,
        xp_mode: str,
        base: int | None = None,
    ):
        await self._handle_slash_level_action(interaction, "xp", xp_mode=xp_mode, base=base)

    @level_group.command(name="xp-level", description="Set XP cần đạt cho level")
    @app_commands.describe(level="Mốc level", xp_required="XP cần đạt")
    async def slash_level_xp_level(self, interaction: discord.Interaction, level: int, xp_required: int):
        await self._handle_slash_level_action(
            interaction,
            "xp-level",
            level=level,
            xp_required=xp_required,
        )

    @level_group.command(name="reward-add", description="Thêm role reward")
    @app_commands.describe(level="Mốc level", role="Role reward")
    async def slash_level_reward_add(self, interaction: discord.Interaction, level: int, role: discord.Role):
        await self._handle_slash_level_action(interaction, "reward-add", level=level, role=role)

    @level_group.command(name="reward-remove", description="Xóa role reward")
    @app_commands.describe(level="Mốc level", role="Role reward")
    async def slash_level_reward_remove(
        self,
        interaction: discord.Interaction,
        level: int,
        role: discord.Role | None = None,
    ):
        await self._handle_slash_level_action(interaction, "reward-remove", level=level, role=role)

    @level_group.command(name="rewards", description="List role reward")
    async def slash_level_rewards(self, interaction: discord.Interaction):
        await self._handle_slash_level_action(interaction, "rewards")

    @level_group.command(name="add", description="Add config")
    @app_commands.describe(member="User cần edit config")
    async def slash_level_add(self, interaction: discord.Interaction, member: discord.Member):
        await self._handle_slash_level_action(interaction, "add", member=member)

    @level_group.command(name="remove", description="Remove config")
    @app_commands.describe(member="User cần edit config")
    async def slash_level_remove(self, interaction: discord.Interaction, member: discord.Member):
        await self._handle_slash_level_action(interaction, "remove", member=member)

    @level_group.command(name="edit", description="edit config")
    @app_commands.describe(member="User cần edit config")
    async def slash_level_edit(self, interaction: discord.Interaction, member: discord.Member):
        await self._handle_slash_level_action(interaction, "edit", member=member)


async def setup(bot):
    await bot.add_cog(LevelCog(bot))
