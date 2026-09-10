import io
import re
import unicodedata

import aiohttp
import discord
from discord.ext import commands

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_error_splash,
    create_info_splash,
    create_success_splash,
    create_warning_splash,
    parse_color,
)
from services.responsive_service import ResponsiveService
from utils import append_discord_timestamp, get_prefix, match_case_insensitive_prefix


FORM_TEMPLATE = (
    "**Form booking**\n"
    "Tên:\n"
    "Địa chỉ:\n"
    "Nhận những gì:\n"
    "Caption:\n"
    "Giá tiền game:\n"
    "Giá tiền hát:\n"
    "Giá tiền cam:\n\n"
    "Điền form rồi reply tin nhắn đó bằng `ar description <key> <số>` hoặc `ar description <key><số>`.\n"
    "Hoặc dùng `ar description <key> <số> | <form đã nhập>`."
)

FORM_FIELD_BY_LABEL = {
    "ten": "name",
    "dia chi": "address",
    "nhan nhung gi": "receives",
    "caption": "caption",
    "gia tien game": "price_game",
    "gia game": "price_game",
    "gia tien hat": "price_sing",
    "gia hat": "price_sing",
    "gia tien cam": "price_cam",
    "gia cam": "price_cam",
}

PRICE_FIELD_BY_LABEL = {
    "game": "price_game",
    "gia game": "price_game",
    "gia tien game": "price_game",
    "hat": "price_sing",
    "gia hat": "price_sing",
    "gia tien hat": "price_sing",
    "cam": "price_cam",
    "gia cam": "price_cam",
    "gia tien cam": "price_cam",
}


class BookingFormModal(discord.ui.Modal):
    def __init__(self, cog: "AdministratorResponsiveCog", profile_key: str | None = None, profile_number: int | None = None):
        title = "Điền form booking"
        if profile_key is not None and profile_number is not None:
            title = f"Điền form {profile_key}{profile_number}"
        super().__init__(title=title)
        self.cog = cog
        self.profile_key = profile_key
        self.profile_number = profile_number

        self.name_input = discord.ui.TextInput(label="Tên", required=False, max_length=100)
        self.address_input = discord.ui.TextInput(label="Địa chỉ", required=False, max_length=150)
        self.receives_input = discord.ui.TextInput(label="Nhận những gì", style=discord.TextStyle.paragraph, required=False, max_length=800)
        self.caption_input = discord.ui.TextInput(label="Caption", style=discord.TextStyle.paragraph, required=False, max_length=500)
        self.price_input = discord.ui.TextInput(
            label="Giá (Game / Hát / Cam)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=500,
            placeholder="Game: 50k/h\nHát: 30k/bài\nCam: 300k",
        )

        self.add_item(self.name_input)
        self.add_item(self.address_input)
        self.add_item(self.receives_input)
        self.add_item(self.caption_input)
        self.add_item(self.price_input)

    def _build_form_text(self) -> str:
        fields = {
            "name": str(self.name_input.value or "").strip(),
            "address": str(self.address_input.value or "").strip(),
            "receives": str(self.receives_input.value or "").strip(),
            "caption": str(self.caption_input.value or "").strip(),
            **self.cog._parse_price_block(str(self.price_input.value or "")),
        }
        lines = ["Form booking"]
        if fields["name"]:
            lines.append(f"Tên: {fields['name']}")
        if fields["address"]:
            lines.append(f"Địa chỉ: {fields['address']}")
        if fields["receives"]:
            lines.append(f"Nhận những gì: {fields['receives']}")
        if fields["caption"]:
            lines.append(f"Caption: {fields['caption']}")
        if fields["price_game"]:
            lines.append(f"Giá tiền game: {fields['price_game']}")
        if fields["price_sing"]:
            lines.append(f"Giá tiền hát: {fields['price_sing']}")
        if fields["price_cam"]:
            lines.append(f"Giá tiền cam: {fields['price_cam']}")
        return "\n".join(lines)

    async def on_submit(self, interaction: discord.Interaction):
        form_text = self._build_form_text()
        if form_text.strip() == "Form booking":
            await interaction.response.send_message("❌ Form chưa có nội dung nào.", ephemeral=True)
            return

        if self.profile_key is None or self.profile_number is None:
            if interaction.guild is None:
                await interaction.response.send_message("❌ Form chỉ lưu được trong server.", ephemeral=True)
                return
            self.cog.service.save_submitted_form(
                interaction.guild.id,
                interaction.user.id,
                interaction.user.display_name,
                form_text,
            )
            await interaction.response.send_message(
                embed=create_success_splash(
                    "✅ Đã Lưu Form",
                    f"Form của bạn đã được lưu. Admin có thể dùng `ar a ad1 {interaction.user.mention}` để tạo profile từ form này.",
                ),
                ephemeral=True,
            )
            if interaction.channel:
                await interaction.followup.send(
                    embed=create_success_splash(
                        "✅ Form Booking Đã Được Gửi",
                        f"{interaction.user.mention} đã điền form booking.",
                    )
                )
            return

        if not await self.cog.require_role_or_admin_interaction(
            interaction,
            "ar",
            "Chỉ admin hoặc role có quyền `ar` trong DB mới lưu form profile.",
        ):
            return

        assert interaction.guild is not None
        existing = self.cog.service.get_profile(interaction.guild.id, self.profile_key, self.profile_number)
        try:
            if existing:
                self.cog.service.update_profile_field(interaction.guild.id, self.profile_key, self.profile_number, "description", form_text)
                action_text = "Đã cập nhật"
            else:
                self.cog.service.upsert_profile(interaction.guild.id, self.profile_key, self.profile_number, interaction.user.id, form_text)
                action_text = "Đã tạo"
        except ValueError as exc:
            await interaction.response.send_message(f"❌ Lỗi profile: {exc}", ephemeral=True)
            return

        profile = self.cog.service.get_profile(interaction.guild.id, self.profile_key, self.profile_number)
        await interaction.response.send_message(
            embed=create_success_splash("✅ Đã Lưu Form Profile", f"{action_text} `{self.profile_key}{self.profile_number}`."),
        )
        if profile:
            member = None
            if profile.get("assigned_user_id"):
                member = interaction.guild.get_member(profile["assigned_user_id"])
            embed, files = await self.cog._profile_payload(profile, member)
            await interaction.followup.send(embed=embed, files=files)


