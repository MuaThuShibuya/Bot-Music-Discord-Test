import os

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

APP_NAME = os.getenv("APP_NAME", "Discord Music Bot")
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "your_discord_bot_token")
BOT_PREFIX = os.getenv("BOT_PREFIX", "b")
SUPPORT_SERVER_URL = os.getenv("SUPPORT_SERVER_URL", "https://discord.com")
