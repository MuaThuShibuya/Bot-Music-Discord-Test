import discord
from discord.ext import commands

from cogs.admin_command_utils import create_error_splash, create_success_splash, format_vnd, parse_vnd_amount, parse_vnd_amount_or_zero
from cogs.booking.booking_command_utils import BookingCommandBase
from models.constants import ERROR_MESSAGE


class SalaryDetailSelect(discord.ui.Select):
    def __init__(self, cog: "BookingLuongCog", records: list[dict], placeholder: str):
        self.cog = cog
        self.records = {str(record.get("record_key", record["user_id"])): record for record in records}
        options = [
            discord.SelectOption(
                label=str(record["username"])[:100],
                value=str(record.get("record_key", record["user_id"])),
                description=f"Đã trả {format_vnd(record['paid_amount'])} VNĐ"[:100],
            )
            for record in records
        ]
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            record = self.records.get(self.values[0])
            if not record:
                await interaction.response.send_message("Không tìm thấy dữ liệu chi tiết.")
                return

            embed = self.cog.build_traluong_record_detail_embed(record)
            await interaction.response.send_message(embed=embed)
        except Exception as exc:
            message = f"❌ Lỗi khi mở chi tiết lương: {exc}"
            if interaction.response.is_done():
                await interaction.followup.send(message)
            else:
                await interaction.response.send_message(message)


class SalaryDetailView(discord.ui.View):
    def __init__(self, cog: "BookingLuongCog", records: list[dict]):
        super().__init__(timeout=900)
        for start in range(0, min(len(records), 125), 25):
            chunk = records[start:start + 25]
            placeholder = f"Chọn người để xem chi tiết lương {start + 1}-{start + len(chunk)}"
            self.add_item(SalaryDetailSelect(cog, chunk, placeholder))