class BookingFormView(discord.ui.View):
    def __init__(self, cog: "AdministratorResponsiveCog", profile_key: str | None = None, profile_number: int | None = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.profile_key = profile_key
        self.profile_number = profile_number

    @discord.ui.button(label="Điền form", style=discord.ButtonStyle.primary)
    async def fill_form(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BookingFormModal(self.cog, self.profile_key, self.profile_number))


class AdministratorResponsiveCog(AdminCommandBase):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self._service = None

    @property
    def service(self) -> ResponsiveService:
        if self._service is None:
            self._service = ResponsiveService()
        return self._service

    def _can_manage(self, ctx) -> bool:
        return self.can_use_role_or_admin(ctx, "ar")

    async def _require_manage(self, ctx) -> bool:
        if self._can_manage(ctx):
            return True
        await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ admin hoặc role có quyền `ar` trong DB mới chỉnh auto res."))
        return False

    @staticmethod
    def _first_attachment_url(ctx) -> str | None:
        if ctx.message.attachments:
            return ctx.message.attachments[0].url
        return None

    @staticmethod
    def _clean_manual_content(content: str) -> str:
        cleaned = (content or "").strip()
        if cleaned.startswith("|"):
            cleaned = cleaned[1:].strip()
        return cleaned

    @staticmethod
    def _merge_token_into_content(token: str | None, content: str) -> str:
        if token:
            return f"{token} {content}".strip()
        return (content or "").strip()

    @staticmethod
    def _split_key_number(raw_key: str | None) -> tuple[str | None, str | None]:
        if not raw_key:
            return raw_key, None
        key = raw_key.strip()
        index = len(key)
        while index > 0 and key[index - 1].isdigit():
            index -= 1
        if index == len(key) or index == 0:
            return key, None
        return key[:index], key[index:]

    @staticmethod
    def _strip_description_suffix(raw_key: str | None) -> str | None:
        if not raw_key:
            return raw_key
        key = raw_key.strip()
        for suffix in (".description", ".desc", ".des"):
            if key.lower().endswith(suffix):
                return key[: -len(suffix)].strip()
        return key

    @staticmethod
    def _extract_response_text(token: str | None, content: str) -> str:
        raw_text = f"{token or ''} {content or ''}".strip()
        if raw_text.startswith("|"):
            return raw_text[1:].strip()
        if "|" in raw_text:
            return raw_text.split("|", 1)[1].strip()
        return raw_text

    def _normalize_profile_ref(self, key: str | None, number: str | None, content: str = "") -> tuple[str | None, str | None, str]:
        split_key, split_number = self._split_key_number(key)
        if split_number and (not number or not number.isdigit()):
            return split_key, split_number, self._merge_token_into_content(number, content)
        return key, number, content

    async def _reply_text(self, ctx) -> str:
        reference = ctx.message.reference
        if not reference:
            return ""
        resolved = reference.resolved
        if isinstance(resolved, discord.Message):
            return resolved.content.strip()
        if reference.message_id:
            try:
                message = await ctx.channel.fetch_message(reference.message_id)
                return message.content.strip()
            except Exception:
                return ""
        return ""

    async def _resolve_member_from_text(self, ctx, raw_member: str | None) -> discord.Member | None:
        raw_member = (raw_member or "").strip()
        if not raw_member:
            return None
        try:
            return await commands.MemberConverter().convert(ctx, raw_member)
        except Exception:
            return None

    @staticmethod
    def _profile_label(profile: dict) -> str:
        return f"{profile['profile_key']}{profile['profile_number']}"

    @staticmethod
    def _normalize_form_label(label: str) -> str:
        text = label.strip().lower().rstrip(":")
        text = text.replace("đ", "d")
        text = unicodedata.normalize("NFD", text)
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        text = re.sub(r"[^a-z0-9\s]+", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _parse_price_block(self, price_text: str) -> dict:
        prices = {
            "price_game": "",
            "price_sing": "",
            "price_cam": "",
        }
        for raw_item in re.split(r"[\n;]+", price_text or ""):
            item = raw_item.strip()
            if not item or ":" not in item:
                continue
            raw_label, raw_value = item.split(":", 1)
            field_key = PRICE_FIELD_BY_LABEL.get(self._normalize_form_label(raw_label))
            value = raw_value.strip()
            if field_key and value:
                prices[field_key] = value
        return prices

    def _parse_booking_form(self, description: str | None) -> dict | None:
        if not description:
            return None

        fields = {}
        current_field = None
        found_form_field = False
        for raw_line in description.splitlines():
            line = raw_line.strip().strip("*_")
            if not line:
                continue

            normalized_line = self._normalize_form_label(line)
            if normalized_line in {"form booking", "booking form"}:
                found_form_field = True
                current_field = None
                continue

            if ":" in line:
                raw_label, raw_value = line.split(":", 1)
                field_key = FORM_FIELD_BY_LABEL.get(self._normalize_form_label(raw_label))
                if field_key:
                    found_form_field = True
                    current_field = field_key
                    value = raw_value.strip()
                    if value:
                        fields[field_key] = value
                    else:
                        fields.setdefault(field_key, "")
                    continue

            if current_field:
                if fields.get(current_field):
                    fields[current_field] = f"{fields[current_field]}\n{line}"
                else:
                    fields[current_field] = line

        return fields if found_form_field else None

    @staticmethod
    def _escape_markdown_value(value: str) -> str:
        return discord.utils.escape_markdown(value.strip()) if value else ""

    def _format_profile_description(self, raw_description: str | None) -> str:
        form = self._parse_booking_form(raw_description)
        if not form:
            return raw_description or "Chưa có nội dung."

        lines = []
        name = self._escape_markdown_value(form.get("name", ""))
        address = self._escape_markdown_value(form.get("address", ""))
        receives = self._escape_markdown_value(form.get("receives", ""))
        caption = self._escape_markdown_value(form.get("caption", ""))

        if name:
            lines.append(f"**{name}**")
        if address:
            lines.append(f"**{address}**")
        if receives:
            lines.append(receives)
        if caption:
            lines.append(f"_{caption}_")

        price_lines = []
        price_game = self._escape_markdown_value(form.get("price_game", ""))
        price_sing = self._escape_markdown_value(form.get("price_sing", ""))
        price_cam = self._escape_markdown_value(form.get("price_cam", ""))
        if price_game:
            price_lines.append(f"Game: {price_game}")
        if price_sing:
            price_lines.append(f"Hát: {price_sing}")
        if price_cam:
            price_lines.append(f"Cam: {price_cam}")
        if price_lines:
            lines.append("**Giá**")
            lines.extend(price_lines)

        return "\n".join(lines) if lines else "Chưa có nội dung."

    def _profile_title(self, profile: dict, member: discord.Member | None = None) -> str | None:
        if member:
            return member.display_name
        if profile.get("assigned_username"):
            return profile["assigned_username"]
        form = self._parse_booking_form(profile.get("description"))
        if form and form.get("name"):
            return form["name"].strip()
        return None

    @staticmethod
    def _safe_attachment_name(prefix: str) -> str:
        safe_prefix = re.sub(r"[^a-zA-Z0-9_-]+", "_", prefix).strip("_") or "thumbnail"
        return f"{safe_prefix[:60]}_thumb.png"

    async def _square_thumbnail_file(self, image_url: str | None, filename_prefix: str) -> tuple[discord.File | None, str | None]:
        if not image_url or image_url.startswith("attachment://"):
            return None, None
        try:
            from PIL import Image, ImageOps
        except ImportError:
            return None, None

        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(image_url) as response:
                    if response.status != 200:
                        return None, None
                    image_data = await response.read()
        except Exception:
            return None, None

        try:
            with Image.open(io.BytesIO(image_data)) as image:
                image = ImageOps.exif_transpose(image)
                width, height = image.size
                side = min(width, height)
                if side <= 0:
                    return None, None
                left = (width - side) // 2
                top = (height - side) // 2
                cropped = image.crop((left, top, left + side, top + side))
                if side > 512:
                    resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
                    cropped = cropped.resize((512, 512), resampling)
                if cropped.mode not in {"RGB", "RGBA"}:
                    cropped = cropped.convert("RGBA")
                buffer = io.BytesIO()
                cropped.save(buffer, format="PNG")
                buffer.seek(0)
        except Exception:
            return None, None

        filename = self._safe_attachment_name(filename_prefix)
        return discord.File(buffer, filename=filename), f"attachment://{filename}"

    def _build_profile_embed(self, profile: dict, member: discord.Member | None = None) -> discord.Embed:
        color = parse_color(profile.get("color_value") or "") or discord.Color.from_rgb(46, 48, 53)
        title = self._profile_title(profile, member)
        embed = discord.Embed(title=title, description=self._format_profile_description(profile.get("description")), color=color)
        if member:
            embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        elif profile.get("assigned_username"):
            embed.set_author(name=profile["assigned_username"])
        if profile.get("image_url"):
            embed.set_image(url=profile["image_url"])
        if profile.get("thumbnail_url"):
            embed.set_thumbnail(url=profile["thumbnail_url"])
        append_discord_timestamp(embed)
        return embed

    async def _profile_payload(self, profile: dict, member: discord.Member | None = None) -> tuple[discord.Embed, list[discord.File]]:
        embed = self._build_profile_embed(profile, member)
        files = []
        thumbnail_file, thumbnail_url = await self._square_thumbnail_file(
            profile.get("thumbnail_url"),
            f"profile_{self._profile_label(profile)}",
        )
        if thumbnail_file and thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
            files.append(thumbnail_file)
        return embed, files

    def _build_form_embed(self, key: str, profiles: list) -> discord.Embed:
        embed = discord.Embed(
            title=f"Form {key}",
            description=f"Danh sách form/profile cho key `{key}`",
            color=discord.Color.from_rgb(180, 205, 255),
        )
        for profile in profiles[:10]:
            value = profile.get("description") or "Chưa có nội dung."
            assigned = profile.get("assigned_username")
            if assigned:
                value = f"{value}\nGắn với: `{assigned}`"
            embed.add_field(name=self._profile_label(profile), value=value[:1024], inline=False)
        embed.set_footer(text=f"Tổng {len(profiles)} profile")
        return embed

    @staticmethod
    def _build_response_media_embed(response: dict) -> discord.Embed | None:
        if not response.get("image_url") and not response.get("thumbnail_url"):
            return None
        embed = discord.Embed(color=discord.Color.from_rgb(46, 48, 53))
        if response.get("image_url"):
            embed.set_image(url=response["image_url"])
        if response.get("thumbnail_url"):
            embed.set_thumbnail(url=response["thumbnail_url"])
        return embed

    async def _response_media_payload(self, response: dict) -> tuple[discord.Embed | None, list[discord.File]]:
        embed = self._build_response_media_embed(response)
        files = []
        if embed is None:
            return None, files
        thumbnail_file, thumbnail_url = await self._square_thumbnail_file(
            response.get("thumbnail_url"),
            f"res_{response.get('trigger_key') or 'thumbnail'}",
        )
        if thumbnail_file and thumbnail_url:
            embed.set_thumbnail(url=thumbnail_url)
            files.append(thumbnail_file)
        return embed, files

    @staticmethod
    async def _send_payload(channel, *, content: str | None = None, embed: discord.Embed | None = None, files: list[discord.File] | None = None):
        payload = {}
        if content:
            payload["content"] = content
        if embed:
            payload["embed"] = embed
        if files:
            payload["files"] = files
        return await channel.send(**payload)

    def _format_response(self, response: dict, message: discord.Message) -> str:
        target = ""
        if response.get("target_user_id"):
            target = f"<@{response['target_user_id']}>"
        return (
            response["response_text"]
            .replace("{user}", message.author.mention)
            .replace("{author}", message.author.mention)
            .replace("{target}", target)
            .replace("{key}", response["trigger_key"])
        )

    @commands.command(name="ar")
    async def auto_response(self, ctx, action: str = None, key: str = None, maybe_number: str = None, *, content: str = ""):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Responsive chỉ hoạt động trong server."))
            return
        if not action:
            await ctx.send(
                embed=create_info_splash(
                    "Auto Response",
                    (
                        "`ar a <key> | <text>` thêm auto res\n"
                        "`ar a <key>` tạo auto res rỗng để set nội dung sau\n"
                        "`ar a <key> <số>` hoặc `ar a <key><số>` thêm profile/form\n"
                        "`ar e <key> <text>` sửa auto res\n"
                        "`ar e <key> <số> <text>` sửa nội dung profile\n"
                        "`ar r <key> [số]` xóa auto res hoặc profile\n"
                        "`ar set <key> <số> @user` gắn profile\n"
                        "`ar up <key><số> #channel` up profile sang channel\n"
                        "`ar des <key>` lấy nội dung auto res từ reply\n"
                        "`ar description <key> <số>` lấy form từ tin nhắn reply\n"
                        "`ar iurl/turl <key> [số] <url|ảnh>` set ảnh auto res hoặc profile, `turl` tự crop vuông\n"
                        "`ar list <key>` xem profile đã tạo theo key"
                    ),
                )
            )
            return

        action = action.lower().strip()
        if action in {"a", "add"}:
            await self._handle_add(ctx, key, maybe_number, content)
            return
        if action in {"r", "remove", "rm", "d", "delete", "del"}:
            await self._handle_delete(ctx, key, maybe_number)
            return
        if action in {"e", "edit"}:
            await self._handle_edit(ctx, key, maybe_number, content)
            return
        if action in {"description", "desc", "des"}:
            await self._handle_description(ctx, key, maybe_number, content)
            return
        if action in {"color", "mau", "màu"}:
            await self._handle_profile_field(ctx, "color_value", key, maybe_number, content)
            return
        if action == "iurl":
            await self._handle_media_url(ctx, "image_url", key, maybe_number, content)
            return
        if action == "turl":
            await self._handle_media_url(ctx, "thumbnail_url", key, maybe_number, content)
            return
        if action == "set":
            await self._handle_set(ctx, key, maybe_number, content)
            return
        if action == "up":
            await self._handle_up(ctx, key, maybe_number, content)
            return
        if action == "target":
            await self._handle_target(ctx, key, maybe_number)
            return
        if action == "show":
            await self._handle_show(ctx, key)
            return
        if action == "list":
            await self._handle_list(ctx, key)
            return

        await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng `ar` để xem hướng dẫn."))

    @commands.command(name="form")
    async def form(self, ctx, key: str = None):
        if ctx.guild is None:
            return
        await self._send_form_template(ctx, key)

    @commands.command(name="res")
    async def response(self, ctx, key: str = None):
        if ctx.guild is None:
            return
        if not key:
            await ctx.send("❌ Dùng: `res <key>`")
            return
        await self._send_response(ctx.channel, ctx.guild.id, key, ctx.message)

    @commands.command(name="up")
    async def up_profile(self, ctx, key: str = None, maybe_number: str = None, *, content: str = ""):
        if ctx.guild is None:
            return
        await self._handle_up(ctx, key, maybe_number, content)

    async def _handle_add(self, ctx, key: str, maybe_number: str, content: str):
        if not await self._require_manage(ctx):
            return
        split_key, split_number = self._split_key_number(key)
        if split_number and (not maybe_number or not maybe_number.isdigit()):
            key = split_key
            content = self._merge_token_into_content(maybe_number, content)
            maybe_number = split_number
        if not key:
            await ctx.send("❌ Dùng: `ar a <key> | <text>`, `ar a <key>`, hoặc `ar a <key><số>`")
            return
        if maybe_number and maybe_number.isdigit():
            description = content.strip()
            if self.service.get_profile(ctx.guild.id, key, int(maybe_number)):
                await ctx.send(embed=create_error_splash("❌ Profile Đã Tồn Tại", f"`{key}{maybe_number}` đã tồn tại. Dùng `ar e {key} {maybe_number} <nội dung>` hoặc `ar des {key}{maybe_number}` để sửa."))
                return
            assigned_member = await self._resolve_member_from_text(ctx, description)
            if assigned_member:
                submitted_form = self.service.get_submitted_form(ctx.guild.id, assigned_member.id)
                if not submitted_form:
                    await ctx.send(embed=create_error_splash("❌ Chưa Có Form", f"{assigned_member.mention} chưa gửi form bằng `form`."))
                    return
                description = submitted_form["form_text"]
            try:
                self.service.upsert_profile(ctx.guild.id, key, int(maybe_number), ctx.author.id, description)
                if assigned_member:
                    self.service.assign_profile(ctx.guild.id, key, int(maybe_number), assigned_member.id, assigned_member.display_name)
            except ValueError as exc:
                await ctx.send(embed=create_error_splash("❌ Lỗi Profile", str(exc)))
                return
            if assigned_member:
                await ctx.send(embed=create_success_splash("✅ Đã Thêm Profile", f"Đã tạo `{key}{maybe_number}` từ form của {assigned_member.mention} và gắn profile luôn."))
                profile = self.service.get_profile(ctx.guild.id, key, int(maybe_number))
                if profile:
                    embed, files = await self._profile_payload(profile, assigned_member)
                    await self._send_payload(ctx, embed=embed, files=files)
            else:
                await ctx.send(embed=create_success_splash("✅ Đã Thêm Profile", f"Đã tạo `{key}{maybe_number}`."))
            return
        response_text = self._extract_response_text(maybe_number, content)
        if self.service.get_response(ctx.guild.id, key):
            await ctx.send(embed=create_error_splash("❌ Auto Res Đã Tồn Tại", f"`{key}` đã tồn tại. Dùng `ar e {key} <nội dung>` hoặc `ar des {key} | <nội dung>` để sửa."))
            return
        try:
            self.service.upsert_response(ctx.guild.id, key, response_text, ctx.author.id)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Lỗi Auto Res", str(exc)))
            return
        if response_text:
            await ctx.send(embed=create_success_splash("✅ Đã Thêm Auto Res", f"`{key}` sẽ trả lời:\n{response_text}"))
        else:
            await ctx.send(embed=create_success_splash("✅ Đã Tạo Auto Res", f"Đã tạo `{key}`. Dùng `ar des {key} | <nội dung>` để thêm nội dung."))

    async def _handle_delete(self, ctx, key: str, maybe_number: str):
        if not await self._require_manage(ctx):
            return
        split_key, split_number = self._split_key_number(key)
        if split_number and (not maybe_number or not maybe_number.isdigit()):
            key = split_key
            maybe_number = split_number
        if not key:
            await ctx.send("❌ Dùng: `ar r/rm/remove/d/delete <key>` hoặc `ar r/rm/remove/d/delete <key> <số>`")
            return
        if maybe_number and maybe_number.isdigit():
            self.service.delete_profile(ctx.guild.id, key, int(maybe_number))
            await ctx.send(embed=create_success_splash("✅ Đã Xóa Profile", f"Đã xóa `{key}{maybe_number}`."))
            return
        self.service.delete_response(ctx.guild.id, key)
        await ctx.send(embed=create_success_splash("✅ Đã Xóa Auto Res", f"Đã xóa auto res `{key}`."))

    async def _handle_edit(self, ctx, key: str, maybe_number: str, content: str):
        if not await self._require_manage(ctx):
            return
        split_key, split_number = self._split_key_number(key)
        if split_number and (not maybe_number or not maybe_number.isdigit()):
            key = split_key
            content = self._merge_token_into_content(maybe_number, content)
            maybe_number = split_number
        if not key or not maybe_number:
            await ctx.send("❌ Dùng: `ar e <key> <text>` hoặc `ar e <key> <số> <text>`")
            return
        if maybe_number.isdigit():
            if not content.strip():
                await ctx.send("❌ Nội dung profile không được trống.")
                return
            try:
                self.service.update_profile_field(ctx.guild.id, key, int(maybe_number), "description", content.strip())
            except ValueError as exc:
                await ctx.send(embed=create_error_splash("❌ Lỗi Profile", str(exc)))
                return
            await ctx.send(embed=create_success_splash("✅ Đã Sửa Profile", f"Đã sửa nội dung `{key}{maybe_number}`."))
            return
        response_text = f"{maybe_number} {content}".strip()
        try:
            self.service.upsert_response(ctx.guild.id, key, response_text, ctx.author.id)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Lỗi Auto Res", str(exc)))
            return
        await ctx.send(embed=create_success_splash("✅ Đã Sửa Auto Res", f"`{key}` sẽ trả lời:\n{response_text}"))

    async def _handle_description(self, ctx, key: str, number: str, content: str):
        key = self._strip_description_suffix(key)
        split_key, split_number = self._split_key_number(key)
        if split_number and (not number or not number.isdigit()):
            key = split_key
            content = self._merge_token_into_content(number, content)
            number = split_number
        if number and number.isdigit():
            await self._handle_profile_field(ctx, "description", key, number, content)
            return
        await self._handle_response_description(ctx, key, number, content)

    async def _handle_response_description(self, ctx, key: str, token: str, content: str):
        if not await self._require_manage(ctx):
            return
        key = self._strip_description_suffix(key)
        if not key:
            await ctx.send("❌ Dùng: `ar des <res> | <nội dung>` hoặc reply nội dung rồi `ar des <res>`")
            return
        response_text = self._extract_response_text(token, content)
        if not response_text:
            response_text = await self._reply_text(ctx)
        if not response_text:
            await ctx.send("❌ Gửi nội dung sau dấu `|`, hoặc reply tin nhắn nội dung rồi dùng `ar des <res>`.")
            return
        try:
            self.service.upsert_response(ctx.guild.id, key, response_text, ctx.author.id)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Lỗi Auto Res", str(exc)))
            return
        await ctx.send(embed=create_success_splash("✅ Đã Cập Nhật Auto Res", f"`{key}` sẽ trả lời:\n{response_text}"))

    async def _handle_profile_field(self, ctx, field: str, key: str, number: str, content: str):
        if not await self._require_manage(ctx):
            return
        split_key, split_number = self._split_key_number(key)
        if split_number and (not number or not number.isdigit()):
            key = split_key
            content = self._merge_token_into_content(number, content)
            number = split_number
        if not key or not number or not number.isdigit():
            await ctx.send("❌ Dùng: `ar description/color <key> <số> <nội dung>`")
            return

        value = self._clean_manual_content(content)
        if field == "description" and not value:
            value = await self._reply_text(ctx)
        if not value:
            await ctx.send("❌ Gửi nội dung sau lệnh, sau dấu `|`, hoặc reply form đã nhập rồi dùng lại lệnh này.")
            return

        try:
            self.service.update_profile_field(ctx.guild.id, key, int(number), field, value)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Lỗi Profile", str(exc)))
            return
        await ctx.send(embed=create_success_splash("✅ Đã Cập Nhật Profile", f"Đã cập nhật `{key}{number}`."))

    async def _handle_media_url(self, ctx, field: str, key: str, number: str, content: str):
        if not await self._require_manage(ctx):
            return
        split_key, split_number = self._split_key_number(key)
        if split_number and (not number or not number.isdigit()):
            key = split_key
            content = self._merge_token_into_content(number, content)
            number = split_number
        if not key:
            await ctx.send("❌ Dùng: `ar iurl/turl <res> <url>`, `ar iurl/turl <key> <số> <url>` hoặc đính kèm ảnh.")
            return

        is_profile = bool(number and number.isdigit())
        image_url = (content.strip() if is_profile else self._merge_token_into_content(number, content)) or self._first_attachment_url(ctx)
        if not image_url:
            await ctx.send("❌ Bạn cần gửi URL ảnh hoặc đính kèm ảnh.")
            return

        if is_profile:
            try:
                self.service.update_profile_field(ctx.guild.id, key, int(number), field, image_url)
            except ValueError as exc:
                await ctx.send(embed=create_error_splash("❌ Lỗi Profile", str(exc)))
                return
            await ctx.send(embed=create_success_splash("✅ Đã Set Ảnh", f"Đã cập nhật ảnh cho `{key}{number}`."))
            return

        try:
            self.service.update_response_field(ctx.guild.id, key, field, image_url)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Lỗi Auto Res", str(exc)))
            return
        label = "ảnh lớn" if field == "image_url" else "ảnh nhỏ"
        await ctx.send(embed=create_success_splash("✅ Đã Set Ảnh Auto Res", f"Đã cập nhật {label} cho auto res `{key}`."))

    async def _handle_set(self, ctx, key: str, number: str, content: str):
        if not await self._require_manage(ctx):
            return
        key, number, content = self._normalize_profile_ref(key, number, content)
        if not key or not number or not number.isdigit() or not content.strip():
            await ctx.send("❌ Dùng: `ar set <key> <số> @user`")
            return
        try:
            member = await commands.MemberConverter().convert(ctx, content.strip())
        except Exception:
            await ctx.send("❌ Không tìm thấy user để gắn profile.")
            return
        try:
            self.service.assign_profile(ctx.guild.id, key, int(number), member.id, member.display_name)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Lỗi Profile", str(exc)))
            return
        await ctx.send(embed=create_success_splash("✅ Đã Gắn Profile", f"`{key}{number}` đã gắn với {member.mention}."))
        profile = self.service.get_profile(ctx.guild.id, key, int(number))
        if profile:
            embed, files = await self._profile_payload(profile, member)
            await self._send_payload(ctx, embed=embed, files=files)

    async def _resolve_channel(self, ctx, raw_channel: str):
        raw_channel = (raw_channel or "").strip()
        if not raw_channel:
            return None
        try:
            return await commands.TextChannelConverter().convert(ctx, raw_channel)
        except Exception:
            cleaned = raw_channel.strip("<#>")
            if cleaned.isdigit():
                channel = ctx.guild.get_channel(int(cleaned))
                if isinstance(channel, discord.TextChannel):
                    return channel
            return None

    async def _handle_up(self, ctx, key: str, number: str, content: str):
        if not await self._require_manage(ctx):
            return
        key, number, channel_raw = self._normalize_profile_ref(key, number, content)
        if not key or not number or not number.isdigit() or not channel_raw.strip():
            await ctx.send("❌ Dùng: `ar up <key><số> #channel` hoặc `up <key><số> #channel`")
            return
        channel = await self._resolve_channel(ctx, channel_raw)
        if not channel:
            await ctx.send("❌ Không tìm thấy channel để up profile.")
            return
        profile = self.service.get_profile(ctx.guild.id, key, int(number))
        if not profile:
            await ctx.send(embed=create_warning_splash("⚠️ Chưa Có Profile", f"Chưa có profile `{key}{number}`."))
            return
        member = None
        if profile.get("assigned_user_id"):
            member = ctx.guild.get_member(profile["assigned_user_id"])
        try:
            embed, files = await self._profile_payload(profile, member)
            await self._send_payload(channel, embed=embed, files=files)
        except discord.Forbidden:
            await ctx.send("❌ Bot không có quyền gửi tin nhắn vào channel đó.")
            return
        except discord.HTTPException as exc:
            await ctx.send(f"❌ Không up được profile: {exc}")
            return
        await ctx.send(embed=create_success_splash("✅ Đã Up Profile", f"Đã up `{key}{number}` lên {channel.mention}."))

    async def _handle_target(self, ctx, key: str, raw_member: str):
        if not await self._require_manage(ctx):
            return
        if not key or not raw_member:
            await ctx.send("❌ Dùng: `ar target <res|profile> @user`, ví dụ `ar target yang @user` hoặc `ar target ad1 @user`.")
            return
        member = await self._resolve_member_from_text(ctx, raw_member)
        if not member:
            await ctx.send("❌ Không tìm thấy user target.")
            return

        profile_key, profile_number = self._split_key_number(key)
        if profile_key and profile_number is not None:
            profile = self.service.get_profile(ctx.guild.id, profile_key, int(profile_number))
            if profile:
                try:
                    self.service.assign_profile(ctx.guild.id, profile_key, int(profile_number), member.id, member.display_name)
                except ValueError as exc:
                    await ctx.send(embed=create_error_splash("❌ Lỗi Profile", str(exc)))
                    return
                await ctx.send(embed=create_success_splash("✅ Đã Gắn Target", f"`{profile_key}{profile_number}` đã gắn với {member.mention}."))
                updated_profile = self.service.get_profile(ctx.guild.id, profile_key, int(profile_number))
                if updated_profile:
                    embed, files = await self._profile_payload(updated_profile, member)
                    await self._send_payload(ctx, embed=embed, files=files)
                return

        try:
            self.service.set_response_target(ctx.guild.id, key, member.id, member.display_name)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Target Thất Bại", f"{exc}. Nếu muốn gắn profile, hãy dùng đúng mã profile như `ad1` và đảm bảo profile đã tồn tại."))
            return
        await ctx.send(embed=create_success_splash("✅ Đã Gắn Target", f"Auto res `{key}` sẽ dùng target {member.mention}."))

    async def _handle_show(self, ctx, raw_member: str):
        member = ctx.author
        if raw_member:
            try:
                member = await commands.MemberConverter().convert(ctx, raw_member.strip())
            except Exception:
                await ctx.send("❌ Không tìm thấy user.")
                return
        profile = self.service.get_assigned_profile(ctx.guild.id, member.id)
        if not profile:
            await ctx.send(embed=create_warning_splash("⚠️ Chưa Có Profile", f"{member.mention} chưa được gắn responsive profile."))
            return
        embed, files = await self._profile_payload(profile, member)
        await self._send_payload(ctx, embed=embed, files=files)

    async def _handle_list(self, ctx, mode: str):
        if mode and mode.lower() in {"res", "response", "responses"}:
            rows = self.service.list_responses(ctx.guild.id)
            if not rows:
                await ctx.send(embed=create_warning_splash("⚠️ Auto Res", "Chưa có auto res nào."))
                return
            text = "\n".join(f"`{row['trigger_key']}` - {row['response_text'][:80]}" for row in rows[:20])
            await ctx.send(embed=create_info_splash(f"Auto Res ({len(rows)})", text))
            return
        if mode:
            await self._send_form(ctx.channel, ctx.guild.id, mode)
            return
        await ctx.send("Dùng `ar list res` để xem auto res. Dùng `ar list <key>` để xem profile theo key.")

    async def _send_form(self, channel, guild_id: int, key: str):
        profiles = self.service.get_profiles_by_key(guild_id, key)
        if not profiles:
            await channel.send(embed=create_warning_splash("⚠️ Chưa Có Form", f"Chưa có profile/form nào cho key `{key}`."))
            return
        await channel.send(embed=self._build_form_embed(key, profiles))

    async def _send_form_template(self, ctx, key: str | None = None):
        prefix = get_prefix(ctx.guild.id if ctx.guild else None)
        title = "Form booking"
        profile_key = None
        profile_number = None
        if key:
            title = f"Form booking cho `{key}`"
            split_key, split_number = self._split_key_number(key)
            if split_key and split_number is not None:
                profile_key = split_key
                profile_number = int(split_number)
        embed = discord.Embed(
            title=title,
            description=FORM_TEMPLATE,
            color=discord.Color.from_rgb(180, 205, 255),
        )
        embed.add_field(
            name="Cách lưu vào profile",
            value=(
                f"1. Tạo profile: `{prefix}ar a <key> <số>`\n"
                f"2. Reply form đã điền: `{prefix}ar description <key> <số>` hoặc `{prefix}ar description <key><số>`\n"
                f"3. Hoặc nhập tay: `{prefix}ar description <key> <số> | <form đã nhập>`"
            ),
            inline=False,
        )
        if profile_key is not None and profile_number is not None:
            embed.add_field(
                name="Lưu nhanh",
                value=f"Bấm **Điền form** để lưu trực tiếp vào `{profile_key}{profile_number}`.",
                inline=False,
            )
        else:
            embed.add_field(
                name="Điền bằng ô",
                value="Bấm **Điền form** để mở các ô nhập, bot sẽ trả form đã điền cho bạn.",
                inline=False,
            )
        await ctx.send(embed=embed, view=BookingFormView(self, profile_key, profile_number))

    async def _send_response(self, channel, guild_id: int, key: str, message: discord.Message) -> bool:
        response = self.service.get_response(guild_id, key)
        if not response:
            return False
        response_text = self._format_response(response, message).strip()
        response_embed, response_files = await self._response_media_payload(response)
        if not response_text and response_embed is None:
            return False
        await self._send_payload(channel, content=response_text or None, embed=response_embed, files=response_files)
        return True

    async def _send_profile_by_label(self, message: discord.Message, label: str) -> bool:
        key, number = self._split_key_number(label)
        if not key or number is None:
            return False
        profile = self.service.get_profile(message.guild.id, key, int(number))
        if not profile:
            return False
        member = None
        if profile.get("assigned_user_id"):
            member = message.guild.get_member(profile["assigned_user_id"])
        embed, files = await self._profile_payload(profile, member)
        await self._send_payload(message.channel, embed=embed, files=files)
        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return

        content = message.content.strip()
        if not content:
            return

        prefix = get_prefix(message.guild.id)
        lowered = content.lower()
        if match_case_insensitive_prefix(content, prefix):
            invoked = content[len(prefix):].strip().split(maxsplit=1)[0].lower()
            if invoked.startswith("form") and len(invoked) > len("form"):
                key = invoked[len("form"):]
                class _ProxyContext:
                    def __init__(self, source: discord.Message):
                        self.message = source
                        self.channel = source.channel
                        self.guild = source.guild
                        self.author = source.author

                    async def send(self, *args, **kwargs):
                        return await self.channel.send(*args, **kwargs)

                await self._send_form_template(_ProxyContext(message), key)
            return

        if await self._send_profile_by_label(message, lowered):
            return

        await self._send_response(message.channel, message.guild.id, lowered, message)


async def setup(bot):
    await bot.add_cog(AdministratorResponsiveCog(bot))
