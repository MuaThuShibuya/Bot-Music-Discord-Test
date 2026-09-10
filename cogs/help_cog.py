"""
Custom help menu
- Index page with category overview
- Dropdown navigation for categories
- Detailed command cards per category
"""

from __future__ import annotations

from typing import Optional

import discord
from discord.ext import commands

from config import APP_NAME, SUPPORT_SERVER_URL
from utils import get_prefix


HELP_CATEGORIES = [
    {
        "key": "general",
        "emoji": "❓",
        "title": "General",
        "description": "Lệnh cơ bản và tra cứu nhanh",
        "commands": [
            {
                "name": "help",
                "description": "Mở bảng lệnh hoặc xem chi tiết một command",
                "usage": "[command]",
                "aliases": ["commands"],
            },
            {"name": "afk", "description": "Đặt trạng thái AFK và báo lý do khi có người tag", "usage": "[lý do]", "aliases": []},
            {"name": "random", "description": "Lấy một số ngẫu nhiên từ 1 đến số đã nhập", "usage": "<số lớn nhất>", "aliases": ["rand", "rd"]},
            {"name": "pick", "description": "Chọn ngẫu nhiên một mục trong danh sách", "usage": "<mục 1, mục 2, mục 3>", "aliases": ["choose", "chon", "chọn"]},
            {"name": "uptime", "description": "Xem uptime, RAM, memory bot và dung lượng VPS", "usage": "", "aliases": ["upt", "system", "sys", "stats", "st"]},
        ],
    },
    {
        "key": "user",
        "emoji": "👤",
        "title": "User",
        "description": "Lệnh cho mọi người dùng",
        "commands": [
            {"name": "cash", "description": "Xem số dư hoặc quản trị cash", "usage": "[@user|all] | a|r|e @user amount", "aliases": []},
            {"name": "avatar", "description": "Xem avatar user bằng mention, ID hoặc chính bạn", "usage": "[@user|id]", "aliases": ["av", "ava", "avata"]},
            {"name": "banner", "description": "Xem banner/bìa user hoặc bìa server", "usage": "[@user|id]", "aliases": ["bn", "bia", "bìa"]},
            {"name": "donate", "description": "Donate cho server bằng QR/bank hoặc cash", "usage": "[bank|qr|cash] [amount] [nội dung] | check | top | config ...", "aliases": ["dn", "dnt"]},
            {"name": "give", "description": "Chuyển cash cho user khác", "usage": "@user amount hoặc amount @user", "aliases": []},
            {"name": "math", "description": "Tính toán nhanh với số có dấu phẩy hoặc dấu chấm", "usage": "<biểu thức>", "aliases": ["calc", "tinh", "tính"]},
            {"name": "naptien", "description": "Tạo QR nạp cash, kiểm tra giao dịch và admin xem số dư ACB", "usage": "<amount> | check [id|code] | reload|sodu|balance | config ...", "aliases": ["nap"]},
            {"name": "note", "description": "Ghi chú cá nhân, note cho người khác, public/private và TXT popup", "usage": "[@user] <nội dung|txt> | public|private [@user] | edit [@user] số ... | del 1,2", "aliases": []},
            {"name": "notes", "description": "Xem danh sách note bằng embed", "usage": "[@user]", "aliases": []},
            {"name": "points", "description": "Xem hoặc quản trị points", "usage": "[@user|all] | a|r|e @user amount", "aliases": []},
            {"name": "profile", "description": "Xem profile của bạn hoặc người khác", "usage": "[@user]", "aliases": []},
            {"name": "snipe", "description": "Xem lịch sử tin nhắn vừa bị xoá trong kênh", "usage": "[số|all]", "aliases": ["sn"]},
            {"name": "setname", "description": "Tự đổi nickname; đổi tên người khác cần hard admin hoặc role DB", "usage": "[@user] <tên mới>", "aliases": ["setnick", "nickname"]},
            {"name": "level", "description": "Thống kê level, tin nhắn, voice và role reward", "usage": "[@user] [total|month|week|day]", "aliases": ["lv"]},
            {"name": "time", "description": "Xem hoặc quản trị tổng giờ", "usage": "[@user|all] | a|r|e @user hours", "aliases": []},
            {"name": "topusers", "description": "Xem top users", "usage": "[limit]", "aliases": []},
        ],
    },
    {
        "key": "bot",
        "emoji": "🎧",
        "title": "Bot",
        "description": "Voice, đọc giọng Google và phát nhạc",
        "commands": [
            {"name": "join", "description": "Cho bot vào voice channel của bạn", "usage": "", "aliases": ["j"]},
            {"name": "say", "description": "Bot đọc nội dung bằng giọng Google", "usage": "<nội dung>", "aliases": ["s"]},
            {"name": "leave", "description": "Cho bot rời voice nếu bạn là người mời bot vào", "usage": "", "aliases": ["l", "disconnect", "dc"]},
            {"name": "play", "description": "Phát nhạc bằng player canvas, playlist và Radio autoplay cùng chủ đề", "usage": "<url|từ khóa|playlist> | q|sh|a|s|p|r|st|l|n|lo|v|rm|c|settings", "aliases": ["a", "p"]},
        ],
    },
    {
        "key": "booking",
        "emoji": "📘",
        "title": "Booking",
        "description": "Lệnh booking, thống kê giờ, nạp tiền và quà",
        "commands": [
            {"name": "book", "description": "Ghi nhận book theo giờ, hỗ trợ cash hoặc banking", "usage": "@booking 1,2,5 [@user] [cash|banking]", "aliases": []},
            {"name": "luong", "description": "Xem hoặc quản trị lương booking", "usage": "[@user|all] | a|r|e @user amount", "aliases": []},
            {"name": "star", "description": "Xem booking, ghi nhận nạp tiền hoặc quản trị star", "usage": "money|top|@user|all | a|r|e @user amount", "aliases": []},
            {"name": "tinhluong", "description": "Gửi bảng tính lương booking qua DM", "usage": "[@user|all]", "aliases": []},
            {"name": "traluong", "description": "Trả phần lương còn lại và reset về 0", "usage": "@user|all", "aliases": ["payluong"]},
            {"name": "topbook", "description": "Xem top giờ được book nhất (admin/role DB)", "usage": "[limit]", "aliases": []},
            {"name": "topnap", "description": "Xem top người nạp tiền nhiều nhất (admin/role DB)", "usage": "[limit]", "aliases": []},
            {"name": "topgift", "description": "Xem tổng quà đang có", "usage": "", "aliases": []},
        ],
    },
    {
        "key": "administrator",
        "emoji": "🛡️",
        "title": "Administrator",
        "description": "Danh sách lệnh trong danh mục Administrator",
        "commands": [
            {"name": "addadmin", "description": "Thêm admin bot trong server hiện tại", "usage": "@user | user_id server_id trong DM", "aliases": ["themadmin"]},
            {"name": "addcashadmin", "description": "Thêm quyền quản trị cash/naptien trong server", "usage": "@user | user_id server_id trong DM", "aliases": ["themcashadmin", "cashadmin"]},
            {"name": "addcash", "description": "Cộng cash cho user", "usage": "@user amount", "aliases": ["ac"]},
            {"name": "addluong", "description": "Cộng lương cho booking", "usage": "@user amount", "aliases": ["al"]},
            {"name": "addpoints", "description": "Thêm/sửa/trừ points cho user", "usage": "[@user amount] | a|r|e @user amount", "aliases": []},
            {"name": "addtime", "description": "Thêm/sửa/trừ giờ cho user", "usage": "[@user hours] | a|r|e @user hours", "aliases": []},
            {"name": "ar", "description": "Quản lý auto res và responsive profile", "usage": "a|r|e|set|description|iurl|turl ...", "aliases": []},
            {"name": "ban", "description": "Ban hoặc ban tạm thời một user", "usage": "@user|username|id [time] [reason]", "aliases": []},
            {"name": "bookconfig", "description": "Xem cấu hình giá booking", "usage": "", "aliases": ["bookingconfig", "giabook"]},
            {"name": "cogs", "description": "Liệt kê các cog đang load", "usage": "", "aliases": []},
            {"name": "color", "description": "Đổi màu role", "usage": "@role <hex|name>", "aliases": []},
            {"name": "command", "description": "Bật hoặc tắt command theo từng channel", "usage": "enable|disable <command>", "aliases": ["cmd"]},
            {"name": "enable", "description": "Bật lại command trong channel hiện tại", "usage": "<command>", "aliases": []},
            {"name": "disable", "description": "Tắt command trong channel hiện tại", "usage": "<command>", "aliases": []},
            {"name": "emoji", "description": "Quản lý emoji", "usage": "a|r|list ...", "aliases": []},
            {"name": "form", "description": "Gửi mẫu form booking để booking tự điền", "usage": "[key]", "aliases": ["form<key>"]},
            {"name": "giveaway", "description": "Tạo giveaway và mở menu chỉnh nội dung/icon", "usage": "<time> <winners> <reward> [quantity] | config", "aliases": ["ga"]},
            {"name": "group", "description": "Quản lý bot join/leave server bằng splash", "usage": "join [invite] | leave", "aliases": ["g"]},
            {"name": "gitpull", "description": "Đồng bộ VPS với GitHub, hỗ trợ lịch sử bị force-push", "usage": "", "aliases": ["pull", "update"]},
            {"name": "gitstatus", "description": "Xem trạng thái git hiện tại", "usage": "", "aliases": ["status"]},
            {"name": "end", "description": "End giveaway theo ID", "usage": "<giveaway_id>", "aliases": []},
            {"name": "gastop", "description": "Dừng giveaway theo ID", "usage": "<giveaway_id>", "aliases": []},
            {"name": "load", "description": "Load một cog hoặc cả catalog", "usage": "<catalog|module>", "aliases": []},
            {
                "name": "log",
                "description": "Setup log toàn server: chat, voice, channel, server, cash và member join/leave",
                "usage": "[chat|voice|channel|server|cash|join #channel] | all #channel | off <loại> | voice room|joinmsg|leavemsg|embed",
                "aliases": ["logs"],
            },
            {"name": "kick", "description": "Kick một member khỏi server", "usage": "@user|username|id [reason]", "aliases": []},
            {"name": "lock", "description": "Khoá chat tại kênh hiện tại hoặc kênh được tag", "usage": "[#channel]", "aliases": []},
            {"name": "mute", "description": "Mute một thành viên", "usage": "@user|username|id [duration] [reason]", "aliases": []},
            {"name": "prefix", "description": "Đổi prefix của bot", "usage": "<value>", "aliases": []},
            {"name": "rate", "description": "Xem hoặc đặt tỷ giá cash VND / OWO casino", "usage": "[cash <hệ số> owo <hệ số>]", "aliases": []},
            {"name": "reload", "description": "Reload một cog, một catalog hoặc tất cả", "usage": "[catalog|module]", "aliases": []},
            {"name": "reroll", "description": "Quay lại winner giveaway theo ID", "usage": "<giveaway_id>", "aliases": []},
            {"name": "gareroll", "description": "Quay lại winner giveaway theo ID", "usage": "<giveaway_id>", "aliases": []},
            {"name": "res", "description": "Gọi auto res theo key tùy chỉnh", "usage": "<key>", "aliases": []},
            {"name": "role", "description": "Cấp hoặc gỡ Discord role cho user", "usage": "a|r @user @role", "aliases": []},
            {"name": "addrole", "description": "Cấp quyền dùng command cho 1 hoặc nhiều role", "usage": "@role1, @role2 command1, command2", "aliases": ["themrole"]},
            {"name": "removerole", "description": "Xóa quyền dùng command khỏi 1 hoặc nhiều role", "usage": "@role1, @role2 command1, command2", "aliases": ["rmrole", "xoarole"]},
            {"name": "setrole", "description": "Gán Discord role làm role hệ thống qua menu chọn", "usage": "@role|role_id [admin|booking|user|staff]", "aliases": []},
            {"name": "perms", "description": "Xem role nào đang có quyền", "usage": "command1, command2", "aliases": []},
            {"name": "myroles", "description": "Xem role của bạn hoặc user khác", "usage": "[@user]", "aliases": []},
            {"name": "rolescommands", "description": "Xem role đang dùng được lệnh nào", "usage": "@role|role_id", "aliases": []},
            {"name": "rmadmin", "description": "Xóa admin bot khỏi server hiện tại", "usage": "@user | user_id server_id trong DM", "aliases": ["xoaadmin"]},
            {"name": "rmcashadmin", "description": "Xóa quyền quản trị cash/naptien trong server", "usage": "@user | user_id server_id trong DM", "aliases": ["xoacashadmin"]},
            {"name": "setan", "description": "Đặt phần trăm bot/server ăn từ booking", "usage": "<percent>", "aliases": ["setfee", "sethoahong"]},
            {"name": "setgiobook", "description": "Đặt giá tiền cho 1h booking", "usage": "<amount>", "aliases": ["setgia", "giabooking"]},
            {"name": "setphantram", "description": "Đặt phần trăm tiền trả cho booking", "usage": "<percent>", "aliases": ["setpayout", "settraluong"]},
            {"name": "steal", "description": "Thêm custom emoji hoặc ảnh URL vào server", "usage": "<emoji> [name] | <url> <name>", "aliases": []},
            {"name": "subcash", "description": "Trừ cash của user", "usage": "@user amount", "aliases": ["sc"]},
            {"name": "subluong", "description": "Trừ lương của booking", "usage": "@user amount", "aliases": ["sl"]},
            {"name": "subtime", "description": "Trừ giờ của user", "usage": "@user hours", "aliases": []},
            {"name": "ticket", "description": "Quản lý Ticket và tùy chỉnh nội dung/icon", "usage": "manager|config|panel|add|remove|rename|transfer|unclaim|info|close", "aliases": []},
            {"name": "tongluong", "description": "Xem tổng lương", "usage": "", "aliases": ["tl"]},
            {"name": "topstar", "description": "Xem top star", "usage": "[limit]", "aliases": []},
            {"name": "unban", "description": "Gỡ ban một thành viên", "usage": "user_id [reason]", "aliases": []},
            {"name": "unload", "description": "Unload một cog hoặc cả catalog", "usage": "<catalog|module>", "aliases": []},
            {"name": "unmute", "description": "Gỡ mute một thành viên", "usage": "@user|username|id [reason]", "aliases": []},
            {"name": "unlock", "description": "Mở khoá chat tại kênh hiện tại hoặc kênh được tag", "usage": "[#channel]", "aliases": []},
            {"name": "up", "description": "Up responsive profile lên channel chỉ định", "usage": "<key><số> #channel", "aliases": []},
        ],
        "slash_commands": [
            {"name": "antiraid", "description": "Bật/tắt chống raid", "usage": "mode: on|off", "aliases": []},
            {"name": "antinuke", "description": "Bật/tắt chống nuke", "usage": "mode: on|off", "aliases": []},
            {"name": "giveaway", "description": "Một slash tổng để tạo/end/reroll/config giveaway", "usage": "action: create|end|reroll|config", "aliases": []},
            {"name": "command", "description": "Bật hoặc tắt command trong channel hiện tại", "usage": "action: enable|disable command_name:<lệnh>", "aliases": []},
            {"name": "group", "description": "Một slash tổng, chọn join/leave bên trong", "usage": "action: join|leave", "aliases": []},
            {
                "name": "log",
                "description": "Một slash tổng để setup log toàn server",
                "usage": "action: show|set|off|test|voice-announce|voice-room|voice-join-message|voice-leave-message|voice-embed",
                "aliases": [],
            },
            {"name": "steal", "description": "Thêm custom emoji hoặc URL ảnh vào server", "usage": "emoji:<emoji|url> [name]", "aliases": []},
            {"name": "ticket", "description": "Quản lý, xem thông tin hoặc đóng ticket", "usage": "manager|info|close", "aliases": []},
        ],
    },
]


