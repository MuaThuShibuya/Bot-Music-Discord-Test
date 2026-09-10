from __future__ import annotations

import discord

from cogs.admin_command_utils import format_vnd
from services.log_service import LogService
from ui.administrator.log_ui import build_basic_log_embed, truncate_text


async def send_cash_log(
    guild: discord.Guild | None,
    *,
    title: str,
    actor: discord.abc.User | discord.Member | None = None,
    target: discord.abc.User | discord.Member | None = None,
    amount: int | None = None,
    action: str = "cash",
    code: str | None = None,
    note: str | None = None,
    transaction_id: str | None = None,
) -> None:
    if guild is None:
        return

    service = LogService()
    channel_id = service.get_channel_id(guild.id, "cash")
    channel = guild.get_channel(channel_id) if channel_id else None
    if channel is None:
        channel = discord.utils.get(guild.text_channels, name="log_cash")
        channel = channel or discord.utils.get(guild.text_channels, name="log-cash")
        channel = channel or discord.utils.get(guild.text_channels, name="cash-log")
    if not isinstance(channel, discord.TextChannel):
        return

    lines = [f"**Hành động:** `{action}`"]
    if actor:
        lines.append(f"**Người thực hiện:** {actor.mention}")
    if target:
        lines.append(f"**Người nhận/tác động:** {target.mention}")
    if amount is not None:
        lines.append(f"**Số tiền:** `{format_vnd(int(amount))} VNĐ`")
    if code:
        lines.append(f"**Mã:** `{code}`")
    if transaction_id:
        lines.append(f"**Mã GD ngân hàng:** `{transaction_id}`")
    if note:
        lines.append(f"**Ghi chú:** {truncate_text(note, 450)}")
    embed = build_basic_log_embed(title, "\n".join(lines), "cash", target or actor)
    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass
