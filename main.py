import discord
from discord.ext import commands
from difflib import get_close_matches
import os
import ssl
import aiohttp
import certifi
import sys
from config import DISCORD_TOKEN, COGS_DIR, LOGS_DIR
from cogs.cog_loader_utils import iter_cog_modules
from services.admin_service import AdminService
from services.command_toggle_service import ChannelCommandToggleService
from services.guild_settings_service import GuildSettingsService
from utils import create_error_splash, get_prefix, match_case_insensitive_prefix

# Tạo các thư mục nếu chưa tồn tại
os.makedirs(LOGS_DIR, exist_ok=True)

if COGS_DIR not in sys.path:
    sys.path.insert(0, COGS_DIR)


COMMAND_LOCK_ALLOWED_PREFIX = {
    "avatar",
    "av",
    "ava",
    "avata",
    "banner",
    "bn",
    "bia",
    "bìa",
    "log",
    "logs",
    "command",
    "cmd",
    "enable",
    "disable",
}
COMMAND_LOCK_ALLOWED_SLASH = {"avatar", "banner", "log", "admin", "command"}


class CommandsLocked(commands.CheckFailure):
    """Raised when a guild has command usage locked for non-hardadmins."""


class ChannelCommandDisabled(commands.CheckFailure):
    """Raised when a command is disabled in the current channel."""

    def __init__(self, command_name: str):
        self.command_name = command_name
        super().__init__(command_name)


# Load cogs từ thư mục cogs và các subfolder catalog
async def load_cogs(bot):
    for module_name in iter_cog_modules():
        try:
            await bot.load_extension(module_name)
            print(f'✅ Đã tải cog: {module_name}')
        except Exception as e:
            print(f'❌ Lỗi khi tải {module_name}: {e}')


async def sync_slash_commands(bot):
    for guild in bot.guilds:
        try:
            # Dọn các slash guild cũ để Discord không hiện trùng với slash global.
            bot.tree.clear_commands(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"✅ Đã xoá slash guild cũ cho {guild.name} ({guild.id}): {len(synced)}")
        except Exception as e:
            print(f"❌ Lỗi xoá slash guild cũ cho {guild.name} ({guild.id}): {e}")

    try:
        synced = await bot.tree.sync()
        print(f"✅ Đã sync global slash commands: {len(synced)}")
    except Exception as e:
        print(f"❌ Lỗi sync global slash commands: {e}")


def prefix_callable(bot, message):
    guild_id = message.guild.id if message.guild else None
    prefix = get_prefix(guild_id)
    typed_prefix = match_case_insensitive_prefix(message.content, prefix)
    return commands.when_mentioned_or(typed_prefix or prefix)(bot, message)


def get_unknown_command_suggestion(bot, invoked: str | None) -> str | None:
    invoked = (invoked or "").strip().lower()
    if not invoked:
        return None

    if invoked.startswith("form") and len(invoked) > len("form"):
        return None

    command_names = sorted({name.lower() for name in bot.all_commands.keys()})
    matches = get_close_matches(invoked, command_names, n=1, cutoff=0.78)
    return matches[0] if matches else None


def get_prefix_command_root(ctx) -> str:
    if ctx.command is not None:
        return ctx.command.qualified_name.split()[0].lower()
    return (ctx.invoked_with or "").strip().lower()


def get_slash_command_root(interaction: discord.Interaction) -> str:
    data = interaction.data if isinstance(interaction.data, dict) else {}
    return str(data.get("name") or getattr(interaction.command, "name", "") or "").strip().lower()


def get_prefix_command_candidates(ctx: commands.Context) -> list[str]:
    command_root = get_prefix_command_root(ctx)
    canonical_root = command_root
    if ctx.command is not None:
        canonical_root = (
            ctx.command.root_parent.name if ctx.command.root_parent else ctx.command.name
        ).strip().lower()

    candidates: list[str] = []
    prefix = get_prefix(ctx.guild.id if ctx.guild else None)
    content = str(getattr(ctx.message, "content", "") or "")
    if match_case_insensitive_prefix(content, prefix):
        tokens = content[len(prefix):].strip().split()
        if len(tokens) > 1:
            candidates.extend(
                [
                    f"{canonical_root} {tokens[1].lower()}",
                    f"{command_root} {tokens[1].lower()}",
                ]
            )
    candidates.extend([canonical_root, command_root])
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def _slash_first_option_value(options) -> str | None:
    for option in options or []:
        if not isinstance(option, dict):
            continue
        nested = option.get("options")
        if nested:
            nested_value = _slash_first_option_value(nested)
            if nested_value:
                return nested_value
        value = option.get("value")
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def get_slash_command_candidates(interaction: discord.Interaction) -> list[str]:
    root = get_slash_command_root(interaction)
    data = interaction.data if isinstance(interaction.data, dict) else {}
    option_value = _slash_first_option_value(data.get("options"))
    candidates = [f"{root} {option_value}" if option_value else "", root]
    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