THEME_COLOR = discord.Color.from_rgb(46, 48, 53)
ACCENT_COLOR = discord.Color.from_rgb(180, 205, 255)


def _find_category(category_key: str) -> Optional[dict]:
    for category in HELP_CATEGORIES:
        if category["key"] == category_key:
            return category
    return None


def _find_command(command_name: str) -> tuple[Optional[dict], Optional[dict]]:
    lowered = command_name.lower()
    for category in HELP_CATEGORIES:
        for command in category["commands"]:
            aliases = [alias.lower() for alias in command.get("aliases", [])]
            if lowered == command["name"].lower() or lowered in aliases:
                return category, command
    return None, None


def _is_role_management_key(command_name: str) -> bool:
    return command_name.lower() in {"role", "roles", "rolemanagement", "role_management"}


def _role_management_commands() -> list[dict]:
    role_command_names = {
        "role",
        "addrole",
        "removerole",
        "setrole",
        "perms",
        "myroles",
        "rolescommands",
        "addadmin",
        "rmadmin",
        "addcashadmin",
        "rmcashadmin",
    }
    admin_category = _find_category("administrator")
    if not admin_category:
        return []
    return [command for command in admin_category["commands"] if command["name"] in role_command_names]


def _format_usage(command: dict, guild_id: int | None = None) -> str:
    usage = command["usage"].strip()
    prefix = get_prefix(guild_id)
    command_text = f"{prefix}{command['name']}"
    if usage:
        command_text = f"{command_text} {usage}"
    return f"`{command_text}`"


