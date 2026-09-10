import asyncio

import discord
from discord.ext import commands

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_error_splash,
    create_success_splash,
    format_duration_seconds,
    parse_duration,
    split_reason,
)


class AdministratorBanCog(AdminCommandBase):
    @staticmethod
    def _split_target_and_rest(content: str | None) -> tuple[str | None, str]:
        content = (content or "").strip()
        if not content:
            return None, ""
        parts = content.split(maxsplit=1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    @staticmethod
    def _split_duration_and_reason(content: str) -> tuple[int | None, str]:
        content = (content or "").strip()
        if not content:
            return None, ""
        parts = content.split(maxsplit=1)
        duration_seconds = parse_duration(parts[0])
        if duration_seconds is None:
            return None, content
        return duration_seconds, parts[1] if len(parts) > 1 else ""

    async def _resolve_ban_target(self, ctx, raw_target: str | None):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh ban chỉ hoạt động trong server."))
            return None
        if not raw_target:
            await ctx.send(embed=create_error_splash("❌ Thiếu User", "Dùng: `ban @user|username|id [time] [reason]`."))
            return None

        member = await self.resolve_member_target(ctx, raw_target)
        if member:
            return member

        user_id = self.extract_user_id(raw_target)
        if user_id is not None:
            try:
                return await self.bot.fetch_user(user_id)
            except (discord.NotFound, discord.HTTPException):
                return discord.Object(id=user_id)

        await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy User", f"Không tìm thấy `{raw_target}` trong server. Nếu muốn ban bằng ID, hãy nhập user ID."))
        return None

    async def _ensure_bot_can_act_on_member(self, ctx, member: discord.Member, action_name: str) -> bool:
        if member == ctx.guild.owner:
            await ctx.send(embed=create_error_splash("❌ Không Thể Thao Tác", f"Không thể {action_name} owner của server."))
            return False
        me = ctx.guild.me
        if me is None:
            await ctx.send(embed=create_error_splash("❌ Lỗi Bot", "Không lấy được thông tin role của bot trong server."))
            return False
        if member.top_role >= me.top_role:
            await ctx.send(
                embed=create_error_splash(
                    "❌ Sai Thứ Tự Role",
                    f"Bot chỉ có thể {action_name} user có role thấp hơn role cao nhất của bot.",
                )
            )
            return False
        return True

    async def _send_user_notice(self, target, title: str, description: str):
        if not isinstance(target, (discord.Member, discord.User)):
            return False
        try:
            await target.send(embed=create_success_splash(title, description))
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def _auto_unban_later(self, guild_id: int, user_id: int, duration_seconds: int):
        await asyncio.sleep(duration_seconds)
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return
        try:
            await guild.unban(
                discord.Object(id=user_id),
                reason=f"Tự động unban sau {format_duration_seconds(duration_seconds)}",
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            await user.send(
                embed=create_success_splash(
                    "✅ Đã Hết Thời Gian Ban",
                    f"Bạn đã được tự động unban khỏi **{guild.name}** sau `{format_duration_seconds(duration_seconds)}`.",
                )
            )
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

    @commands.command(name="ban")
    async def ban(self, ctx, *, content: str = None):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        raw_target, rest = self._split_target_and_rest(content)
        target = await self._resolve_ban_target(ctx, raw_target)
        if target is None:
            return
        if isinstance(target, discord.Member) and not await self._ensure_bot_can_act_on_member(ctx, target, "ban"):
            return

        duration_seconds, reason = self._split_duration_and_reason(rest)
        reason_text = split_reason(reason)
        target_label = target.mention if isinstance(target, discord.Member) else f"`{target.id}`"
        try:
            dm_lines = [f"Bạn đã bị ban khỏi **{ctx.guild.name}**."]
            if duration_seconds is not None:
                dm_lines.append(f"Thời gian: `{format_duration_seconds(duration_seconds)}`")
            dm_lines.append(f"Lý do: {reason_text}")
            await self._send_user_notice(target, "⛔ Bạn Đã Bị Ban", "\n".join(dm_lines))
            await ctx.guild.ban(target, reason=reason_text, delete_message_seconds=0)
            description = f"Đã ban {target_label}."
            if duration_seconds is not None:
                duration_text = format_duration_seconds(duration_seconds)
                description += f"\nThời gian: `{duration_text}`"
                self.bot.loop.create_task(self._auto_unban_later(ctx.guild.id, target.id, duration_seconds))
            if reason_text != "Không có lý do":
                description += f"\nLý do: {reason_text}"
            await ctx.send(embed=create_success_splash("✅ Ban Thành Công", description))
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Ban Thất Bại", str(exc)))

    @commands.command(name="kick")
    async def kick(self, ctx, *, content: str = None):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        raw_target, reason = self._split_target_and_rest(content)
        if not raw_target:
            await ctx.send(embed=create_error_splash("❌ Thiếu User", "Dùng: `kick @user|username|id [reason]`."))
            return
        member = await self.resolve_member_target(ctx, raw_target)
        if member is None:
            await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy User", f"Không tìm thấy `{raw_target or ''}` trong server. Kick chỉ dùng được với member đang ở server."))
            return
        if not await self._ensure_bot_can_act_on_member(ctx, member, "kick"):
            return
        reason_text = split_reason(reason)
        try:
            await self._send_user_notice(
                member,
                "👢 Bạn Đã Bị Kick",
                f"Bạn đã bị kick khỏi **{ctx.guild.name}**.\nLý do: {reason_text}",
            )
            await member.kick(reason=reason_text)
            description = f"Đã kick {member.mention}."
            if reason_text != "Không có lý do":
                description += f"\nLý do: {reason_text}"
            await ctx.send(embed=create_success_splash("✅ Kick Thành Công", description))
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Kick Thất Bại", str(exc)))

    @commands.command(name="unban")
    async def unban(self, ctx, raw_target: str = None, *, reason: str = "Không có lý do"):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        user_id = self.extract_user_id(raw_target)
        if user_id is None:
            await ctx.send(embed=create_error_splash("❌ Thiếu User ID", "Dùng: `unban <user_id> [reason]`."))
            return
        reason_text = split_reason(reason)
        try:
            await ctx.guild.unban(discord.Object(id=user_id), reason=reason_text)
            try:
                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                await user.send(
                    embed=create_success_splash(
                        "✅ Bạn Đã Được Unban",
                        f"Bạn đã được unban khỏi **{ctx.guild.name}**.\nLý do: {reason_text}",
                    )
                )
            except (discord.Forbidden, discord.NotFound, discord.HTTPException):
                pass
            await ctx.send(embed=create_success_splash("✅ Unban Thành Công", f"Đã unban user ID `{user_id}`."))
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Unban Thất Bại", str(exc)))


async def setup(bot):
    await bot.add_cog(AdministratorBanCog(bot))
