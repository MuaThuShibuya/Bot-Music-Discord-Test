from discord.ext import commands

from cogs.admin_command_utils import (
    AdminCommandBase,
    create_error_splash,
    create_info_splash,
    create_success_splash,
    format_vnd,
)
from services.currency_sync_service import CurrencySyncService


class CurrencyRateCog(AdminCommandBase):
    def __init__(self, bot):
        super().__init__(bot)
        self.currency_sync = CurrencySyncService()

    @staticmethod
    def _format_number(value: int) -> str:
        return f"{int(value):,}"

    @commands.command(name="rate")
    async def rate(self, ctx, *args):
        if not self.admins.is_hard_admin(ctx.author.id):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ hard admin trong env mới được xem hoặc thay đổi tỷ giá cash/OWO global."))
            return

        if not args:
            rate = self.currency_sync.get_rate()
            await ctx.send(
                embed=create_info_splash(
                    "💱 Tỷ Giá Cash / OWO",
                    f"`{format_vnd(rate.cash_unit_vnd)} VND` = "
                    f"`{self._format_number(rate.owo_unit)} OWO`\n"
                    f"Cài đặt: `{ctx.prefix}rate cash 1 owo 1`\n"
                    f"Hỗ trợ số thập phân: `{ctx.prefix}rate cash 1 owo 0,5`.",
                )
            )
            return

        if (
            len(args) != 4
            or args[0].lower() != "cash"
            or args[2].lower() != "owo"
        ):
            await ctx.send(
                embed=create_error_splash(
                    "❌ Sai Cú Pháp",
                    f"Dùng: `{ctx.prefix}rate cash <hệ số> owo <hệ số>`\n"
                    f"Ví dụ: `{ctx.prefix}rate cash 1 owo 1`.",
                )
            )
            return

        try:
            rate, updated_wallets = self.currency_sync.set_rate(
                args[1],
                args[3],
                ctx.author.id,
            )
        except ValueError as exc:
            await ctx.send(embed=create_error_splash("❌ Tỷ Giá Không Hợp Lệ", str(exc)))
            return
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Không Thể Lưu Tỷ Giá", str(exc)))
            return

        await ctx.send(
            embed=create_success_splash(
                "✅ Đã Cập Nhật Tỷ Giá",
                f"`{format_vnd(rate.cash_unit_vnd)} VND` = "
                f"`{self._format_number(rate.owo_unit)} OWO`\n"
                f"Đã quy đổi lại cash cho `{updated_wallets}` ví; số OWO được giữ nguyên.",
            )
        )


async def setup(bot):
    await bot.add_cog(CurrencyRateCog(bot))