def _category_total_commands(category: dict) -> int:
    return len(category.get("commands", [])) + len(category.get("slash_commands", []))


def _build_support_button() -> discord.ui.Button:
    return discord.ui.Button(
        label="Support Server",
        style=discord.ButtonStyle.link,
        url=SUPPORT_SERVER_URL,
        emoji="↗",
    )


async def _safe_edit_help(interaction: discord.Interaction, embed: discord.Embed, view: discord.ui.View):
    try:
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.response.edit_message(embed=embed, view=view)
    except Exception as exc:
        print(f"❌ Lỗi tương tác help menu: {exc}")
        if interaction.response.is_done():
            await interaction.followup.send("❌ Menu help cũ bị lỗi. Gõ lại `help` để mở menu mới.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Menu help cũ bị lỗi. Gõ lại `help` để mở menu mới.", ephemeral=True)


class HelpCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=category["title"],
                value=category["key"],
                description=category["description"][:100],
                emoji=category["emoji"],
            )
            for category in HELP_CATEGORIES
        ]
        super().__init__(
            placeholder="Chọn category để xem chi tiết...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="help:category_select",
        )

    async def callback(self, interaction: discord.Interaction):
        category = _find_category(self.values[0])
        if not category:
            await interaction.response.send_message("❌ Không tìm thấy category.", ephemeral=True)
            return

        await _safe_edit_help(
            interaction,
            embed=HelpView.build_category_embed(category, interaction.guild),
            view=CategoryView(category["key"]),
        )


class HomeButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Trang chủ",
            style=discord.ButtonStyle.primary,
            emoji="🏠",
            custom_id="help:home",
        )

    async def callback(self, interaction: discord.Interaction):
        await _safe_edit_help(
            interaction,
            embed=HelpView.build_index_embed(interaction.guild),
            view=IndexView(),
        )


class BackButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Quay lại",
            style=discord.ButtonStyle.secondary,
            emoji="⬅",
            custom_id="help:back",
        )

    async def callback(self, interaction: discord.Interaction):
        await _safe_edit_help(
            interaction,
            embed=HelpView.build_index_embed(interaction.guild),
            view=IndexView(),
        )


class IndexView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(HelpCategorySelect())
        self.add_item(_build_support_button())


class CategoryView(discord.ui.View):
    def __init__(self, category_key: str):
        super().__init__(timeout=None)
        self.category_key = category_key
        self.add_item(BackButton())
        self.add_item(HomeButton())
        self.add_item(_build_support_button())


class HelpView:
    @staticmethod
    def build_index_embed(guild: discord.Guild | None = None) -> discord.Embed:
        prefix = get_prefix(guild.id if guild else None)
        title_name = guild.name if guild else APP_NAME
        embed = discord.Embed(
            title=f"{title_name} Commands Directory",
            color=THEME_COLOR,
        )
        embed.description = (
            f"Dùng menu bên dưới để xem category.\n"
            f"Prefix hiện tại: `{prefix}`\n"
            f"Xem chi tiết một lệnh: `{prefix}help <command>`"
        )

        for category in HELP_CATEGORIES:
            embed.add_field(
                name=f"{category['emoji']} **{category['title']}** [{_category_total_commands(category)}]",
                value=category["description"],
                inline=False,
            )

        embed.set_author(name=APP_NAME)
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        else:
            embed.set_thumbnail(url="https://cdn.discordapp.com/embed/avatars/0.png")
        embed.set_footer(text=f"{len(HELP_CATEGORIES)} categories • {prefix}help")
        return embed

    @staticmethod
    def build_category_embed(category: dict, guild: discord.Guild | None = None) -> discord.Embed:
        prefix = get_prefix(guild.id if guild else None)
        category_title = category["title"]
        embed = discord.Embed(
            title=f"{category['emoji']} {category_title}",
            description=(
                f"Danh sách lệnh trong danh mục **{category_title}**"
                if category["key"] == "administrator"
                else category["description"]
            ),
            color=ACCENT_COLOR,
        )

        if category["key"] == "administrator":
            prefix_commands = ", ".join(f"`{command['name']}`" for command in category["commands"])
            slash_commands = ", ".join(f"`{command['name']}`" for command in category.get("slash_commands", []))

            embed.add_field(
                name="**Prefix:**",
                value=prefix_commands,
                inline=False,
            )
            if slash_commands:
                embed.add_field(
                    name="**Slash:**",
                    value=slash_commands,
                    inline=False,
                )
        else:
            for command in category["commands"]:
                alias_text = ""
                if command.get("aliases"):
                    alias_list = ", ".join(f"`{prefix}{alias}`" for alias in command["aliases"])
                    alias_text = f"\nAliases: {alias_list}"

                embed.add_field(
                    name=_format_usage(command, guild.id if guild else None),
                    value=f"{command['description']}{alias_text}",
                    inline=False,
                )
            if category.get("slash_commands"):
                slash_commands = ", ".join(f"`/{command['name']}`" for command in category["slash_commands"])
                embed.add_field(
                    name="**Slash:**",
                    value=slash_commands,
                    inline=False,
                )

        embed.set_author(name=guild.name if guild else APP_NAME)
        embed.set_footer(text=f"Tổng cộng {_category_total_commands(category)} lệnh • {prefix}help <command>")
        return embed

    @staticmethod
    def build_command_embed(category: dict, command: dict, guild: discord.Guild | None = None) -> discord.Embed:
        prefix = get_prefix(guild.id if guild else None)
        embed = discord.Embed(
            title=f"{category['emoji']} {command['name']}",
            color=ACCENT_COLOR,
        )
        embed.add_field(name="Cú pháp", value=_format_usage(command, guild.id if guild else None), inline=False)
        embed.add_field(name="Mô tả", value=command["description"], inline=False)
        embed.add_field(name="Category", value=category["title"], inline=True)
        if command.get("aliases"):
            embed.add_field(
                name="Aliases",
                value=", ".join(f"`{prefix}{alias}`" for alias in command["aliases"]),
                inline=True,
            )
        if command["name"] == "book":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`book @booking 1` - ghi nhận book 1h, mặc định phương thức banking\n"
                    "`book @booking 1,2,5 @user cash` - ghi nhận nhiều mốc giờ và trừ cash của user thanh toán\n"
                    "`book @booking 10 @user banking` - ghi nhận booking nhưng không trừ ví cash\n"
                    "Nếu chọn `cash` mà người thanh toán không đủ tiền trong ví, bot sẽ báo lỗi và không ghi book."
                ),
                inline=False,
            )
        if command["name"] == "star":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`star` - xem giờ book và số tiền đã tiêu của bạn\n"
                    "`star @user` - xem booking người khác nếu có quyền\n"
                    "`star all` - xem tất cả star trong users DB\n"
                    "`star a/add @user <amount>` - cộng star cho user\n"
                    "`star r/rm/remove/d/delete @user <amount>` - trừ star của user\n"
                    "`star e/edit @user <amount>` - set star của user về số mới\n"
                    "`star money <amount> [@user]` - ghi nhận tiền nạp, hỗ trợ `100k`, `1m`, `1b`\n"
                    "`star top` - top giờ được book và top nạp tiền"
                ),
                inline=False,
            )
        if command["name"] == "cash":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`cash` - xem số dư của bạn\n"
                    "`cash @user` - xem số dư người khác nếu có quyền\n"
                    "`cash all` - xem tất cả cash nếu có quyền\n"
                    "`cash a/add @user <money>` - cộng cash\n"
                    "`cash r/rm/remove/d/delete @user <money>` - trừ cash\n"
                    "`cash e/edit @user <money>` - set cash về số mới"
                ),
                inline=False,
            )
        if command["name"] == "donate":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`dnt` - mở menu chọn Bank/QR hoặc Cash và biểu mẫu nhập tiền\n"
                    "`dnt bank 100k lời nhắn` hoặc `dnt qr 100k lời nhắn` - tạo QR; không cộng cash khi thanh toán\n"
                    "`dnt cash 100k lời nhắn` - trừ cash và ghi nhận donate\n"
                    "`dnt 100k` - mặc định tạo QR bank\n"
                    "`dnt 100k cash lời nhắn` - cú pháp cash dạng đảo vị trí"
                ),
                inline=False,
            )
        if command["name"] == "rate":
            embed.add_field(
                name="Cách dùng",
                value=(
                    f"`{prefix}rate` - xem tỷ giá cash VND / OWO hiện tại\n"
                    f"`{prefix}rate cash 1 owo 1` - đặt 1.000 VND = 1.000.000 OWO\n"
                    f"`{prefix}rate cash 1 owo 0,5` - đặt 1.000 VND = 500.000 OWO\n"
                    "Chỉ bot admin được dùng. Khi đổi tỷ giá, casino sẽ tự đồng bộ lại toàn bộ ví."
                ),
                inline=False,
            )
        if command["name"] == "points":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`points` - xem points của bạn\n"
                    "`points @user` - xem points người khác nếu có quyền\n"
                    "`points all` - xem tất cả points nếu có quyền\n"
                    "`points a/add @user <amount>` - cộng points\n"
                    "`points r/rm/remove/d/delete @user <amount>` - trừ points\n"
                    "`points e/edit @user <amount>` - set points về số mới"
                ),
                inline=False,
            )
        if command["name"] == "time":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`time` - xem tổng giờ của bạn\n"
                    "`time @user` - xem tổng giờ người khác nếu có quyền\n"
                    "`time all` - xem tất cả tổng giờ nếu có quyền\n"
                    "`time a/add @user <hours>` - cộng giờ\n"
                    "`time r/rm/remove/d/delete @user <hours>` - trừ giờ\n"
                    "`time e/edit @user <hours>` - set giờ về số mới"
                ),
                inline=False,
            )
        if command["name"] == "luong":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`luong` - xem bảng lương của bạn ở kênh hiện tại\n"
                    "`luong @user` - xem bảng lương người khác nếu có quyền\n"
                    "`luong all` - xem tất cả bảng lương nếu có quyền\n"
                    "`luong a/add @user <money>` - cộng lương cho booking\n"
                    "`luong r/rm/remove/d/delete @user <money>` - trừ lương booking\n"
                    "`luong e/edit @user <money>` - set lương booking về số mới\n"
                    "User phải có role hệ thống `booking`."
                ),
                inline=False,
            )
        if command["name"] == "traluong":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`traluong @user` - trả toàn bộ số lương còn lại của user đó, gửi DM chi tiết cho admin và DM thông báo cho user\n"
                    "`traluong all` - trả lương tất cả user/booking còn tiền, gửi DM tổng hợp cho admin kèm menu chọn người để xem chi tiết\n"
                    "`luong traluong @user|all` - dùng được nếu muốn gọi trong cụm lương"
                ),
                inline=False,
            )
            embed.add_field(
                name="Quyền",
                value="Chỉ bot admin hoặc role có quyền `traluong`/`luong` trong database mới dùng được.",
                inline=False,
            )
        if command["name"] == "level":
            embed.add_field(
                name=f"`{prefix}level [@user] [total|month|week|day]`",
                value=(
                    "Xem level/stat của bạn hoặc user khác\n"
                    f"Aliases: `{prefix}lv`"
                ),
                inline=False,
            )
            embed.add_field(
                name=f"`{prefix}level all [total|month|week|day] [xp|level|messages|voice] [limit]`",
                value="Bảng xếp hạng level/stat",
                inline=False,
            )
            embed.add_field(
                name=f"`{prefix}level count [total|month|week|day]`",
                value="Xem tổng count user, XP, tin nhắn và voice",
                inline=False,
            )
            embed.add_field(
                name=f"`{prefix}level setup #channel|on|off|messagexp|voicexp|xp easy|normal|hard|manual|levelxp`",
                value="Set kênh thông báo, XP mỗi hoạt động và kiểu XP lên level",
                inline=False,
            )
            embed.add_field(
                name=f"`{prefix}level role add|remove|list <level> [@role]`",
                value="Gán/xóa/list role reward theo mốc level",
                inline=False,
            )
            embed.add_field(
                name="Slash",
                value="`/level`",
                inline=False,
            )
        if command["name"] in {"topstar", "topbook", "topnap"}:
            embed.add_field(
                name="Quyền",
                value="Chỉ admin hoặc role được cấp trong database mới dùng được.",
                inline=False,
            )
        if command["name"] == "give":
            embed.add_field(
                name="Cách dùng",
                value="`give @user 100k` hoặc `give 100k @user`\nChỉ dùng trong server. Hỗ trợ tiền VND: `100000`, `100k`, `1m`, `1b`, `100.000`, `100,000`, `0,01vnđ`.",
                inline=False,
            )
        if command["name"] == "giveaway":
            embed.add_field(
                name="Cách dùng prefix",
                value=(
                    "`ga 1d 1 100k 10` - tạo 10 giveaway, mỗi giveaway 1 ngày, 1 winner, phần thưởng 100k.\n"
                    "`giveaway create 1h 2 Nitro 5` - tạo 5 giveaway Nitro, mỗi giveaway 2 winner.\n"
                    "`ga config` - mở menu sửa emoji, icon và toàn bộ nội dung giveaway.\n"
                    "`ga config emoji 🎁` vẫn dùng được để đổi nhanh emoji tham gia.\n"
                    "Thứ tự `time`, `winners`, `reward` không bắt buộc; riêng số lượng giveaway nếu có thì để cuối."
                ),
                inline=False,
            )
            embed.add_field(
                name="Slash",
                value=(
                    "`/giveaway action:create reward:<nội dung> duration:<10m|1h|1d> winners:<số> quantity:<số lượng ga>`\n"
                    "`/giveaway action:end giveaway_id:<ID>` hoặc `action:reroll` để end/reroll.\n"
                    "`/giveaway action:config` mở menu; thêm `emoji:<emoji>` để đổi nhanh emoji tham gia."
                ),
                inline=False,
            )
            embed.add_field(
                name="Quyền",
                value="Tạo/end/reroll: bot admin hoặc role có quyền `giveaway` trong database.",
                inline=False,
            )
            embed.add_field(
                name="Tham gia",
                value="Người dùng react emoji giveaway vào tin nhắn để tham gia, không dùng nút bấm nữa.",
                inline=False,
            )
        if command["name"] == "group":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`group join <invite>` hoặc `g j <invite>` - tạo splash/link OAuth để mời bot vào server.\n"
                    "`group join` - hiện nút nhập link server.\n"
                    "`group leave` hoặc `g l` - hiện list server bot đang join để chọn rời."
                ),
                inline=False,
            )
            embed.add_field(
                name="Lưu ý",
                value="Discord không cho bot tự join server bằng invite như user. Lệnh join sẽ tạo link OAuth để admin server bấm thêm bot.",
                inline=False,
            )
            embed.add_field(
                name="Slash",
                value=(
                    "`/group action:join server:<invite>` - tạo splash/link OAuth mời bot.\n"
                    "`/group action:join` - hiện modal nhập link server.\n"
                    "`/group action:leave` - hiện list server bot đang join để chọn rời."
                ),
                inline=False,
            )
            embed.add_field(
                name="Quyền",
                value="Chỉ bot admin dùng được trong server hoặc DMs.",
                inline=False,
            )
        if command["name"] in {"end", "gastop"}:
            embed.add_field(
                name="Cách dùng",
                value="`end <id giveaway>` hoặc `gastop <id giveaway>`. ID là ID tin nhắn giveaway, chuột phải tin nhắn rồi chọn **Sao chép ID Tin Nhắn**.",
                inline=False,
            )
        if command["name"] in {"reroll", "gareroll"}:
            embed.add_field(
                name="Cách dùng",
                value="`reroll <id giveaway>` hoặc `gareroll <id giveaway>` để quay winner mới sau khi giveaway đã kết thúc. Số lần reroll được tính riêng theo từng ID giveaway.",
                inline=False,
            )
        if command["name"] == "say":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`say xin chào mọi người` hoặc `s xin chào mọi người` - bot vào voice của bạn và đọc bằng giọng Google.\n"
                    "Nếu bot chưa ở voice, người gọi `say` sẽ là người giữ quyền `play l/leave`.\n"
                    "Nếu không dùng gì thêm trong 5 phút sau khi đọc/phát xong, bot sẽ tự rời voice."
                ),
                inline=False,
            )
        if command["name"] == "play":
            embed.add_field(
                name="Nguồn nhạc",
                value="Hỗ trợ YouTube, YouTube Music, SoundCloud, MixCloud và playlist qua `yt-dlp`. Spotify sẽ cố xử lý qua extractor; nếu link không chạy hãy gửi tên bài hoặc link YouTube/YT Music.",
                inline=False,
            )
            embed.add_field(
                name="Điều khiển",
                value=(
                    "`play <url|từ khóa>`, `p <url|từ khóa>` hoặc `a <url|từ khóa>` - thêm/phát nhạc\n"
                    "`play q/queue` - xem queue\n"
                    "`play sh/shuffle` - trộn queue\n"
                    "`play a/autoplay` - bật/tắt autoplay\n"
                    "`play s/skip`, `play p/pause`, `play r/resume`, `play st/stop`, `play l/leave`\n"
                    "`play n/now`, `play lo/loop`, `play v/vol <0-200>`, `play rm <số>`, `play c/clear`\n"
                    "`play settings` - menu sửa giao diện, nội dung, icon và reaction"
                ),
                inline=False,
            )
            embed.add_field(
                name="Quyền leave",
                value="Người làm bot auto join bằng `join`, `say` hoặc `play` sẽ giữ quyền `play l/leave`. Người khác vẫn có thể thêm nhạc trong cùng voice nhưng không được leave bot.",
                inline=False,
            )
        if command["name"] == "ar":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`ar a <res> | <nội dung>` thêm auto res\n"
                    "`ar a <res>` tạo auto res rỗng\n"
                    "`ar des <res> | <nội dung>` sửa nội dung auto res\n"
                    "`ar des <res>` lấy nội dung auto res từ tin nhắn reply\n"
                    "`ar a <key> <số>` hoặc `ar a <key><số>` thêm profile/form, số `0` dùng được\n"
                    "`ar e <key> <text>` sửa auto res\n"
                    "`ar e <key> <số> <text>` sửa nội dung profile\n"
                    "`ar r/rm/remove/d/delete <key> [số]` xóa auto res hoặc profile\n"
                    "`ar set <key> <số> @user` gắn profile\n"
                    "`ar up <key><số> #channel` up profile sang channel chỉ định\n"
                    "`ar description <key> <số>` hoặc `ar description <key><số>` lấy nội dung từ tin nhắn reply\n"
                    "`ar description <key> <số> | <form>` nhập form thủ công\n"
                    "`ar target <res|profile> @user` gắn target cho auto res hoặc profile, ví dụ `ar target yang @user`, `ar target ad1 @user`\n"
                    "`ar iurl/turl <res> <url|ảnh>` set ảnh auto res\n"
                    "`ar iurl/turl <key> <số> <url|ảnh>` set ảnh profile\n"
                    "`turl` là ảnh đại diện/thumbnail và bot sẽ tự crop vuông khi hiển thị\n"
                    "`ar list <key>` xem các profile đã tạo theo key"
                ),
                inline=False,
            )
            embed.add_field(
                name="Placeholder auto res",
                value="Dùng `{user}` cho người gọi, `{key}` cho key trigger. `{target}` vẫn hỗ trợ nếu đã gắn, nhưng không bắt buộc.",
                inline=False,
            )
        if command["name"] == "form":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`form` gửi nút **Điền form** để user tự nhập và lưu form của họ.\n"
                    "Sau đó admin dùng `ar a ad1 @user` để tạo profile từ form đã lưu và gắn profile luôn.\n"
                    "`form ad1` sẽ hiện nút mở ô nhập và lưu trực tiếp vào profile `ad1`. Có thể gọi dính liền kiểu `formau` để gửi mẫu theo key."
                ),
                inline=False,
            )
        if command["name"] == "res":
            embed.add_field(
                name="Cách dùng",
                value="`res yang` sẽ gọi nội dung auto res của key `yang`. Có thể dùng `{user}`, `{target}`, `{key}` trong nội dung.",
                inline=False,
            )
        if command["name"] == "note":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`note` xem danh sách note của bạn bằng text thường.\n"
                    "`note <nội dung> <số tiền>` thêm note kèm tiền, ví dụ `note mua đồ 100k`.\n"
                    "`note @user` xem note của user đó nếu public hoặc bạn có quyền `note`.\n"
                    "`note @user <nội dung>` thêm note vào người khác nếu họ public hoặc bạn có quyền `note`.\n"
                    "Reply tin nhắn rồi dùng `note` hoặc `note @user` để lưu nội dung thành TXT kèm link nhảy tới tin nhắn gốc.\n"
                    "`note public/private` hoặc `note pb/prv` bật/tắt cho người khác note vào bạn.\n"
                    "`note public/private @user` admin hoặc role `note public`/`note private` bật/tắt cho người khác.\n"
                    "`note @user txt` mở popup nhập tiêu đề và nội dung dài.\n"
                    "`note tiêu đề [file nội dung dài]` lưu dạng TXT; chỉ hiện `- Fix` sau khi đã sửa.\n"
                    "`note view/v [@user] 2` xem thành phẩm TXT; bấm Phóng to để xem đầy đủ, Thu gọn để quay lại bản ngắn.\n"
                    "`note edit/e @user 2 <nội dung>` sửa note; người ngoài chỉ sửa note họ đã thêm.\n"
                    "`note edit/e @user 2 txt` xem nguyên mã nguồn rồi mở popup sửa TXT.\n"
                    "`note del 1,2` hoặc `note d 1,2` xoá note theo số thứ tự.\n"
                    "`note 2 +100k` cộng tiền vào note số 2.\n"
                    "`note 2 -100k` trừ tiền khỏi note số 2.\n"
                    "`notes` xem danh sách note bằng embed."
                ),
                inline=False,
            )
        if command["name"] == "notes":
            embed.add_field(
                name="Cách dùng",
                value="`notes` hiển thị note của bạn trong embed. `notes @user` xem note người khác nếu họ public hoặc bạn có quyền `note`.",
                inline=False,
            )
        if command["name"] == "math":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`math 120+520` ra `640`.\n"
                    "`math 100.000 + 50,000` tự hiểu dấu phân tách số lớn.\n"
                    "Hỗ trợ `+`, `-`, `*`, `/`, `^`, ngoặc `()`."
                ),
                inline=False,
            )
        if command["name"] == "role":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`role a @user @role` để cấp Discord role cho user.\n"
                    "`role r @user @role` để gỡ Discord role khỏi user.\n"
                    "Có thể dùng chữ đầy đủ: `role add @user @role`, `role remove @user @role`, `role rm @user @role`, `role d @user @role`, `role delete @user @role`.\n"
                    "Bot cần quyền `Manage Roles` và role cần cấp/gỡ phải thấp hơn role cao nhất của bot."
                ),
                inline=False,
            )
        if command["name"] == "addpoints":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`addpoints @user <amount>` - cộng points kiểu cũ\n"
                    "`addpoints a/add @user <amount>` - cộng points\n"
                    "`addpoints r/rm/remove/d/delete @user <amount>` - trừ points\n"
                    "`addpoints e/edit @user <amount>` - set points về số mới"
                ),
                inline=False,
            )
        if command["name"] == "addtime":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`addtime @user <hours>` - cộng giờ kiểu cũ\n"
                    "`addtime a/add @user <hours>` - cộng giờ\n"
                    "`addtime r/rm/remove/d/delete @user <hours>` - trừ giờ\n"
                    "`addtime e/edit @user <hours>` - set giờ về số mới"
                ),
                inline=False,
            )
        if command["name"] == "ban":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`ban @user [reason]` ban vĩnh viễn.\n"
                    "`ban @user 1d [reason]` ban tạm thời rồi tự unban sau thời gian đó.\n"
                    "Target có thể là mention, username hoặc user ID. Thời gian hỗ trợ `s`, `m`, `h`, `d`."
                ),
                inline=False,
            )
        if command["name"] == "kick":
            embed.add_field(
                name="Cách dùng",
                value="`kick @user [reason]`. Target có thể là mention, username hoặc user ID của member đang ở server.",
                inline=False,
            )
        if command["name"] == "mute":
            embed.add_field(
                name="Cách dùng",
                value="`mute @user [duration] [reason]`. Target có thể là mention, username hoặc user ID. Không nhập duration thì mặc định 1h.",
                inline=False,
            )
        if command["name"] == "emoji":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`emoji a/add <name> <url>` để thêm emoji.\n"
                    "`emoji r/rm/remove/d/delete <name|id>` để xóa emoji.\n"
                    "`emoji list [limit]` để xem emoji custom."
                ),
                inline=False,
            )
        if command["name"] == "setrole":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`setrole @Booking` hoặc `setrole <role_id>` để mở menu chọn `admin/booking/user/staff`.\n"
                    "Có thể set nhanh: `setrole @Booking booking`.\n"
                    "Ai có Discord role được set `booking` sẽ được bot tự nhận là booking."
                ),
                inline=False,
            )
        if command["name"] == "addrole":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`addrole @role command` cấp 1 role cho 1 lệnh.\n"
                    "`addrole @role1, @role2 command1, command2` cấp nhiều role cho nhiều lệnh.\n"
                    "Command không tồn tại sẽ được báo riêng và không được lưu quyền."
                ),
                inline=False,
            )
        if command["name"] == "removerole":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`removerole @role command` xóa quyền 1 role khỏi 1 lệnh.\n"
                    "`removerole @role1, @role2 command1, command2` xóa nhiều role khỏi nhiều lệnh.\n"
                    "Command không tồn tại sẽ được báo riêng và không được xử lý."
                ),
                inline=False,
            )
        if command["name"] == "perms":
            embed.add_field(
                name="Cách dùng",
                value=(
                    "`perms command` xem role đang có quyền dùng 1 lệnh.\n"
                    "`perms command1, command2` xem quyền của nhiều lệnh cùng lúc.\n"
                    "Command không tồn tại sẽ hiện trong mục riêng."
                ),
                inline=False,
            )
        if command["name"] == "up":
            embed.add_field(
                name="Cách dùng",
                value="`up ad1 #booking` hoặc `ar up ad1 #booking` để gửi profile `ad1` lên channel chỉ định.",
                inline=False,
            )
        if command["name"] in {"setgiobook", "cash", "luong"}:
            embed.add_field(
                name="Định dạng tiền",
                value="Hỗ trợ `100000`, `100k`, `1m`, `1b`, `100.000`, `100,000`, `0,5m`. Đơn vị mặc định là VNĐ.",
                inline=False,
            )
        embed.set_author(name=guild.name if guild else APP_NAME)
        embed.set_footer(text=f"Dùng {prefix}help để quay lại bảng lệnh")
        return embed

    @staticmethod
    def build_role_management_embed(guild: discord.Guild | None = None) -> discord.Embed:
        prefix = get_prefix(guild.id if guild else None)
        commands = _role_management_commands()
        embed = discord.Embed(
            title="🧩 Role Management",
            description="Quản lý role và quyền command. Tất cả dùng chung quyền `role` trong database.",
            color=ACCENT_COLOR,
        )
        for command in commands:
            alias_text = ""
            if command.get("aliases"):
                alias_list = ", ".join(f"`{prefix}{alias}`" for alias in command["aliases"])
                alias_text = f"\nAliases: {alias_list}"
            embed.add_field(
                name=_format_usage(command, guild.id if guild else None),
                value=f"{command['description']}{alias_text}",
                inline=False,
            )
        embed.set_author(name=guild.name if guild else APP_NAME)
        embed.set_footer(text=f"Tổng cộng {len(commands)} lệnh • {prefix}help <command>")
        return embed


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='help', aliases=['commands'])
    async def help_command(self, ctx, command_name: str = None):
        if command_name:
            normalized_name = command_name.strip().lower()
            if _is_role_management_key(normalized_name):
                await ctx.send(embed=HelpView.build_role_management_embed(ctx.guild), view=CategoryView("administrator"))
                return

            category = _find_category(normalized_name)
            if category:
                await ctx.send(embed=HelpView.build_category_embed(category, ctx.guild), view=CategoryView(category["key"]))
                return

            category, command = _find_command(command_name)
            if not command or not category:
                await ctx.send(f"❌ Không tìm thấy lệnh `{command_name}`.")
                return

            await ctx.send(embed=HelpView.build_command_embed(category, command, ctx.guild))
            return

        await ctx.send(embed=HelpView.build_index_embed(ctx.guild), view=IndexView())


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
