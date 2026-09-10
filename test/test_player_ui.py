import unittest

from PIL import Image

from ui.bot.player_ui import (
    ANIMATED_CARD_FILENAME,
    CARD_FILENAME,
    MusicPlayerView,
    PlayerCardData,
    _render_card,
)


def player_data(*, paused: bool) -> PlayerCardData:
    return PlayerCardData(
        title="Bài test",
        requester="Tester",
        duration=3,
        elapsed=1,
        thumbnail=None,
        volume=65,
        paused=paused,
        loop=False,
        autoplay=False,
    )


class PlayerCardRenderTest(unittest.TestCase):
    def test_playing_card_is_an_animated_progress_gif(self):
        buffer, filename = _render_card(player_data(paused=False), None, None)

        self.assertEqual(filename, ANIMATED_CARD_FILENAME)
        with Image.open(buffer) as image:
            self.assertEqual(image.format, "GIF")
            self.assertGreater(image.n_frames, 1)

    def test_paused_card_is_a_static_png(self):
        buffer, filename = _render_card(player_data(paused=True), None, None)

        self.assertEqual(filename, CARD_FILENAME)
        with Image.open(buffer) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(getattr(image, "n_frames", 1), 1)

    def test_player_controls_are_persistent(self):
        view = MusicPlayerView(object(), 0)

        self.assertIsNone(view.timeout)
        custom_ids = [child.custom_id for child in view.children]
        self.assertEqual(len(custom_ids), len(set(custom_ids)))
        self.assertTrue(all(custom_ids))


if __name__ == "__main__":
    unittest.main()
