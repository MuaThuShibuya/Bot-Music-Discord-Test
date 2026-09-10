import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from cogs.bot.voice_cog import AudioItem, BotVoiceCog, GuildAudioState
from services.music_player_service import MusicPlayerService


class MusicPlayerPreferencesTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        database_dir = self.temp_dir.name
        patcher = patch("utils.DATABASE_DIR", database_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = MusicPlayerService()

    def tearDown(self):
        self.service.db.close()
        self.temp_dir.cleanup()

    def test_preferences_are_saved_per_user(self):
        self.service.set_user_preferences(
            123,
            volume=100,
        )

        first = self.service.get_user_preferences(123)
        second = self.service.get_user_preferences(456)

        self.assertEqual(first["volume"], 100)
        self.assertEqual(second["volume"], 65)
        self.assertNotIn("autoplay", first)
        self.assertNotIn("loop_current", first)

    def test_volume_is_limited_to_supported_range(self):
        self.assertEqual(
            self.service.set_user_preferences(123, volume=999)["volume"],
            200,
        )
        self.assertEqual(
            self.service.set_user_preferences(123, volume=-5)["volume"],
            0,
        )

    def test_volume_changes_are_saved_only_for_the_user_who_changed_it(self):
        cog = BotVoiceCog.__new__(BotVoiceCog)
        cog.player_service = self.service
        state = GuildAudioState()

        state.volume = 1.0
        cog._save_user_preferences(state, 123, volume=100)
        state.volume = 0.4
        cog._save_user_preferences(state, 456, volume=40)

        self.assertEqual(self.service.get_user_preferences(123)["volume"], 100)
        self.assertEqual(self.service.get_user_preferences(456)["volume"], 40)
        self.assertEqual(state.volume, 0.4)

        cog._apply_user_preferences(state, 123)
        self.assertEqual(state.volume, 1.0)
        cog._apply_user_preferences(state, 456)
        self.assertEqual(state.volume, 0.4)

    def test_player_content_and_icon_theme_can_be_saved_and_reset(self):
        theme = self.service.set_theme(
            777,
            button_play="Phát",
            button_skip="Bỏ qua",
            icon_skip="➡️",
            reaction_success="☑️",
        )
        self.assertNotIn("button_play", theme)
        self.assertEqual(theme["button_skip"], "Bỏ qua")
        self.assertEqual(theme["icon_skip"], "➡️")
        self.assertEqual(theme["reaction_success"], "☑️")

        default = self.service.reset_theme_value(777, "button_skip")
        self.assertEqual(default, "Skip")
        self.assertEqual(self.service.get_theme(777)["button_skip"], "Skip")

    def test_queue_added_message_uses_configured_content_and_icon(self):
        self.service.set_theme(
            777,
            message_queue_added_title="Đã xếp {count} bài",
            message_queue_added_body="{title} ở vị trí {position} bởi {requester}",
            icon_queue_added="➕",
        )
        cog = BotVoiceCog.__new__(BotVoiceCog)
        cog.player_service = self.service
        item = AudioItem(
            title="Bài hát mới",
            query="test",
            requester_id=123,
            requester_name="Tester",
        )

        embed = cog._queue_added_embed(777, [item], 2)

        self.assertEqual(embed.title, "➕ Đã xếp 1 bài")
        self.assertEqual(embed.description, "Bài hát mới ở vị trí 2 bởi Tester")

    def test_old_player_theme_table_is_migrated(self):
        self.service.db.execute("DROP TABLE player_theme")
        self.service.db.create_table(
            "player_theme",
            """
            guild_id INTEGER PRIMARY KEY,
            accent_color TEXT NOT NULL DEFAULT '#7f314d',
            background_url TEXT DEFAULT '',
            title_text TEXT NOT NULL DEFAULT 'BLACK LOUS MUSIC',
            updated_at TEXT
            """,
        )
        self.service._ensure_theme_columns()

        columns = {
            row["name"]
            for row in self.service.db.fetch("PRAGMA table_info(player_theme)")
        }
        self.assertIn("button_skip", columns)
        self.assertIn("reaction_error", columns)


class MusicPlayerAutoplayTest(unittest.IsolatedAsyncioTestCase):
    async def test_autoplay_uses_first_unseen_youtube_radio_item(self):
        previous = AudioItem(
            title="Bài hiện tại",
            query="https://www.youtube.com/watch?v=current",
            webpage_url="https://www.youtube.com/watch?v=current",
            video_id="current",
            requester_id=123,
            requester_name="Tester",
        )
        duplicate = AudioItem(
            title="Bài hiện tại",
            query=previous.query,
            webpage_url=previous.webpage_url,
            video_id="current",
            requester_id=123,
            requester_name="Tester",
        )
        recommended = AudioItem(
            title="YouTube đề xuất",
            query="https://www.youtube.com/watch?v=next",
            webpage_url="https://www.youtube.com/watch?v=next",
            video_id="next",
            requester_id=123,
            requester_name="Tester",
        )

        cog = BotVoiceCog.__new__(BotVoiceCog)
        cog.bot = MagicMock()
        cog.bot.get_user.return_value = SimpleNamespace(id=123, display_name="Tester")
        cog.states = {
            777: GuildAudioState(current=previous, autoplay=True),
        }
        cog._extract_music_items = AsyncMock(return_value=[duplicate, recommended])

        added = await cog._enqueue_autoplay(777)

        self.assertTrue(added)
        self.assertEqual(cog.states[777].queue, [recommended])
        query = cog._extract_music_items.await_args.args[0]
        self.assertIn("list=RDcurrent", query)

    async def test_playback_starts_before_player_card_is_scheduled(self):
        events = []
        item = AudioItem(
            title="Bài test",
            query="https://example.com/watch",
            stream_url="https://example.com/audio",
            duration=120,
            requester_id=123,
            requester_name="Tester",
        )
        voice_client = MagicMock()
        voice_client.is_connected.return_value = True
        voice_client.play.side_effect = lambda source, after: events.append("play")

        cog = BotVoiceCog.__new__(BotVoiceCog)
        cog.states = {
            777: GuildAudioState(
                voice_client=voice_client,
                queue=[item],
            ),
        }
        cog.bot = MagicMock()

        def discard_task(coroutine):
            coroutine.close()
            return MagicMock()

        cog.bot.loop.create_task.side_effect = discard_task
        cog._cancel_idle = MagicMock()
        cog._resolve_stream_url = AsyncMock(return_value=item)
        cog._find_ffmpeg = MagicMock(return_value="ffmpeg")
        cog._autoplay_item_key = MagicMock(return_value="test")
        cog._schedule_now_playing_card = MagicMock(
            side_effect=lambda guild_id, current: events.append("card")
        )
        cog._schedule_player_sync = MagicMock()

        with (
            patch("cogs.bot.voice_cog.discord.FFmpegPCMAudio", return_value=object()),
            patch("cogs.bot.voice_cog.discord.PCMVolumeTransformer", return_value=object()),
        ):
            await cog._play_next(777)

        self.assertEqual(events[:2], ["play", "card"])


if __name__ == "__main__":
    unittest.main()
