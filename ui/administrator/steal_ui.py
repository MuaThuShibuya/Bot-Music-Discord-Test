from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

import discord

from cogs.admin_command_utils import (
    create_error_splash,
    create_info_splash,
    create_success_splash,
)


CUSTOM_EMOJI_RE = re.compile(
    r"<(?P<animated>a?):(?P<name>[A-Za-z0-9_]{2,32}):(?P<id>\d+)>"
)
EMOJI_NAME_RE = re.compile(r"^[A-Za-z0-9_]{2,32}$")


@dataclass(slots=True)
class StealEmojiSource:
    url: str
    name: str
    animated: bool = False


def normalize_emoji_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned[:32]


def parse_steal_source(raw_source: str, requested_name: str = "") -> StealEmojiSource:
    source = str(raw_source or "").strip()
    custom_match = CUSTOM_EMOJI_RE.fullmatch(source)
    if custom_match:
        animated = bool(custom_match.group("animated"))
        emoji_id = custom_match.group("id")
        name = normalize_emoji_name(requested_name) or custom_match.group("name")
        extension = "gif" if animated else "png"
        return StealEmojiSource(
            url=f"https://cdn.discordapp.com/emojis/{emoji_id}.{extension}?size=128&quality=lossless",
            name=name,
            animated=animated,
        )

    parsed = urlparse(source)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Hãy gửi custom emoji dạng `<:name:id>` hoặc URL ảnh hợp lệ.")

    name = normalize_emoji_name(requested_name)
    if not name:
        raise ValueError("Khi dùng URL hoặc ảnh đính kèm, bạn phải nhập tên emoji.")
    return StealEmojiSource(
        url=source,
        name=name,
        animated=parsed.path.lower().endswith(".gif"),
    )


def validate_emoji_name(name: str) -> str:
    if not EMOJI_NAME_RE.fullmatch(name):
        raise ValueError("Tên emoji phải dài 2-32 ký tự và chỉ gồm chữ, số hoặc `_`.")
    return name


def build_steal_help_embed(prefix: str) -> discord.Embed:
    return create_info_splash(
        "✨ Steal Emoji",
        (
            f"`{prefix}steal <emoji> [name]`\n"
            f"`{prefix}steal <url> <name>`\n"
            f"Hoặc đính kèm ảnh: `{prefix}steal <name>`\n"
            "`/steal emoji:<emoji hoặc URL> name:<không bắt buộc với custom emoji>`"
        ),
    )


def build_steal_success_embed(emoji: discord.Emoji) -> discord.Embed:
    return create_success_splash(
        "✅ Steal Emoji Thành Công",
        f"Đã thêm {emoji} với tên `{emoji.name}` vào server.",
    )


def build_steal_error_embed(message: str) -> discord.Embed:
    return create_error_splash("❌ Steal Emoji Thất Bại", message)
