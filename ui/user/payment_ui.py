from __future__ import annotations

from io import BytesIO
from pathlib import Path

import discord
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

from cogs.admin_command_utils import format_vnd
from utils import append_discord_timestamp


CARD_SIZE = (980, 620)
ASSET_ROOT = Path(__file__).resolve().parent / "assets"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _fetch_image(url: str | None, timeout: int = 12) -> Image.Image | None:
    if not url:
        return None
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        return Image.open(BytesIO(response.content)).convert("RGBA")
    except Exception:
        return None


def _local_decor(kind: str) -> Image.Image | None:
    asset_dir = ASSET_ROOT / ("donate" if kind == "donate" else "naptien")
    candidates = [asset_dir / "card.png", asset_dir / "background.png"]
    candidates.extend(sorted(asset_dir.glob("*.jpg")))
    candidates.extend(sorted(asset_dir.glob("*.jpeg")))
    candidates.extend(sorted(asset_dir.glob("*.webp")))
    for path in candidates:
        if not path.is_file():
            continue
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            continue
    return None


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _rounded_rect(draw: ImageDraw.ImageDraw, xy, radius: int, fill, outline=None, width: int = 1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def _fit_font(text: str, max_width: int, start_size: int = 26, min_size: int = 15, bold: bool = True):
    for size in range(start_size, min_size - 1, -1):
        font = _font(size, bold)
        if font.getbbox(str(text))[2] <= max_width:
            return font
    return _font(min_size, bold)


def _default_background(kind: str) -> Image.Image:
    width, height = CARD_SIZE
    base = Image.new("RGBA", CARD_SIZE, (246, 223, 230, 255) if kind == "donate" else (224, 236, 255, 255))
    draw = ImageDraw.Draw(base)
    accent = (255, 136, 170, 255) if kind == "donate" else (92, 122, 255, 255)
    pale = (255, 246, 250, 255) if kind == "donate" else (242, 246, 255, 255)
    for x in range(-80, width, 90):
        draw.rounded_rectangle((x, -40, x + 42, height + 40), radius=20, fill=(*accent[:3], 42))
    for y in range(20, height, 105):
        draw.ellipse((width - 260, y, width - 20, y + 240), fill=(*accent[:3], 34))
    _rounded_rect(draw, (34, 34, width - 34, height - 34), 34, pale, accent, 5)
    return base


def render_payment_card(payment: dict, settings: dict, kind: str) -> discord.File | None:
    """Render QR card. Nếu thiếu mạng/QR thì trả None để embed dùng QR URL trực tiếp."""

    decor_url = settings.get("donate_decor_url") if kind == "donate" else settings.get("deposit_decor_url")
    background = _fetch_image(decor_url) or _local_decor(kind)
    if background:
        canvas = _cover(background, CARD_SIZE)
        overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 72))
        canvas = Image.alpha_composite(canvas, overlay)
    else:
        canvas = _default_background(kind)

    draw = ImageDraw.Draw(canvas)
    is_donate = kind == "donate"
    accent = (255, 104, 145, 255) if is_donate else (90, 116, 255, 255)
    dark = (42, 36, 48, 255)
    white = (255, 255, 255, 255)

    qr = _fetch_image(payment.get("qr_url"))
    if qr is None:
        return None

    title = "DONATE" if is_donate else "NẠP TIỀN"
    subtitle = "Scan QR để donate" if is_donate else "Scan QR để nạp cash"

    panel = (64, 62, 558, 545)
    _rounded_rect(draw, panel, 32, (255, 255, 255, 224), accent, 4)

    qr_box = (104, 145, 474, 515)
    _rounded_rect(draw, qr_box, 30, white, accent, 5)
    qr = ImageOps.contain(qr, (330, 330), method=Image.Resampling.LANCZOS)
    qr_x = 124 + ((330 - qr.width) // 2)
    qr_y = 165 + ((330 - qr.height) // 2)
    canvas.alpha_composite(qr, (qr_x, qr_y))

    draw.text((92, 72), "scan here", font=_font(50, True), fill=accent)
    info_x = 590
    info_right = 950
    draw.text((info_x, 62), title, font=_font(52, True), fill=white if background else dark)
    draw.text((info_x, 120), subtitle, font=_font(26, True), fill=white if background else dark)

    amount_text = f"{format_vnd(int(payment['amount']))} VNĐ"
    code = payment["code"]
    bank = str(settings.get("bank_code") or "ACB").upper()
    account = str(settings.get("account_number") or "")
    account_name = str(settings.get("account_name") or "ACB")

    info_y = 182
    for label, value in [
        ("Số tiền", amount_text),
        ("Nội dung", code),
        ("Ngân hàng", bank),
        ("STK", account),
        ("Tên tài khoản", account_name),
    ]:
        draw.text((info_x, info_y), label, font=_font(21, True), fill=white if background else (75, 70, 86, 255))
        _rounded_rect(draw, (info_x, info_y + 25, info_right, info_y + 61), 12, (255, 255, 255, 224), accent, 2)
        value_text = str(value)
        value_font = _fit_font(value_text, info_right - info_x - 34, start_size=22, min_size=10)
        draw.text((info_x + 17, info_y + 29), value_text, font=value_font, fill=dark)
        info_y += 72

    draw.text((98, 552), "Bleck Lous • Bank QR", font=_font(20, True), fill=accent)

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG", optimize=True)
    output.seek(0)
    return discord.File(output, filename=f"payment_{payment['id']}.png")


def build_payment_embed(payment: dict, settings: dict, kind: str, has_card: bool) -> discord.Embed:
    is_donate = kind == "donate"
    title = "💝 Donate" if is_donate else "💳 Nạp Tiền"
    color = discord.Color.from_rgb(255, 127, 169) if is_donate else discord.Color.from_rgb(96, 165, 250)
    embed = discord.Embed(
        title=title,
        description="Quét QR hoặc chuyển khoản đúng nội dung bên dưới, sau đó bấm **Tôi đã chuyển tiền** để bot kiểm tra.",
        color=color,
    )
    embed.add_field(name="Số tiền", value=f"`{format_vnd(int(payment['amount']))} VNĐ`", inline=True)
    embed.add_field(name="Nội dung CK", value=f"`{payment['code']}`", inline=True)
    embed.add_field(
        name="Tài khoản",
        value=f"`{settings.get('bank_code') or 'ACB'}` • `{settings.get('account_number') or 'Chưa set'}`",
        inline=False,
    )
    embed.add_field(
        name="Chủ tài khoản",
        value=f"`{settings.get('account_name') or 'Chưa set'}`",
        inline=False,
    )
    donor_message = str(payment.get("donor_message") or "").strip()
    if is_donate and donor_message:
        embed.add_field(name="Lời nhắn", value=donor_message[:1024], inline=False)
    if has_card:
        embed.set_image(url=f"attachment://payment_{payment['id']}.png")
    else:
        embed.add_field(name="QR", value=f"[Mở QR]({payment['qr_url']})", inline=False)
        embed.set_image(url=payment["qr_url"])
    return embed


def build_bank_balance_embed(result: dict, settings: dict) -> discord.Embed:
    account_number = result.get("account_number") or settings.get("account_number") or "Chưa set"
    account_name = result.get("account_name") or settings.get("account_name") or "ACB"
    balance = int(result.get("balance") or 0)
    embed = discord.Embed(
        title="🏦 Số Dư Tài Khoản Ngân Hàng",
        description=f"`{format_vnd(balance)} VNĐ`",
        color=discord.Color.green(),
    )
    embed.add_field(name="Ngân hàng", value=f"`{settings.get('bank_code') or 'ACB'}`", inline=True)
    embed.add_field(name="Số tài khoản", value=f"`{account_number}`", inline=True)
    embed.add_field(name="Chủ tài khoản", value=f"`{account_name}`", inline=False)
    if result.get("source"):
        embed.add_field(name="Nguồn", value=f"`{result['source']}`", inline=False)
    if result.get("updated_at"):
        embed.set_footer(text="Cập nhật số dư ngân hàng")
    append_discord_timestamp(embed)
    return embed


def build_paid_embed(payment: dict, kind: str, user: discord.abc.User | discord.Member | None = None) -> discord.Embed:
    is_donate = kind == "donate"
    title = "✅ Donate Thành Công" if is_donate else "✅ Nạp Tiền Thành Công"
    description = (
        f"Đã ghi nhận `{format_vnd(int(payment['amount']))} VNĐ` donate. Khoản này không cộng vào cash."
        if is_donate
        else f"Đã cộng `{format_vnd(int(payment['amount']))} VNĐ` vào cash."
    )
    embed = discord.Embed(title=title, description=description, color=discord.Color.green())
    embed.add_field(name="Mã giao dịch", value=f"`{payment['code']}`", inline=True)
    embed.add_field(name="Trạng thái", value="`Đã thanh toán`", inline=True)
    if user:
        embed.set_author(name=getattr(user, "display_name", str(user)), icon_url=user.display_avatar.url)
    return embed


def build_config_status_embed(settings: dict) -> discord.Embed:
    configured = all(settings.get(key) for key in ("username", "password", "account_number"))
    embed = discord.Embed(
        title="🏦 Bank Config",
        description="Cấu hình dùng cho `naptien` và `donate`.",
        color=discord.Color.green() if configured else discord.Color.orange(),
    )
    embed.add_field(name="ACB username", value=f"`{settings.get('username') or 'Chưa set'}`", inline=True)
    embed.add_field(name="ACB password", value="`Đã set`" if settings.get("password") else "`Chưa set`", inline=True)
    embed.add_field(name="Số tài khoản", value=f"`{settings.get('account_number') or 'Chưa set'}`", inline=True)
    embed.add_field(name="Tên tài khoản", value=f"`{settings.get('account_name') or 'ACB'}`", inline=True)
    embed.add_field(name="Auto check", value="`Bật`" if int(settings.get("auto_check_enabled") or 0) else "`Tắt`", inline=True)
    embed.add_field(
        name="Giao diện nạp tiền",
        value=f"[Mở ảnh]({settings['deposit_decor_url']})" if settings.get("deposit_decor_url") else "`Mặc định`",
        inline=True,
    )
    embed.add_field(
        name="Giao diện donate",
        value=f"[Mở ảnh]({settings['donate_decor_url']})" if settings.get("donate_decor_url") else "`Mặc định`",
        inline=True,
    )
    donate_channel = settings.get("donate_channel_id")
    embed.add_field(name="Kênh cảm ơn donate", value=f"<#{int(donate_channel)}>" if donate_channel else "`Chưa set`", inline=True)
    leaderboard_channel = settings.get("donate_leaderboard_channel_id")
    embed.add_field(
        name="Kênh BXH donate",
        value=f"<#{int(leaderboard_channel)}>" if leaderboard_channel else "`Chưa set`",
        inline=True,
    )
    leaderboard_message = settings.get("donate_leaderboard_message_id")
    embed.add_field(
        name="Tin nhắn BXH",
        value=f"`{leaderboard_message}`" if leaderboard_message else "`Chưa tạo`",
        inline=True,
    )
    return embed


def build_donate_leaderboard_embed(
    rows: list[dict],
    guild: discord.Guild | None,
    *,
    page: int = 0,
    per_page: int = 10,
) -> discord.Embed:
    rows = rows[:50]
    total_pages = max(1, (len(rows) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    page_rows = rows[start : start + per_page]
    total_amount = sum(int(row.get("amount") or 0) for row in rows)

    embed = discord.Embed(
        title="💝 Bảng Xếp Hạng Donate",
        color=discord.Color.from_rgb(255, 127, 169),
    )
    if guild and guild.icon:
        embed.set_thumbnail(url=guild.icon.url)

    if not page_rows:
        embed.description = "Chưa có ai donate trong bảng tháng này."
    else:
        lines = []
        for index, row in enumerate(page_rows, start=start + 1):
            amount = format_vnd(int(row.get("amount") or 0))
            count = int(row.get("donate_count") or 0)
            lines.append(f"**#{index}** <@{int(row['user_id'])}> - `{amount} VNĐ` · `{count}` lần")
        embed.description = "\n".join(lines)

    embed.add_field(name="Tổng người", value=f"`{len(rows)}`", inline=True)
    embed.add_field(name="Tổng donate", value=f"`{format_vnd(total_amount)} VNĐ`", inline=True)
    embed.add_field(name="Trang", value=f"`{page + 1}/{total_pages}`", inline=True)
    append_discord_timestamp(embed, style="f")
    return embed
