from __future__ import annotations

import discord
from discord.ext import commands

from cogs.admin_command_utils import create_error_splash, create_success_splash, format_vnd
from cogs.cash_log_utils import send_cash_log
from services.bank_service import BankPaymentService
from services.user_service import UserService
from ui.user.payment_ui import build_donate_leaderboard_embed, build_paid_embed


async def send_interaction_notice(
    interaction: discord.Interaction,
    *,
    embed: discord.Embed | None = None,
    content: str | None = None,
    ephemeral: bool = True,
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(content=content, embed=embed, ephemeral=ephemeral)


class DonateLeaderboardView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        bank: BankPaymentService,
        guild_id: int,
        *,
        page: int = 0,
        timeout: float | None = None,
    ):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.bank = bank
        self.guild_id = int(guild_id)
        self.page = max(0, int(page))

    async def _render(self, interaction: discord.Interaction, page: int) -> None:
        rows = self.bank.get_donate_leaderboard(self.guild_id, limit=50)
        total_pages = max(1, (len(rows) + 9) // 10)
        self.page = max(0, min(page, total_pages - 1))
        guild = self.bot.get_guild(self.guild_id)
        await interaction.response.edit_message(
            embed=build_donate_leaderboard_embed(rows, guild, page=self.page),
            view=DonateLeaderboardView(self.bot, self.bank, self.guild_id, page=self.page),
        )

    @discord.ui.button(
        label="Lùi",
        emoji="◀️",
        style=discord.ButtonStyle.secondary,
        custom_id="donate_leaderboard:previous",
    )
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, self.page - 1)

    @discord.ui.button(
        label="Tiếp",
        emoji="▶️",
        style=discord.ButtonStyle.secondary,
        custom_id="donate_leaderboard:next",
    )
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._render(interaction, self.page + 1)


async def refresh_donate_leaderboard(bot: commands.Bot, bank: BankPaymentService, guild: discord.Guild | None) -> None:
    if not guild:
        return
    settings = bank.get_settings(guild.id) or {}
    channel_id = settings.get("donate_leaderboard_channel_id")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        return

    rows = bank.get_donate_leaderboard(guild.id, limit=50)
    embed = build_donate_leaderboard_embed(rows, guild, page=0)
    view = DonateLeaderboardView(bot, bank, guild.id, page=0)
    message_id = settings.get("donate_leaderboard_message_id")
    if message_id:
        try:
            message = await channel.fetch_message(int(message_id))
            await message.edit(embed=embed, view=view)
            return
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            bank.set_donate_leaderboard_message(guild.id, None)

    try:
        message = await channel.send(embed=embed, view=view)
        bank.set_donate_leaderboard_message(guild.id, message.id)
    except (discord.Forbidden, discord.HTTPException):
        pass


async def _resolve_payment_user(bot: commands.Bot, guild: discord.Guild | None, payment: dict):
    user_id = int(payment["user_id"])
    if guild:
        member = guild.get_member(user_id)
        if member:
            return member
    try:
        return await bot.fetch_user(user_id)
    except (discord.NotFound, discord.HTTPException):
        return None


async def finalize_paid_payment(
    bot: commands.Bot,
    bank: BankPaymentService,
    users: UserService,
    payment: dict,
    *,
    transaction: dict | None = None,
    interaction: discord.Interaction | None = None,
) -> dict | None:
    latest = bank.get_payment(int(payment["id"]))
    if not latest:
        if interaction:
            await send_interaction_notice(
                interaction,
                embed=create_error_splash("❌ Không Tìm Thấy", "Không tìm thấy payment này trong database."),
            )
        return None
    if latest.get("status") == "paid":
        if interaction:
            already_text = (
                "Donation này đã được ghi nhận trước đó."
                if latest.get("kind") == "donate"
                else "Payment này đã được cộng cash trước đó."
            )
            await send_interaction_notice(
                interaction,
                embed=create_success_splash("✅ Đã Thanh Toán", already_text),
            )
        return latest

    paid = bank.mark_paid(int(latest["id"]), transaction)
    if not paid:
        current = bank.get_payment(int(latest["id"]))
        if current and current.get("status") == "paid":
            if interaction:
                already_text = (
                    "Donation này đã được ghi nhận trước đó."
                    if current.get("kind") == "donate"
                    else "Payment này đã được cộng cash trước đó."
                )
                await send_interaction_notice(
                    interaction,
                    embed=create_success_splash("✅ Đã Thanh Toán", already_text),
                )
            return current
        if interaction:
            failure_title = "❌ Không Thể Ghi Nhận Donate" if latest.get("kind") == "donate" else "❌ Không Thể Cộng Cash"
            await send_interaction_notice(
                interaction,
                embed=create_error_splash(failure_title, "Payment này không còn ở trạng thái chờ."),
            )
        return current

    guild = bot.get_guild(int(paid["guild_id"]))
    user = await _resolve_payment_user(bot, guild, paid)
    username = getattr(user, "display_name", paid.get("username") or str(paid["user_id"]))
    users.get_or_create_user(int(paid["user_id"]), username)
    is_donate = paid.get("kind") == "donate"
    if is_donate:
        users.add_total_donate(int(paid["user_id"]), int(paid["amount"]))
        bank.add_donate_leaderboard(int(paid["guild_id"]), int(paid["user_id"]), username, int(paid["amount"]))
    else:
        users.add_cash(int(paid["user_id"]), int(paid["amount"]))
        users.add_total_money(int(paid["user_id"]), int(paid["amount"]))

    await _edit_payment_message(bot, paid, user)
    await _send_payment_success_dm(paid, user, guild)
    await _send_donate_thanks(bot, bank, paid, user)
    if is_donate:
        await refresh_donate_leaderboard(bot, bank, guild)

    tx_id = bank._transaction_id(transaction or {}) if transaction else paid.get("bank_transaction_id")
    tx_note = bank._transaction_text(transaction or {}) if transaction else paid.get("bank_description")
    await send_cash_log(
        guild,
        title="💝 Donate Thành Công" if paid.get("kind") == "donate" else "💳 Nạp Tiền Thành Công",
        actor=user,
        target=user,
        amount=int(paid["amount"]),
        action="donate" if paid.get("kind") == "donate" else "naptien",
        code=paid.get("code"),
        note=tx_note,
        transaction_id=tx_id,
    )

    if interaction:
        if is_donate:
            notice = create_success_splash(
                "✅ Donate Thành Công",
                f"Đã ghi nhận `{format_vnd(int(paid['amount']))} VNĐ` donate từ {user.mention if user else paid['username']}. Không cộng vào cash.",
            )
        else:
            notice = create_success_splash(
                "✅ Đã Cộng Cash",
                f"Đã cộng `{format_vnd(int(paid['amount']))} VNĐ` vào cash của {user.mention if user else paid['username']}.",
            )
        await send_interaction_notice(
            interaction,
            embed=notice,
        )
    return paid


