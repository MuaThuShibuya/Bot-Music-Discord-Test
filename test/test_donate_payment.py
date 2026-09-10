from types import SimpleNamespace
from io import BytesIO
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from PIL import Image

from cogs.user.donate_cog import DonateCog
from cogs.user.payment_common import finalize_cash_donation, finalize_paid_payment
from ui.user.payment_ui import CARD_SIZE, _fetch_image, build_paid_embed, build_payment_embed, render_payment_card


class DonatePaymentFinalizeTest(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _paid_payment(kind: str) -> dict:
        return {
            "id": 1,
            "guild_id": 777,
            "user_id": 42,
            "username": "Donor",
            "kind": kind,
            "amount": 10_000,
            "code": "BLTEST",
            "status": "paid",
            "donor_message": "Chúc server vui vẻ",
        }

    async def test_bank_donate_records_donation_without_adding_cash(self):
        pending = {**self._paid_payment("donate"), "status": "pending"}
        paid = self._paid_payment("donate")
        bank = MagicMock()
        bank.get_payment.return_value = pending
        bank.mark_paid.return_value = paid
        bot = MagicMock()
        bot.get_guild.return_value = None
        bot.fetch_user = AsyncMock(return_value=SimpleNamespace(id=42, display_name="Donor", mention="<@42>"))
        users = MagicMock()

        result = await finalize_paid_payment(bot, bank, users, pending)

        self.assertEqual(result, paid)
        users.add_total_donate.assert_called_once_with(42, 10_000)
        bank.add_donate_leaderboard.assert_called_once_with(777, 42, "Donor", 10_000)
        users.add_cash.assert_not_called()
        users.add_total_money.assert_not_called()

    async def test_naptien_still_adds_cash_and_total_money(self):
        pending = {**self._paid_payment("naptien"), "status": "pending"}
        paid = self._paid_payment("naptien")
        bank = MagicMock()
        bank.get_payment.return_value = pending
        bank.mark_paid.return_value = paid
        bot = MagicMock()
        bot.get_guild.return_value = None
        bot.fetch_user = AsyncMock(return_value=SimpleNamespace(id=42, display_name="Donor", mention="<@42>"))
        users = MagicMock()

        await finalize_paid_payment(bot, bank, users, pending)

        users.add_cash.assert_called_once_with(42, 10_000)
        users.add_total_money.assert_called_once_with(42, 10_000)
        users.add_total_donate.assert_not_called()
        bank.add_donate_leaderboard.assert_not_called()

    async def test_cash_donate_deducts_wallet_and_records_donation(self):
        bot = MagicMock()
        bank = MagicMock()
        users = MagicMock()
        users.touch_user.return_value = SimpleNamespace(cash=50_000)
        guild = MagicMock(spec=discord.Guild)
        guild.id = 777
        guild.name = "Test Guild"
        user = MagicMock(spec=discord.Member)
        user.id = 42
        user.display_name = "Donor"

        with (
            patch("cogs.user.payment_common._send_donate_thanks", new=AsyncMock()) as send_thanks,
            patch("cogs.user.payment_common.refresh_donate_leaderboard", new=AsyncMock()) as refresh_board,
            patch("cogs.user.payment_common.send_cash_log", new=AsyncMock()) as send_log,
        ):
            donation = await finalize_cash_donation(
                bot,
                bank,
                users,
                guild,
                user,
                10_000,
                "Cảm ơn server",
            )

        self.assertEqual(donation["kind"], "donate_cash")
        users.remove_cash.assert_called_once_with(42, 10_000)
        users.add_total_donate.assert_called_once_with(42, 10_000)
        users.add_cash.assert_not_called()
        bank.add_donate_leaderboard.assert_called_once_with(777, 42, "Donor", 10_000)
        send_thanks.assert_awaited_once()
        refresh_board.assert_awaited_once()
        send_log.assert_awaited_once()

    async def test_cash_donate_rejects_insufficient_balance(self):
        users = MagicMock()
        users.touch_user.return_value = SimpleNamespace(cash=5_000)
        guild = MagicMock(spec=discord.Guild)
        guild.id = 777
        guild.name = "Test Guild"
        user = MagicMock(spec=discord.Member)
        user.id = 42
        user.display_name = "Donor"

        with self.assertRaises(ValueError):
            await finalize_cash_donation(MagicMock(), MagicMock(), users, guild, user, 10_000)

        users.remove_cash.assert_not_called()
        users.add_total_donate.assert_not_called()


class PaymentCardTest(unittest.TestCase):
    def test_fetch_image_decodes_http_response(self):
        source = BytesIO()
        Image.new("RGB", (20, 20), "pink").save(source, format="PNG")
        response = MagicMock()
        response.content = source.getvalue()

        with patch("ui.user.payment_ui.requests.get", return_value=response) as request:
            image = _fetch_image("https://example.com/card.png")

        self.assertIsNotNone(image)
        self.assertEqual(image.size, (20, 20))
        response.raise_for_status.assert_called_once_with()
        request.assert_called_once_with("https://example.com/card.png", timeout=12)

    def test_card_has_room_for_account_name(self):
        payment = {
            "id": 1,
            "amount": 10_000,
            "code": "BL12345678901234567890",
            "qr_url": "https://example.com/qr.png",
        }
        settings = {
            "bank_code": "ACB",
            "account_number": "26309901",
            "account_name": "HA MAC TRUONG GIANG",
        }
        qr = Image.new("RGBA", (400, 400), "white")
        with (
            patch("ui.user.payment_ui._fetch_image", side_effect=[None, qr]),
            patch("ui.user.payment_ui._local_decor", return_value=None),
        ):
            card = render_payment_card(payment, settings, "donate")

        self.assertIsNotNone(card)
        rendered = Image.open(card.fp)
        self.assertEqual(rendered.size, CARD_SIZE)
        self.assertEqual(CARD_SIZE, (980, 620))

    def test_card_preserves_full_tall_qr_image(self):
        payment = {
            "id": 2,
            "amount": 100_000,
            "code": "BL123456789012345678901234567890",
            "qr_url": "https://example.com/qr.png",
        }
        settings = {
            "bank_code": "ACB",
            "account_number": "50126497",
            "account_name": "PHAN THANH LOI",
        }
        qr = Image.new("RGBA", (200, 400), "red")
        qr.paste("blue", (0, 200, 200, 400))

        with (
            patch("ui.user.payment_ui._fetch_image", side_effect=[None, qr]),
            patch("ui.user.payment_ui._local_decor", return_value=None),
        ):
            card = render_payment_card(payment, settings, "naptien")

        rendered = Image.open(card.fp).convert("RGB")
        top = rendered.getpixel((288, 170))
        bottom = rendered.getpixel((288, 490))
        self.assertGreater(top[0], top[2], "Phần trên của QR/VietQR đã bị crop")
        self.assertGreater(bottom[2], bottom[0], "Phần dưới của QR đã bị crop")

    def test_donate_embeds_explain_no_cash_credit(self):
        payment = {
            "id": 1,
            "amount": 10_000,
            "code": "BLTEST",
            "donor_message": "Cảm ơn server",
            "qr_url": "https://example.com/qr.png",
        }
        settings = {
            "bank_code": "ACB",
            "account_number": "26309901",
            "account_name": "HA MAC TRUONG GIANG",
        }

        pending = build_payment_embed(payment, settings, "donate", False)
        paid = build_paid_embed(payment, "donate")

        self.assertIn("Chủ tài khoản", [field.name for field in pending.fields])
        self.assertIn("Lời nhắn", [field.name for field in pending.fields])
        self.assertIn("không cộng vào cash", paid.description.lower())


class DonateCommandParsingTest(unittest.IsolatedAsyncioTestCase):
    def make_cog_and_context(self):
        cog = DonateCog.__new__(DonateCog)
        cog.process_donation = AsyncMock()
        cog._show_donate_form = AsyncMock()
        ctx = MagicMock()
        ctx.guild = SimpleNamespace(id=777)
        return cog, ctx

    async def test_cash_mode_before_amount(self):
        cog, ctx = self.make_cog_and_context()

        await DonateCog.donate.callback(cog, ctx, "cash", "10k", "Cảm", "ơn")

        cog.process_donation.assert_awaited_once_with(ctx, "cash", "10k", "Cảm ơn")

    async def test_qr_mode_before_amount(self):
        cog, ctx = self.make_cog_and_context()

        await DonateCog.donate.callback(cog, ctx, "qr", "10k", "Ủng", "hộ")

        cog.process_donation.assert_awaited_once_with(ctx, "bank", "10k", "Ủng hộ")

    async def test_cash_mode_after_amount(self):
        cog, ctx = self.make_cog_and_context()

        await DonateCog.donate.callback(cog, ctx, "10k", "cash", "Hello")

        cog.process_donation.assert_awaited_once_with(ctx, "cash", "10k", "Hello")

    async def test_no_arguments_opens_mode_form(self):
        cog, ctx = self.make_cog_and_context()

        await DonateCog.donate.callback(cog, ctx)

        cog._show_donate_form.assert_awaited_once_with(ctx)


if __name__ == "__main__":
    unittest.main()
