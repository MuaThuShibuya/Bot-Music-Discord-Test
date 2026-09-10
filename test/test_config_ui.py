import tempfile
import unittest
from unittest.mock import patch

from services.ticket_service import TicketService
from services.music_player_service import DEFAULT_PLAYER_THEME
from ui.administrator.giveaway_emoji import GIVEAWAY_THEME_DEFAULTS
from ui.administrator.giveaway_ui import GIVEAWAY_CONTENT_FIELDS, GIVEAWAY_ICON_FIELDS
from ui.bot.play_config_ui import PLAY_CONTENT_FIELDS, PLAY_ICON_FIELDS
from ui.ticket.emoji import (
    TICKET_CONTENT_FIELDS,
    TICKET_ICON_FIELDS,
    TICKET_THEME_DEFAULTS,
    ticket_emoji,
    ticket_theme_value,
)


class ConfigMenuLimitTest(unittest.TestCase):
    def test_discord_select_menus_stay_within_25_options(self):
        self.assertLessEqual(len(GIVEAWAY_CONTENT_FIELDS), 25)
        self.assertLessEqual(len(GIVEAWAY_ICON_FIELDS), 25)
        self.assertLessEqual(len(PLAY_CONTENT_FIELDS), 25)
        self.assertLessEqual(len(PLAY_ICON_FIELDS), 25)
        self.assertLessEqual(len(TICKET_CONTENT_FIELDS), 25)
        self.assertLessEqual(len(TICKET_ICON_FIELDS), 25)

    def test_all_customizable_theme_keys_are_exposed_in_ui(self):
        giveaway_keys = set(GIVEAWAY_CONTENT_FIELDS) | set(GIVEAWAY_ICON_FIELDS)
        self.assertTrue(set(GIVEAWAY_THEME_DEFAULTS).issubset(giveaway_keys))

        ticket_keys = set(TICKET_CONTENT_FIELDS) | set(TICKET_ICON_FIELDS)
        self.assertEqual(set(TICKET_THEME_DEFAULTS), ticket_keys)

        play_keys = set(PLAY_CONTENT_FIELDS) | set(PLAY_ICON_FIELDS)
        self.assertEqual(
            set(DEFAULT_PLAYER_THEME) - {"accent_color", "background_url"},
            play_keys,
        )


class TicketThemeServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        patcher = patch("utils.DATABASE_DIR", self.temp_dir.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = TicketService()

    def tearDown(self):
        self.service.db.close()
        self.temp_dir.cleanup()

    def test_ticket_content_and_icon_are_saved_per_guild(self):
        self.service.set_theme_value(777, "panel_title", "Hỗ trợ riêng")
        self.service.set_theme_value(777, "icon_ticket", "🎟️")
        theme = self.service.get_theme(777)

        self.assertEqual(ticket_theme_value(theme, "panel_title"), "Hỗ trợ riêng")
        self.assertEqual(ticket_emoji("ticket", theme), "🎟️")
        self.assertNotEqual(
            ticket_theme_value(self.service.get_theme(888), "panel_title"),
            "Hỗ trợ riêng",
        )

        self.service.reset_theme_value(777, "panel_title")
        self.assertNotEqual(
            ticket_theme_value(self.service.get_theme(777), "panel_title"),
            "Hỗ trợ riêng",
        )


if __name__ == "__main__":
    unittest.main()
