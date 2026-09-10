from __future__ import annotations

import re


GIVEAWAY_DEFAULT_ENTRY_EMOJI = "🎉"
GIVEAWAY_CUSTOM_EMOJI_RE = re.compile(r"<(?P<animated>a?):(?P<name>[A-Za-z0-9_~]+):(?P<id>\d+)>")

GIVEAWAY_ICONS = {
    "start": "🌸",
    "ended": "🏁",
    "winner": "🏆",
    "time": "⏳",
    "host": "👑",
    "selected": "🎯",
    "package": "🎁",
    "template": "📝",
    "dm": "🎉",
    "result": "🎉",
    "reroll": "🔄",
    "random": "🎲",
    "config": "🎉",
    "created": "🎉",
    "set": "🎯",
}


def giveaway_icon(key: str) -> str:
    return GIVEAWAY_ICONS.get(key, GIVEAWAY_DEFAULT_ENTRY_EMOJI)


GIVEAWAY_THEME_DEFAULTS = {
    "icon_start": GIVEAWAY_ICONS["start"],
    "icon_ended": GIVEAWAY_ICONS["ended"],
    "icon_winner": GIVEAWAY_ICONS["winner"],
    "icon_time": GIVEAWAY_ICONS["time"],
    "icon_host": GIVEAWAY_ICONS["host"],
    "icon_selected": GIVEAWAY_ICONS["selected"],
    "icon_package": GIVEAWAY_ICONS["package"],
    "icon_template": GIVEAWAY_ICONS["template"],
    "icon_dm": GIVEAWAY_ICONS["dm"],
    "icon_result": GIVEAWAY_ICONS["result"],
    "icon_reroll": GIVEAWAY_ICONS["reroll"],
    "icon_random": GIVEAWAY_ICONS["random"],
    "icon_config": GIVEAWAY_ICONS["config"],
    "icon_created": GIVEAWAY_ICONS["created"],
    "icon_set": GIVEAWAY_ICONS["set"],
    "title_start": "{start} GIVEAWAY BẮT ĐẦU {start}",
    "title_ended": "{ended} GIVEAWAY ĐÃ KẾT THÚC {ended}",
    "text_join": "Nhấn vào {emoji} để tham gia",
    "text_ended": "",
    "label_winner": "Người thắng",
    "label_time": "Đếm ngược",
    "label_host": "Tổ chức bởi",
    "label_selected": "Winner đã chọn",
    "label_package": "Gói",
    "label_template": "Template",
    "dm_winner": "{dm} Chúc mừng! Bạn đã {action} giveaway **{reward}** tại **{guild}**.\nHãy quay lại server để nhận thưởng nhé.",
    "result_winner": "{icon} Giveaway đã kết thúc!\nChúc mừng {winners} đã trúng **{reward}**.\nLiên hệ host để nhận thưởng nhé.",
    "result_reroll": "{icon} Giveaway đã reroll lần {round}!\nChúc mừng {winners} đã trúng **{reward}**.\nLiên hệ host để nhận thưởng nhé.",
    "result_no_winner": "{icon} Giveaway **{reward}** đã kết thúc.\nKhông có người tham gia nên không có winner.",
}

GIVEAWAY_THEME_ALIASES = {
    "start": "icon_start",
    "batdau": "icon_start",
    "bắtđầu": "icon_start",
    "ended": "icon_ended",
    "end": "icon_ended",
    "winner": "icon_winner",
    "win": "icon_winner",
    "nguoithang": "icon_winner",
    "người_thắng": "icon_winner",
    "time": "icon_time",
    "ketthuc": "icon_time",
    "kết_thúc": "icon_time",
    "host": "icon_host",
    "selected": "icon_selected",
    "chon": "icon_selected",
    "chọn": "icon_selected",
    "package": "icon_package",
    "goi": "icon_package",
    "gói": "icon_package",
    "template": "icon_template",
    "dm": "icon_dm",
    "result": "icon_result",
    "ketqua": "icon_result",
    "kết_quả": "icon_result",
    "reroll": "icon_reroll",
    "random": "icon_random",
    "config": "icon_config",
    "created": "icon_created",
    "set": "icon_set",
    "title_start": "title_start",
    "start_title": "title_start",
    "title_ended": "title_ended",
    "end_title": "title_ended",
    "join_text": "text_join",
    "text_join": "text_join",
    "thamgia": "text_join",
    "tham_gia": "text_join",
    "content": "text_join",
    "noidung": "text_join",
    "nội_dung": "text_join",
    "join": "text_join",
    "tham_gia_text": "text_join",
    "ended_text": "text_ended",
    "text_ended": "text_ended",
    "end_text": "text_ended",
    "ketthuc_text": "text_ended",
    "kết_thúc_text": "text_ended",
    "winner_text": "label_winner",
    "label_winner": "label_winner",
    "time_text": "label_time",
    "label_time": "label_time",
    "host_text": "label_host",
    "label_host": "label_host",
    "selected_text": "label_selected",
    "label_selected": "label_selected",
    "package_text": "label_package",
    "label_package": "label_package",
    "template_text": "label_template",
    "label_template": "label_template",
    "dm_text": "dm_winner",
    "dm_winner": "dm_winner",
    "result_winner": "result_winner",
    "result_reroll": "result_reroll",
    "result_no_winner": "result_no_winner",
}


def giveaway_theme_key(raw_key: str) -> str | None:
    key = str(raw_key or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in GIVEAWAY_THEME_DEFAULTS:
        return key
    return GIVEAWAY_THEME_ALIASES.get(key)


def giveaway_theme_value(theme: dict | None, key: str) -> str:
    theme = theme or {}
    value = theme.get(key)
    if value is not None and str(value).strip():
        return str(value)
    return GIVEAWAY_THEME_DEFAULTS.get(key, "")
