"""
Shared helpers for administrator command cogs.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

import discord
from discord.ext import commands

from services.admin_service import AdminService
from services.guild_settings_service import GuildSettingsService
from services.role_permission_service import RolePermissionService, normalize_permission_key
from services.settings_service import SettingsService
from services.user_service import UserService
from utils import (
    create_error_splash,
    create_info_splash,
    create_success_splash,
    create_warning_splash,
)


def format_vnd(amount: int) -> str:
    return f"{int(amount):,}"


def _normalize_decimal_text(value: str, suffix: str | None) -> str:
    if "," in value and "." in value:
        if value.rfind(",") > value.rfind("."):
            return value.replace(".", "").replace(",", ".")
        return value.replace(",", "")

    if "," in value:
        parts = value.split(",")
        if len(parts) > 2:
            return value.replace(",", "")
        if suffix or len(parts[1]) <= 2:
            return value.replace(",", ".")
        if len(parts[1]) == 3:
            return value.replace(",", "")
        return value.replace(",", ".")

    if "." in value:
        parts = value.split(".")
        if len(parts) > 2:
            return value.replace(".", "")
        if suffix or len(parts[1]) != 3:
            return value
        return value.replace(".", "")

    return value


def parse_vnd_amount(raw_amount: str | int | float) -> int:
    """Parse VND text like 100k, 1m, 1b, 100.000, 100,000 or 0,5m."""
    if isinstance(raw_amount, (int, float)):
        amount = Decimal(str(raw_amount))
    else:
        cleaned = str(raw_amount).strip().lower()
        cleaned = (
            cleaned.replace("vnđ", "")
            .replace("vnd", "")
            .replace("đ", "")
            .replace("d", "")
            .replace("_", "")
            .replace(" ", "")
        )
        if not cleaned:
            raise ValueError("Số tiền không được để trống")

        suffix = cleaned[-1] if cleaned[-1] in {"k", "m", "b"} else None
        multiplier = {
            "k": Decimal("1000"),
            "m": Decimal("1000000"),
            "b": Decimal("1000000000"),
            None: Decimal("1"),
        }[suffix]
        number_text = cleaned[:-1] if suffix else cleaned
        number_text = _normalize_decimal_text(number_text, suffix)

        try:
            amount = Decimal(number_text) * multiplier
        except InvalidOperation as exc:
            raise ValueError(f"Số tiền `{raw_amount}` không hợp lệ") from exc

    if amount <= 0:
        raise ValueError("Số tiền phải lớn hơn 0 VNĐ")
    rounded = int(amount.to_integral_value(rounding=ROUND_HALF_UP))
    if rounded <= 0:
        return 1
    return rounded


def parse_vnd_amount_or_zero(raw_amount: str | int | float) -> int:
    cleaned = str(raw_amount).strip().lower()
    zero_values = {"0", "0vnd", "0vnđ", "0đ", "0d"}
    if cleaned.replace(" ", "") in zero_values:
        return 0
    return parse_vnd_amount(raw_amount)


def parse_percent(raw_percent: str | int | float) -> Decimal:
    cleaned = str(raw_percent).strip().lower().replace("%", "").replace(",", ".")
    try:
        percent = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"Phần trăm `{raw_percent}` không hợp lệ") from exc
    if percent < 0 or percent > 100:
        raise ValueError("Phần trăm phải nằm trong khoảng 0-100")
    return percent


def format_percent(percent: Decimal | str | int | float) -> str:
    value = Decimal(str(percent))
    if value == value.to_integral_value():
        return str(int(value))
    return f"{value.normalize():f}".rstrip("0").rstrip(".")


def format_hours(hours: float) -> str:
    if float(hours).is_integer():
        return f"{int(hours)}h"
    return f"{hours:.1f}".rstrip("0").rstrip(".") + "h"


def split_reason(reason: str) -> str:
    return reason.strip() if reason and reason.strip() else "Không có lý do"


def parse_duration(value: str) -> Optional[int]:
    if not value:
        return None
    cleaned = value.strip().lower()
    if cleaned.isdigit():
        return int(cleaned) * 60

    match = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd])", cleaned)
    if not match:
        return None

    amount = float(match.group(1))
    unit = match.group(2)
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }[unit]
    return max(1, int(amount * multiplier))


def format_duration_seconds(seconds: int) -> str:
    seconds = int(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds or not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts)


def parse_color(color_text: str) -> Optional[discord.Color]:
    if not color_text:
        return None

    cleaned = color_text.strip().lower()
    named = {
        "red": discord.Color.red(),
        "blue": discord.Color.blue(),
        "green": discord.Color.green(),
        "yellow": discord.Color.yellow(),
        "orange": discord.Color.orange(),
        "purple": discord.Color.purple(),
        "pink": discord.Color.magenta(),
        "black": discord.Color.from_rgb(0, 0, 0),
        "white": discord.Color.from_rgb(255, 255, 255),
    }
    if cleaned in named:
        return named[cleaned]

    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]

    if re.fullmatch(r"[0-9a-f]{6}", cleaned):
        return discord.Color(int(cleaned, 16))

    return None


class AdminCommandBase(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._admins = None
        self._users = None
        self._settings = None
        self._guild_settings = None
        self._role_permissions = None

    @property
    def admins(self) -> AdminService:
        if self._admins is None:
            self._admins = AdminService()
        return self._admins

    @property
    def users(self) -> UserService:
        if self._users is None:
            self._users = UserService()
        return self._users

    @property
    def settings(self) -> SettingsService:
        if self._settings is None:
            self._settings = SettingsService()
        return self._settings

    @property
    def guild_settings(self) -> GuildSettingsService:
        if self._guild_settings is None:
            self._guild_settings = GuildSettingsService()
        return self._guild_settings

    @property
    def role_permissions(self) -> RolePermissionService:
        if self._role_permissions is None:
            self._role_permissions = RolePermissionService()
        return self._role_permissions

    @staticmethod
    def _target_user(target):
        return getattr(target, "author", None) or getattr(target, "user", None)

    @staticmethod
    def _target_guild_id(target) -> int | None:
        guild = getattr(target, "guild", None)
        return getattr(guild, "id", None)

    def is_admin(self, target) -> bool:
        user = self._target_user(target)
        return bool(user and self.admins.is_admin(user.id, self._target_guild_id(target)))

    def can_use_cash(self, ctx, guild_id: int | None = None) -> bool:
        guild_id = guild_id if guild_id is not None else (ctx.guild.id if ctx.guild else None)
        if guild_id is None:
            return False
        if self.admins.is_cash_admin(ctx.author.id, guild_id):
            return True
        if ctx.guild is None:
            return False
        user_roles = [role.id for role in ctx.author.roles if role.name != "@everyone"]
        return self.role_permissions.user_can_use(ctx.guild.id, user_roles, "cash")

    async def require_admin_ctx(self, ctx, message: str = "Chỉ bot admin mới được dùng lệnh này.") -> bool:
        if self.is_admin(ctx):
            return True
        await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", message))
        return False

    async def require_role_or_admin_ctx(
        self,
        ctx,
        command_name: str | None = None,
        message: str | None = None,
    ) -> bool:
        resolved_command = normalize_permission_key(command_name or getattr(ctx.command, "name", "") or "")
        if self.can_use_role_or_admin(ctx, resolved_command):
            return True
        detail = message or f"Chỉ bot admin hoặc role có quyền `{resolved_command}` trong DB mới dùng được lệnh này."
        await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", detail))
        return False

    async def require_admin_interaction(self, interaction: discord.Interaction, message: str = "Chỉ bot admin mới được dùng lệnh này.") -> bool:
        if self.is_admin(interaction):
            return True
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ {message}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {message}", ephemeral=True)
        return False

    async def require_role_or_admin_interaction(
        self,
        interaction: discord.Interaction,
        command_name: str,
        message: str | None = None,
    ) -> bool:
        resolved_command = normalize_permission_key(command_name)
        if resolved_command != "cash" and self.is_admin(interaction):
            return True
        if interaction.guild is None or not isinstance(interaction.user, discord.Member):
            allowed = False
        else:
            if resolved_command == "cash" and self.admins.is_cash_admin(interaction.user.id, interaction.guild.id):
                allowed = True
            else:
                user_roles = [role.id for role in interaction.user.roles if role.name != "@everyone"]
                allowed = self.role_permissions.user_can_use(interaction.guild.id, user_roles, resolved_command)
        if allowed:
            return True

        detail = message or f"Chỉ bot admin hoặc role có quyền `{resolved_command}` trong DB mới dùng được lệnh này."
        if interaction.response.is_done():
            await interaction.followup.send(f"❌ {detail}", ephemeral=True)
        else:
            await interaction.response.send_message(f"❌ {detail}", ephemeral=True)
        return False

    def can_use_role_or_admin(self, ctx, command_name: str) -> bool:
        resolved_command = normalize_permission_key(command_name)
        if resolved_command == "cash":
            return self.can_use_cash(ctx)
        if self.is_admin(ctx):
            return True
        if ctx.guild is None:
            return False
        user_roles = [role.id for role in ctx.author.roles if role.name != "@everyone"]
        return self.role_permissions.user_can_use(ctx.guild.id, user_roles, resolved_command)

    @staticmethod
    def extract_user_id(raw_target: str | None) -> int | None:
        if not raw_target:
            return None
        cleaned = raw_target.strip()
        mention_match = re.fullmatch(r"<@!?(\d+)>", cleaned)
        if mention_match:
            return int(mention_match.group(1))
        return int(cleaned) if cleaned.isdigit() else None

    async def resolve_member_target(self, ctx, raw_target: str | None) -> discord.Member | None:
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh này chỉ hoạt động trong server."))
            return None
        if not raw_target:
            await ctx.send(embed=create_error_splash("❌ Thiếu User", "Hãy nhập @user, username hoặc user ID."))
            return None

        try:
            return await commands.MemberConverter().convert(ctx, raw_target)
        except Exception:
            pass

        user_id = self.extract_user_id(raw_target)
        if user_id is not None:
            member = ctx.guild.get_member(user_id)
            if member:
                return member
            try:
                return await ctx.guild.fetch_member(user_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None

        lowered_target = raw_target.strip().casefold()
        try:
            queried_members = await ctx.guild.query_members(query=raw_target.strip(), limit=10)
            exact_matches = [
                member
                for member in queried_members
                if lowered_target
                in {
                    member.name.casefold(),
                    member.display_name.casefold(),
                    str(member).casefold(),
                }
            ]
            if exact_matches:
                return exact_matches[0]
            if len(queried_members) == 1:
                return queried_members[0]
        except (discord.Forbidden, discord.HTTPException):
            pass

        for member in ctx.guild.members:
            names = {
                member.name.casefold(),
                member.display_name.casefold(),
                str(member).casefold(),
            }
            if lowered_target in names:
                return member
        return None

    async def send_dm_notice(self, member: discord.Member, title: str, description: str) -> bool:
        embed = create_info_splash(title, description)
        try:
            await member.send(embed=embed)
            return True
        except discord.Forbidden:
            return False

    async def send_stat_update(
        self,
        ctx,
        member: discord.Member,
        amount: int | float,
        field: str,
        action_label: str,
        dm_title: str | None = None,
        dm_description: str | None = None,
        guild_id: int | None = None,
    ):
        if field == "cash":
            if not self.can_use_cash(ctx, guild_id):
                await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ hard admin, cash-admin hoặc role có quyền `cash` trong server này mới dùng lệnh này."))
                return
        elif not await self.require_role_or_admin_ctx(ctx):
            return
        if amount <= 0:
            await ctx.send(embed=create_error_splash("❌ Lỗi", "Số lượng phải lớn hơn 0."))
            return

        try:
            if field == "cash":
                if action_label.startswith("Trừ"):
                    self.users.remove_cash(member.id, int(amount))
                else:
                    self.users.add_cash(member.id, int(amount))
                new_value = self.users.get_user(member.id).cash
            elif field == "luong":
                resolved_guild_id = guild_id or (ctx.guild.id if ctx.guild else None)
                if resolved_guild_id is None:
                    raise ValueError("guild_id là bắt buộc cho lương")
                if action_label.startswith("Trừ"):
                    self.users.remove_luong(member.id, int(amount), resolved_guild_id)
                else:
                    self.users.add_luong(member.id, int(amount), resolved_guild_id)
                new_value = self.users.get_user(member.id, resolved_guild_id).luong
            elif field == "star":
                if action_label.startswith("Trừ"):
                    self.users.remove_star(member.id, int(amount))
                else:
                    self.users.add_star(member.id, int(amount))
                new_value = self.users.get_user(member.id).star
            elif field == "total_hours":
                if action_label.startswith("Trừ"):
                    self.users.remove_hours(member.id, float(amount))
                else:
                    self.users.add_hours(member.id, float(amount))
                new_value = self.users.get_user(member.id).total_hours
            else:
                raise ValueError("Trường dữ liệu không hợp lệ")
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Cập Nhật Thất Bại", str(exc)))
            return

        if field == "total_hours":
            amount_text = format_hours(amount)
            value_text = format_hours(new_value)
        elif field in {"cash", "luong"}:
            amount_text = f"{format_vnd(int(amount))} VNĐ"
            value_text = None
        elif field == "star":
            amount_text = f"{int(amount):,} star"
            value_text = f"{int(new_value):,} star"
        else:
            amount_text = str(amount)
            value_text = str(new_value)

        description = f"{member.mention} đã được {action_label.lower()} `{amount_text}`."
        if value_text is not None:
            description += f"\nGiá trị hiện tại: `{value_text}`"

        embed = create_success_splash(
            f"✅ {action_label} Thành Công",
            description,
        )

        if dm_title and dm_description:
            dm_sent = await self.send_dm_notice(member, dm_title, dm_description)
            if not dm_sent:
                embed.add_field(
                    name="DM",
                    value="Không gửi được DM vì người dùng đã tắt tin nhắn riêng.",
                    inline=False,
                )

        await ctx.send(embed=embed)
        if field == "cash":
            from cogs.cash_log_utils import send_cash_log

            log_guild = ctx.guild or (self.bot.get_guild(guild_id) if guild_id else None)
            await send_cash_log(
                log_guild,
                title=f"✅ {action_label} Thành Công",
                actor=ctx.author,
                target=member,
                amount=int(amount),
                action=f"admin {field} {action_label.lower()}",
            )
