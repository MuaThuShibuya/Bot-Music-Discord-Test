import os
import unittest


class MusicOnlyEntryPointTest(unittest.TestCase):
    def test_music_bot_declares_only_music_cog(self):
        os.environ.setdefault("DISCORD_TOKEN", "token-for-test")
        import music_bot

        self.assertEqual(music_bot.MUSIC_COGS, ["cogs.bot.voice_cog"])
        self.assertNotIn("cogs.user.donate_cog", music_bot.MUSIC_COGS)
        self.assertNotIn("cogs.user.naptien_cog", music_bot.MUSIC_COGS)

    def test_music_config_uses_minimal_env(self):
        os.environ.setdefault("DISCORD_TOKEN", "token-for-test")
        import importlib

        music_config = importlib.import_module("music_config")

        self.assertTrue(hasattr(music_config, "DISCORD_TOKEN"))
        self.assertTrue(hasattr(music_config, "BOT_PREFIX"))
        self.assertFalse(hasattr(music_config, "CASH_DB_PATH"))
        self.assertFalse(hasattr(music_config, "ACB_USERNAME"))


if __name__ == "__main__":
    unittest.main()