async def main():
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.voice_states = True
    intents.messages = True
    intents.message_content = True
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_context)
    bot = commands.Bot(
        command_prefix=prefix_callable,
        intents=intents,
        connector=connector,
        help_command=None,
    )
    command_lock_admins = AdminService()
    command_lock_settings = GuildSettingsService()
    channel_command_settings = ChannelCommandToggleService()

    @bot.check
    async def command_lock_check(ctx):
        if ctx.guild is None:
            return True
        command_root = get_prefix_command_root(ctx)
        if command_lock_admins.is_hard_admin(ctx.author.id):
            return True
        if command_root in COMMAND_LOCK_ALLOWED_PREFIX:
            return True
        disabled = channel_command_settings.find_disabled(
            ctx.guild.id,
            ctx.channel.id,
            get_prefix_command_candidates(ctx),
        )
        if disabled:
            raise ChannelCommandDisabled(disabled)
        if not command_lock_settings.are_commands_locked(ctx.guild.id):
            return True
        raise CommandsLocked()

    async def command_lock_interaction_check(interaction: discord.Interaction):
        if interaction.guild is None:
            return True
        command_root = get_slash_command_root(interaction)
        if command_lock_admins.is_hard_admin(interaction.user.id):
            return True
        if command_root in COMMAND_LOCK_ALLOWED_SLASH:
            return True
        disabled = channel_command_settings.find_disabled(
            interaction.guild.id,
            interaction.channel_id,
            get_slash_command_candidates(interaction),
        )
        if disabled:
            message = f"Lệnh `{disabled}` không được dùng trong {interaction.channel.mention} này."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return False
        if not command_lock_settings.are_commands_locked(interaction.guild.id):
            return True

        message = "Bot đang khoá quyền dùng lệnh."
        if interaction.response.is_done():
            await interaction.followup.send(embed=create_error_splash(message), ephemeral=True)
        else:
            await interaction.response.send_message(embed=create_error_splash(message), ephemeral=True)
        return False

    bot.tree.interaction_check = command_lock_interaction_check

    @bot.event
    async def on_ready():
        if not getattr(bot, "_tree_synced", False):
            await sync_slash_commands(bot)
            bot._tree_synced = True

        current_prefix = get_prefix()
        print(f'{bot.user} đã trực tuyến!')
        print(f'Bot ID: {bot.user.id}')
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=f'{current_prefix}help'))

    @bot.event
    async def on_command_error(ctx, error):
        current_prefix = get_prefix(ctx.guild.id if ctx.guild else None)
        if isinstance(error, CommandsLocked):
            await ctx.send(embed=create_error_splash("Bot đang khoá quyền dùng lệnh."))
        elif isinstance(error, ChannelCommandDisabled):
            invoked = (ctx.invoked_with or error.command_name).strip().lower()
            await ctx.send(f"Lệnh `{invoked}` không được dùng trong {ctx.channel.mention} này.")
        elif isinstance(error, commands.CommandNotFound):
            suggestion = get_unknown_command_suggestion(bot, ctx.invoked_with)
            if not suggestion:
                return
            await ctx.send(f"❌ Lệnh `{current_prefix}{ctx.invoked_with}` không tồn tại. Có phải bạn muốn dùng `{current_prefix}{suggestion}`?")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Thiếu tham số! Gõ `{current_prefix}help {ctx.command}` để xem hướng dẫn.")
        else:
            await ctx.send(f"❌ Lỗi: {error}")
            print(f"Lỗi: {error}")

    try:
        async with bot:
            await load_cogs(bot)
            await bot.start(DISCORD_TOKEN)
    finally:
        channel_command_settings.close()

if __name__ == '__main__':
    try:
        import asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\n⚠️ Bot đã dừng.')