async def finalize_cash_donation(
    bot: commands.Bot,
    bank: BankPaymentService,
    users: UserService,
    guild: discord.Guild,
    user: discord.Member,
    amount: int,
    donor_message: str = "",
) -> dict:
    username = user.display_name
    profile = users.touch_user(user.id, username)
    if int(profile.cash) < int(amount):
        raise ValueError(
            f"Bạn không đủ cash. Hiện có `{format_vnd(int(profile.cash))} VNĐ`, "
            f"cần `{format_vnd(int(amount))} VNĐ`."
        )

    users.remove_cash(user.id, int(amount))
    users.add_total_donate(user.id, int(amount))
    bank.add_donate_leaderboard(guild.id, user.id, username, int(amount))
    donation = {
        "id": 0,
        "guild_id": guild.id,
        "user_id": user.id,
        "username": username,
        "kind": "donate_cash",
        "amount": int(amount),
        "code": "CASH",
        "donor_message": str(donor_message or "")[:500],
    }
    await _send_donate_thanks(bot, bank, donation, user)
    await refresh_donate_leaderboard(bot, bank, guild)
    await send_cash_log(
        guild,
        title="💝 Donate Cash Thành Công",
        actor=user,
        target=user,
        amount=int(amount),
        action="donate cash",
        code="CASH",
        note=str(donor_message or "")[:500] or None,
    )
    return donation


async def _send_payment_success_dm(payment: dict, user, guild: discord.Guild | None) -> None:
    if not user or not guild:
        return
    action = "donate" if payment.get("kind") == "donate" else "nạp tiền"
    try:
        await user.send(
            f"✅ Bạn đã {action} thành công `{format_vnd(int(payment['amount']))} VNĐ` "
            f"trong **{guild.name}**."
        )
    except (discord.Forbidden, discord.HTTPException):
        pass


async def _edit_payment_message(bot: commands.Bot, payment: dict, user) -> None:
    channel_id = payment.get("channel_id")
    message_id = payment.get("message_id")
    if not channel_id or not message_id:
        return
    channel = bot.get_channel(int(channel_id))
    if not hasattr(channel, "fetch_message"):
        return
    try:
        message = await channel.fetch_message(int(message_id))
        await message.edit(embed=build_paid_embed(payment, payment.get("kind") or "naptien", user), view=None)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


async def _send_donate_thanks(bot: commands.Bot, bank: BankPaymentService, payment: dict, user) -> None:
    if payment.get("kind") not in {"donate", "donate_cash"}:
        return
    guild = bot.get_guild(int(payment["guild_id"]))
    if not guild:
        return
    settings = bank.get_settings(guild.id) or {}
    channel_id = settings.get("donate_channel_id")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        return

    mention = user.mention if user else f"<@{int(payment['user_id'])}>"
    username = getattr(user, "display_name", payment.get("username") or str(payment["user_id"]))
    template = settings.get("donate_thank_template") or "Cảm ơn {user} đã donate {amount} VNĐ cho {server}!"
    donor_message = str(payment.get("donor_message") or "").strip()
    method = "Cash" if payment.get("kind") == "donate_cash" else "Bank/QR"
    try:
        text = template.format(
            user=mention,
            username=username,
            amount=format_vnd(int(payment["amount"])),
            server=guild.name,
            code=payment.get("code") or "",
            message=donor_message,
            method=method,
        )
    except KeyError:
        text = f"Cảm ơn {mention} đã donate {format_vnd(int(payment['amount']))} VNĐ cho {guild.name}!"

    if donor_message and "{message}" not in template:
        text += f"\n💬 **Lời nhắn:** {donor_message}"

    try:
        await channel.send(
            text,
            allowed_mentions=discord.AllowedMentions(
                users=[user] if user else False,
                roles=False,
                everyone=False,
            ),
        )
    except (discord.Forbidden, discord.HTTPException):
        pass


class PaymentReloadView(discord.ui.View):
    def __init__(self, cog, payment_id: int, user_id: int, *, timeout: float | None = 86400):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.payment_id = int(payment_id)
        self.user_id = int(user_id)

    @discord.ui.button(label="Tôi đã chuyển tiền", emoji="✅", style=discord.ButtonStyle.success)
    async def reload_payment(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id and not self.cog.can_manage_cash(interaction):
            await interaction.response.send_message("❌ Chỉ người tạo QR hoặc người có quyền cash trong server này mới kiểm tra giao dịch này.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        await self.cog.check_and_finalize_payment(interaction, self.payment_id)
