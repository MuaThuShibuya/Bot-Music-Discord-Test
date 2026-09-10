from discord.ext import commands

from cogs.admin_command_utils import (
    create_error_splash,
    create_success_splash,
    create_warning_splash,
    format_hours,
    format_vnd,
    parse_vnd_amount,
)
from cogs.booking.booking_command_utils import BookingCommandBase
from models.constants import ERROR_MESSAGE


class BookingStarCog(BookingCommandBase):
    STAT_ACTIONS = {
        "a": "add",
        "add": "add",
        "d": "remove",
        "del": "remove",
        "delete": "remove",
        "r": "remove",
        "rm": "remove",
        "remove": "remove",
        "e": "edit",
        "edit": "edit",
    }

    def _can_manage_star(self, ctx, action: str) -> bool:
        if self.can_use_role_or_admin(ctx, "star"):
            return True
        legacy_command = {
            "add": "addstar",
            "remove": "substar",
            "edit": "star",
        }[action]
        return self.can_use_role_or_admin(ctx, legacy_command)

    @staticmethod
    def _parse_star_amount(raw_amount: str, allow_zero: bool = False) -> int:
        try:
            amount = int(str(raw_amount).strip().replace(",", "").replace(".", ""))
        except ValueError as exc:
            raise ValueError(f"Số star `{raw_amount}` không hợp lệ") from exc
        if allow_zero:
            if amount < 0:
                raise ValueError("Star không thể âm")
        elif amount <= 0:
            raise ValueError("Số star phải lớn hơn 0")
        return amount

    async def _apply_star_action(self, ctx, action: str, raw_member: str, raw_amount: str):
        if not self._can_manage_star(ctx, action):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ bot admin hoặc role có quyền `star` trong DB mới quản trị star."))
            return

        target = await self.resolve_member(ctx, raw_member)
        if not target:
            await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy User", f"Không tìm thấy `{raw_member}` trong server."))
            return

        try:
            amount = self._parse_star_amount(raw_amount, allow_zero=action == "edit")
            if action in {"add", "edit"}:
                self.users.get_or_create_user(target.id, target.display_name)
            if action == "add":
                self.users.add_star(target.id, amount)
                title = "✅ Cộng Star Thành Công"
                detail = f"Đã cộng `{amount:,}` star cho {target.mention}."
            elif action == "remove":
                self.users.remove_star(target.id, amount)
                title = "✅ Trừ Star Thành Công"
                detail = f"Đã trừ `{amount:,}` star của {target.mention}."
            else:
                self.users.set_star(target.id, amount)
                title = "✅ Sửa Star Thành Công"
                detail = f"Đã set star của {target.mention} thành `{amount:,}`."
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Cập Nhật Thất Bại", str(exc)))
            return

        current_star = self.users.get_user(target.id).star
        await ctx.send(embed=create_success_splash(title, f"{detail}\nStar hiện tại: `{int(current_star):,}`"))

    @commands.command(name="star")
    async def star(self, ctx, *args):
        try:
            service = self.service_for(ctx)
            if not args:
                booking = service.get_or_create_booking(ctx.author.id, ctx.author.display_name)
                await ctx.send(embed=self.build_star_embed(ctx.author, booking))
                return

            action = args[0].lower()
            stat_action = self.STAT_ACTIONS.get(action)
            if stat_action:
                if len(args) != 3:
                    await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `star a/add @user <amount>`, `star r/rm/remove/d/delete @user <amount>` hoặc `star e/edit @user <amount>`."))
                    return
                await self._apply_star_action(ctx, stat_action, args[1], args[2])
                return

            if action == "all":
                if not self._can_manage_star(ctx, "edit"):
                    await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ admin hoặc role có quyền `star` trong DB mới xem được tất cả star."))
                    return
                rows = self.users.get_users_by_stat("star", 25)
                if not rows:
                    await ctx.send(embed=create_warning_splash("⚠️ Star", "Chưa có dữ liệu star nào trong database."))
                    return
                description = [
                    f"**#{index}** `{row['username']}` - `{int(row['star']):,}` star"
                    for index, row in enumerate(rows, 1)
                ]
                await ctx.send(embed=create_success_splash(f"⭐ Tất Cả Star ({len(rows)})", "\n".join(description)))
                return

            if action == "top":
                if not (self.can_use_role_or_admin(ctx, "topbook") or self.can_use_role_or_admin(ctx, "topnap")):
                    await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ admin hoặc role trong DB mới dùng `star top`."))
                    return
                hour_rows = service.get_top_booking_hours(10)
                recharge_rows = service.get_top_recharges(10)
                hour_lines = [
                    f"**#{index}** `{row['username']}` - `{format_hours(row['booking_hours'])}`"
                    for index, row in enumerate(hour_rows, 1)
                ]
                recharge_lines = [
                    f"**#{index}** `{row['username']}` - `{format_vnd(row['booking_received_money'])} VNĐ`"
                    for index, row in enumerate(recharge_rows, 1)
                ]
                description = (
                    "**Top giờ được book**\n"
                    f"{chr(10).join(hour_lines) if hour_lines else 'Chưa có dữ liệu.'}\n\n"
                    "**Top nạp tiền**\n"
                    f"{chr(10).join(recharge_lines) if recharge_lines else 'Chưa có dữ liệu.'}"
                )
                await ctx.send(embed=create_success_splash("⭐ Top", description))
                return

            if action == "time":
                await ctx.send(embed=create_error_splash("❌ Lệnh Đã Đổi", "Ghi nhận giờ book đã chuyển sang `book @booking 1,2,5 [@user] [cash|banking]`."))
                return

            if action == "money":
                if len(args) < 2:
                    await ctx.send("❌ Dùng: `star money <amount> [@user]`")
                    return

                target = ctx.author
                if len(args) >= 3:
                    maybe_member = await self.resolve_member(ctx, args[2])
                    if maybe_member:
                        target = maybe_member
                if target.id != ctx.author.id and not self.can_use_role_or_admin(ctx, "star"):
                    await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ admin bot hoặc role có quyền `star` trong DB mới thao tác trên người khác."))
                    return

                amount = parse_vnd_amount(args[1])
                service.add_booking_received_money(target.id, target.display_name, amount)
                booking = service.get_or_create_booking(target.id, target.display_name)
                await ctx.send(embed=create_success_splash("✅ Ghi Nhận Tiền Nạp", f"Đã cộng `{format_vnd(amount)} VNĐ` cho {target.mention}."))
                return

            target = await self.resolve_member(ctx, args[0])
            if target:
                if target.id != ctx.author.id and not self.can_use_role_or_admin(ctx, "star"):
                    await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ admin bot hoặc role có quyền `star` trong DB mới xem booking của người khác."))
                    return
                booking = service.get_or_create_booking(target.id, target.display_name)
                await ctx.send(embed=self.build_star_embed(target, booking))
                return

            await ctx.send("❌ Dùng: `star`, `star @user`, `star all`, `star top`, `star a/r/e @user <amount>` hoặc `star money <amount> [@user]`")
        except Exception as e:
            await ctx.send(f"{ERROR_MESSAGE} {str(e)}")


async def setup(bot):
    await bot.add_cog(BookingStarCog(bot))
