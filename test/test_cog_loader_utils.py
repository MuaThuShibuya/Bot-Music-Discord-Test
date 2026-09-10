import os
import tempfile
import unittest
from unittest.mock import patch

from cogs.cog_loader_utils import resolve_cog_modules


class CogLoaderUtilsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        os.makedirs(os.path.join(self.temp_dir.name, "administrator"))
        os.makedirs(os.path.join(self.temp_dir.name, "bot"))
        for path in (
            "administrator/ticket_cog.py",
            "administrator/giveaway_cog.py",
            "bot/voice_cog.py",
        ):
            with open(os.path.join(self.temp_dir.name, path), "w", encoding="utf-8"):
                pass

    def resolve(self, target):
        with patch("cogs.cog_loader_utils.COGS_DIR", self.temp_dir.name):
            return resolve_cog_modules(target)

    def test_short_cog_name_resolves_full_module(self):
        self.assertEqual(
            self.resolve("ticket"),
            ["administrator.ticket_cog"],
        )

    def test_short_name_with_cog_suffix_is_supported(self):
        self.assertEqual(
            self.resolve("voice_cog"),
            ["bot.voice_cog"],
        )

    def test_full_module_name_still_works(self):
        self.assertEqual(
            self.resolve("administrator.giveaway_cog"),
            ["administrator.giveaway_cog"],
        )


if __name__ == "__main__":
    unittest.main()
