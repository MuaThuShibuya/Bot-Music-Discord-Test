from __future__ import annotations

import asyncio
import importlib

import discord
from discord import app_commands
from discord.ext import commands

import cogs.user.payment_common as payment_common_module
import services.bank_service as bank_service_module
import ui.user.donate_ui as donate_ui_module
import ui.user.payment_ui as payment_ui_module

# Extension reload does not refresh imported service/UI modules automatically.
# Reload dependencies so `breload` applies payment card and donate menu changes.
importlib.reload(bank_service_module)
importlib.reload(payment_ui_module)
importlib.reload(payment_common_module)
importlib.reload(donate_ui_module)

from cogs.admin_command_utils import create_error_splash, create_success_splash, format_vnd, parse_vnd_amount
from cogs.user.payment_common import (
    DonateLeaderboardView,
    PaymentReloadView,
    finalize_cash_donation,
    finalize_paid_payment,
    refresh_donate_leaderboard,
)
from cogs.user_command_utils import UserCommandBase
from services.bank_service import BankPaymentService
from ui.user.payment_ui import (
    build_bank_balance_embed,
    build_config_status_embed,
    build_donate_leaderboard_embed,
    build_payment_embed,
    render_payment_card,
)
from ui.user.donate_ui import DonateFormLauncherView, DonateModal, DonateModeView


CHECK_WORDS = {"check", "kiemtra", "kiểmtra", "kt", "xacnhan", "xácnhận"}
BALANCE_WORDS = {"reload", "sodu", "sốdư", "số-dư", "balance", "bank", "bankbalance"}
CONFIG_WORDS = {"config", "cfg", "setup", "cauhinh", "cấuhình", "cấu-hình"}
TOP_WORDS = {"top", "bxh", "rank", "leaderboard", "bangxephang", "bảngxếphạng"}
RESET_WORDS = {"reset", "rs", "clear", "monthlyreset", "resetmonth", "resetthang", "resettháng"}
BANK_WORDS = {"bank", "banking", "qr", "ck", "chuyenkhoan", "chuyểnkhoản"}
CASH_WORDS = {"cash", "c"}


