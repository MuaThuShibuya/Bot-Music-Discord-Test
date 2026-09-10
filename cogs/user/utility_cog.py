from __future__ import annotations

import random
import re

import discord
from discord.ext import commands

from services.admin_service import AdminService
from services.afk_service import AfkService
from services.role_permission_service import RolePermissionService
from services.system_stats_service import (
    collect_system_stats,
    format_bytes,
    format_duration,
    format_usage,
)
from utils import get_prefix, match_case_insensitive_prefix


class UserUtilityCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.afk_service = AfkService()
        self.admin_service = AdminService()
        self.role_permissions = RolePermissionService()

    def cog_unload(self):
        self.afk_service.close()

    @staticmethod
    def _pick_options(raw: str) -> list[str]:
        if not raw or not raw.strip():
            return []
        separator = r"\s*,\s*" if "," in raw else r"\s+"
        return [item.strip() for item in re.split(separator, raw.strip()) if item.strip()]

    @commands.command(name="afk")
    @commands.guild_only()
    async def afk(self, ctx: commands.Context, *, reason: str = "AFK"):
        reason = reason.strip() or "AFK"
        if len(reason) > 300:
            await ctx.reply("❌ Lý do AFK tối đa 300 ký tự.", mention_author=False)
            return
        status = self.afk_service.set_afk(ctx.guild.id, ctx.author.id, reason)
        if status is None:
            await ctx.reply("❌ Không thể lưu trạng thái AFK lúc này.", mention_author=False)
            return
        await ctx.reply(
            f"||{ctx.author.display_name}|| is AFK: {reason} - <t:{status['started_at']}:R>",
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @commands.command(name="random", aliases=["rand", "rd"])
    async def random_number(self, ctx: commands.Context, *, content: str = ""):
        parts = content.strip().split()
        if parts and parts[0].lower() == "set":
            if ctx.guild is not None:
                await ctx.reply("❌ Lệnh `random set` chỉ dùng trong DM với bot.", mention_author=False)
                return
            if not self.admin_service.is_hard_admin(ctx.author.id):
                await ctx.reply("❌ Chỉ hard admin mới dùng được lệnh này.", mention_author=False)
                return
            if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
                await ctx.reply("❌ Dùng trong DM: `random set <user_id> <số>`.", mention_author=False)
                return
            user_id = int(parts[1])
            result = int(parts[2])
            if result < 1:
                await ctx.reply("❌ Kết quả chỉ định phải từ 1 trở lên.", mention_author=False)
                return
            if not self.afk_service.set_random_override(user_id, result, ctx.author.id):
                await ctx.reply("❌ Không thể lưu kết quả chỉ định.", mention_author=False)
                return
            await ctx.reply(
                f"✅ Đã đặt kết quả kế tiếp của user `{user_id}` thành `{result:,}`. Thiết lập dùng một lần.",
                mention_author=False,
            )
            return

        if len(parts) != 1 or not parts[0].isdigit():
            await ctx.reply("❌ Dùng: `random <số lớn nhất>`.", mention_author=False)
            return
        maximum = int(parts[0])
        if maximum < 1:
            await ctx.reply("❌ Số lớn nhất phải từ 1 trở lên.", mention_author=False)
            return
        override = self.afk_service.get_random_override(ctx.author.id)
        if override:
            result = int(override["result"])
            if result > maximum:
                await ctx.reply(
                    f"❌ Kết quả được chỉ định là `{result:,}` nhưng phạm vi hiện tại chỉ từ 1-{maximum:,}. Hãy dùng lại với số lớn nhất từ {result:,} trở lên.",
                    mention_author=False,
                )
                return
            self.afk_service.remove_random_override(ctx.author.id)
        else:
            result = random.randint(1, maximum)
        await ctx.reply(
            f"✅ | Số ngẫu nhiên từ **1-{maximum:,}** là **{result:,}**.",
            mention_author=False,
        )

    @commands.command(name="pick", aliases=["choose", "chon", "chọn"])
    async def pick(self, ctx: commands.Context, *, choices: str = ""):
        options = self._pick_options(choices)
        if not options:
            await ctx.reply("❌ Dùng: `pick lựa chọn 1, lựa chọn 2, lựa chọn 3`.", mention_author=False)
            return
        selected = random.choice(options)
        await ctx.reply(f"✅ | Mình chọn **{selected}**, còn bạn?", mention_author=False)

    @commands.command(name="uptime", aliases=["upt", "system", "sys", "stats", "st"])
    async def uptime(self, ctx: commands.Context):
        stats = collect_system_stats()
        embed = discord.Embed(
            title="Trạng thái hệ thống",
            color=discord.Color.from_rgb(46, 48, 53),
        )
        embed.add_field(
            name="Bot đã chạy",
            value=f"`{format_duration(stats.bot_uptime_seconds)}`",
            inline=False,
        )
        embed.add_field(
            name="VPS đã chạy",
            value=f"`{format_duration(stats.vps_uptime_seconds)}`",
            inline=False,
        )
        embed.add_field(
            name="RAM VPS",
            value=f"`{format_usage(stats.ram_used_bytes, stats.ram_total_bytes)}`",
            inline=False,
        )
        embed.add_field(
            name="Memory của bot",
            value=f"`{format_bytes(stats.process_memory_bytes)}`",
            inline=False,
        )
        embed.add_field(
            name="Dung lượng ổ đĩa",
            value=(
                f"`{format_usage(stats.disk_used_bytes, stats.disk_total_bytes)}`\n"
                f"Còn trống: `{format_bytes(stats.disk_free_bytes)}`"
            ),
            inline=False,
        )
        embed.set_footer(text=f"Ping Discord: {round(self.bot.latency * 1000)} ms")
        await ctx.reply(embed=embed, mention_author=False)

    @commands.command(name="setname", aliases=["setnick", "nickname"])
    @commands.guild_only()
    async def setname(self, ctx: commands.Context, *, content: str = ""):
        raw = content.strip()
        member = ctx.author
        new_name = raw
        target_match = re.match(r"^<@!?(\d+)>\s*(.*)$", raw, flags=re.DOTALL)
        if target_match:
            member = ctx.guild.get_member(int(target_match.group(1)))
            if member is None:
                await ctx.reply("❌ Không tìm thấy user được tag trong server.", mention_author=False)
                return
            new_name = target_match.group(2).strip()

        if member.id != ctx.author.id:
            role_ids = [role.id for role in ctx.author.roles if role.name != "@everyone"]
            can_manage_others = self.admin_service.is_hard_admin(
                ctx.author.id
            ) or self.role_permissions.user_can_use(ctx.guild.id, role_ids, "setname")
            if not can_manage_others:
                await ctx.reply(
                    "❌ Chỉ hard admin hoặc role có quyền `setname` trong DB mới đổi tên người khác.",
                    mention_author=False,
                )
                return

        if not new_name:
            await ctx.reply(
                "❌ Dùng: `setname <tên mới>` hoặc `setname @user <tên mới>`.",
                mention_author=False,
            )
            return
        if len(new_name) > 32:
            await ctx.reply("❌ Nickname Discord tối đa 32 ký tự.", mention_author=False)
            return
        old_name = member.display_name
        try:
            await member.edit(
                nick=new_name,
                reason=f"setname bởi {ctx.author} ({ctx.author.id})",
            )
        except discord.Forbidden:
            await ctx.reply(
                "❌ Bot không thể đổi tên user này. Hãy kiểm tra quyền Manage Nicknames và thứ tự role của bot.",
                mention_author=False,
            )
            return
        except discord.HTTPException as exc:
            await ctx.reply(f"❌ Đổi tên thất bại: {exc}", mention_author=False)
            return
        await ctx.reply(
            f"✅ Đã đổi tên {member.mention} từ `{old_name}` thành `{new_name}`.",
            mention_author=False,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return

        prefix = get_prefix(message.guild.id)
        content = message.content.strip()
        invoked = ""
        if match_case_insensitive_prefix(content, prefix):
            invoked = content[len(prefix):].strip().split(maxsplit=1)[0].lower()

        author_status = self.afk_service.get_afk(message.guild.id, message.author.id)
        if author_status and invoked != "afk":
            self.afk_service.remove_afk(message.guild.id, message.author.id)
            await message.reply(
                f"Chào mừng ||{message.author.display_name}|| trở lại, AFK đã được gỡ.",
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )

        notices = []
        seen_ids = set()
        for member in message.mentions:
            if member.id == message.author.id or member.id in seen_ids:
                continue
            seen_ids.add(member.id)
            status = self.afk_service.get_afk(message.guild.id, member.id)
            if status:
                notices.append(
                    f"||{member.display_name}|| is AFK: {status['reason']} - <t:{status['started_at']}:R>"
                )

        if notices:
            await message.reply(
                "\n".join(notices),
                mention_author=False,
                allowed_mentions=discord.AllowedMentions.none(),
            )


async def setup(bot: commands.Bot):
    await bot.add_cog(UserUtilityCog(bot))
