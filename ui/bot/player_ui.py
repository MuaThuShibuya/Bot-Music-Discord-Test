from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import discord
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps


CARD_WIDTH = 1000
CARD_HEIGHT = 360
CARD_FILENAME = "music-player.png"
ANIMATED_CARD_FILENAME = "music-player.gif"
MAX_PROGRESS_FRAMES = 300
ASSET_DIR = Path(__file__).resolve().parent / "assets"
THUMBNAIL_CACHE: dict[str, bytes] = {}


@dataclass(slots=True)
class PlayerCardData:
    title: str
    requester: str
    duration: int | None
    elapsed: int
    thumbnail: str | None
    volume: int
    paused: bool
    loop: bool
    autoplay: bool
    queue_count: int = 0
    accent_color: str = "#7f314d"
    background_url: str | None = None
    header_text: str = "BLACK LOUS MUSIC"
    requester_text: str = "Yêu cầu bởi: {requester}"
    status_playing_text: str = "ĐANG PHÁT"
    status_paused_text: str = "TẠM DỪNG"
    duration_label: str = "THỜI LƯỢNG"
    volume_text: str = "Âm lượng {volume}%"
    loop_text: str = "Loop {status}"
    autoplay_text: str = "Đề xuất YouTube {status}"
    queue_text: str = "Queue {count}"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"),
        Path("/System/Library/Fonts/SFNS.ttf"),
        Path("/System/Library/Fonts/HelveticaNeue.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    value = " ".join((text or "Không rõ").split())
    if draw.textlength(value, font=font) <= max_width:
        return value
    suffix = "..."
    while value and draw.textlength(value + suffix, font=font) > max_width:
        value = value[:-1]
    return value.rstrip() + suffix


def _time_text(seconds: int | None) -> str:
    value = max(0, int(seconds or 0))
    hours, remainder = divmod(value, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _format_ui_text(template: str, **values) -> str:
    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


async def _download_thumbnail(url: str | None) -> bytes | None:
    if not url:
        return None
    if url in THUMBNAIL_CACHE:
        return THUMBNAIL_CACHE[url]
    timeout = aiohttp.ClientTimeout(total=8)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    return None
                raw = await response.read()
                if len(THUMBNAIL_CACHE) >= 30:
                    THUMBNAIL_CACHE.pop(next(iter(THUMBNAIL_CACHE)))
                THUMBNAIL_CACHE[url] = raw
                return raw
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


def _cover_image(raw: bytes | None) -> Image.Image:
    if raw:
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            return ImageOps.fit(image, (270, 270), method=Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            pass

    image = Image.new("RGB", (270, 270), "#2b1820")
    draw = ImageDraw.Draw(image)
    draw.ellipse((58, 58, 212, 212), fill="#f8c6d8")
    draw.ellipse((94, 94, 176, 176), fill="#542636")
    draw.ellipse((127, 127, 143, 143), fill="#f8c6d8")
    return image


def _open_background(raw: bytes | None, cover: Image.Image) -> Image.Image:
    if raw:
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGB")
            return ImageOps.fit(image, (CARD_WIDTH, CARD_HEIGHT), method=Image.Resampling.LANCZOS)
        except (OSError, ValueError):
            pass
    local_background = ASSET_DIR / "player_background.png"
    if local_background.exists():
        try:
            image = Image.open(local_background).convert("RGB")
            return ImageOps.fit(image, (CARD_WIDTH, CARD_HEIGHT), method=Image.Resampling.LANCZOS)
        except OSError:
            pass
    return cover.resize((CARD_WIDTH, CARD_HEIGHT)).filter(ImageFilter.GaussianBlur(30))


def normalize_accent_color(value: str | None) -> str:
    color = str(value or "").strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        return color.lower()
    return "#7f314d"


def _render_card(
    data: PlayerCardData,
    raw_thumbnail: bytes | None,
    raw_background: bytes | None,
) -> tuple[io.BytesIO, str]:
    cover = _cover_image(raw_thumbnail)
    background = _open_background(raw_background, cover)
    dark_layer = Image.new("RGBA", background.size, (29, 10, 18, 210))
    canvas = Image.alpha_composite(background.convert("RGBA"), dark_layer)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        (18, 18, CARD_WIDTH - 18, CARD_HEIGHT - 18),
        radius=34,
        fill=(255, 245, 239, 238),
        outline=(255, 197, 216, 255),
        width=5,
    )

    cover_mask = Image.new("L", (270, 270), 0)
    ImageDraw.Draw(cover_mask).rounded_rectangle((0, 0, 270, 270), radius=28, fill=255)
    canvas.paste(cover, (48, 45), cover_mask)

    title_font = _font(42, bold=True)
    meta_font = _font(25)
    small_font = _font(20)
    status_font = _font(22, bold=True)
    accent = normalize_accent_color(data.accent_color)
    text = "#27171e"
    muted = "#725d65"

    header_font = _font(18, bold=True)
    title = _fit_text(draw, data.title, title_font, 590)
    header = _fit_text(draw, data.header_text.upper(), header_font, 580)
    draw.text((355, 35), header, font=header_font, fill=accent)
    draw.text((355, 62), title, font=title_font, fill=text)
    draw.text(
        (355, 125),
        _format_ui_text(data.requester_text, requester=data.requester),
        font=meta_font,
        fill=muted,
    )

    status = data.status_paused_text if data.paused else data.status_playing_text
    status_color = "#c44c72" if data.paused else "#4f9b72"
    status_width = min(
        590,
        max(90, int(draw.textlength(status, font=status_font)) + 34),
    )
    status_box = (355, 170, 355 + status_width, 210)
    draw.rounded_rectangle(status_box, radius=18, fill=status_color)
    status_bbox = draw.textbbox((0, 0), status, font=status_font)
    status_height = status_bbox[3] - status_bbox[1]
    status_y = status_box[1] + ((status_box[3] - status_box[1] - status_height) // 2) - status_bbox[1]
    draw.text((372, status_y), status, font=status_font, fill="white")

    duration = max(0, int(data.duration or 0))
    duration_text = _time_text(duration) if duration else "Không rõ"
    draw.text((355, 235), data.duration_label, font=small_font, fill=muted)

    modes = [
        _format_ui_text(data.volume_text, volume=data.volume),
        _format_ui_text(data.loop_text, status="Bật" if data.loop else "Tắt"),
        _format_ui_text(data.autoplay_text, status="Bật" if data.autoplay else "Tắt"),
        _format_ui_text(data.queue_text, count=data.queue_count),
    ]
    mode_font_size = 20
    mode_font = small_font
    available_width = 595
    gap = 8
    while mode_font_size > 13:
        widths = [int(draw.textlength(mode, font=mode_font)) + 24 for mode in modes]
        if sum(widths) + gap * (len(widths) - 1) <= available_width:
            break
        mode_font_size -= 1
        mode_font = _font(mode_font_size)

    widths = [int(draw.textlength(mode, font=mode_font)) + 24 for mode in modes]
    if sum(widths) + gap * (len(widths) - 1) > available_width:
        max_chip_width = (available_width - gap * (len(modes) - 1)) // len(modes)
        modes = [
            _fit_text(draw, mode, mode_font, max_chip_width - 24)
            for mode in modes
        ]
        widths = [max_chip_width] * len(modes)

    x = 355
    for mode, width in zip(modes, widths):
        draw.rounded_rectangle((x, 298, x + width, 330), radius=14, fill="#f2dce4")
        mode_bbox = draw.textbbox((0, 0), mode, font=mode_font)
        mode_height = mode_bbox[3] - mode_bbox[1]
        mode_y = 298 + ((32 - mode_height) // 2) - mode_bbox[1]
        draw.text((x + 12, mode_y), mode, font=mode_font, fill=accent)
        x += width + gap

    frame_path = ASSET_DIR / "player_frame.png"
    if frame_path.exists():
        try:
            frame = Image.open(frame_path).convert("RGBA")
            frame = ImageOps.fit(frame, (CARD_WIDTH, CARD_HEIGHT), method=Image.Resampling.LANCZOS)
            canvas = Image.alpha_composite(canvas, frame)
        except OSError:
            pass

    def progress_frame(elapsed: int) -> Image.Image:
        frame = canvas.copy()
        frame_draw = ImageDraw.Draw(frame)
        current = min(duration, max(0, int(elapsed))) if duration else max(0, int(elapsed))
        current_text = _time_text(current)
        frame_draw.text((355, 263), current_text, font=small_font, fill=accent)
        total_width = int(frame_draw.textlength(duration_text, font=small_font))
        frame_draw.text((950 - total_width, 263), duration_text, font=small_font, fill=muted)

        track_left = 425
        track_right = 925 - total_width
        track_top = 271
        track_bottom = 281
        if track_right > track_left:
            frame_draw.rounded_rectangle(
                (track_left, track_top, track_right, track_bottom),
                radius=5,
                fill="#ead4dc",
            )
            ratio = (current / duration) if duration else 0
            fill_right = track_left + int((track_right - track_left) * min(1.0, ratio))
            if fill_right > track_left:
                frame_draw.rounded_rectangle(
                    (track_left, track_top, fill_right, track_bottom),
                    radius=5,
                    fill=accent,
                )
        return frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)

    output = io.BytesIO()
    elapsed = max(0, int(data.elapsed))
    remaining = max(0, duration - elapsed)
    if duration and remaining and not data.paused:
        frame_count = min(MAX_PROGRESS_FRAMES, remaining + 1)
        frame_count = max(2, frame_count)
        frames = [
            progress_frame(elapsed + round((remaining * index) / (frame_count - 1)))
            for index in range(frame_count)
        ]
        frame_duration = max(100, round((remaining * 1000) / (frame_count - 1)))
        frames[0].save(
            output,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=frame_duration,
            loop=0,
            optimize=True,
            disposal=1,
        )
        filename = ANIMATED_CARD_FILENAME
    else:
        progress_frame(elapsed).convert("RGB").save(output, format="PNG", optimize=True)
        filename = CARD_FILENAME
    output.seek(0)
    return output, filename


async def build_player_file(data: PlayerCardData) -> discord.File:
    raw_thumbnail, raw_background = await asyncio.gather(
        _download_thumbnail(data.thumbnail),
        _download_thumbnail(data.background_url),
    )
    buffer, filename = await asyncio.to_thread(
        _render_card,
        data,
        raw_thumbnail,
        raw_background,
    )
    return discord.File(buffer, filename=filename)


class PlayerVolumeModal(discord.ui.Modal, title="Chỉnh âm lượng"):
    volume = discord.ui.TextInput(
        label="Âm lượng từ 0 đến 200",
        placeholder="100",
        min_length=1,
        max_length=3,
    )

    def __init__(self, controller, guild_id: int):
        super().__init__()
        self.controller = controller
        self.guild_id = guild_id

    async def on_submit(self, interaction: discord.Interaction):
        await self.controller.handle_player_volume(interaction, self.guild_id, self.volume.value)


class MusicPlayerView(discord.ui.View):
    def __init__(self, controller, guild_id: int, theme: dict | None = None):
        super().__init__(timeout=None)
        self.controller = controller
        self.guild_id = guild_id
        theme = theme or {}
        mapping = [
            ("Pause / Resume", "button_pause", "icon_pause"),
            ("Stop", "button_stop", "icon_stop"),
            ("Skip", "button_skip", "icon_skip"),
            ("Loop", "button_loop", "icon_loop"),
            ("Đề xuất YouTube", "button_autoplay", "icon_autoplay"),
            ("Shuffle", "button_shuffle", "icon_shuffle"),
            ("Queue", "button_queue", "icon_queue"),
            ("Âm lượng", "button_volume", "icon_volume"),
            ("Settings", "button_settings", "icon_settings"),
            ("Rời voice", "button_leave", "icon_leave"),
        ]
        for child in self.children:
            for default_label, label_key, icon_key in mapping:
                if child.label == default_label:
                    child.label = str(theme.get(label_key) or child.label)
                    child.emoji = str(theme.get(icon_key) or child.emoji)
                    break

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await self.controller.check_player_interaction(
            interaction,
            interaction.guild_id or self.guild_id,
        )

    @discord.ui.button(label="Pause / Resume", emoji="⏯️", style=discord.ButtonStyle.primary, row=0, custom_id="music_player:pause_resume")
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.handle_player_button(interaction, interaction.guild_id or self.guild_id, "pause_resume")

    @discord.ui.button(label="Stop", emoji="⏹️", style=discord.ButtonStyle.danger, row=0, custom_id="music_player:stop")
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.handle_player_button(interaction, interaction.guild_id or self.guild_id, "stop")

    @discord.ui.button(label="Skip", emoji="⏭️", style=discord.ButtonStyle.secondary, row=0, custom_id="music_player:skip")
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.handle_player_button(interaction, interaction.guild_id or self.guild_id, "skip")

    @discord.ui.button(label="Loop", emoji="🔁", style=discord.ButtonStyle.secondary, row=0, custom_id="music_player:loop")
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.handle_player_button(interaction, interaction.guild_id or self.guild_id, "loop")

    @discord.ui.button(label="Đề xuất YouTube", emoji="♾️", style=discord.ButtonStyle.secondary, row=0, custom_id="music_player:autoplay")
    async def autoplay(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.handle_player_button(interaction, interaction.guild_id or self.guild_id, "autoplay")

    @discord.ui.button(label="Shuffle", emoji="🔀", style=discord.ButtonStyle.secondary, row=1, custom_id="music_player:shuffle")
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.handle_player_button(interaction, interaction.guild_id or self.guild_id, "shuffle")

    @discord.ui.button(label="Queue", emoji="📋", style=discord.ButtonStyle.secondary, row=1, custom_id="music_player:queue")
    async def queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.handle_player_button(interaction, interaction.guild_id or self.guild_id, "queue")

    @discord.ui.button(label="Âm lượng", emoji="🔊", style=discord.ButtonStyle.secondary, row=1, custom_id="music_player:volume")
    async def volume(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerVolumeModal(self.controller, interaction.guild_id or self.guild_id))

    @discord.ui.button(label="Settings", emoji="⚙️", style=discord.ButtonStyle.secondary, row=1, custom_id="music_player:settings")
    async def settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.handle_player_settings_button(interaction, interaction.guild_id or self.guild_id)

    @discord.ui.button(label="Rời voice", emoji="🚪", style=discord.ButtonStyle.secondary, row=1, custom_id="music_player:leave")
    async def leave(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.controller.handle_player_button(interaction, interaction.guild_id or self.guild_id, "leave")
