from discord.ext import commands

from cogs.admin_command_utils import create_info_splash, create_success_splash, create_warning_splash, format_hours, format_vnd
from cogs.booking.booking_command_utils import BookingCommandBase
from models.constants import ERROR_MESSAGE


class BookingTopCog(BookingCommandBase):
    @commands.command(name="topbook")
    async def topbook(self, ctx, limit: int = 10):
        try:
            if not self.can_use_role_or_admin(ctx, "topbook"):
                await ctx.send(embed=create_warning_splash("❌ Quyền Bị Từ Chối", "Chỉ admin hoặc role trong DB mới xem được bảng xếp hạng này."))
                return
            limit = 10 if limit < 1 else min(limit, 25)
            rows = self.service_for(ctx).get_top_booking_hours(limit)
            if not rows:
                await ctx.send(embed=create_warning_splash("⚠️ Top Book", "Chưa có dữ liệu booking nào."))
                return
            description = [
                f"**#{index}** `{row['username']}` - `{format_hours(row['booking_hours'])}`"
                for index, row in enumerate(rows, 1)
            ]
            await ctx.send(embed=create_success_splash(f"📊 Top Book ({len(rows)})", "\n".join(description)))
        except Exception as e:
            await ctx.send(f"{ERROR_MESSAGE} {str(e)}")

    @commands.command(name="topnap")
    async def topnap(self, ctx, limit: int = 10):
        try:
            if not self.can_use_role_or_admin(ctx, "topnap"):
                await ctx.send(embed=create_warning_splash("❌ Quyền Bị Từ Chối", "Chỉ admin hoặc role trong DB mới xem được bảng xếp hạng này."))
                return
            limit = 10 if limit < 1 else min(limit, 25)
            rows = self.service_for(ctx).get_top_recharges(limit)
            if not rows:
                await ctx.send(embed=create_warning_splash("⚠️ Top Nạp", "Chưa có dữ liệu nạp tiền nào."))
                return
            description = [
                f"**#{index}** `{row['username']}` - `{format_vnd(row['booking_received_money'])} VNĐ`"
                for index, row in enumerate(rows, 1)
            ]
            await ctx.send(embed=create_success_splash(f"💸 Top Nạp ({len(rows)})", "\n".join(description)))
        except Exception as e:
            await ctx.send(f"{ERROR_MESSAGE} {str(e)}")

    @commands.command(name="topgift")
    async def topgift(self, ctx):
        try:
            gifts = self.service_for(ctx).get_gifts()
            total_gifts = self.service_for(ctx).get_total_gifts()
            if not gifts:
                await ctx.send(embed=create_warning_splash("🎁 Top Gift", "Chưa có quà nào trong kho."))
                return
            lines = [f"**{gift['gift_name']}**: `{gift['amount']}`" for gift in gifts]
            await ctx.send(embed=create_info_splash(f"🎁 Top Gift ({total_gifts})", "\n".join(lines)))
        except Exception as e:
            await ctx.send(f"{ERROR_MESSAGE} {str(e)}")


async def setup(bot):
    await bot.add_cog(BookingTopCog(bot))
