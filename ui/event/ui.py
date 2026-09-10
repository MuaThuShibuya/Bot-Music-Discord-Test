from __future__ import annotations

import discord

from ui.event.emoji import event_emoji, event_text, event_theme_value
from utils import create_info_splash, create_success_splash


def build_manager_selection_embed(events: list[dict], theme: dict | None = None) -> discord.Embed:
    """Builds the initial embed for the event manager, asking to create or select an event."""
    embed = create_info_splash(
        event_text("event", event_theme_value(theme, "title_manager"), theme),
        event_theme_value(theme, "desc_manager"),
    )
    if not events:
        embed.description += f"\n\n{event_theme_value(theme, 'label_no_event')}"
    else:
        embed.description += f"\n\n{event_theme_value(theme, 'label_select_event')}"
        active_events = [f"▶️ `{event['name']}`" for event in events if event["status"] == "active"]
        draft_events = [f"📝 `{event['name']}`" for event in events if event["status"] == "draft"]
        if active_events:
            embed.add_field(name=event_theme_value(theme, "label_active"), value="\n".join(active_events), inline=False)
        if draft_events:
            embed.add_field(name=event_theme_value(theme, "label_draft"), value="\n".join(draft_events), inline=False)
    return embed


def build_event_dashboard_embed(event: dict, theme: dict | None = None) -> discord.Embed:
    """Builds the dashboard embed for a specific event."""
    status_map = {
        "draft": f"📝 {event_theme_value(theme, 'label_draft')}",
        "active": f"▶️ {event_theme_value(theme, 'label_active')}",
        "closed": f"⏹️ {event_theme_value(theme, 'label_closed')}",
    }
    filter_map = {
        "any": "Tất cả (Ảnh, Video, Text, Link...)",
        "image": "Chỉ Ảnh",
        "video": "Chỉ Video",
        "link": "Chỉ Link (Tiktok, Youtube...)",
    }
    embed = create_info_splash(
        f"{event_emoji('manage', theme)} Quản lý: {event['name']}",
        f"ID sự kiện: `{event['event_id']}`",
    )
    embed.add_field(name="Trạng thái", value=status_map.get(event["status"], event["status"]), inline=True)
    embed.add_field(name="Kênh", value=f"<#{event['channel_id']}>" if event["channel_id"] else "Chưa set", inline=True)
    embed.add_field(name="Emoji vote", value=event["reaction_emoji"], inline=True)
    embed.add_field(name="Loại bài thi", value=filter_map.get(event["filter_mode"], event["filter_mode"]), inline=False)
    embed.add_field(name="Chống gian lận", value="Bật" if event["anti_cheat_mode"] else "Tắt", inline=True)
    embed.set_footer(text="Dùng các nút bên dưới để cấu hình.")
    return embed


def build_leaderboard_embed(
    event: dict,
    entries: list[dict],
    theme: dict | None,
    page: int,
    total_pages: int,
) -> discord.Embed:
    """Builds the leaderboard embed for an event."""
    embed = create_success_splash(
        event_text("leaderboard", f"{event_theme_value(theme, 'title_leaderboard')}: {event['name']}", theme),
        f"Cập nhật lúc: <t:{int(discord.utils.utcnow().timestamp())}:R>",
    )
    if not entries:
        embed.description += "\n\nChưa có bài dự thi nào có vote."
        return embed

    lines = []
    for rank, entry in enumerate(entries, 1):
        user_mention = f"<@{entry['user_id']}>"
        score = entry["score"]
        message_url = f"https://discord.com/channels/{event['guild_id']}/{event['channel_id']}/{entry['message_id']}"
        lines.append(f"**#{rank}** {user_mention} - `{score}` vote Mở bài thi")

    embed.add_field(name="Top bài dự thi", value="\n".join(lines), inline=False)
    if total_pages > 1:
        embed.set_footer(text=f"Trang {page}/{total_pages}")
    return embed