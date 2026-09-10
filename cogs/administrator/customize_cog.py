import asyncio
import io

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, UnidentifiedImageError

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_error_splash,
    create_info_splash,
    create_success_splash,
    create_warning_splash,
    parse_color,
)
from ui.administrator.steal_ui import (
    build_steal_error_embed,
    build_steal_help_embed,
    build_steal_success_embed,
    parse_steal_source,
    validate_emoji_name,
)


MAX_EMOJI_BYTES = 256 * 1024
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


class AdministratorCustomizeCog(AdminCommandBase):
    @staticmethod
    async def _download_emoji_image(url: str) -> bytes:
        timeout = aiohttp.ClientTimeout(total=15)
        headers = {"User-Agent": "Bleck-Lous-Discord-Bot/1.0"}
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, allow_redirects=True, max_redirects=3) as response:
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if content_type and content_type not in IMAGE_CONTENT_TYPES:
                    raise ValueError("URL không trả về file ảnh PNG, JPG, GIF hoặc WEBP.")
                content_length = int(response.headers.get("Content-Length") or 0)
                if content_length > MAX_EMOJI_BYTES:
                    raise ValueError("Ảnh emoji vượt quá giới hạn 256 KB của Discord.")
                image = bytearray()
                async for chunk in response.content.iter_chunked(32 * 1024):
                    image.extend(chunk)
                    if len(image) > MAX_EMOJI_BYTES:
                        raise ValueError("Ảnh emoji vượt quá giới hạn 256 KB của Discord.")
                if not image:
                    raise ValueError("Không tải được dữ liệu ảnh.")
                image_bytes = bytes(image)
                try:
                    with Image.open(io.BytesIO(image_bytes)) as opened:
                        opened.verify()
                except (UnidentifiedImageError, OSError) as exc:
                    raise ValueError("Dữ liệu tải về không phải ảnh hợp lệ.") from exc
                return image_bytes

    @staticmethod
    def _bot_can_manage_emojis(guild: discord.Guild) -> bool:
        member = guild.me
        return bool(member and member.guild_permissions.manage_emojis_and_stickers)

    async def _create_stolen_emoji(
        self,
        guild: discord.Guild,
        source_text: str,
        requested_name: str,
        actor: discord.abc.User,
    ) -> discord.Emoji:
        if not self._bot_can_manage_emojis(guild):
            raise PermissionError("Bot thiếu quyền **Quản lý Biểu cảm** trong server.")
        source = parse_steal_source(source_text, requested_name)
        emoji_name = validate_emoji_name(source.name)
        image_bytes = await self._download_emoji_image(source.url)
        return await guild.create_custom_emoji(
            name=emoji_name,
            image=image_bytes,
            reason=f"Steal emoji bởi {actor} ({actor.id})",
        )

    @commands.command(name="color")
    async def color(self, ctx, role: discord.Role, color_value: str):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        color = parse_color(color_value)
        if color is None:
            await ctx.send(embed=create_error_splash("❌ Màu Không Hợp Lệ", "Dùng tên màu cơ bản hoặc mã hex như `#ff00ff`."))
            return
        try:
            await role.edit(color=color, reason=f"Đổi màu bởi {ctx.author}")
            await ctx.send(embed=create_success_splash("✅ Đổi Màu Thành Công", f"Role {role.mention} đã được đổi màu."))
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Đổi Màu Thất Bại", str(exc)))

    @commands.command(name="emoji")
    async def emoji(self, ctx, action: str = None, arg1: str = None, *, rest: str = ""):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        if not action:
            await ctx.send(embed=create_info_splash("😊 Emoji", "Dùng:\n`emoji a/add <name> <url>`\n`emoji r/rm/remove/d/delete <name|id>`\n`emoji list [limit]`"))
            return

        action = action.lower().strip()
        if action in {"a", "add"}:
            if not arg1:
                await ctx.send(embed=create_error_splash("❌ Thiếu Tên Emoji", "Dùng: `emoji a/add <name> <url>`"))
                return
            source = rest.strip() or (ctx.message.attachments[0].url if ctx.message.attachments else "")
            if not source:
                await ctx.send(embed=create_error_splash("❌ Thiếu Nguồn Ảnh", "Gửi URL ảnh hoặc đính kèm file ảnh."))
                return
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(source) as response:
                        response.raise_for_status()
                        image_bytes = await response.read()
                emoji = await ctx.guild.create_custom_emoji(name=arg1, image=image_bytes, reason=f"Emoji bởi {ctx.author}")
                await ctx.send(embed=create_success_splash("✅ Thêm Emoji Thành Công", f"Đã tạo emoji {emoji}"))
            except Exception as exc:
                await ctx.send(embed=create_error_splash("❌ Thêm Emoji Thất Bại", str(exc)))
            return

        if action in {"r", "remove", "rm", "d", "delete", "del"}:
            target = arg1 or rest.strip()
            if not target:
                await ctx.send(embed=create_error_splash("❌ Thiếu Emoji", "Dùng: `emoji r/rm/remove/d/delete <name|id>`"))
                return
            found = discord.utils.get(ctx.guild.emojis, name=target)
            if found is None and target.isdigit():
                found = discord.utils.get(ctx.guild.emojis, id=int(target))
            if found is None:
                await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy Emoji", f"Không có emoji `{target}` trong server."))
                return
            try:
                await found.delete(reason=f"Emoji bị xoá bởi {ctx.author}")
                await ctx.send(embed=create_success_splash("✅ Xoá Emoji Thành Công", f"Đã xoá emoji `{found.name}`"))
            except Exception as exc:
                await ctx.send(embed=create_error_splash("❌ Xoá Emoji Thất Bại", str(exc)))
            return

        if action == "list":
            try:
                limit = int(arg1 or rest.strip() or 20)
            except ValueError:
                limit = 20
            emojis = list(ctx.guild.emojis)[:limit]
            if not emojis:
                await ctx.send(embed=create_warning_splash("⚠️ Emoji", "Server chưa có emoji custom nào."))
                return
            text = "\n".join(f"• {emoji} - `{emoji.name}`" for emoji in emojis)
            await ctx.send(embed=create_info_splash(f"😊 Emoji ({len(emojis)})", text))
            return

        await ctx.send(embed=create_error_splash("❌ Lệnh Không Hợp Lệ", "Dùng: `emoji a/add`, `emoji r/rm/remove/d/delete` hoặc `emoji list`"))

    @commands.command(name="steal")
    async def steal(self, ctx, source: str = None, *, name: str = ""):
        if ctx.guild is None:
            await ctx.send(embed=build_steal_error_embed("Lệnh này chỉ dùng trong server."))
            return
        if not await self.require_role_or_admin_ctx(ctx, "steal"):
            return

        attachment = ctx.message.attachments[0] if ctx.message.attachments else None
        if attachment and not source:
            await ctx.send(embed=build_steal_help_embed(ctx.clean_prefix))
            return
        if attachment:
            requested_name = name.strip() or str(source or "").strip()
            source_text = attachment.url
        else:
            source_text = str(source or "").strip()
            requested_name = name.strip()
        if not source_text:
            await ctx.send(embed=build_steal_help_embed(ctx.clean_prefix))
            return

        try:
            async with ctx.typing():
                emoji = await self._create_stolen_emoji(
                    ctx.guild,
                    source_text,
                    requested_name,
                    ctx.author,
                )
        except PermissionError as exc:
            await ctx.send(embed=build_steal_error_embed(str(exc)))
        except (ValueError, aiohttp.ClientError, aiohttp.InvalidURL, asyncio.TimeoutError) as exc:
            await ctx.send(embed=build_steal_error_embed(str(exc)))
        except discord.Forbidden:
            await ctx.send(embed=build_steal_error_embed("Discord từ chối tạo emoji. Hãy kiểm tra quyền của bot."))
        except discord.HTTPException as exc:
            await ctx.send(embed=build_steal_error_embed(f"Discord không tạo được emoji: {exc}"))
        else:
            await ctx.send(embed=build_steal_success_embed(emoji))

    @app_commands.command(name="steal", description="Thêm một emoji vào server này")
    @app_commands.describe(
        emoji="Custom emoji hoặc URL tới ảnh",
        name="Tên mới; không bắt buộc khi dùng custom emoji",
    )
    async def slash_steal(
        self,
        interaction: discord.Interaction,
        emoji: str,
        name: str = "",
    ):
        if interaction.guild is None:
            await interaction.response.send_message(
                embed=build_steal_error_embed("Lệnh này chỉ dùng trong server."),
                ephemeral=True,
            )
            return
        if not await self.require_role_or_admin_interaction(interaction, "steal"):
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            created = await self._create_stolen_emoji(
                interaction.guild,
                emoji,
                name,
                interaction.user,
            )
        except PermissionError as exc:
            embed = build_steal_error_embed(str(exc))
        except (ValueError, aiohttp.ClientError, aiohttp.InvalidURL, asyncio.TimeoutError) as exc:
            embed = build_steal_error_embed(str(exc))
        except discord.Forbidden:
            embed = build_steal_error_embed("Discord từ chối tạo emoji. Hãy kiểm tra quyền của bot.")
        except discord.HTTPException as exc:
            embed = build_steal_error_embed(f"Discord không tạo được emoji: {exc}")
        else:
            embed = build_steal_success_embed(created)
        await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdministratorCustomizeCog(bot))
