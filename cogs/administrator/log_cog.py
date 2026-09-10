from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_error_splash,
    create_info_splash,
    create_success_splash,
)
from services.log_service import LOG_CHANNEL_FIELDS, LogService
from ui.administrator.log_ui import (
    LOG_CATEGORY_EMOJIS,
    LOG_CATEGORY_LABELS,
    build_basic_log_embed,
    build_log_settings_embed,
    truncate_text,
)


CATEGORY_ALIASES = {
    "chat": "chat",
    "message": "chat",
    "messages": "chat",
    "msg": "chat",
    "voice": "voice",
    "vc": "voice",
    "channel": "channel",
    "channels": "channel",
    "kenh": "channel",
    "kênh": "channel",
    "server": "server",
    "guild": "server",
    "sv": "server",
    "join": "member",
    "joinleave": "member",
    "join/leave": "member",
    "leave": "member",
    "out": "member",
    "member": "member",
    "members": "member",
    "mem": "member",
    "cash": "cash",
    "money": "cash",
    "bank": "cash",
    "naptien": "cash",
    "nap": "cash",
    "donate": "cash",
    "all": "all",
}

CATEGORY_CHOICES = [
    app_commands.Choice(name="chat", value="chat"),
    app_commands.Choice(name="voice", value="voice"),
    app_commands.Choice(name="channel", value="channel"),
    app_commands.Choice(name="server", value="server"),
    app_commands.Choice(name="join/leave", value="member"),
    app_commands.Choice(name="cash", value="cash"),
    app_commands.Choice(name="all", value="all"),
]

ACTION_CHOICES = [
    app_commands.Choice(name="show", value="show"),
    app_commands.Choice(name="set", value="set"),
    app_commands.Choice(name="off", value="off"),
    app_commands.Choice(name="test", value="test"),
    app_commands.Choice(name="voice-announce", value="voice-announce"),
    app_commands.Choice(name="voice-room", value="voice-room"),
    app_commands.Choice(name="voice-join-message", value="voice-join-message"),
    app_commands.Choice(name="voice-leave-message", value="voice-leave-message"),
    app_commands.Choice(name="voice-embed", value="voice-embed"),
]


