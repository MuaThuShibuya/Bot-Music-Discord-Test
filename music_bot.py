import asyncio
import logging
import os

import discord
from discord.ext import commands

from music_config import APP_NAME, BOT_PREFIX, DISCORD_TOKEN

MUSIC_COGS = ["cogs.bot.voice_cog"]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("music_bot")


async def health_handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await reader.read(4096)
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "Content-Length: 2\r\n"
            "Connection: close\r\n"
            "\r\n"
            "OK"
        )
        writer.write(response.encode("ascii"))
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def start_health_server() -> asyncio.AbstractServer:
    port = int(os.getenv("PORT", "10000"))
    server = await asyncio.start_server(health_handler, "0.0.0.0", port)
    logger.info("Health server listening on port %s", port)
    return server


async def load_music_cogs(bot: commands.Bot) -> None:
    for module_name in MUSIC_COGS:
        try:
            await bot.load_extension(module_name)
            logger.info("Music cog loaded: %s", module_name)
        except Exception as exc:  # pragma: no cover - startup guard
            logger.exception("Failed to load %s: %s", module_name, exc)
            raise


async def main() -> None:
    if DISCORD_TOKEN in {None, "", "your_discord_bot_token"}:
        raise RuntimeError("DISCORD_TOKEN is required. Set it in .env or the environment before starting the music bot.")

    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.voice_states = True
    intents.messages = True
    intents.message_content = True

    bot = commands.Bot(
        command_prefix=commands.when_mentioned_or(BOT_PREFIX),
        intents=intents,
        help_command=None,
    )

    @bot.event
    async def on_ready() -> None:
        logger.info("Bot Type       : MUSIC_ONLY")
        logger.info("Discord Config : CONFIGURED")
        logger.info("Music Cog      : LOADED")
        logger.info("Bot user       : %s (%s)", bot.user, bot.user.id)
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=f"{BOT_PREFIX}play"))

    @bot.event
    async def on_command_error(ctx, error) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        logger.warning("Command error on %s: %s", getattr(ctx.command, "qualified_name", "unknown"), error)
        if ctx.command is not None:
            await ctx.send(f"An error occurred: {error}")

    health_server = await start_health_server()
    try:
        async with bot:
            await load_music_cogs(bot)
            await bot.start(DISCORD_TOKEN)
    finally:
        health_server.close()
        await health_server.wait_closed()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Music bot stopped.")
