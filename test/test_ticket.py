import datetime
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from cogs.administrator.ticket_cog import (
    ContextAdapter,
    TicketCog,
    build_ticket_channel_name,
    build_transcript,
    ticket_emoji,
)
from services.ticket_service import TicketService


class TestTicketHelpers(unittest.TestCase):
    @patch.dict(os.environ, {"TICKET_EMOJI_CLAIM_ID": "123456789012345678"})
    def test_custom_emoji_from_environment(self):
        self.assertEqual(ticket_emoji("claim"), "<:claim:123456789012345678>")

    def test_unknown_emoji_uses_ticket_fallback(self):
        self.assertEqual(ticket_emoji("unknown"), ticket_emoji("ticket"))

    def test_channel_name_is_sanitized(self):
        self.assertEqual(build_ticket_channel_name("AB-12 @$"), "ticket-ab12")

    def test_transcript_contains_message_and_attachment(self):
        message = MagicMock()
        message.created_at = datetime.datetime(2026, 6, 7, 12, 0)
        message.author = "Tester"
        message.content = "Xin chào"
        message.clean_content = "Xin chào"
        attachment = MagicMock()
        attachment.url = "https://example.com/file.png"
        message.attachments = [attachment]

        transcript = build_transcript([message])

        self.assertIn("Tester", transcript)
        self.assertIn("Xin chào", transcript)
        self.assertIn("https://example.com/file.png", transcript)


class TestTicketPermissions(unittest.TestCase):
    def setUp(self):
        self.cog = TicketCog.__new__(TicketCog)
        self.cog._admins = MagicMock()
        self.cog._role_permissions = MagicMock()

        self.guild = MagicMock()
        self.guild.id = 777
        self.member = MagicMock(spec=discord.Member)
        self.member.id = 123
        self.member.guild = self.guild
        role = MagicMock()
        role.id = 456
        role.name = "Ticket Team"
        self.member.roles = [role]

    def test_bot_admin_can_manage_ticket(self):
        self.cog._admins.is_admin.return_value = True

        self.assertTrue(self.cog.member_can_manage(self.member))
        self.cog._admins.is_admin.assert_called_once_with(123, 777)
        self.cog._role_permissions.user_can_use.assert_not_called()

    def test_role_database_controls_ticket_permission(self):
        self.cog._admins.is_admin.return_value = False
        self.cog._role_permissions.user_can_use.return_value = True

        self.assertTrue(self.cog.member_can_manage(self.member))
        self.cog._role_permissions.user_can_use.assert_called_once_with(
            777,
            [456],
            "ticket",
        )

    def test_command_roles_are_loaded_from_shared_role_database(self):
        role = MagicMock(spec=discord.Role)
        role.id = 456
        self.guild.get_role.return_value = role
        self.cog._role_permissions.get_roles_for_command.return_value = [
            {"role_id": 456},
            {"role_id": 456},
        ]

        self.assertEqual(self.cog.command_roles(self.guild), [role])
        self.cog._role_permissions.get_roles_for_command.assert_called_once_with(
            777,
            "ticket",
        )

    def test_ticket_notify_targets_resolves_configured_roles_and_users(self):
        role = MagicMock(spec=discord.Role)
        member = MagicMock(spec=discord.Member)
        self.guild.get_role.side_effect = lambda target_id: role if target_id == 456 else None
        self.guild.get_member.side_effect = lambda target_id: member if target_id == 123 else None
        self.cog.service = MagicMock()
        self.cog.service.get_type_mentions.return_value = [
            {"target_type": "role", "target_id": 456},
            {"target_type": "user", "target_id": 123},
        ]

        roles, members, configured = self.cog.ticket_notify_targets(
            self.guild,
            "payment",
        )

        self.assertEqual(roles, [role])
        self.assertEqual(members, [member])
        self.assertTrue(configured)


class TestTicketDatabase(unittest.TestCase):
    def test_invalid_config_key_is_rejected(self):
        service = TicketService.__new__(TicketService)
        service.db = MagicMock()
        service.ensure_config = MagicMock()

        with self.assertRaises(ValueError):
            service.update_single_config(777, "invalid_key", 1)

    def test_ticket_service_has_no_separate_staff_role_api(self):
        self.assertFalse(hasattr(TicketService, "add_staff_role"))
        self.assertFalse(hasattr(TicketService, "get_staff_roles"))


class TestTicketTypeMentions(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        patcher = patch("utils.DATABASE_DIR", self.temp_dir.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = TicketService()

    def tearDown(self):
        self.service.db.close()
        self.temp_dir.cleanup()

    def test_mentions_are_saved_per_guild_and_ticket_type(self):
        self.service.set_type_mentions(
            777,
            "payment",
            role_ids=[111, 111],
            user_ids=[222],
        )
        self.service.set_type_mentions(
            777,
            "support",
            role_ids=[333],
            user_ids=[],
        )

        payment = self.service.get_type_mentions(777, "payment")
        support = self.service.get_type_mentions(777, "support")

        self.assertEqual(
            {(row["target_type"], row["target_id"]) for row in payment},
            {("role", 111), ("user", 222)},
        )
        self.assertEqual(
            {(row["target_type"], row["target_id"]) for row in support},
            {("role", 333)},
        )
        self.assertEqual(self.service.get_type_mentions(888, "payment"), [])

    def test_replacing_roles_keeps_configured_users(self):
        self.service.set_type_mentions(
            777,
            "payment",
            role_ids=[111],
            user_ids=[222],
        )

        self.service.replace_type_mentions(777, "payment", "role", [333])

        targets = self.service.get_type_mentions(777, "payment")
        self.assertEqual(
            {(row["target_type"], row["target_id"]) for row in targets},
            {("role", 333), ("user", 222)},
        )

    def test_clear_removes_only_selected_ticket_type(self):
        self.service.replace_type_mentions(777, "payment", "role", [111])
        self.service.replace_type_mentions(777, "support", "role", [333])

        self.service.clear_type_mentions(777, "payment")

        self.assertEqual(self.service.get_type_mentions(777, "payment"), [])
        self.assertEqual(len(self.service.get_type_mentions(777, "support")), 1)


class TestContextAdapter(unittest.IsolatedAsyncioTestCase):
    async def test_prefix_context_drops_ephemeral_argument(self):
        context = MagicMock()
        context.guild = MagicMock()
        context.channel = MagicMock()
        context.author = MagicMock()
        context.send = AsyncMock()
        adapter = ContextAdapter(context)

        await adapter.send("ok", ephemeral=True)

        context.send.assert_awaited_once_with("ok")


if __name__ == "__main__":
    unittest.main()
