import asyncio
from datetime import datetime, timedelta, timezone

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


class AdministratorMuteCog(AdminCommandBase):
    def __init__(self, bot):
        super().__init__(bot)
        self._mute_notice_tasks: dict[tuple[int, int], asyncio.Task] = {}

    def cog_unload(self):
        for task in self._mute_notice_tasks.values():
            task.cancel()
        self._mute_notice_tasks.clear()

    @staticmethod
    def _split_target_and_rest(content: str | None) -> tuple[str | None, str]:
        content = (content or "").strip()
        if not content:
            return None, ""
        parts = content.split(maxsplit=1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    @staticmethod
    def _split_duration_and_reason(content: str) -> tuple[int, str]:
        content = (content or "").strip()
        if not content:
            return 3600, ""
        parts = content.split(maxsplit=1)
        duration_seconds = parse_duration(parts[0])
        if duration_seconds is None:
            return 3600, content
        return duration_seconds, parts[1] if len(parts) > 1 else ""

    async def _send_user_notice(self, member: discord.Member, title: str, description: str):
        try:
            await member.send(embed=create_success_splash(title, description))
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    def _schedule_unmute_notice(self, member: discord.Member, duration_seconds: int):
        key = (member.guild.id, member.id)
        old_task = self._mute_notice_tasks.pop(key, None)
        if old_task:
            old_task.cancel()

        async def runner():
            try:
                await discord.utils.sleep_until(datetime.now(timezone.utc) + timedelta(seconds=duration_seconds))
                await self._send_user_notice(
                    member,
                    "✅ Đã Hết Thời Gian Mute",
                    f"Bạn đã hết thời gian mute tại **{member.guild.name}**.",
                )
            except Exception:
                pass
            finally:
                self._mute_notice_tasks.pop(key, None)

        self._mute_notice_tasks[key] = self.bot.loop.create_task(runner())

    @commands.command(name="mute")
    async def mute(self, ctx, *, content: str = None):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        raw_target, rest = self._split_target_and_rest(content)
        if not raw_target:
            await ctx.send(embed=create_error_splash("❌ Thiếu User", "Dùng: `mute @user|username|id [duration] [reason]`."))
            return
        member = await self.resolve_member_target(ctx, raw_target)
        if member is None:
            await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy User", f"Không tìm thấy `{raw_target or ''}` trong server. Mute chỉ dùng được với member đang ở server."))
            return
        duration_seconds, reason = self._split_duration_and_reason(rest)
        timeout_until = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        reason_text = split_reason(reason)
        try:
            await member.edit(timed_out_until=timeout_until, reason=reason_text)
            await self._send_user_notice(
                member,
                "🔇 Bạn Đã Bị Mute",
                (
                    f"Bạn đã bị mute tại **{ctx.guild.name}** trong `{format_duration_seconds(duration_seconds)}`.\n"
                    f"Lý do: {reason_text}"
                ),
            )
            self._schedule_unmute_notice(member, duration_seconds)
            description = f"Đã mute {member.mention} trong `{format_duration_seconds(duration_seconds)}`."
            if reason_text != "Không có lý do":
                description += f"\nLý do: {reason_text}"
            await ctx.send(embed=create_success_splash("✅ Mute Thành Công", description))
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Mute Thất Bại", str(exc)))

    @commands.command(name="unmute")
    async def unmute(self, ctx, *, content: str = None):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        raw_target, reason = self._split_target_and_rest(content)
        if not raw_target:
            await ctx.send(embed=create_error_splash("❌ Thiếu User", "Dùng: `unmute @user|username|id [reason]`."))
            return
        member = await self.resolve_member_target(ctx, raw_target)
        if member is None:
            await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy User", f"Không tìm thấy `{raw_target or ''}` trong server."))
            return
        reason_text = split_reason(reason)
        try:
            await member.edit(timed_out_until=None, reason=reason_text)
            task = self._mute_notice_tasks.pop((member.guild.id, member.id), None)
            if task:
                task.cancel()
            await self._send_user_notice(
                member,
                "✅ Bạn Đã Được Gỡ Mute",
                f"Bạn đã được gỡ mute tại **{ctx.guild.name}**.\nLý do: {reason_text}",
            )
            await ctx.send(embed=create_success_splash("✅ Unmute Thành Công", f"Đã gỡ mute cho {member.mention}."))
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Unmute Thất Bại", str(exc)))


async def setup(bot):
    await bot.add_cog(AdministratorMuteCog(bot))
