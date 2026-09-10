from __future__ import annotations

import discord
from discord.ui import View

from ui.ticket.emoji import ticket_text, ticket_theme_value
from utils import create_error_splash, create_info_splash, create_success_splash


TICKET_TYPES = {
    "support": "Hỗ trợ chung/event",
    "bug": "Báo lỗi",
    "report": "Tố cáo",
    "payment": "Thanh toán",
    "contact_admin": "Liên hệ Admin",
}


def ticket_types(theme: dict | None = None) -> dict[str, str]:
    return {
        key: ticket_theme_value(theme, f"type_{key}") or fallback
        for key, fallback in TICKET_TYPES.items()
    }


def format_ticket_template(theme: dict | None, key: str, **values) -> str:
    template = ticket_theme_value(theme, key)
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template


async def safe_interaction_send(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    view: View | None = None,
    ephemeral: bool = True,
):
    kwargs = {"ephemeral": ephemeral}
    if content is not None:
        kwargs["content"] = content
    if embed is not None:
        kwargs["embed"] = embed
    if view is not None:
        kwargs["view"] = view
    if interaction.response.is_done():
        return await interaction.followup.send(**kwargs)
    return await interaction.response.send_message(**kwargs)


async def defer_interaction(interaction: discord.Interaction, *, ephemeral: bool = True):
    if interaction.response.is_done():
        return
    try:
        await interaction.response.defer(ephemeral=ephemeral, thinking=True)
    except discord.InteractionResponded:
        pass


def build_ticket_error_embed(title: str, description: str) -> discord.Embed:
    return create_error_splash(ticket_text("error", title), description)


def build_ticket_success_embed(title: str, description: str) -> discord.Embed:
    return create_success_splash(ticket_text("success", title), description)


def build_ticket_notice_embed(icon: str, title: str, description: str) -> discord.Embed:
    return create_info_splash(ticket_text(icon, title), description)


def build_ticket_help_embed(prefix: str) -> discord.Embed:
    return build_ticket_notice_embed(
        "ticket",
        "Ticket",
        (
            f"`{prefix}ticket manager` mở bảng quản lý.\n"
            f"`{prefix}ticket panel` gửi/refresh panel.\n"
            f"`{prefix}ticket add|remove @user`\n"
            f"`{prefix}ticket rename <tên>`\n"
            f"`{prefix}ticket transfer @user`\n"
            f"`{prefix}ticket unclaim|info|close [lý do]`\n\n"
            f"**Lệnh tắt (Dùng thẳng trong ticket):**\n"
            f"`{prefix}tickclose [lý do]` - Đóng ticket nhanh\n"
            f"`{prefix}ticksetname <tên>` - Đổi tên ticket nhanh\n"
            f"`{prefix}tickremind` - Nhắc user đóng ticket"
        ),
    )


def build_ticket_manager_embed(cog, guild: discord.Guild) -> discord.Embed:
    config = cog.service.ensure_config(guild.id)

    def channel_text(value):
        return f"<#{value}>" if value else "Chưa chọn"

    roles = cog.command_roles(guild)
    role_text = ", ".join(role.mention for role in roles) if roles else "Chưa có. Dùng `baddrole @role ticket`."
    embed = discord.Embed(
        title=ticket_text("settings", "Ticket Manager"),
        description="Ticket dùng chung quyền `ticket` trong role database.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Panel", value=channel_text(config.get("panel_channel_id")), inline=False)
    embed.add_field(name="Danh mục Ticket", value=channel_text(config.get("ticket_category_id")), inline=False)
    embed.add_field(name="Danh mục lưu trữ", value=channel_text(config.get("archive_category_id")), inline=False)
    embed.add_field(name="Kênh log", value=channel_text(config.get("log_channel_id")), inline=False)
    embed.add_field(name="Role quản trị Ticket", value=role_text, inline=False)
    mention_lines = []
    for ticket_type, label in ticket_types(cog.service.get_theme(guild.id)).items():
        targets = cog.service.get_type_mentions(guild.id, ticket_type)
        mentions = [
            f"<@&{row['target_id']}>" if row["target_type"] == "role" else f"<@{row['target_id']}>"
            for row in targets
        ]
        visible = mentions[:5]
        if len(mentions) > len(visible):
            visible.append(f"và {len(mentions) - len(visible)} mục khác")
        mention_lines.append(f"**{label}:** {', '.join(visible) if visible else 'Chưa cài'}")
    embed.add_field(name="Tag theo mục", value="\n".join(mention_lines), inline=False)
    embed.add_field(name="Giới hạn", value=f"`{config.get('max_open_tickets', 1)}` ticket/user", inline=True)
    embed.add_field(name="Cooldown", value=f"`{config.get('cooldown_seconds', 60)} giây`", inline=True)
    embed.add_field(name="Đóng ticket", value=f"`{config.get('close_mode', 'archive')}`", inline=True)
    return embed