class DonateCog(UserCommandBase):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.bank = BankPaymentService()
        self._restore_views_task = bot.loop.create_task(self._restore_leaderboard_views())

    def cog_unload(self):
        if self._restore_views_task and not self._restore_views_task.done():
            self._restore_views_task.cancel()

    async def _restore_leaderboard_views(self) -> None:
        try:
            await self.bot.wait_until_ready()
            for row in self.bank.get_donate_leaderboard_messages():
                self.bot.add_view(
                    DonateLeaderboardView(
                        self.bot,
                        self.bank,
                        int(row["guild_id"]),
                        timeout=None,
                    ),
                    message_id=int(row["donate_leaderboard_message_id"]),
                )
        except asyncio.CancelledError:
            return

    async def _send_payment(self, target, amount_text: str, donor_message: str = ""):
        guild = target.guild
        if guild is None:
            await self._send_target_embed(target, create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh donate chỉ hoạt động trong server."))
            return None
        if not self.bank.is_configured(guild.id):
            await self._send_target_embed(
                target,
                create_error_splash(
                    "❌ Chưa Cấu Hình ACB",
                    "Bot admin cần dùng `donate config username|password|account|name ...` trước.",
                ),
            )
            return None

        try:
            amount = parse_vnd_amount(amount_text)
        except ValueError as exc:
            await self._send_target_embed(target, create_error_splash("❌ Số Tiền Không Hợp Lệ", str(exc)))
            return None

        settings = self.bank.get_settings(guild.id) or {}
        user = target.author if isinstance(target, commands.Context) else target.user
        payment = self.bank.create_payment(
            guild.id,
            user.id,
            user.display_name,
            "donate",
            amount,
            donor_message=donor_message,
        )
        card = await asyncio.to_thread(render_payment_card, payment, settings, "donate")
        embed = build_payment_embed(payment, settings, "donate", card is not None)
        view = PaymentReloadView(self, int(payment["id"]), user.id)

        if isinstance(target, commands.Context):
            message = await target.send(embed=embed, file=card, view=view) if card else await target.send(embed=embed, view=view)
        else:
            message = (
                await target.followup.send(embed=embed, file=card, view=view, wait=True)
                if card
                else await target.followup.send(embed=embed, view=view, wait=True)
            )
        self.bank.mark_message(int(payment["id"]), message.channel.id, message.id)
        return payment

    async def _send_target_embed(self, target, embed: discord.Embed, *, view: discord.ui.View | None = None):
        if isinstance(target, commands.Context):
            return await target.send(embed=embed, view=view)
        if target.response.is_done():
            return await target.followup.send(embed=embed, view=view, wait=True)
        await target.response.send_message(embed=embed, view=view)
        return await target.original_response()

    async def process_donation(self, target, mode: str, amount_text: str, donor_message: str = ""):
        guild = target.guild
        if guild is None:
            await self._send_target_embed(
                target,
                create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh donate chỉ hoạt động trong server."),
            )
            return None

        mode = "cash" if str(mode).lower() == "cash" else "bank"
        donor_message = str(donor_message or "").strip()[:500]
        if mode == "bank":
            return await self._send_payment(target, amount_text, donor_message)

        try:
            amount = parse_vnd_amount(amount_text)
        except ValueError as exc:
            await self._send_target_embed(target, create_error_splash("❌ Số Tiền Không Hợp Lệ", str(exc)))
            return None

        user = target.author if isinstance(target, commands.Context) else target.user
        if not isinstance(user, discord.Member):
            user = guild.get_member(user.id)
        if not user:
            await self._send_target_embed(target, create_error_splash("❌ Không Tìm Thấy User", "Không lấy được member để trừ cash."))
            return None

        try:
            donation = await finalize_cash_donation(
                self.bot,
                self.bank,
                self.service,
                guild,
                user,
                amount,
                donor_message,
            )
        except ValueError as exc:
            await self._send_target_embed(target, create_error_splash("❌ Donate Cash Thất Bại", str(exc)))
            return None

        detail = f"Đã trừ `{format_vnd(amount)} VNĐ` cash và ghi nhận donate cho **{guild.name}**."
        if donor_message:
            detail += f"\nLời nhắn: {donor_message}"
        await self._send_target_embed(target, create_success_splash("✅ Donate Cash Thành Công", detail))
        return donation

    async def _show_donate_form(self, ctx: commands.Context, mode: str | None = None):
        if mode:
            label = "Cash" if mode == "cash" else "Bank / QR"
            await ctx.send(
                embed=create_success_splash("💝 Biểu Mẫu Donate", f"Bấm nút bên dưới để nhập số tiền và lời nhắn bằng **{label}**."),
                view=DonateFormLauncherView(self, ctx.author.id, mode),
            )
            return
        await ctx.send(
            embed=create_success_splash("💝 Chọn Hình Thức Donate", "Chọn **Bank / QR** hoặc **Cash**, sau đó nhập số tiền và lời nhắn."),
            view=DonateModeView(self, ctx.author.id),
        )

    async def _resolve_payment_for_check(self, guild_id: int, user_id: int, raw: str | None) -> dict | None:
        if raw:
            raw = raw.strip()
            return self.bank.get_payment(int(raw)) if raw.isdigit() else self.bank.get_payment_by_code(raw)
        pending = [
            payment
            for payment in self.bank.get_user_pending_payments(guild_id, user_id, limit=10)
            if payment.get("kind") == "donate"
        ]
        return pending[0] if pending else None

    async def _check_payment(self, target, raw: str | None = None):
        guild = target.guild
        user = target.author if isinstance(target, commands.Context) else target.user
        if guild is None:
            await target.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Kiểm tra donate chỉ hoạt động trong server."))
            return

        payment = await self._resolve_payment_for_check(guild.id, user.id, raw)
        if not payment:
            await target.send(embed=create_error_splash("❌ Không Có Payment", "Bạn chưa có QR donate pending để kiểm tra."))
            return
        if int(payment["guild_id"]) != guild.id:
            await target.send(embed=create_error_splash("❌ Sai Server", "Payment này không thuộc server hiện tại."))
            return
        if int(payment["user_id"]) != user.id and not self.can_manage_cash(target):
            await target.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Bạn không thể kiểm tra payment của người khác."))
            return

        result = await self.bank.check_payment_online(guild.id, payment["code"], int(payment["amount"]))
        if result.get("matched"):
            paid = await finalize_paid_payment(
                self.bot,
                self.bank,
                self.service,
                payment,
                transaction=result.get("transaction"),
            )
            if paid:
                await target.send(embed=create_success_splash("✅ Donate Thành Công", "Donation đã được xác nhận và ghi nhận cho server. Khoản này không cộng vào cash."))
            return
        detail = result.get("error") or "Chưa thấy giao dịch khớp số tiền và nội dung chuyển khoản."
        await target.send(embed=create_error_splash("❌ Chưa Nhận Được Tiền", detail))

    async def _show_bank_balance(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Reload số dư ngân hàng chỉ hoạt động trong server."))
            return
        if not self.can_manage_cash(ctx):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ hard admin, cash-admin hoặc role có quyền `cash` mới được reload số dư tài khoản ngân hàng."))
            return
        if not self.bank.is_configured(ctx.guild.id):
            await ctx.send(
                embed=create_error_splash(
                    "❌ Chưa Cấu Hình ACB",
                    "Cần cấu hình `username`, `password` và `account` trước khi xem số dư.",
                )
            )
            return
        result = await self.bank.get_bank_balance_online(ctx.guild.id)
        if not result.get("matched"):
            await ctx.send(embed=create_error_splash("❌ Không Lấy Được Số Dư", result.get("error") or "ACB không trả về số dư."))
            return
        settings = self.bank.get_settings(ctx.guild.id) or {}
        await ctx.send(embed=build_bank_balance_embed(result, settings))

    async def _show_donate_leaderboard(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Bảng donate chỉ hoạt động trong server."))
            return
        rows = self.bank.get_donate_leaderboard(ctx.guild.id, limit=50)
        await ctx.send(
            embed=build_donate_leaderboard_embed(rows, ctx.guild, page=0),
            view=DonateLeaderboardView(self.bot, self.bank, ctx.guild.id, page=0),
        )

    async def _reset_donate_leaderboard(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Reset donate chỉ hoạt động trong server."))
            return
        if not self.can_manage_cash(ctx):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ hard admin, cash-admin hoặc role có quyền `cash` mới được reset bảng donate."))
            return

        rows = self.bank.reset_donate_leaderboard(ctx.guild.id)
        total = sum(int(row.get("amount") or 0) for row in rows)
        lines = [
            f"📊 Bảng donate trước khi reset của {ctx.guild.name}",
            f"Tổng người: {len(rows)}",
            f"Tổng tiền: {format_vnd(total)} VNĐ",
            "",
        ]
        if rows:
            for index, row in enumerate(rows, start=1):
                lines.append(
                    f"#{index} {row.get('username') or row['user_id']} ({row['user_id']}) - "
                    f"{format_vnd(int(row.get('amount') or 0))} VNĐ · {int(row.get('donate_count') or 0)} lần"
                )
        else:
            lines.append("Chưa có dữ liệu donate để reset.")

        chunks: list[str] = []
        current: list[str] = []
        for line in lines:
            candidate = "\n".join([*current, line])
            if current and len(candidate) > 1900:
                chunks.append("\n".join(current))
                current = [line]
            else:
                current.append(line)
        if current:
            chunks.append("\n".join(current))

        try:
            for chunk in chunks:
                await ctx.author.send(chunk)
        except (discord.Forbidden, discord.HTTPException):
            pass

        await refresh_donate_leaderboard(self.bot, self.bank, ctx.guild)
        await ctx.send(
            embed=create_success_splash(
                "✅ Đã Reset BXH Donate",
                f"Đã gửi chi tiết `{len(rows)}` người về DMs admin. Bảng hiển thị tháng này đã về trắng.",
            )
        )

    async def check_and_finalize_payment(self, interaction: discord.Interaction, payment_id: int):
        payment = self.bank.get_payment(payment_id)
        if not payment:
            await interaction.followup.send(embed=create_error_splash("❌ Không Tìm Thấy", "Không tìm thấy payment này."), ephemeral=True)
            return
        result = await self.bank.check_payment_online(int(payment["guild_id"]), payment["code"], int(payment["amount"]))
        if result.get("matched"):
            await finalize_paid_payment(
                self.bot,
                self.bank,
                self.service,
                payment,
                transaction=result.get("transaction"),
                interaction=interaction,
            )
            return
        detail = result.get("error") or "Chưa thấy giao dịch khớp số tiền và nội dung chuyển khoản."
        await interaction.followup.send(embed=create_error_splash("❌ Chưa Nhận Được Tiền", detail), ephemeral=True)

    async def _handle_config(self, ctx: commands.Context, args: tuple[str, ...]):
        if not self.can_manage_cash(ctx):
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ hard admin, cash-admin hoặc role có quyền `cash` mới được cấu hình donate/ngân hàng."))
            return
        if not args or args[0].lower() in {"show", "status", "info"}:
            await ctx.send(embed=build_config_status_embed(self.bank.get_settings(ctx.guild.id) or {}))
            return

        key = args[0].lower()
        value = " ".join(args[1:]).strip()
        if key in {"channel", "thankchannel", "thankschannel", "kenh", "kênh"}:
            if not value or value.lower() in {"off", "none", "xoa", "xoá"}:
                self.bank.set_donate_channel(ctx.guild.id, None)
                await ctx.send(embed=create_success_splash("✅ Đã Tắt Kênh Cảm Ơn", "Donate vẫn được ghi nhận nhưng không gửi lời cảm ơn ra kênh."))
                return
            try:
                channel = await commands.TextChannelConverter().convert(ctx, value)
            except commands.BadArgument:
                await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy Kênh", "Dùng: `donate config channel #channel`."))
                return
            self.bank.set_donate_channel(ctx.guild.id, channel.id)
            await ctx.send(embed=create_success_splash("✅ Đã Set Kênh Cảm Ơn", f"Donate sẽ cảm ơn tại {channel.mention}."))
            return

        if key in {"leaderboard", "top", "rank", "bxh", "leaderboardchannel", "topchannel", "rankchannel"}:
            if not value or value.lower() in {"off", "none", "xoa", "xoá"}:
                self.bank.set_donate_leaderboard_channel(ctx.guild.id, None)
                await ctx.send(embed=create_success_splash("✅ Đã Tắt BXH Donate", "Donate vẫn được ghi nhận nhưng không cập nhật bảng xếp hạng."))
                return
            try:
                channel = await commands.TextChannelConverter().convert(ctx, value)
            except commands.BadArgument:
                await ctx.send(embed=create_error_splash("❌ Không Tìm Thấy Kênh", "Dùng: `donate config leaderboard #channel`."))
                return
            self.bank.set_donate_leaderboard_channel(ctx.guild.id, channel.id)
            await refresh_donate_leaderboard(self.bot, self.bank, ctx.guild)
            await ctx.send(embed=create_success_splash("✅ Đã Set BXH Donate", f"Bảng xếp hạng donate sẽ cập nhật tại {channel.mention}."))
            return

        if key in {"thank", "thanks", "template", "thanks_template", "camon", "cảmơn"}:
            if not value:
                await ctx.send(
                    embed=create_error_splash(
                        "❌ Thiếu Nội Dung",
                        "Dùng: `donate config thanks Cảm ơn {user} đã donate {amount} VNĐ! {message}`.",
                    )
                )
                return
            self.bank.set_donate_template(ctx.guild.id, value)
            await ctx.send(embed=create_success_splash("✅ Đã Set Lời Cảm Ơn", value))
            return

        if key == "decor":
            key = "donate_decor"
            if not value and ctx.message.attachments:
                value = ctx.message.attachments[0].url
        if key == "auto":
            value = value or "on"
        if not value:
            await ctx.send(embed=create_error_splash("❌ Thiếu Giá Trị", "Dùng: `donate config <key> <value>`."))
            return
        try:
            self.bank.set_setting(ctx.guild.id, key, value)
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Config Lỗi", str(exc)))
            return
        shown = "`Đã set`" if key in {"password", "pass"} else f"`{value}`"
        await ctx.send(embed=create_success_splash("✅ Đã Cập Nhật Donate Config", f"`{key}` = {shown}"))

    @commands.command(name="donate", aliases=["dn", "dnt"])
    async def donate(self, ctx: commands.Context, *args):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh donate chỉ hoạt động trong server."))
            return
        if not args:
            await self._show_donate_form(ctx)
            return

        first = args[0].lower()
        if first in CONFIG_WORDS:
            await self._handle_config(ctx, args[1:])
            return
        if first in TOP_WORDS:
            await self._show_donate_leaderboard(ctx)
            return
        if first in RESET_WORDS:
            await self._reset_donate_leaderboard(ctx)
            return
        if first in BALANCE_WORDS:
            await self._show_bank_balance(ctx)
            return
        if first in CHECK_WORDS:
            await self._check_payment(ctx, args[1] if len(args) > 1 else None)
            return
        if first in BANK_WORDS | CASH_WORDS:
            mode = "cash" if first in CASH_WORDS else "bank"
            if len(args) == 1:
                await self._show_donate_form(ctx, mode)
                return
            amount_text = args[1]
            donor_message = " ".join(args[2:])
        else:
            amount_text = args[0]
            if len(args) > 1 and args[1].lower() in CASH_WORDS:
                mode = "cash"
                donor_message = " ".join(args[2:])
            else:
                mode = "bank"
                donor_message = " ".join(args[1:])
        await self.process_donation(ctx, mode, amount_text, donor_message)

    @app_commands.command(name="donate", description="Tạo QR donate")
    @app_commands.describe(
        amount="Số tiền donate, ví dụ 100k hoặc 100,000",
        method="Hình thức donate",
        message="Lời nhắn gửi tới server",
    )
    @app_commands.choices(
        method=[
            app_commands.Choice(name="Bank / QR", value="bank"),
            app_commands.Choice(name="Cash", value="cash"),
        ]
    )
    async def slash_donate(
        self,
        interaction: discord.Interaction,
        amount: str | None = None,
        method: app_commands.Choice[str] | None = None,
        message: str | None = None,
    ):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Chỉ dùng trong server.", ephemeral=True)
            return
        selected_mode = method.value if method else "bank"
        if not amount:
            if method:
                await interaction.response.send_modal(DonateModal(self, selected_mode))
            else:
                await interaction.response.send_message(
                    embed=create_success_splash("💝 Chọn Hình Thức Donate", "Chọn **Bank / QR** hoặc **Cash** để mở biểu mẫu."),
                    view=DonateModeView(self, interaction.user.id),
                    ephemeral=True,
                )
            return
        await interaction.response.defer(thinking=True)
        await self.process_donation(interaction, selected_mode, amount, message or "")


async def setup(bot):
    await bot.add_cog(DonateCog(bot))