class LogCog(AdminCommandBase):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.service = LogService()

    async def _log_channel(self, guild: discord.Guild, category: str) -> discord.TextChannel | None:
        channel_id = self.service.get_channel_id(guild.id, category)
        if not channel_id:
            return None
        channel = guild.get_channel(channel_id)
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _send_log(self, guild: discord.Guild, category: str, embed: discord.Embed | None = None, content: str | None = None):
        channel = await self._log_channel(guild, category)
        if not channel:
            return
        try:
            await channel.send(content=content, embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _find_audit_actor(
        self,
        guild: discord.Guild,
        action: discord.AuditLogAction,
        target_id: int | None = None,
        channel_id: int | None = None,
        seconds: int = 12,
    ) -> tuple[discord.User | discord.Member | None, str | None]:
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                if abs((discord.utils.utcnow() - entry.created_at).total_seconds()) > seconds:
                    continue
                if target_id is not None and getattr(entry.target, "id", None) != target_id:
                    continue
                extra_channel = getattr(getattr(entry, "extra", None), "channel", None)
                if channel_id is not None and extra_channel and getattr(extra_channel, "id", None) != channel_id:
                    continue
                return entry.user, entry.reason
        except (discord.Forbidden, discord.HTTPException):
            return None, None
        return None, None

    @staticmethod
    def _member_tag(member: discord.Member | discord.User | None, fallback: str = "Không rõ") -> str:
        return member.mention if member else fallback

    @staticmethod
    def _asset_link(asset: discord.Asset | None) -> str:
        return f"[Mở ảnh]({asset.url})" if asset else "`Không có`"

    @staticmethod
    def _age_text(created_at: datetime) -> str:
        delta = datetime.now(timezone.utc) - created_at
        days = max(0, delta.days)
        if days < 1:
            hours = max(0, delta.seconds // 3600)
            minutes = max(0, (delta.seconds % 3600) // 60)
            return f"{hours} giờ {minutes} phút"
        years, remain = divmod(days, 365)
        months, remain_days = divmod(remain, 30)
        parts = []
        if years:
            parts.append(f"{years} năm")
        if months:
            parts.append(f"{months} tháng")
        if remain_days or not parts:
            parts.append(f"{remain_days} ngày")
        return " ".join(parts)

    @staticmethod
    def _format_template(template: str, member: discord.Member, channel: discord.VoiceChannel | discord.StageChannel | None) -> str:
        return (template or "").format(
            user=member.mention,
            username=member.display_name,
            id=member.id,
            channel=channel.mention if channel else "voice",
            channel_name=channel.name if channel else "voice",
            server=member.guild.name,
        )

    async def _send_voice_announce(
        self,
        member: discord.Member,
        template_key: str,
        channel: discord.VoiceChannel | discord.StageChannel | None,
    ):
        config = self.service.get_config(member.guild.id)
        if not config or not config.get("voice_announce_channel_id"):
            return
        announce_channel = member.guild.get_channel(int(config["voice_announce_channel_id"]))
        if not isinstance(announce_channel, discord.TextChannel):
            return
        field = "voice_join_template" if template_key == "join" else "voice_leave_template"
        template = config.get(field) or (
            "{username} vừa vào kênh {channel_name}."
            if template_key == "join"
            else "{username} đã rời kênh {channel_name}."
        )
        try:
            text = self._format_template(template, member, channel)
        except KeyError as exc:
            text = f"Template lỗi biến `{exc}`. Dùng: {{user}}, {{username}}, {{channel}}, {{server}}."
        try:
            if int(config.get("voice_announce_embed") or 0):
                title = "🎙️ Voice Joined" if template_key == "join" else "🎙️ Voice Left"
                await announce_channel.send(embed=build_basic_log_embed(title, text, "voice", member))
            else:
                await announce_channel.send(text)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def _send_voice_room_announce(
        self,
        member: discord.Member,
        template_key: str,
        channel: discord.VoiceChannel | discord.StageChannel | None,
    ):
        if channel is None or not hasattr(channel, "send"):
            return
        config = self.service.get_config(member.guild.id)
        if not config or not int(config.get("voice_room_announce") or 0):
            return
        field = "voice_join_template" if template_key == "join" else "voice_leave_template"
        template = config.get(field) or (
            "{username} vừa vào kênh {channel_name}."
            if template_key == "join"
            else "{username} đã rời kênh {channel_name}."
        )
        try:
            text = self._format_template(template, member, channel)
        except KeyError as exc:
            text = f"Template lỗi biến `{exc}`. Dùng: {{user}}, {{username}}, {{channel}}, {{channel_name}}, {{server}}."
        try:
            if int(config.get("voice_announce_embed") or 0):
                title = "🎙️ Tham Gia Voice" if template_key == "join" else "🎙️ Rời Voice"
                await channel.send(embed=build_basic_log_embed(title, text, "voice", member))
            else:
                await channel.send(text)
        except (discord.Forbidden, discord.HTTPException):
            pass

    def _build_status_embed(self, guild: discord.Guild) -> discord.Embed:
        return build_log_settings_embed(guild, self.service.get_config(guild.id))

    async def _set_category_channel(self, guild: discord.Guild, category: str, channel: discord.TextChannel | None):
        if category == "all":
            self.service.set_all_channels(guild.id, channel.id if channel else None)
            return
        self.service.set_channel(guild.id, category, channel.id if channel else None)

    async def _convert_text_channel(self, ctx: commands.Context, raw: str) -> discord.TextChannel | None:
        try:
            channel = await commands.TextChannelConverter().convert(ctx, raw)
        except commands.BadArgument:
            return None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _handle_prefix_voice_special(self, ctx: commands.Context, tokens: list[str], raw_after_category: str) -> bool:
        if not tokens:
            return False
        sub = tokens[0].lower()
        if sub in {"room", "rooms", "roomannounce", "room_announce"}:
            enabled = len(tokens) < 2 or tokens[1].lower() in {"on", "enable", "bat", "bật", "true", "1"}
            self.service.set_voice_room_announce(ctx.guild.id, enabled)
            await ctx.send(
                embed=create_success_splash(
                    "✅ Đã Cập Nhật Voice Room",
                    (
                        "Bot sẽ thông báo vào chat của tất cả voice room khi có người vào/rời."
                        if enabled
                        else "Đã tắt thông báo vào/rời trong chat voice room."
                    ),
                )
            )
            return True

        if sub in {"announce", "ann", "notify", "greeting"}:
            if len(tokens) < 2:
                await ctx.send(embed=create_error_splash("❌ Thiếu Kênh", "Dùng: `log voice announce #channel` hoặc `log voice announce off`."))
                return True
            if tokens[1].lower() in {"off", "disable", "tat", "tắt"}:
                self.service.set_voice_announce_channel(ctx.guild.id, None)
                await ctx.send(embed=create_success_splash("✅ Đã Tắt Voice Greeting", "Bot sẽ không gửi câu chào khi user vào voice nữa."))
                return True
            channel = await self._convert_text_channel(ctx, " ".join(tokens[1:]))
            if not channel:
                await ctx.send(embed=create_error_splash("❌ Kênh Không Hợp Lệ", "Hãy nhập text channel hợp lệ."))
                return True
            self.service.set_voice_announce_channel(ctx.guild.id, channel.id)
            await ctx.send(embed=create_success_splash("✅ Đã Set Voice Greeting", f"Thông báo voice greeting sẽ gửi ở {channel.mention}."))
            return True

        if sub in {"message", "msg", "joinmsg", "join_message", "template"}:
            template = raw_after_category.split(maxsplit=1)[1].strip() if len(raw_after_category.split(maxsplit=1)) > 1 else ""
            if not template:
                await ctx.send(
                    embed=create_error_splash(
                        "❌ Thiếu Nội Dung",
                        "Dùng: `log voice joinmsg {username} vừa vào {channel_name}`.",
                    )
                )
                return True
            self.service.set_voice_template(ctx.guild.id, "join", template)
            await ctx.send(embed=create_success_splash("✅ Đã Set Câu Vào Voice", template))
            return True

        if sub in {"leavemsg", "leave_message", "outmsg"}:
            template = raw_after_category.split(maxsplit=1)[1].strip() if len(raw_after_category.split(maxsplit=1)) > 1 else ""
            if not template:
                await ctx.send(
                    embed=create_error_splash(
                        "❌ Thiếu Nội Dung",
                        "Dùng: `log voice leavemsg {username} đã rời {channel_name}`.",
                    )
                )
                return True
            self.service.set_voice_template(ctx.guild.id, "leave", template)
            await ctx.send(embed=create_success_splash("✅ Đã Set Câu Rời Voice", template))
            return True

        if sub == "embed":
            enabled = len(tokens) < 2 or tokens[1].lower() in {"on", "enable", "bat", "bật", "true", "1"}
            self.service.set_voice_announce_embed(ctx.guild.id, enabled)
            await ctx.send(embed=create_success_splash("✅ Đã Cập Nhật Voice Embed", f"Voice greeting embed: `{'Bật' if enabled else 'Tắt'}`."))
            return True
        return False

    @commands.command(name="log", aliases=["logs"])
    async def log(self, ctx: commands.Context, *, content: str = ""):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Log chỉ hoạt động trong server."))
            return
        if not await self.require_role_or_admin_ctx(ctx, "log"):
            return

        raw = (content or "").strip()
        if not raw:
            await ctx.send(embed=self._build_status_embed(ctx.guild))
            return

        tokens = raw.split()
        first = tokens[0].lower()
        if first in {"show", "status", "info", "xem"}:
            await ctx.send(embed=self._build_status_embed(ctx.guild))
            return

        if first in {"off", "disable", "tat", "tắt"}:
            if len(tokens) < 2:
                await ctx.send(embed=create_error_splash("❌ Thiếu Loại Log", "Dùng: `log off chat|voice|channel|server|join|cash|all`."))
                return
            category = CATEGORY_ALIASES.get(tokens[1].lower())
            if not category:
                await ctx.send(embed=create_error_splash("❌ Loại Log Không Hợp Lệ", "Chọn: chat, voice, channel, server, join/leave, cash hoặc all."))
                return
            await self._set_category_channel(ctx.guild, category, None)
            await ctx.send(embed=create_success_splash("✅ Đã Tắt Log", f"Đã tắt log `{category}`."))
            return

        if first in {"test", "demo"}:
            category = CATEGORY_ALIASES.get(tokens[1].lower(), "chat") if len(tokens) >= 2 else "chat"
            await self._send_log(ctx.guild, category, embed=build_basic_log_embed("🧪 Test Log", f"Log `{category}` đang hoạt động.", category, ctx.author))
            await ctx.send(embed=create_success_splash("✅ Đã Gửi Test Log", f"Đã gửi test về kênh log `{category}` nếu đã set."))
            return

        category = CATEGORY_ALIASES.get(first)
        if not category:
            await ctx.send(
                embed=create_error_splash(
                    "❌ Sai Cú Pháp",
                    "Dùng: `log chat|voice|channel|server|join|cash #channel`, `log off <loại>`, `log voice room on`.",
                )
            )
            return

        after_category = raw.split(maxsplit=1)[1].strip() if len(tokens) >= 2 else ""
        if category == "voice" and await self._handle_prefix_voice_special(ctx, tokens[1:], after_category):
            return

        if not after_category:
            await ctx.send(embed=create_error_splash("❌ Thiếu Kênh", f"Dùng: `log {first} #channel` hoặc `log {first} off`."))
            return
        if after_category.lower() in {"off", "disable", "tat", "tắt"}:
            await self._set_category_channel(ctx.guild, category, None)
            await ctx.send(embed=create_success_splash("✅ Đã Tắt Log", f"Đã tắt log `{category}`."))
            return
        channel = await self._convert_text_channel(ctx, after_category)
        if not channel:
            await ctx.send(embed=create_error_splash("❌ Kênh Không Hợp Lệ", "Hãy nhập text channel hợp lệ."))
            return

        await self._set_category_channel(ctx.guild, category, channel)
        label = "tất cả log" if category == "all" else f"log `{category}`"
        await ctx.send(embed=create_success_splash("✅ Đã Set Log", f"Đã set {label} về {channel.mention}."))

    @app_commands.command(name="log", description="Setup log toàn server")
    @app_commands.choices(action=ACTION_CHOICES, category=CATEGORY_CHOICES)
    @app_commands.describe(
        action="Thao tác log",
        category="Loại log",
        channel="Kênh đích nhận log; bot vẫn theo dõi toàn bộ server",
        message="Template voice: {user}, {username}, {channel}, {channel_name}, {server}",
        embed="Bật/tắt embed cho voice greeting",
    )
    async def slash_log(
        self,
        interaction: discord.Interaction,
        action: str = "show",
        category: str = "chat",
        channel: discord.TextChannel | None = None,
        message: str | None = None,
        embed: bool | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Chỉ dùng trong server.", ephemeral=True)
            return
        if not await self.require_role_or_admin_interaction(interaction, "log"):
            return

        action = (action or "show").lower()
        category = CATEGORY_ALIASES.get((category or "chat").lower(), "chat")
        if action == "show":
            await interaction.response.send_message(embed=self._build_status_embed(interaction.guild), ephemeral=True)
            return
        if action == "set":
            if channel is None:
                await interaction.response.send_message(embed=create_error_splash("❌ Thiếu Kênh", "Hãy chọn kênh nhận log."), ephemeral=True)
                return
            await self._set_category_channel(interaction.guild, category, channel)
            await interaction.response.send_message(embed=create_success_splash("✅ Đã Set Log", f"Đã set `{category}` về {channel.mention}."), ephemeral=True)
            return
        if action == "off":
            await self._set_category_channel(interaction.guild, category, None)
            await interaction.response.send_message(embed=create_success_splash("✅ Đã Tắt Log", f"Đã tắt log `{category}`."), ephemeral=True)
            return
        if action == "test":
            await self._send_log(interaction.guild, category, embed=build_basic_log_embed("🧪 Test Log", f"Log `{category}` đang hoạt động.", category, interaction.user))
            await interaction.response.send_message(embed=create_success_splash("✅ Đã Gửi Test Log", f"Đã gửi test về kênh log `{category}` nếu đã set."), ephemeral=True)
            return
        if action == "voice-announce":
            self.service.set_voice_announce_channel(interaction.guild.id, channel.id if channel else None)
            text = f"Voice greeting sẽ gửi ở {channel.mention}." if channel else "Đã tắt voice greeting."
            await interaction.response.send_message(embed=create_success_splash("✅ Đã Cập Nhật Voice Greeting", text), ephemeral=True)
            return
        if action == "voice-room":
            enabled = True if embed is None else bool(embed)
            self.service.set_voice_room_announce(interaction.guild.id, enabled)
            text = (
                "Bot sẽ thông báo vào chat của tất cả voice room khi có người vào/rời."
                if enabled
                else "Đã tắt thông báo trong chat voice room."
            )
            await interaction.response.send_message(
                embed=create_success_splash("✅ Đã Cập Nhật Voice Room", text),
                ephemeral=True,
            )
            return
        if action == "voice-join-message":
            if not message:
                await interaction.response.send_message(embed=create_error_splash("❌ Thiếu Nội Dung", "Nhập template trong ô `message`."), ephemeral=True)
                return
            self.service.set_voice_template(interaction.guild.id, "join", message)
            await interaction.response.send_message(embed=create_success_splash("✅ Đã Set Câu Vào Voice", message), ephemeral=True)
            return
        if action == "voice-leave-message":
            if not message:
                await interaction.response.send_message(embed=create_error_splash("❌ Thiếu Nội Dung", "Nhập template trong ô `message`."), ephemeral=True)
                return
            self.service.set_voice_template(interaction.guild.id, "leave", message)
            await interaction.response.send_message(embed=create_success_splash("✅ Đã Set Câu Rời Voice", message), ephemeral=True)
            return
        if action == "voice-embed":
            enabled = bool(embed)
            self.service.set_voice_announce_embed(interaction.guild.id, enabled)
            await interaction.response.send_message(embed=create_success_splash("✅ Đã Cập Nhật Voice Embed", f"Voice greeting embed: `{'Bật' if enabled else 'Tắt'}`."), ephemeral=True)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or not message.author or message.author.bot:
            return
        actor, reason = await self._find_audit_actor(
            message.guild,
            discord.AuditLogAction.message_delete,
            target_id=message.author.id,
            channel_id=message.channel.id,
        )
        title = f"Message deleted in {message.channel.mention}"
        actor_text = f"\n**Người xoá:** {actor.mention}" if actor and actor.id != message.author.id else ""
        reason_text = f"\n**Lý do:** {reason}" if reason else ""
        attachment_text = ""
        if message.attachments:
            attachment_text = "\n**Tệp:** " + " | ".join(attachment.url for attachment in message.attachments[:5])
        description = (
            f"{truncate_text(message.content, 900)}\n\n"
            f"**Message ID:** `{message.id}`{actor_text}{reason_text}{attachment_text}\n"
            f"**ID:** `{message.author.id}`"
        )
        embed = build_basic_log_embed(title, description, "chat", message.author)
        await self._send_log(message.guild, "chat", embed=embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages:
            return
        guild = messages[0].guild
        if not guild:
            return
        channel = messages[0].channel
        actor, reason = await self._find_audit_actor(guild, discord.AuditLogAction.message_bulk_delete, channel_id=channel.id)
        actor_text = f"\n**Người xoá:** {actor.mention}" if actor else ""
        reason_text = f"\n**Lý do:** {reason}" if reason else ""
        embed = build_basic_log_embed(
            f"Bulk message deleted in {channel.mention}",
            f"Đã xoá `{len(messages)}` tin nhắn.{actor_text}{reason_text}\n**Kênh:** {channel.mention}",
            "chat",
            actor,
        )
        await self._send_log(guild, "chat", embed=embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot:
            return
        if before.content == after.content:
            return
        description = (
            f"**Before:** {truncate_text(before.content, 500)}\n"
            f"**After:** {truncate_text(after.content, 500)}\n\n"
            f"**ID:** `{before.author.id}`"
        )
        embed = build_basic_log_embed(f"Message edited in {before.channel.mention}", description, "chat", before.author)
        await self._send_log(before.guild, "chat", embed=embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or before.channel == after.channel:
            return
        if before.channel is None and after.channel is not None:
            description = f"{member.mention} vừa vào {after.channel.mention}.\n**ID:** `{member.id}`"
            await self._send_log(member.guild, "voice", embed=build_basic_log_embed("Voice joined", description, "voice", member))
            await self._send_voice_announce(member, "join", after.channel)
            await self._send_voice_room_announce(member, "join", after.channel)
            return
        if before.channel is not None and after.channel is None:
            description = f"{member.mention} vừa rời {before.channel.mention}.\n**ID:** `{member.id}`"
            await self._send_log(member.guild, "voice", embed=build_basic_log_embed("Voice left", description, "voice", member))
            await self._send_voice_announce(member, "leave", before.channel)
            await self._send_voice_room_announce(member, "leave", before.channel)
            return
        if before.channel is not None and after.channel is not None:
            description = f"{member.mention} chuyển từ {before.channel.mention} sang {after.channel.mention}.\n**ID:** `{member.id}`"
            await self._send_log(member.guild, "voice", embed=build_basic_log_embed("Voice moved", description, "voice", member))
            await self._send_voice_room_announce(member, "leave", before.channel)
            await self._send_voice_announce(member, "join", after.channel)
            await self._send_voice_room_announce(member, "join", after.channel)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        age = self._age_text(member.created_at)
        warning = "\n⚠️ **NEW ACCOUNT** ⚠️" if (datetime.now(timezone.utc) - member.created_at).days < 7 else ""
        description = f"{member.mention} người thứ `{member.guild.member_count}` vào server\nAccount tạo `{age}` trước{warning}\n**ID:** `{member.id}`"
        await self._send_log(member.guild, "member", embed=build_basic_log_embed("Member joined", description, "member", member))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        actor, reason = await self._find_audit_actor(member.guild, discord.AuditLogAction.kick, target_id=member.id)
        if actor:
            title = "Member kicked"
            extra = f"\n**Người kick:** {actor.mention}"
        else:
            title = "Member left"
            extra = ""
        reason_text = f"\n**Lý do:** {reason}" if reason else ""
        description = f"{member.mention}\n**ID:** `{member.id}`{extra}{reason_text}"
        await self._send_log(member.guild, "member", embed=build_basic_log_embed(title, description, "member", member))

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.roles != after.roles:
            before_ids = {role.id for role in before.roles}
            after_ids = {role.id for role in after.roles}
            added = [role for role in after.roles if role.id not in before_ids and role.name != "@everyone"]
            removed = [role for role in before.roles if role.id not in after_ids and role.name != "@everyone"]
            lines = []
            if added:
                lines.append("**Role added:** " + ", ".join(role.mention for role in added))
            if removed:
                lines.append("**Role removed:** " + ", ".join(role.name for role in removed))
            if lines:
                actor, reason = await self._find_audit_actor(after.guild, discord.AuditLogAction.member_role_update, target_id=after.id)
                if actor:
                    lines.append(f"**Người chỉnh:** {actor.mention}")
                if reason:
                    lines.append(f"**Lý do:** {reason}")
                lines.append(f"**ID:** `{after.id}`")
                await self._send_log(after.guild, "server", embed=build_basic_log_embed("Member role update", "\n".join(lines), "server", after))
        if before.nick != after.nick:
            description = f"**Before:** `{before.nick or before.name}`\n**After:** `{after.nick or after.name}`\n**ID:** `{after.id}`"
            await self._send_log(after.guild, "server", embed=build_basic_log_embed("Nickname update", description, "server", after))
        if before.guild_avatar != after.guild_avatar:
            embed = build_basic_log_embed(
                "Server avatar update",
                (
                    f"{after.mention}\n"
                    f"**Avatar cũ:** {self._asset_link(before.guild_avatar)}\n"
                    f"**Avatar mới:** {self._asset_link(after.guild_avatar)}\n"
                    f"**ID:** `{after.id}`"
                ),
                "server",
                after,
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            await self._send_log(after.guild, "server", embed=embed)

    @commands.Cog.listener()
    async def on_user_update(self, before: discord.User, after: discord.User):
        if before.avatar == after.avatar:
            return
        for guild in self.bot.guilds:
            member = guild.get_member(after.id)
            if member is None:
                continue
            embed = build_basic_log_embed(
                "Avatar update",
                (
                    f"{member.mention}\n"
                    f"**Avatar cũ:** {self._asset_link(before.avatar)}\n"
                    f"**Avatar mới:** {self._asset_link(after.avatar)}\n"
                    f"**ID:** `{after.id}`"
                ),
                "server",
                member,
            )
            embed.set_thumbnail(url=after.display_avatar.url)
            await self._send_log(guild, "server", embed=embed)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        actor, reason = await self._find_audit_actor(role.guild, discord.AuditLogAction.role_create, target_id=role.id)
        description = f"**Name:** {role.name}\n**Color:** {role.color}\n**Position:** `{role.position}`\n**Role ID:** `{role.id}`"
        if actor:
            description += f"\n**Người tạo:** {actor.mention}"
        if reason:
            description += f"\n**Lý do:** {reason}"
        await self._send_log(role.guild, "server", embed=build_basic_log_embed(f'Role "{role.name}" created', description, "server", actor))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        actor, reason = await self._find_audit_actor(role.guild, discord.AuditLogAction.role_delete, target_id=role.id)
        description = f"**Name:** {role.name}\n**Color:** {role.color}\n**Mentionable:** `{role.mentionable}`\n**Displayed separately:** `{role.hoist}`\n**Position:** `{role.position}`\n**Role ID:** `{role.id}`"
        if actor:
            description += f"\n**Người xoá:** {actor.mention}"
        if reason:
            description += f"\n**Lý do:** {reason}"
        await self._send_log(role.guild, "server", embed=build_basic_log_embed(f'Role "{role.name}" removed', description, "danger", actor))

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` → `{after.color}`")
        if before.hoist != after.hoist:
            changes.append(f"**Displayed separately:** `{before.hoist}` → `{after.hoist}`")
        if before.mentionable != after.mentionable:
            changes.append(f"**Mentionable:** `{before.mentionable}` → `{after.mentionable}`")
        if not changes:
            return
        actor, reason = await self._find_audit_actor(after.guild, discord.AuditLogAction.role_update, target_id=after.id)
        if actor:
            changes.append(f"**Người chỉnh:** {actor.mention}")
        if reason:
            changes.append(f"**Lý do:** {reason}")
        changes.append(f"**Role ID:** `{after.id}`")
        await self._send_log(after.guild, "server", embed=build_basic_log_embed(f'Role "{after.name}" updated', "\n".join(changes), "server", actor))

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        actor, reason = await self._find_audit_actor(channel.guild, discord.AuditLogAction.channel_create, target_id=channel.id)
        description = f"**Channel:** {channel.mention if hasattr(channel, 'mention') else channel.name}\n**ID:** `{channel.id}`"
        if actor:
            description += f"\n**Người tạo:** {actor.mention}"
        if reason:
            description += f"\n**Lý do:** {reason}"
        await self._send_log(channel.guild, "channel", embed=build_basic_log_embed("Channel created", description, "channel", actor))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        actor, reason = await self._find_audit_actor(channel.guild, discord.AuditLogAction.channel_delete, target_id=channel.id)
        description = f"**Name:** `{channel.name}`\n**ID:** `{channel.id}`"
        if actor:
            description += f"\n**Người xoá:** {actor.mention}"
        if reason:
            description += f"\n**Lý do:** {reason}"
        await self._send_log(channel.guild, "channel", embed=build_basic_log_embed("Channel deleted", description, "danger", actor))

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append(f"**Topic:** {truncate_text(getattr(before, 'topic', None), 200)} → {truncate_text(getattr(after, 'topic', None), 200)}")
        if not changes:
            return
        actor, reason = await self._find_audit_actor(after.guild, discord.AuditLogAction.channel_update, target_id=after.id)
        if actor:
            changes.append(f"**Người chỉnh:** {actor.mention}")
        if reason:
            changes.append(f"**Lý do:** {reason}")
        changes.append(f"**ID:** `{after.id}`")
        await self._send_log(after.guild, "channel", embed=build_basic_log_embed("Channel updated", "\n".join(changes), "channel", actor))

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread):
        description = (
            f"**Thread:** {thread.mention}\n"
            f"**Kênh:** {thread.parent.mention if thread.parent else '`Không rõ`'}\n"
            f"**Chủ thread:** {self._member_tag(thread.owner)}\n"
            f"**ID:** `{thread.id}`"
        )
        await self._send_log(
            thread.guild,
            "channel",
            embed=build_basic_log_embed("Thread created", description, "channel", thread.owner),
        )

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread):
        description = (
            f"**Name:** `{thread.name}`\n"
            f"**Kênh:** {thread.parent.mention if thread.parent else '`Không rõ`'}\n"
            f"**ID:** `{thread.id}`"
        )
        await self._send_log(
            thread.guild,
            "channel",
            embed=build_basic_log_embed("Thread deleted", description, "danger", thread.owner),
        )

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread):
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.archived != after.archived:
            changes.append(f"**Archived:** `{before.archived}` → `{after.archived}`")
        if before.locked != after.locked:
            changes.append(f"**Locked:** `{before.locked}` → `{after.locked}`")
        if before.slowmode_delay != after.slowmode_delay:
            changes.append(f"**Slowmode:** `{before.slowmode_delay}s` → `{after.slowmode_delay}s`")
        if not changes:
            return
        changes.append(f"**ID:** `{after.id}`")
        await self._send_log(
            after.guild,
            "channel",
            embed=build_basic_log_embed("Thread updated", "\n".join(changes), "channel", after.owner),
        )

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.icon != after.icon:
            changes.append("**Icon:** Đã thay đổi")
        if before.banner != after.banner:
            changes.append("**Banner:** Đã thay đổi")
        if not changes:
            return
        actor, reason = await self._find_audit_actor(after, discord.AuditLogAction.guild_update)
        if actor:
            changes.append(f"**Người chỉnh:** {actor.mention}")
        if reason:
            changes.append(f"**Lý do:** {reason}")
        changes.append(f"**Guild ID:** `{after.id}`")
        await self._send_log(after, "server", embed=build_basic_log_embed("Server updated", "\n".join(changes), "server", actor))


async def setup(bot):
    await bot.add_cog(LogCog(bot))
