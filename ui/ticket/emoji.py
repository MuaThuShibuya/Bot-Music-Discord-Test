from __future__ import annotations

import os


TICKET_THEME_DEFAULTS = {
    "panel_title": "TRUNG TÂM HỖ TRỢ",
    "panel_description": "Bấm **{open_button}** để tạo yêu cầu hỗ trợ.\nGiới hạn: `{limit}` ticket/người.",
    "guide_title": "Hướng Dẫn Ticket",
    "guide_description": "1. Bấm **{open_button}**.\n2. Chọn đúng loại hỗ trợ.\n3. Xác nhận tạo kênh.\n4. Mô tả vấn đề và gửi hình ảnh nếu cần.",
    "created_title": "{type}",
    "created_description": "Xin chào {user}. Hãy mô tả chi tiết vấn đề cần hỗ trợ.",
    "type_prompt": "Chọn hạng mục cần hỗ trợ.",
    "confirm_prompt": "Tạo ticket **{type}**?",
    "button_open": "Mở Ticket",
    "button_guide": "Hướng dẫn",
    "button_claim": "Claim",
    "button_manage": "Quản lý",
    "button_close": "Đóng",
    "button_confirm": "Xác nhận",
    "button_cancel": "Hủy",
    "type_support": "Hỗ trợ chung/event",
    "type_bug": "Báo lỗi",
    "type_report": "Tố cáo",
    "type_payment": "Thanh toán",
    "type_contact_admin": "Liên hệ Admin",
    "autoresponse_support": "Vui lòng chụp ảnh lệnh oxp/olvl, kèm ảnh trúng GA hoặc ảnh request (nếu có) để admin xử lý nhanh nhất nhé!",
    "autoresponse_bug": "Vui lòng mô tả chi tiết lỗi bạn gặp phải và đính kèm hình ảnh/video (nếu có).",
    "autoresponse_report": "Vui lòng cung cấp ID/tên người vi phạm, hình ảnh hoặc video bằng chứng rõ ràng.",
    "autoresponse_payment": "Vui lòng gửi hình ảnh bill chuyển khoản hoặc mã giao dịch để admin kiểm tra.",
    "autoresponse_contact_admin": "Vui lòng để lại lời nhắn chi tiết, admin sẽ phản hồi bạn trong thời gian sớm nhất.",
    "icon_ticket": "🎫",
    "icon_support": "🛡️",
    "icon_bug": "🐛",
    "icon_report": "⚠️",
    "icon_payment": "💳",
    "icon_contact_admin": "👑",
    "icon_claim": "👋",
    "icon_close": "🔒",
    "icon_confirm": "✅",
    "icon_cancel": "❌",
    "icon_log": "📁",
    "icon_manage": "🛠️",
}

TICKET_CONTENT_FIELDS = {
    key: value
    for key, value in TICKET_THEME_DEFAULTS.items()
    if not key.startswith("icon_")
}
TICKET_ICON_FIELDS = {
    key: value
    for key, value in TICKET_THEME_DEFAULTS.items()
    if key.startswith("icon_")
}


FALLBACK_EMOJIS = {
    "ticket": "🎫",
    "support": "🛡️",
    "bug": "🐛",
    "report": "⚠️",
    "payment": "💳",
    "contact_admin": "👑",
    "claim": "👋",
    "close": "🔒",
    "confirm": "✅",
    "cancel": "❌",
    "success": "✅",
    "error": "❌",
    "add_user": "👤",
    "remove_user": "🗑️",
    "rename": "✏️",
    "log": "📁",
    "settings": "⚙️",
    "manage": "🛠️",
    "refresh": "🔄",
    "channel": "📺",
    "back": "⬅️",
}

# Có thể điền trực tiếp Discord emoji ID tại đây.
DISCORD_EMOJI_IDS = {
    "ticket": "",
    "support": "",
    "bug": "",
    "report": "",
    "payment": "",
    "contact_admin": "",
    "claim": "",
    "close": "",
    "confirm": "",
    "cancel": "",
    "success": "",
    "error": "",
    "add_user": "",
    "remove_user": "",
    "rename": "",
    "log": "",
    "settings": "",
    "manage": "",
    "refresh": "",
    "channel": "",
    "back": "",
}


def ticket_theme_value(theme: dict | None, key: str) -> str:
    theme = theme or {}
    value = theme.get(key)
    if value is not None and str(value).strip():
        return str(value)
    return TICKET_THEME_DEFAULTS.get(key, "")


def ticket_emoji(key: str, theme: dict | None = None) -> str:
    theme = theme or {}
    custom = theme.get(f"icon_{key}")
    if custom is not None and str(custom).strip():
        return str(custom)
    emoji_id = os.getenv(
        f"TICKET_EMOJI_{key.upper()}_ID",
        DISCORD_EMOJI_IDS.get(key, ""),
    ).strip()
    if emoji_id.startswith("<:") or emoji_id.startswith("<a:"):
        return emoji_id
    if emoji_id.isdigit():
        return f"<:{key}:{emoji_id}>"
    return TICKET_THEME_DEFAULTS.get(
        f"icon_{key}",
        FALLBACK_EMOJIS.get(key, FALLBACK_EMOJIS["ticket"]),
    )


def ticket_text(key: str, text: str, theme: dict | None = None) -> str:
    return f"{ticket_emoji(key, theme)} {text}"
