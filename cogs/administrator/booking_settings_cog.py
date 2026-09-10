from discord.ext import commands

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_error_splash,
    create_info_splash,
    create_success_splash,
    format_percent,
    format_vnd,
    parse_percent,
    parse_vnd_amount,
)
from services.booking_service import BookingService


class AdministratorBookingSettingsCog(AdminCommandBase):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self._booking_services = {}

    def booking_service(self, guild_id: int) -> BookingService:
        guild_id = int(guild_id)
        if guild_id not in self._booking_services:
            self._booking_services[guild_id] = BookingService(guild_id)
        return self._booking_services[guild_id]

    def _config_text(self, guild_id: int) -> str:
        config = self.booking_service(guild_id).get_booking_config()
        return (
            f"Giá 1h: `{format_vnd(config['hour_price_vnd'])} VNĐ`\n"
            f"Trả booking: `{format_percent(config['payout_percent'])}%`\n"
            f"Bot/server ăn: `{format_percent(config['fee_percent'])}%`"
        )

    @commands.command(name="bookconfig", aliases=["bookingconfig", "giabook"])
    async def book_config(self, ctx):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        await ctx.send(embed=create_info_splash("⚙️ Cấu Hình Booking", self._config_text(ctx.guild.id)))

    @commands.command(name="setgiobook", aliases=["setgia", "giabooking"])
    async def set_booking_price(self, ctx, amount: str):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        try:
            parsed_amount = parse_vnd_amount(amount)
            self.booking_service(ctx.guild.id).set_hour_price_vnd(parsed_amount)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Giá Booking Không Hợp Lệ", str(exc)))
            return
        await ctx.send(
            embed=create_success_splash(
                "✅ Đã Cập Nhật Giá Booking",
                f"Giá 1h hiện tại là `{format_vnd(parsed_amount)} VNĐ`.\n\n{self._config_text(ctx.guild.id)}",
            )
        )

    @commands.command(name="setphantram", aliases=["setpayout", "settraluong"])
    async def set_booking_payout(self, ctx, percent: str):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        try:
            parsed_percent = parse_percent(percent)
            self.booking_service(ctx.guild.id).set_payout_percent(parsed_percent)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Phần Trăm Không Hợp Lệ", str(exc)))
            return
        await ctx.send(
            embed=create_success_splash(
                "✅ Đã Cập Nhật Phần Trăm Trả",
                f"Booking sẽ nhận `{format_percent(parsed_percent)}%` tiền khách trả.\n\n{self._config_text(ctx.guild.id)}",
            )
        )

    @commands.command(name="setan", aliases=["setfee", "sethoahong"])
    async def set_booking_fee(self, ctx, percent: str):
        if not await self.require_role_or_admin_ctx(ctx):
            return
        try:
            parsed_percent = parse_percent(percent)
            self.booking_service(ctx.guild.id).set_fee_percent(parsed_percent)
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Phần Trăm Không Hợp Lệ", str(exc)))
            return
        await ctx.send(
            embed=create_success_splash(
                "✅ Đã Cập Nhật Phần Trăm Ăn",
                f"Bot/server sẽ ăn `{format_percent(parsed_percent)}%`, booking nhận phần còn lại.\n\n{self._config_text(ctx.guild.id)}",
            )
        )


async def setup(bot):
    await bot.add_cog(AdministratorBookingSettingsCog(bot))
