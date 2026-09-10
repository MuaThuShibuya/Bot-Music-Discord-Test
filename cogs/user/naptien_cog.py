from __future__ import annotations

import asyncio
import importlib

import discord
from discord import app_commands
from discord.ext import commands

import cogs.user.payment_common as payment_common_module
import services.bank_service as bank_service_module
import ui.user.payment_ui as payment_ui_module

# Keep bank/payment dependencies fresh when this extension is hot-reloaded.
importlib.reload(bank_service_module)
importlib.reload(payment_ui_module)
importlib.reload(payment_common_module)

from cogs.admin_command_utils import create_error_splash, create_success_splash, parse_vnd_amount
from cogs.user.payment_common import PaymentReloadView, finalize_paid_payment
from cogs.user_command_utils import UserCommandBase
from services.bank_service import BankPaymentService
from ui.user.payment_ui import build_bank_balance_embed, build_config_status_embed, build_payment_embed, render_payment_card


CHECK_WORDS = {"check", "kiemtra", "kiểmtra", "kt", "xacnhan", "xácnhận"}
BALANCE_WORDS = {"reload", "sodu", "sốdư", "số-dư", "balance", "bank", "bankbalance"}
CONFIG_WORDS = {"config", "cfg", "setup", "cauhinh", "cấuhình", "cấu-hình"}


class NapTienCog(UserCommandBase):
    def __init__(self, bot: commands.Bot):
        super().__init__(bot)
        self.bank = BankPaymentService()
        self._auto_task = bot.loop.create_task(self._auto_check_loop())

    def cog_unload(self):
        self._auto_task.cancel()

    async def _auto_check_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._check_pending_payments()
            except Exception as exc:
                print(f"❌ Lỗi auto check ACB: {exc}")
            await asyncio.sleep(5)

    async def _check_pending_payments(self):
        for payment in self.bank.get_pending_payments(limit=80):
            guild = self.bot.get_guild(int(payment["guild_id"]))
            if not guild:
                continue
            settings = self.bank.get_settings(guild.id) or {}
            if not int(settings.get("auto_check_enabled") or 0):
                continue
            result = await self.bank.check_payment_online(guild.id, payment["code"], int(payment["amount"]))
            if result.get("matched"):
                await finalize_paid_payment(
                    self.bot,
                    self.bank,
                    self.service,
                    payment,
                    transaction=result.get("transaction"),
                )

    async def _send_payment(self, target, amount_text: str, *, kind: str = "naptien"):
        guild = target.guild
        if guild is None:
            await target.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh nạp tiền chỉ hoạt động trong server."))
            return None
        if not self.bank.is_configured(guild.id):
            await target.send(
                embed=create_error_splash(
                    "❌ Chưa Cấu Hình ACB",
                    "Bot admin cần dùng `naptien config username|password|account|name ...` trước.",
                )
            )
            return None

        try:
            amount = parse_vnd_amount(amount_text)
        except ValueError as exc:
            await target.send(embed=create_error_splash("❌ Số Tiền Không Hợp Lệ", str(exc)))
            return None

        settings = self.bank.get_settings(guild.id) or {}
        user = target.author if isinstance(target, commands.Context) else target.user
        payment = self.bank.create_payment(guild.id, user.id, user.display_name, kind, amount)
        card = await asyncio.to_thread(render_payment_card, payment, settings, kind)
        embed = build_payment_embed(payment, settings, kind, card is not None)
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

    async def _resolve_payment_for_check(self, guild_id: int, user_id: int, raw: str | None) -> dict | None:
        if raw:
            raw = raw.strip()
            payment = self.bank.get_payment(int(raw)) if raw.isdigit() else self.bank.get_payment_by_code(raw)
            return payment
        pending = self.bank.get_user_pending_payments(guild_id, user_id, limit=1)
        return pending[0] if pending else None

    async def _check_payment(self, target, raw: str | None = None):
        guild = target.guild
        user = target.author if isinstance(target, commands.Context) else target.user
        if guild is None:
            await target.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Kiểm tra giao dịch chỉ hoạt động trong server."))
            return

        payment = await self._resolve_payment_for_check(guild.id, user.id, raw)
        if not payment:
            await target.send(embed=create_error_splash("❌ Không Có Payment", "Bạn chưa có QR pending để kiểm tra."))
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
                await target.send(embed=create_success_splash("✅ Đã Cộng Cash", "Giao dịch đã được xác nhận và cộng vào cash."))
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
            await ctx.send(embed=create_error_splash("❌ Quyền Bị Từ Chối", "Chỉ hard admin, cash-admin hoặc role có quyền `cash` mới được cấu hình ngân hàng."))
            return
        if not args or args[0].lower() in {"show", "status", "info"}:
            await ctx.send(embed=build_config_status_embed(self.bank.get_settings(ctx.guild.id) or {}))
            return

        key = args[0].lower()
        value = " ".join(args[1:]).strip()
        if key == "decor":
            key = "deposit_decor"
            if not value and ctx.message.attachments:
                value = ctx.message.attachments[0].url
        if key == "auto":
            value = value or "on"
        if not value:
            await ctx.send(embed=create_error_splash("❌ Thiếu Giá Trị", "Dùng: `naptien config <key> <value>`."))
            return
        try:
            self.bank.set_setting(ctx.guild.id, key, value)
        except Exception as exc:
            await ctx.send(embed=create_error_splash("❌ Config Lỗi", str(exc)))
            return
        shown = "`Đã set`" if key in {"password", "pass"} else f"`{value}`"
        await ctx.send(embed=create_success_splash("✅ Đã Cập Nhật Bank Config", f"`{key}` = {shown}"))

    @commands.command(name="naptien", aliases=["nap"])
    async def naptien(self, ctx: commands.Context, *args):
        if ctx.guild is None:
            await ctx.send(embed=create_error_splash("❌ Chỉ Dùng Trong Server", "Lệnh nạp tiền chỉ hoạt động trong server."))
            return
        if not args:
            await ctx.send(embed=create_error_splash("❌ Thiếu Số Tiền", "Dùng: `naptien 100k`, `naptien check` hoặc `naptien reload`."))
            return

        first = args[0].lower()
        if first in CONFIG_WORDS:
            await self._handle_config(ctx, args[1:])
            return
        if first in BALANCE_WORDS:
            await self._show_bank_balance(ctx)
            return
        if first in CHECK_WORDS:
            await self._check_payment(ctx, args[1] if len(args) > 1 else None)
            return
        await self._send_payment(ctx, " ".join(args), kind="naptien")

    @app_commands.command(name="naptien", description="Tạo QR nạp cash")
    @app_commands.describe(amount="Số tiền cần nạp, ví dụ 100k hoặc 100,000")
    async def slash_naptien(self, interaction: discord.Interaction, amount: str):
        if interaction.guild is None:
            await interaction.response.send_message("❌ Chỉ dùng trong server.", ephemeral=True)
            return
        await interaction.response.defer(thinking=True)
        await self._send_payment(interaction, amount, kind="naptien")


async def setup(bot):
    await bot.add_cog(NapTienCog(bot))
