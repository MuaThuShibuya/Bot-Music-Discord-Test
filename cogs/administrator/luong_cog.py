import discord
from discord.ext import commands

from cogs.admin_command_utils import AdminCommandBase, create_error_splash, create_info_splash, format_vnd, parse_vnd_amount
from services.booking_service import BookingService


class AdministratorLuongCog(AdminCommandBase):
    def __init__(self, bot):
        super().__init__(bot)
        self._booking_services = {}

    def booking_service(self, guild_id: int) -> BookingService:
        guild_id = int(guild_id)
        if guild_id not in self._booking_services:
            self._booking_services[guild_id] = BookingService(guild_id)
        return self._booking_services[guild_id]

    async def _require_booking_user(self, ctx, member: discord.Member) -> bool:
        system_role = self.guild_settings.get_system_role(ctx.guild.id, "booking")
        if not system_role:
            await ctx.send(embed=create_error_splash("❌ Chưa Set Role Booking", "Dùng `setrole @role booking` trước."))
            return False

        member_role_ids = [role.id for role in member.roles if role.name != "@everyone"]
        if int(system_role["role_id"]) not in member_role_ids:
            await ctx.send(embed=create_error_splash("❌ Không Phải Booking", f"{member.mention} không phải booking."))
            return False
        return True

    @commands.command(name="addluong", aliases=["al"])
    async def addluong(self, ctx, member: discord.Member, amount: str):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        if not await self._require_booking_user(ctx, member):
            return
        try:
            parsed_amount = parse_vnd_amount(amount)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Số Tiền Không Hợp Lệ", str(exc)))
            return
        try:
            self.booking_service(ctx.guild.id).add_admin_salary(member.id, member.display_name, parsed_amount)
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Cập Nhật Thất Bại", str(exc)))
            return
        await ctx.send(embed=create_info_splash("💰 Cộng Lương", f"Đã cộng `{format_vnd(parsed_amount)} VNĐ` lương cho {member.mention}."))
        try:
            await member.send(embed=create_info_splash("💰 Lương Đã Được Cộng", f"Bạn vừa được cộng `{format_vnd(parsed_amount)} VNĐ` lương bởi {ctx.author.display_name}."))
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.command(name="subluong", aliases=["sl"])
    async def subluong(self, ctx, member: discord.Member, amount: str):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        if not await self._require_booking_user(ctx, member):
            return
        try:
            parsed_amount = parse_vnd_amount(amount)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Số Tiền Không Hợp Lệ", str(exc)))
            return
        try:
            self.booking_service(ctx.guild.id).deduct_admin_salary(member.id, member.display_name, parsed_amount)
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Cập Nhật Thất Bại", str(exc)))
            return
        await ctx.send(embed=create_info_splash("💰 Trừ Lương", f"Đã trừ `{format_vnd(parsed_amount)} VNĐ` lương của {member.mention}."))
        try:
            await member.send(embed=create_info_splash("⚠️ Lương Đã Bị Trừ", f"Bạn vừa bị trừ `{format_vnd(parsed_amount)} VNĐ` lương bởi {ctx.author.display_name}."))
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.command(name="tongluong", aliases=["tl"])
    async def tongluong(self, ctx):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        service = self.booking_service(ctx.guild.id)
        total_luong = service.get_total_current_salary()
        users_count = service.get_current_salary_users_count()
        await ctx.send(
            embed=create_info_splash(
                "📊 Tổng Lương",
                f"Tổng lương trong database hiện tại là `{total_luong:,}` VNĐ.\nSố user đã có dữ liệu: `{users_count}`",
            )
        )


async def setup(bot):
    await bot.add_cog(AdministratorLuongCog(bot))