def build_ticket_guide_embed(theme: dict | None = None) -> discord.Embed:
    return discord.Embed(
        title=ticket_text("log", ticket_theme_value(theme, "guide_title"), theme),
        description=format_ticket_template(
            theme,
            "guide_description",
            open_button=ticket_theme_value(theme, "button_open"),
        ),
        color=discord.Color.blurple(),
    )


def build_ticket_create_progress_embed() -> discord.Embed:
    return create_info_splash(
        ticket_text("ticket", "Đang tạo Ticket"),
        "Bot đang thiết lập kênh hỗ trợ cho bạn...",
    )


def build_ticket_create_cancelled_embed() -> discord.Embed:
    return create_info_splash(ticket_text("cancel", "Đã Hủy"), "Không tạo ticket.")


def build_ticket_close_progress_embed() -> discord.Embed:
    return create_info_splash(
        ticket_text("close", "Đang Đóng Ticket"),
        "Bot đang lưu transcript và xử lý ticket...",
    )


def build_ticket_close_cancelled_embed() -> discord.Embed:
    return create_info_splash(ticket_text("cancel", "Đã Hủy"), "Ticket vẫn tiếp tục mở.")


def build_ticket_panel_embed(config: dict, theme: dict | None = None) -> discord.Embed:
    return discord.Embed(
        title=ticket_text("ticket", ticket_theme_value(theme, "panel_title"), theme),
        description=format_ticket_template(
            theme,
            "panel_description",
            open_button=ticket_theme_value(theme, "button_open"),
            limit=config.get("max_open_tickets", 1),
        ),
        color=discord.Color.blurple(),
    )


def build_ticket_created_embed(user: discord.Member, ticket_type: str, theme: dict | None = None) -> discord.Embed:
    type_label = ticket_types(theme).get(ticket_type, ticket_type)
    embed = discord.Embed(
        title=ticket_text(
            "ticket",
            format_ticket_template(theme, "created_title", type=type_label),
            theme,
        ),
        description=format_ticket_template(
            theme,
            "created_description",
            user=user.mention,
            type=type_label,
        ),
        color=discord.Color.green(),
    )
    auto_res = ticket_theme_value(theme, f"autoresponse_{ticket_type}")
    if auto_res:
        embed.add_field(name="📌 Yêu cầu tự động", value=auto_res, inline=False)
    return embed


def build_ticket_info_embed(ticket: dict) -> discord.Embed:
    embed = discord.Embed(title=ticket_text("ticket", "Thông Tin Ticket"), color=discord.Color.blurple())
    embed.add_field(name="ID", value=f"`{ticket['ticket_id']}`", inline=True)
    embed.add_field(name="Chủ Ticket", value=f"<@{ticket['owner_user_id']}>", inline=True)
    embed.add_field(name="Loại", value=f"`{ticket['ticket_type']}`", inline=True)
    embed.add_field(name="Trạng thái", value=f"`{ticket['status']}`", inline=True)
    claimed = f"<@{ticket['claimed_by_user_id']}>" if ticket.get("claimed_by_user_id") else "Chưa có"
    embed.add_field(name="Người nhận", value=claimed, inline=True)
    return embed


def build_ticket_closed_embed(
    ticket: dict,
    closer: discord.Member,
    opened_text: str,
    reason: str,
) -> discord.Embed:
    embed = discord.Embed(title="Ticket Closed", color=discord.Color.dark_grey())
    embed.add_field(name="Ticket ID", value=f"`{ticket['ticket_id']}`", inline=False)
    embed.add_field(name="Mở bởi", value=f"<@{ticket['owner_user_id']}>", inline=True)
    embed.add_field(name="Đóng bởi", value=closer.mention, inline=True)
    embed.add_field(name="Thời gian mở", value=opened_text, inline=False)
    embed.add_field(name="Lý do", value=reason or "Không có", inline=False)
    return embed