class BookingLuongCog(BookingCommandBase):
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

    def _can_manage_luong(self, ctx, action: str) -> bool:
        if self.can_use_role_or_admin(ctx, "luong"):
            return True
        legacy_command = {
            "add": "addluong",
            "remove": "subluong",
            "edit": "luong",
        }[action]
        return self.can_use_role_or_admin(ctx, legacy_command)

    def _can_pay_luong(self, ctx) -> bool:
        return self.can_use_role_or_admin(ctx, "traluong") or self.can_use_role_or_admin(ctx, "luong")

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

    async def _apply_luong_action(self, ctx, action: str, raw_member: str, raw_amount: str):
        if not self._can_manage_luong(ctx, action):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ bot admin hoặc role có quyền `luong` trong DB mới quản trị lương."))
            return

        member = await self.resolve_member(ctx, raw_member)
        if not member:
            await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy User", f"Không tìm thấy `{raw_member}` trong server."))
            return
        if not await self._require_booking_user(ctx, member):
            return

        try:
            service = self.service_for(ctx)
            amount = parse_vnd_amount_or_zero(raw_amount) if action == "edit" else parse_vnd_amount(raw_amount)
            if action == "add":
                service.add_admin_salary(member.id, member.display_name, amount)
                title = "✅ Cộng Lương Thành Công"
                detail = f"Đã cộng `{format_vnd(amount)} VNĐ` lương cho {member.mention}."
            elif action == "remove":
                service.deduct_admin_salary(member.id, member.display_name, amount)
                title = "✅ Trừ Lương Thành Công"
                detail = f"Đã trừ `{format_vnd(amount)} VNĐ` lương của {member.mention}."
            else:
                service.set_admin_salary_current(member.id, member.display_name, amount)
                title = "✅ Sửa Lương Thành Công"
                detail = f"Đã set lương của {member.mention} thành `{format_vnd(amount)} VNĐ`."
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Cập Nhật Thất Bại", str(exc)))
            return

        await ctx.send(embed=create_success_splash(title, detail))

    async def _resolve_salary_user(self, ctx, user_id: int, username: str):
        if ctx.guild:
            member = ctx.guild.get_member(int(user_id))
            if member:
                return member
            try:
                return await ctx.guild.fetch_member(int(user_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        try:
            return await self.bot.fetch_user(int(user_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return username

    async def _build_salary_record(self, ctx, user_id: int, username: str, payments: list[dict]) -> dict:
        user = await self._resolve_salary_user(ctx, user_id, username)
        return {
            "user_id": user_id,
            "record_key": str(user_id),
            "username": username,
            "user": user,
            "payments": payments,
            "paid_amount": sum(int(payment["paid_amount"]) for payment in payments),
            "hour_details": self.service_for(ctx).get_booking_hour_details(user_id),
        }

    def _salary_row(self, ctx, booking: dict) -> dict:
        row = dict(booking)
        row["admin_salary_amount"] = self.service_for(ctx).get_admin_salary_amount(int(row["user_id"]))
        return row

    def _salary_rows(self, ctx) -> list:
        return [self._salary_row(ctx, row) for row in self.service_for(ctx).get_all_bookings()]

    async def _pay_salary_for_booking_user(self, ctx, user_id: int, username: str) -> dict | None:
        try:
            payment = self.service_for(ctx).pay_booking_salary(user_id)
        except Exception:
            return None
        payment["source"] = "booking"
        username = payment["before"]["username"]
        return await self._build_salary_record(ctx, user_id, username, [payment])

    async def _send_paid_user_dm(self, record: dict) -> bool:
        user = record["user"]
        if not hasattr(user, "send"):
            return False
        try:
            await user.send(embed=self.build_traluong_user_embed(user, record))
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def _send_admin_salary_dm(self, ctx, embed: discord.Embed, view: discord.ui.View | None = None) -> bool:
        try:
            await ctx.author.send(embed=embed, view=view)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def _pay_salary_for_member(self, ctx, member: discord.Member):
        if not self._can_pay_luong(ctx):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ bot admin hoặc role có quyền `traluong`/`luong` trong DB mới trả lương."))
            return
        if not await self._require_booking_user(ctx, member):
            return

        record = await self._pay_salary_for_booking_user(ctx, member.id, member.display_name)
        if not record:
            await ctx.send(embed=create_error_splash("❌ Trả Lương Thất Bại", "Người này không còn lương cần trả."))
            return

        admin_dm_ok = await self._send_admin_salary_dm(
            ctx,
            self.build_traluong_record_detail_embed(record),
        )
        user_dm_ok = await self._send_paid_user_dm(record)

        detail = (
            f"Đã trả `{format_vnd(record['paid_amount'])} VNĐ` cho {member.mention}.\n"
            f"DM admin: `{'đã gửi' if admin_dm_ok else 'không gửi được'}`.\n"
            f"DM người nhận: `{'đã gửi' if user_dm_ok else 'không gửi được'}`."
        )
        await ctx.send(embed=create_success_splash("✅ Trả Lương Thành Công", detail))

    async def _pay_salary_all(self, ctx):
        if not self._can_pay_luong(ctx):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ bot admin hoặc role có quyền `traluong`/`luong` trong DB mới trả lương tất cả."))
            return

        booking_rows = self.service_for(ctx).get_payable_bookings()
        user_ids = {}
        for row in booking_rows:
            user_ids[int(row["user_id"])] = row["username"]

        if not user_ids:
            await ctx.send(embed=create_error_splash("❌ Không Có Lương Cần Trả", "Không có booking nào còn lương cần trả."))
            return

        records = []
        user_dm_success = 0
        for user_id, username in user_ids.items():
            record = await self._pay_salary_for_booking_user(ctx, user_id, username)
            if not record:
                continue
            records.append(record)
            if await self._send_paid_user_dm(record):
                user_dm_success += 1

        if not records:
            await ctx.send(embed=create_error_splash("❌ Trả Lương Thất Bại", "Không có người nào được trả lương."))
            return

        view = SalaryDetailView(self, records)
        admin_dm_ok = await self._send_admin_salary_dm(
            ctx,
            self.build_traluong_all_summary_embed(records),
            view=view,
        )
        total_paid = sum(record["paid_amount"] for record in records)
        detail = (
            f"Đã trả lương cho `{len(records)}` người, tổng `{format_vnd(total_paid)} VNĐ`.\n"
            f"DM admin: `{'đã gửi' if admin_dm_ok else 'không gửi được'}`.\n"
            f"DM người nhận: `{user_dm_success}/{len(records)}`."
        )
        await ctx.send(embed=create_success_splash("✅ Trả Lương All Thành Công", detail))

    async def _handle_traluong(self, ctx, target_text: str | None):
        target_text = (target_text or "").strip()
        if not target_text:
            await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `traluong @user` hoặc `traluong all`."))
            return

        if target_text.lower() == "all":
            await self._pay_salary_all(ctx)
            return

        member = await self.resolve_member(ctx, target_text)
        if not member:
            await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy User", f"Không tìm thấy `{target_text}` trong server."))
            return
        await self._pay_salary_for_member(ctx, member)

    async def _send_private_salary(self, ctx, embed: discord.Embed):
        try:
            await ctx.author.send(embed=embed)
        except discord.Forbidden:
            await ctx.send(embed=create_error_splash("❌ Không Gửi Được DM", "Bạn đang tắt DM từ server này, hãy mở DM rồi thử lại."))
            return
        except discord.HTTPException as exc:
            await ctx.send(embed=create_error_splash("❌ Không Gửi Được DM", str(exc)))
            return

        await ctx.send(embed=create_success_splash("✅ Đã Gửi DM", "Mình đã gửi bảng tính lương riêng cho bạn."))

    @commands.command(name="luong")
    async def luong(self, ctx, *, content: str = None):
        try:
            content = (content or "").strip()
            if not content:
                service = self.service_for(ctx)
                booking = self._salary_row(ctx, service.get_or_create_booking(ctx.author.id, ctx.author.display_name))
                hour_details = service.get_booking_hour_details(ctx.author.id)
                await ctx.send(embed=self.build_tinhluong_dm_embed(ctx.author, booking, hour_details))
                return

            parts = content.split(maxsplit=2)
            action = self.STAT_ACTIONS.get(parts[0].lower())
            if action:
                if len(parts) != 3:
                    await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `luong a/add @user <money>`, `luong r/rm/remove/d/delete @user <money>` hoặc `luong e/edit @user <money>`."))
                    return
                await self._apply_luong_action(ctx, action, parts[1], parts[2])
                return

            if parts[0].lower() in {"traluong", "payluong"}:
                await self._handle_traluong(ctx, parts[1] if len(parts) > 1 else None)
                return

            if content.lower() == "all":
                if not self.can_use_role_or_admin(ctx, "luong") and not self.can_use_role_or_admin(ctx, "tinhluong"):
                    await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ admin bot hoặc role có quyền `luong` trong DB mới xem được tất cả."))
                    return
                rows = self._salary_rows(ctx)
                await ctx.send(embed=self.build_tinhluong_all_embed(rows))
                return

            member = await self.resolve_member(ctx, content)
            if member:
                if member.id != ctx.author.id and not (self.can_use_role_or_admin(ctx, "luong") or self.can_use_role_or_admin(ctx, "tinhluong")):
                    await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ admin bot hoặc role có quyền `luong` trong DB mới xem lương người khác."))
                    return
                service = self.service_for(ctx)
                booking = self._salary_row(ctx, service.get_or_create_booking(member.id, member.display_name))
                hour_details = service.get_booking_hour_details(member.id)
                await ctx.send(embed=self.build_tinhluong_dm_embed(member, booking, hour_details))
                return

            await ctx.send(embed=create_error_splash("❌ Sai Cú Pháp", "Dùng: `luong`, `luong @user`, `luong all` hoặc `luong a/r/e @user <money>`."))
        except Exception as e:
            await ctx.send(f"{ERROR_MESSAGE} {str(e)}")

    @commands.command(name="traluong", aliases=["payluong"])
    async def traluong(self, ctx, *, target_text: str = None):
        try:
            await self._handle_traluong(ctx, target_text)
        except Exception as e:
            await ctx.send(f"{ERROR_MESSAGE} {str(e)}")

    @commands.command(name="tinhluong")
    async def tinhluong(self, ctx, *, target_text: str = None):
        try:
            target_text = (target_text or "").strip()

            if target_text.lower() == "all":
                if not self.can_use_role_or_admin(ctx, "tinhluong"):
                    await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ admin bot hoặc role có quyền `tinhluong` trong DB mới xem được tất cả."))
                    return
                rows = self._salary_rows(ctx)
                await self._send_private_salary(ctx, self.build_tinhluong_all_embed(rows))
                return

            if target_text:
                member = await self.resolve_member(ctx, target_text)
                if not member:
                    await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy User", f"Không tìm thấy `{target_text}` trong server."))
                    return
            else:
                member = ctx.author

            if member.id != ctx.author.id and not self.can_use_role_or_admin(ctx, "tinhluong"):
                await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ admin bot hoặc role có quyền `tinhluong` trong DB mới xem booking của người khác."))
                return

            service = self.service_for(ctx)
            booking = self._salary_row(ctx, service.get_or_create_booking(member.id, member.display_name))
            hour_details = service.get_booking_hour_details(member.id)
            await self._send_private_salary(ctx, self.build_tinhluong_dm_embed(member, booking, hour_details))
        except Exception as e:
            await ctx.send(f"{ERROR_MESSAGE} {str(e)}")


async def setup(bot):
    await bot.add_cog(BookingLuongCog(bot))
