from __future__ import annotations

import discord
from discord.ext import commands

from cogs.admin_command_utils import format_hours, format_vnd
from services.admin_service import AdminService
from services.booking_service import BookingService
from services.guild_settings_service import GuildSettingsService
from services.role_permission_service import RolePermissionService
from services.user_service import UserService


class BookingCommandBase(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._service = None
        self._guild_services = {}
        self._users = None
        self._guild_settings = None
        self._admins = None
        self._role_permissions = None

    @property
    def service(self) -> BookingService:
        if self._service is None:
            self._service = BookingService()
        return self._service

    def service_for(self, source) -> BookingService:
        guild = getattr(source, "guild", source)
        if guild is None:
            raise ValueError("Booking chỉ hoạt động trong server")
        guild_id = int(getattr(guild, "id", guild))
        if guild_id not in self._guild_services:
            self._guild_services[guild_id] = BookingService(guild_id)
        return self._guild_services[guild_id]

    @property
    def users(self) -> UserService:
        if self._users is None:
            self._users = UserService()
        return self._users

    @property
    def guild_settings(self) -> GuildSettingsService:
        if self._guild_settings is None:
            self._guild_settings = GuildSettingsService()
        return self._guild_settings

    @property
    def admins(self) -> AdminService:
        if self._admins is None:
            self._admins = AdminService()
        return self._admins

    @property
    def role_permissions(self) -> RolePermissionService:
        if self._role_permissions is None:
            self._role_permissions = RolePermissionService()
        return self._role_permissions

    def is_admin(self, user_id: int, guild_id: int | None = None) -> bool:
        return self.admins.is_admin(user_id, guild_id)

    def can_use_role_or_admin(self, ctx, command_name: str) -> bool:
        guild_id = ctx.guild.id if ctx.guild else None
        if self.is_admin(ctx.author.id, guild_id):
            return True
        if ctx.guild is None:
            return False
        user_roles = [role.id for role in ctx.author.roles if role.name != "@everyone"]
        return self.role_permissions.user_can_use(ctx.guild.id, user_roles, command_name)

    async def resolve_member(self, ctx, raw: str):
        try:
            return await commands.MemberConverter().convert(ctx, raw)
        except Exception:
            return None

    def build_star_embed(self, member: discord.Member, booking: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"📘 Booking của {member.display_name}",
            color=discord.Color.from_rgb(46, 48, 53),
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Giờ đã book", value=f"`{format_hours(booking['booking_hours'])}`", inline=False)
        embed.add_field(name="Số tiền đã tiêu", value=f"`{format_vnd(booking['booking_spent_money'])} VNĐ`", inline=False)
        return embed

    def build_tinhluong_embed(self, member: discord.Member, booking: dict) -> discord.Embed:
        embed = discord.Embed(
            title=f"📘 Booking của {member.display_name}",
            color=discord.Color.from_rgb(46, 48, 53),
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Giờ đã book", value=f"`{format_hours(booking['booking_hours'])}`", inline=False)
        embed.add_field(name="Số tiền đã tiêu", value=f"`{format_vnd(booking['booking_spent_money'])} VNĐ`", inline=False)
        embed.add_field(name="Số tiền đã trừ", value=f"`{format_vnd(booking['booking_deducted_money'])} VNĐ`", inline=False)
        embed.add_field(name="Tiền tổng được nhận", value=f"`{format_vnd(booking['booking_received_money'])} VNĐ`", inline=False)
        embed.add_field(name="Tổng hiện tại", value=f"`{format_vnd(booking['booking_current_money'])} VNĐ`", inline=False)
        embed.add_field(name="Số lần nhắn luong", value=f"`{booking['booking_messages']}`", inline=False)
        return embed

    def build_tinhluong_dm_embed(self, member: discord.Member, booking: dict, hour_details: list[dict]) -> discord.Embed:
        embed = discord.Embed(
            title=f"📘 Tính lương của {member.display_name}",
            color=discord.Color.from_rgb(46, 48, 53),
        )
        embed.set_author(name=member.display_name, icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)

        detail_lines = []
        admin_salary_amount = int(booking.get("admin_salary_amount", 0) or 0)
        if admin_salary_amount > 0:
            detail_lines.append(f"**ADMIN:** `{format_vnd(admin_salary_amount)} VNĐ`")
        if hour_details:
            detail_lines.extend([
                f"**{format_hours(row['hour_value'])}:** `{int(row['count'])}`"
                for row in hour_details
            ])
        if detail_lines:
            detail_text = "\n".join(detail_lines)
        else:
            detail_text = "Chưa có dữ liệu chi tiết theo từng mốc giờ."

        embed.add_field(name="**Số giờ đã được book chi tiết**", value=detail_text, inline=False)
        embed.add_field(name="**Tổng tiền**", value=f"`{format_vnd(booking['booking_received_money'])} VNĐ`", inline=False)
        embed.add_field(name="**Số tiền đã dùng**", value=f"`{format_vnd(booking['booking_deducted_money'])} VNĐ`", inline=False)
        embed.add_field(name="**Còn lại**", value=f"`{format_vnd(booking['booking_current_money'])} VNĐ`", inline=False)
        return embed

    def build_tinhluong_all_embed(self, rows: list[dict]) -> discord.Embed:
        embed = discord.Embed(
            title="📘 Tính lương tất cả",
            color=discord.Color.from_rgb(46, 48, 53),
        )
        if not rows:
            embed.description = "Chưa có dữ liệu lương."
            return embed

        lines = []
        for index, row in enumerate(rows[:20], 1):
            lines.append(
                "\n".join(
                    [
                        f"**#{index} {row['username']}**",
                        f"**Tổng tiền:** `{format_vnd(row['booking_received_money'])} VNĐ`",
                        f"**Số tiền đã dùng:** `{format_vnd(row['booking_deducted_money'])} VNĐ`",
                        f"**Còn lại:** `{format_vnd(row['booking_current_money'])} VNĐ`",
                    ]
                )
            )

        embed.description = "\n\n".join(lines)
        if len(rows) > 20:
            embed.set_footer(text=f"Đang hiển thị 20/{len(rows)} booking đầu tiên.")
        return embed

    def _display_name(self, user) -> str:
        return getattr(user, "display_name", getattr(user, "name", str(user)))

    def _avatar_url(self, user) -> str | None:
        avatar = getattr(user, "display_avatar", None)
        return avatar.url if avatar else None

    def build_traluong_detail_embed(self, user, payment: dict, hour_details: list[dict]) -> discord.Embed:
        return self.build_traluong_record_detail_embed(
            {
                "user": user,
                "payments": [payment],
                "paid_amount": int(payment["paid_amount"]),
                "hour_details": hour_details,
            }
        )

    def build_traluong_record_detail_embed(self, record: dict) -> discord.Embed:
        user = record["user"]
        payments = record.get("payments") or [record["payment"]]
        paid_amount = int(record["paid_amount"])
        display_name = self._display_name(user)

        embed = discord.Embed(
            title=f"💰 Trả lương cho {display_name}",
            color=discord.Color.from_rgb(46, 48, 53),
        )
        avatar_url = self._avatar_url(user)
        if avatar_url:
            embed.set_author(name=display_name, icon_url=avatar_url)
            embed.set_thumbnail(url=avatar_url)

        hour_details = record.get("hour_details") or []
        if hour_details:
            detail_lines = [
                f"**{format_hours(row['hour_value'])}:** `{int(row['count'])}`"
                for row in hour_details
            ]
            detail_text = "\n".join(detail_lines)
        else:
            detail_text = "Chưa có dữ liệu chi tiết theo từng mốc giờ."

        embed.add_field(name="**Số tiền đã trả**", value=f"`{format_vnd(paid_amount)} VNĐ`", inline=False)
        embed.add_field(name="**Số giờ đã được book chi tiết**", value=detail_text, inline=False)

        for payment in payments:
            before = payment["before"]
            after = payment["after"]
            if payment.get("source") == "users":
                embed.add_field(
                    name="**Nguồn users.db**",
                    value=(
                        f"**Lương trước khi trả:** `{format_vnd(before['luong'])} VNĐ`\n"
                        f"**Còn lại sau khi trả:** `{format_vnd(after['luong'])} VNĐ`"
                    ),
                    inline=False,
                )
                continue

            embed.add_field(
                name="**Nguồn booking.db**",
                value=(
                    f"**Tổng tiền:** `{format_vnd(before['booking_received_money'])} VNĐ`\n"
                    f"**Số tiền đã dùng trước khi trả:** `{format_vnd(before['booking_deducted_money'])} VNĐ`\n"
                    f"**Còn lại trước khi trả:** `{format_vnd(before['booking_current_money'])} VNĐ`\n"
                    f"**Còn lại sau khi trả:** `{format_vnd(after['booking_current_money'])} VNĐ`"
                ),
                inline=False,
            )
        return embed

    def build_traluong_user_embed(self, user, payment_or_record: dict) -> discord.Embed:
        paid_amount = int(payment_or_record["paid_amount"])
        embed = discord.Embed(
            title="💰 Đã Trả Lương",
            description=f"Bạn vừa được trả `{format_vnd(paid_amount)} VNĐ`.",
            color=discord.Color.green(),
        )
        avatar_url = self._avatar_url(user)
        if avatar_url:
            embed.set_author(name=self._display_name(user), icon_url=avatar_url)
        return embed

    def build_traluong_all_summary_embed(self, records: list[dict]) -> discord.Embed:
        embed = discord.Embed(
            title="💰 Trả lương tất cả",
            color=discord.Color.green(),
        )
        if not records:
            embed.description = "Không có user/booking nào còn lương cần trả."
            return embed

        total_paid = sum(int(record["paid_amount"]) for record in records)
        lines = []
        for index, record in enumerate(records[:25], 1):
            user_id = int(record["user_id"])
            username = record["username"]
            paid_amount = int(record["paid_amount"])
            lines.append(f"**#{index}** <@{user_id}> `{username}` - `{format_vnd(paid_amount)} VNĐ`")

        embed.description = "\n".join(lines)
        embed.add_field(name="**Tổng người được trả**", value=f"`{len(records)}`", inline=True)
        embed.add_field(name="**Tổng tiền đã trả**", value=f"`{format_vnd(total_paid)} VNĐ`", inline=True)
        if len(records) > 125:
            embed.set_footer(text=f"Tóm tắt hiển thị 25 dòng đầu. Menu chi tiết chỉ hiển thị 125/{len(records)} người đầu tiên.")
        elif len(records) > 25:
            embed.set_footer(text=f"Tóm tắt hiển thị 25/{len(records)} dòng đầu. Chọn người trong menu bên dưới để xem chi tiết.")
        else:
            embed.set_footer(text="Chọn người trong menu bên dưới để xem chi tiết.")
        return embed
