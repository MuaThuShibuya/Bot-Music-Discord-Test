"""
Shared helpers for owner-only command cogs.
"""

from __future__ import annotations

from discord.ext import commands

from config import DISCORD_OWNER_IDS
from services.admin_service import AdminService
from services.git_service import GitUpdateService
from utils import create_error_splash, create_info_splash, create_success_splash


class OwnerCommandBase(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.git = GitUpdateService()
        self.admins = AdminService()

    def is_owner(self, user_id: int) -> bool:
        return user_id in DISCORD_OWNER_IDS

    def is_hard_admin(self, user_id: int) -> bool:
        return self.admins.is_hard_admin(user_id)

