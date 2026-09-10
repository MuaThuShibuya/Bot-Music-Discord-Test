import discord
from discord.ext import commands

from cogs.admin_command_utils import create_error_splash, create_success_splash, format_hours, format_vnd
from cogs.booking.booking_command_utils import BookingCommandBase
from models.constants import ERROR_MESSAGE


class BookingBookCog(BookingCommandBase):
    PAYMENT_ALIASES = {
        "cash": "cash",
        "c": "cash",
        "banking": "banking",
        "bank": "banking",
        "ck": "banking",
        "chuyenkhoan": "banking",
        "chuyểnkhoản": "banking",
        "chuyển-khoản": "banking",
    }

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

    def _parse_hours_list(self, raw_hours: str) -> list[float]:
        values = []
        for item in raw_hours.split(","):
            text = item.strip()
            if not text:
                continue
            try:
                hour = float(text)
            except ValueError as exc:
                raise ValueError(f"Mốc giờ `{text}` không hợp lệ") from exc
            if hour <= 0:
                raise ValueError("Số giờ phải lớn hơn 0")
            values.append(hour)
        if not values:
            raise ValueError("Bạn chưa nhập số giờ cần book")
        return values

    async def _parse_optional_args(self, ctx, raw_parts: list[str]) -> tuple[discord.Member, str]:
        payer = ctx.author
        payment_method = "banking"
        payer_parts = []

        for part in raw_parts:
            normalized = part.strip().lower()
            if normalized in self.PAYMENT_ALIASES:
                payment_method = self.PAYMENT_ALIASES[normalized]
            else:
                payer_parts.append(part)

        if payer_parts:
            raw_payer = " ".join(payer_parts)
            resolved = await self.resolve_member(ctx, raw_payer)
            if not resolved:
                raise ValueError(f"Không tìm thấy user thanh toán `{raw_payer}` trong server")
            payer = resolved

        return payer, payment_method

    def _check_and_charge_cash(self, payer: discord.Member, amount: int):
        if amount <= 0:
            return
        payer_user = self.users.get_user(payer.id)
        if not payer_user or int(payer_user.cash) < amount:
            current_cash = int(payer_user.cash) if payer_user else 0
            raise ValueError(f"{payer.mention} không đủ cash. Hiện có `{format_vnd(current_cash)} VNĐ`, cần `{format_vnd(amount)} VNĐ`.")
        self.users.remove_cash(payer.id, amount)

    @commands.command(name="book")
    async def book(self, ctx, booking_member: discord.Member = None, hours_text: str = None, *raw_parts: str):
        try:
            if booking_member is None or not hours_text:
                await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `book @booking 1,2,5 [@user] [cash|banking]`."))
                return
            if not await self._require_booking_user(ctx, booking_member):
                return

            try:
                hours_list = self._parse_hours_list(hours_text)
                payer, payment_method = await self._parse_optional_args(ctx, list(raw_parts))
            except ValueError as exc:
                await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", str(exc)))
                return

            service = self.service_for(ctx)
            session_money = [service.calculate_session_money(hours) for hours in hours_list]
            total_spent = sum(item["spent_money"] for item in session_money)
            total_received = sum(item["received_money"] for item in session_money)

            if payment_method == "cash":
                try:
                    self._check_and_charge_cash(payer, total_spent)
                except ValueError as exc:
                    await ctx.send(embed=create_error_splash("❌ Không Đủ Cash", str(exc)))
                    return

            try:
                for hours in hours_list:
                    service.add_booking_session(booking_member.id, booking_member.display_name, hours)
            except Exception:
                if payment_method == "cash" and total_spent > 0:
                    self.users.add_cash(payer.id, total_spent)
                raise

            hours_display = ", ".join(f"`{format_hours(hours)}`" for hours in hours_list)
            payment_text = "Cash" if payment_method == "cash" else "Banking"
            detail = (
                f"Booking: {booking_member.mention}\n"
                f"Người thanh toán: {payer.mention}\n"
                f"Mốc giờ: {hours_display}\n"
                f"Phương thức: `{payment_text}`\n"
                f"Khách trả: `{format_vnd(total_spent)} VNĐ`\n"
                f"Booking nhận: `{format_vnd(total_received)} VNĐ`"
            )
            await ctx.send(embed=create_success_splash("✅ Book Thành Công", detail))
        except Exception as e:
            await ctx.send(f"{ERROR_MESSAGE} {str(e)}")


async def setup(bot):
    await bot.add_cog(BookingBookCog(bot))
