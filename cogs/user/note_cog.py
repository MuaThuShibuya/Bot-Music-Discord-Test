from __future__ import annotations

import importlib
import re

import discord
from discord.ext import commands

from cogs.admin_command_utils import format_vnd, parse_vnd_amount
from services.admin_service import AdminService
import services.note_service as note_service_module
from services.role_permission_service import RolePermissionService
from utils import append_discord_timestamp

note_service_module = importlib.reload(note_service_module)
NoteService = note_service_module.NoteService


class NoteTextModal(discord.ui.Modal):
    def __init__(
        self,
        cog: "NoteCog",
        requester_id: int,
        target_id: int,
        target_name: str,
        *,
        position: int | None = None,
        title_value: str = "",
        content_value: str = "",
    ):
        super().__init__(title="Note TXT", timeout=300)
        self.cog = cog
        self.requester_id = requester_id
        self.target_id = target_id
        self.target_name = target_name
        self.position = position
        self.title_input = discord.ui.TextInput(
            label="Tiêu đề",
            required=False,
            max_length=120,
            default=title_value[:120],
        )
        self.content_input = discord.ui.TextInput(
            label="Nội dung",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=4000,
            default=content_value[:4000],
        )
        self.add_item(self.title_input)
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("❌ Popup này không dành cho bạn.", ephemeral=True)
            return
        title = str(self.title_input.value or "").strip()
        content = str(self.content_input.value or "").strip()
        if not content:
            await interaction.response.send_message("❌ Nội dung note không được để trống.", ephemeral=True)
            return
        if self.position is None:
            created = self.cog.service.add_note(
                interaction.guild.id if interaction.guild else None,
                self.target_id,
                content,
                author_user_id=interaction.user.id,
                author_name=getattr(interaction.user, "display_name", str(interaction.user)),
                title=title,
                kind="txt",
            )
            notes = self.cog.service.list_notes(interaction.guild.id if interaction.guild else None, self.target_id)
            position = len(notes)
            embed = self.cog._build_single_note_embed(
                created,
                position,
                self.target_name,
                compact=True,
                guild=interaction.guild,
            )
            await interaction.response.send_message(
                embed=embed,
                view=NoteContentView(
                    embed,
                    self.cog._build_single_note_embed(
                        created,
                        position,
                        self.target_name,
                        compact=False,
                        guild=interaction.guild,
                    ),
                ),
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

        updated = self.cog.service.update_note_at(
            interaction.guild.id if interaction.guild else None,
            self.target_id,
            self.position,
            content,
            title=title,
            kind="txt",
            editor_user_id=interaction.user.id,
            editor_name=getattr(interaction.user, "display_name", str(interaction.user)),
        )
        embed = self.cog._build_single_note_embed(
            updated,
            self.position,
            self.target_name,
            compact=True,
            guild=interaction.guild,
        )
        await interaction.response.send_message(
            embed=embed,
            view=NoteContentView(
                embed,
                self.cog._build_single_note_embed(
                    updated,
                    self.position,
                    self.target_name,
                    compact=False,
                    guild=interaction.guild,
                ),
            ),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class NoteModalLaunchView(discord.ui.View):
    def __init__(
        self,
        cog: "NoteCog",
        requester_id: int,
        target_id: int,
        target_name: str,
        *,
        position: int | None = None,
        title_value: str = "",
        content_value: str = "",
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.requester_id = requester_id
        self.target_id = target_id
        self.target_name = target_name
        self.position = position
        self.title_value = title_value
        self.content_value = content_value

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.requester_id:
            return True
        await interaction.response.send_message("❌ Nút này không dành cho bạn.", ephemeral=True)
        return False

    @discord.ui.button(label="Mở popup note TXT", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            NoteTextModal(
                self.cog,
                self.requester_id,
                self.target_id,
                self.target_name,
                position=self.position,
                title_value=self.title_value,
                content_value=self.content_value,
            )
        )


class NoteContentView(discord.ui.View):
    def __init__(self, compact_embed: discord.Embed, full_embed: discord.Embed):
        super().__init__(timeout=300)
        self.compact_embed = compact_embed
        self.full_embed = full_embed
        self.expanded = False

    @discord.ui.button(label="Phóng to", style=discord.ButtonStyle.secondary)
    async def toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.expanded = not self.expanded
        button.label = "Thu gọn" if self.expanded else "Phóng to"
        await interaction.response.edit_message(embed=self.full_embed if self.expanded else self.compact_embed, view=self)


class NoteCog(commands.Cog):
    DELETE_ACTIONS = {"d", "del", "delete", "rm", "remove", "xoa", "xóa"}
    EDIT_ACTIONS = {"e", "edit", "sua", "sửa"}
    PUBLIC_ACTIONS = {"public", "pb"}
    PRIVATE_ACTIONS = {"private", "prv"}
    STATUS_ACTIONS = {"status", "st", "check", "kiemtra", "kiểmtra"}
    VIEW_ACTIONS = {"view", "v", "show", "xem"}
    ADJUST_PATTERN = re.compile(r"^(?P<index>\d+)\s*(?P<sign>[+-])\s*(?P<amount>.+)$")
    FILE_PATTERN = re.compile(r"^(?P<title>.+?)\s*\[file\s+(?P<content>.+)\]\s*$", re.IGNORECASE | re.DOTALL)
    EMOJI_PATTERN = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>|:([A-Za-z0-9_]{2,32}):")

    def __init__(self, bot):
        self.bot = bot
        self.service = NoteService()
        self.admins = AdminService()
        self.role_permissions = RolePermissionService()

    def cog_unload(self):
        self.service.close()

    @staticmethod
    def _guild_id(ctx) -> int | None:
        return ctx.guild.id if ctx.guild else None

    @staticmethod
    def _format_amount_plain(amount: int | None) -> str:
        if amount is None:
            return ""
        return f" {format_vnd(amount)} VNĐ"

    @staticmethod
    def _shorten(value: str, limit: int = 180) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        return text[: limit - 3].rstrip() + "..."

    @classmethod
    def _render_txt_content(cls, content: str, guild: discord.Guild | None) -> str:
        text = str(content or "")
        if guild is None:
            return text
        emojis = {emoji.name: str(emoji) for emoji in guild.emojis}

        def replace_emoji(match: re.Match) -> str:
            emoji_name = match.group(1)
            if emoji_name is None:
                return match.group(0)
            return emojis.get(emoji_name, match.group(0))

        return cls.EMOJI_PATTERN.sub(replace_emoji, text)

    @staticmethod
    def _source_code_block(value: str) -> str:
        safe_value = str(value or "").replace("```", "``" + chr(8203) + "`")
        return f"```\n{safe_value}\n```"

    def _can_manage_notes(self, ctx) -> bool:
        if ctx.guild is None:
            return self.admins.is_hard_admin(ctx.author.id)
        if self.admins.is_admin(ctx.author.id, ctx.guild.id):
            return True
        role_ids = [role.id for role in ctx.author.roles if role.name != "@everyone"]
        return self.role_permissions.user_can_use(ctx.guild.id, role_ids, "note")

    def _can_manage_visibility(self, ctx, action: str) -> bool:
        if ctx.guild is None:
            return self.admins.is_hard_admin(ctx.author.id)
        if self.admins.is_admin(ctx.author.id, ctx.guild.id):
            return True
        command_name = "note public" if action in self.PUBLIC_ACTIONS else "note private"
        role_ids = [role.id for role in ctx.author.roles if role.name != "@everyone"]
        return self.role_permissions.manager.can_use_command(ctx.guild.id, role_ids, command_name)

    async def _target_from_leading_mention(self, ctx, raw: str) -> tuple[discord.Member | None, str]:
        text = (raw or "").strip()
        match = re.match(r"^<@!?(\d+)>\s*(.*)$", text, flags=re.DOTALL)
        if not match:
            return None, text
        user_id = int(match.group(1))
        member = ctx.guild.get_member(user_id) if ctx.guild else None
        if member is None and ctx.guild:
            try:
                member = await ctx.guild.fetch_member(user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                member = None
        return member, match.group(2).strip()

    @classmethod
    def _parse_note_content_and_amount(cls, raw: str) -> tuple[str, int | None, str, str]:
        text = raw.strip()
        if not text:
            raise ValueError("Hãy nhập nội dung note.")

        file_match = cls.FILE_PATTERN.match(text)
        if file_match:
            return file_match.group("content").strip(), None, file_match.group("title").strip(), "txt"

        parts = text.rsplit(maxsplit=1)
        if len(parts) == 2 and cls._looks_like_amount_token(parts[1]):
            try:
                amount = parse_vnd_amount(parts[1])
            except ValueError:
                return text, None, "", "plain"
            content = parts[0].strip()
            if content:
                return content, amount, "", "plain"

        return text, None, "", "plain"

    @staticmethod
    def _looks_like_amount_token(token: str) -> bool:
        cleaned = token.strip().lower()
        if re.search(r"(vnđ|vnd|đ|d|[kmb]|[.,])", cleaned):
            return True
        return bool(re.fullmatch(r"\d{4,}", cleaned))

    @staticmethod
    def _parse_positions(raw: str) -> list[int]:
        positions: list[int] = []
        for chunk in re.split(r"[\s,]+", raw.strip()):
            if not chunk:
                continue
            if not chunk.isdigit():
                raise ValueError(f"Số thứ tự `{chunk}` không hợp lệ.")
            positions.append(int(chunk))
        if not positions:
            raise ValueError("Hãy nhập số thứ tự note cần xoá.")
        return positions

    def _note_label(self, note: dict, position: int) -> str:
        title = str(note.get("title") or "").strip()
        content = str(note.get("content") or "").strip()
        kind_label = "TXT · " if note.get("kind") == "txt" else ""
        marker = " - Fix" if int(note.get("edit_count") or 0) > 0 else ""
        head = title if title else content
        amount = self._format_amount_plain(note.get("amount"))
        author = ""
        if int(note.get("author_user_id") or note.get("user_id") or 0) != int(note.get("user_id") or 0):
            author_name = note.get("author_name") or f"User {note.get('author_user_id')}"
            author = f" · bởi {author_name}"
        source_url = str(note.get("source_url") or "").strip()
        source_link = f" · [Tin nhắn]({source_url})" if source_url else ""
        return f"{kind_label}{position}. {self._shorten(head, 170)}{marker}{amount}{author}{source_link}"

    def _format_notes_plain(self, ctx, member: discord.Member | None = None) -> str:
        target = member or ctx.author
        notes = self.service.list_notes(self._guild_id(ctx), target.id)
        if not notes:
            return f"{target.display_name} chưa có note nào."
        return "\n".join(self._note_label(note, index) for index, note in enumerate(notes, 1))

    def _build_single_note_embed(
        self,
        note: dict | None,
        position: int,
        target_name: str,
        *,
        compact: bool,
        guild: discord.Guild | None = None,
    ) -> discord.Embed:
        embed = discord.Embed(color=discord.Color.from_rgb(255, 184, 90))
        if not note:
            embed.title = "🗒️ Note"
            embed.description = "Không tìm thấy note."
            return embed
        title = str(note.get("title") or "").strip()
        content = str(note.get("content") or "").strip()
        if note.get("kind") == "txt":
            title = self._render_txt_content(title, guild)
            content = self._render_txt_content(content, guild)
        kind_label = "TXT · " if note.get("kind") == "txt" else ""
        embed.title = f"🗒️ {kind_label}Note #{position} của {target_name}"
        if title:
            embed.add_field(name="Tiêu đề", value=title[:1024], inline=False)
        embed.description = self._shorten(content, 350) if compact else content[:4096]
        source_url = str(note.get("source_url") or "").strip()
        if source_url:
            embed.add_field(
                name="Tin nhắn gốc",
                value=f"[Đi tới tin nhắn]({source_url})",
                inline=False,
            )
        footer = "TXT" if note.get("kind") == "txt" else "Note"
        if int(note.get("edit_count") or 0) > 0:
            footer += " - Fix"
        embed.set_footer(text=footer)
        append_discord_timestamp(embed)
        return embed

    async def _resolve_replied_message(self, ctx) -> discord.Message | None:
        reference = getattr(ctx.message, "reference", None)
        if not reference:
            return None
        resolved = getattr(reference, "resolved", None)
        if isinstance(resolved, discord.Message):
            return resolved
        if not reference.message_id:
            return None
        try:
            return await ctx.channel.fetch_message(reference.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    @staticmethod
    def _reply_note_content(message: discord.Message) -> str:
        parts: list[str] = []
        content = str(message.content or "").strip()
        if content:
            parts.append(content)
        parts.extend(str(attachment.url) for attachment in message.attachments)
        parts.extend(str(sticker.url) for sticker in message.stickers)
        for embed in message.embeds:
            if embed.title:
                parts.append(str(embed.title))
            if embed.description:
                parts.append(str(embed.description))
            for field in embed.fields:
                parts.append(f"{field.name}: {field.value}")
        return "\n".join(parts).strip()

    def _build_note_source_embed(self, note: dict, position: int, target_name: str) -> discord.Embed:
        embed = discord.Embed(
            title=f"📝 TXT · Mã nguồn note #{position} của {target_name}",
            description=self._source_code_block(note.get("content") or ""),
            color=discord.Color.from_rgb(255, 184, 90),
        )
        title = str(note.get("title") or "").strip()
        if title:
            embed.add_field(name="Tiêu đề", value=self._source_code_block(title), inline=False)
        embed.set_footer(text="Hiển thị nguyên văn để sửa, gồm cả ID emoji")
        return embed

    def _build_notes_embed(self, ctx, member: discord.Member | None = None, title: str = "🗒️ Note") -> discord.Embed:
        target = member or ctx.author
        notes = self.service.list_notes(self._guild_id(ctx), target.id)
        embed = discord.Embed(color=discord.Color.from_rgb(255, 184, 90))
        embed.set_author(name=target.display_name, icon_url=target.display_avatar.url)
        public_text = "public" if self.service.is_public(self._guild_id(ctx), target.id) else "private"
        embed.title = title

        if not notes:
            embed.description = f"{target.display_name} chưa có note nào.\nQuyền nhận note: `{public_text}`"
            return embed

        embed.description = "\n".join(self._note_label(note, index) for index, note in enumerate(notes[:50], 1))
        embed.set_footer(text=f"Quyền nhận note: {public_text}" + (f" · Đang hiện 50/{len(notes)} note" if len(notes) > 50 else ""))
        append_discord_timestamp(embed)
        return embed

    async def _handle_visibility(self, ctx, action: str, rest: str):
        member, remaining = await self._target_from_leading_mention(ctx, rest)
        target = member or ctx.author
        if target.id != ctx.author.id and not self._can_manage_visibility(ctx, action):
            permission_name = "note public" if action in self.PUBLIC_ACTIONS else "note private"
            await ctx.reply(f"❌ Chỉ admin hoặc role có quyền `{permission_name}` mới đổi trạng thái này cho người khác.", mention_author=False)
            return
        is_public = action in self.PUBLIC_ACTIONS
        self.service.set_public(self._guild_id(ctx), target.id, is_public)
        await ctx.reply(f"✅ Note của {target.mention} đã chuyển sang `{action}`.", mention_author=False)

    async def _handle_status(self, ctx, rest: str):
        member, remaining = await self._target_from_leading_mention(ctx, rest)
        target = member or ctx.author
        if target.id != ctx.author.id and not self._can_manage_notes(ctx):
            await ctx.reply("❌ Bạn không có quyền xem trạng thái note của người khác.", mention_author=False)
            return
        public_text = "public" if self.service.is_public(self._guild_id(ctx), target.id) else "private"
        await ctx.reply(f"🗒️ Note của {target.mention} đang `{public_text}`.", mention_author=False)

    async def _handle_delete(self, ctx, rest: str):
        member, remaining = await self._target_from_leading_mention(ctx, rest)
        target = member or ctx.author
        if target.id != ctx.author.id and not self._can_manage_notes(ctx):
            await ctx.reply("❌ Chỉ admin hoặc role có quyền `note` mới xoá note của người khác.", mention_author=False)
            return
        try:
            positions = self._parse_positions(remaining if member else rest)
        except ValueError as exc:
            await ctx.reply(f"❌ Xoá note lỗi: {exc}", mention_author=False)
            return
        deleted = self.service.delete_positions(self._guild_id(ctx), target.id, positions)
        if not deleted:
            await ctx.reply("❌ Không có note nào khớp số thứ tự bạn nhập.", mention_author=False)
            return
        deleted_lines = [f"#{row['position']} {row['title'] or row['content']}" for row in deleted]
        await ctx.reply(f"Đã xoá note {', '.join(deleted_lines)}.", mention_author=False)

    async def _handle_edit(self, ctx, rest: str):
        member, remaining = await self._target_from_leading_mention(ctx, rest)
        target = member or ctx.author
        raw = remaining if member else rest
        parts = raw.split(maxsplit=1)
        if not parts or not parts[0].isdigit():
            await ctx.reply("❌ Dùng: `note edit [@user] <số> <nội dung|txt>`.", mention_author=False)
            return
        position = int(parts[0])
        new_content = parts[1].strip() if len(parts) > 1 else ""
        note = self.service.get_note_at(self._guild_id(ctx), target.id, position)
        if not note:
            await ctx.reply(f"❌ Không có note số {position}.", mention_author=False)
            return
        author_id = int(note.get("author_user_id") or target.id)
        can_edit = target.id == ctx.author.id or author_id == ctx.author.id or self._can_manage_notes(ctx)
        if not can_edit:
            await ctx.reply("❌ Bạn chỉ sửa được note của mình thêm vào, trừ khi có quyền `note`.", mention_author=False)
            return
        if not new_content or new_content.lower() == "txt" or note.get("kind") == "txt" and new_content.lower() in {"popup", "modal"}:
            await ctx.reply(
                f"Bấm nút để sửa note TXT #{position} của {target.mention}.",
                embed=self._build_note_source_embed(note, position, target.display_name),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
                view=NoteModalLaunchView(
                    self,
                    ctx.author.id,
                    target.id,
                    target.display_name,
                    position=position,
                    title_value=note.get("title") or "",
                    content_value=note.get("content") or "",
                ),
            )
            return
        try:
            content, amount, title, kind = self._parse_note_content_and_amount(new_content)
        except ValueError as exc:
            await ctx.reply(f"❌ Sửa note lỗi: {exc}", mention_author=False)
            return
        updated = self.service.update_note_at(
            self._guild_id(ctx),
            target.id,
            position,
            content,
            amount,
            title=title,
            kind=kind,
            editor_user_id=ctx.author.id,
            editor_name=ctx.author.display_name,
        )
        await ctx.reply(f"✅ Đã sửa note #{position} của {target.mention}: {updated['title'] or updated['content']}", mention_author=False)

    async def _handle_view(self, ctx, rest: str):
        member, remaining = await self._target_from_leading_mention(ctx, rest)
        target = member or ctx.author
        raw = remaining if member else rest
        if not raw.strip().isdigit():
            await ctx.reply("❌ Dùng: `note view [@user] <số>`.", mention_author=False)
            return
        if target.id != ctx.author.id and not (self.service.is_public(self._guild_id(ctx), target.id) or self._can_manage_notes(ctx)):
            await ctx.reply("❌ Note của người này đang private.", mention_author=False)
            return
        position = int(raw.strip())
        note = self.service.get_note_at(self._guild_id(ctx), target.id, position)
        if not note:
            await ctx.reply(f"❌ Không có note số {position}.", mention_author=False)
            return
        compact = self._build_single_note_embed(note, position, target.display_name, compact=True, guild=ctx.guild)
        full = self._build_single_note_embed(note, position, target.display_name, compact=False, guild=ctx.guild)
        await ctx.reply(
            embed=compact,
            view=NoteContentView(compact, full),
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _handle_add(self, ctx, stripped: str):
        mentioned_target, rest = await self._target_from_leading_mention(ctx, stripped)
        target = mentioned_target or ctx.author
        raw_content = rest if mentioned_target else stripped
        replied_message = None
        if not raw_content.strip():
            replied_message = await self._resolve_replied_message(ctx)
        if mentioned_target and not raw_content.strip() and replied_message is None:
            if not (self.service.is_public(self._guild_id(ctx), target.id) or self._can_manage_notes(ctx)):
                await ctx.reply("❌ Bạn không có quyền truy cập note của người này.", mention_author=False)
                return
            await ctx.reply(self._format_notes_plain(ctx, target), mention_author=False)
            return
        if target.id != ctx.author.id and not self.service.is_public(self._guild_id(ctx), target.id) and not self._can_manage_notes(ctx):
            await ctx.reply("❌ Người này đang để note `private`. Chỉ admin hoặc role có quyền `note` mới thêm được.", mention_author=False)
            return
        if replied_message is not None:
            reply_content = self._reply_note_content(replied_message)
            if not reply_content:
                await ctx.reply("❌ Tin nhắn được reply không có nội dung hoặc tệp để lưu.", mention_author=False)
                return
            created = self.service.add_note(
                self._guild_id(ctx),
                target.id,
                reply_content,
                author_user_id=ctx.author.id,
                author_name=ctx.author.display_name,
                title=f"Tin nhắn của {replied_message.author.display_name}",
                kind="txt",
                source_url=replied_message.jump_url,
                source_message_id=replied_message.id,
            )
            position = len(self.service.list_notes(self._guild_id(ctx), target.id))
            compact = self._build_single_note_embed(
                created,
                position,
                target.display_name,
                compact=True,
                guild=ctx.guild,
            )
            full = self._build_single_note_embed(
                created,
                position,
                target.display_name,
                compact=False,
                guild=ctx.guild,
            )
            await ctx.reply(
                embed=compact,
                view=NoteContentView(compact, full),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        if raw_content.strip().lower() == "txt":
            await ctx.reply(
                f"Bấm nút để nhập note TXT cho {target.mention}.",
                mention_author=False,
                view=NoteModalLaunchView(self, ctx.author.id, target.id, target.display_name),
            )
            return
        try:
            note_content, amount, title, kind = self._parse_note_content_and_amount(raw_content)
        except ValueError as exc:
            await ctx.reply(f"❌ Thêm note lỗi: {exc}", mention_author=False)
            return
        created = self.service.add_note(
            self._guild_id(ctx),
            target.id,
            note_content,
            amount,
            author_user_id=ctx.author.id,
            author_name=ctx.author.display_name,
            title=title,
            kind=kind,
        )
        notes = self.service.list_notes(self._guild_id(ctx), target.id)
        position = len(notes)
        if kind == "txt":
            compact = self._build_single_note_embed(created, position, target.display_name, compact=True, guild=ctx.guild)
            full = self._build_single_note_embed(created, position, target.display_name, compact=False, guild=ctx.guild)
            await ctx.reply(
                embed=compact,
                view=NoteContentView(compact, full),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return
        await ctx.reply(f"Đã thêm note #{position} cho {target.mention}: {created['content']}{self._format_amount_plain(amount)}.", mention_author=False)

    @commands.command(name="note")
    async def note(self, ctx, *, content: str = None):
        if not content:
            if ctx.message.reference:
                await self._handle_add(ctx, "")
                return
            await ctx.reply(self._format_notes_plain(ctx), mention_author=False)
            return

        stripped = content.strip()
        action, _, rest = stripped.partition(" ")
        lowered_action = action.lower()

        if lowered_action in self.PUBLIC_ACTIONS or lowered_action in self.PRIVATE_ACTIONS:
            await self._handle_visibility(ctx, lowered_action, rest)
            return
        if lowered_action in self.STATUS_ACTIONS:
            await self._handle_status(ctx, rest)
            return
        if lowered_action in self.VIEW_ACTIONS:
            await self._handle_view(ctx, rest)
            return
        if lowered_action in self.DELETE_ACTIONS:
            await self._handle_delete(ctx, rest)
            return
        if lowered_action in self.EDIT_ACTIONS:
            await self._handle_edit(ctx, rest)
            return

        adjust_match = self.ADJUST_PATTERN.match(stripped)
        if adjust_match:
            position = int(adjust_match.group("index"))
            sign = adjust_match.group("sign")
            try:
                amount = parse_vnd_amount(adjust_match.group("amount"))
            except ValueError as exc:
                await ctx.reply(f"❌ Sửa tiền note lỗi: {exc}", mention_author=False)
                return
            delta = amount if sign == "+" else -amount
            updated = self.service.adjust_amount(self._guild_id(ctx), ctx.author.id, position, delta)
            if not updated:
                await ctx.reply(f"❌ Không có note số {position}.", mention_author=False)
                return
            await ctx.reply(f"Đã sửa note #{position} {updated['content']}{self._format_amount_plain(updated['amount'])}.", mention_author=False)
            return

        await self._handle_add(ctx, stripped)

    @commands.command(name="notes")
    async def notes(self, ctx, member: discord.Member | None = None):
        if member and member.id != ctx.author.id and not (self.service.is_public(self._guild_id(ctx), member.id) or self._can_manage_notes(ctx)):
            await ctx.reply("❌ Note của người này đang private.", mention_author=False)
            return
        await ctx.reply(embed=self._build_notes_embed(ctx, member, "🗒️ Note"), mention_author=False)


async def setup(bot):
    await bot.add_cog(NoteCog(bot))
