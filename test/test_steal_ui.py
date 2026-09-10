import unittest

from ui.administrator.steal_ui import parse_steal_source, validate_emoji_name


class StealEmojiInputTest(unittest.TestCase):
    def test_custom_emoji_keeps_original_name(self):
        source = parse_steal_source("<:hello_1:123456789012345678>")

        self.assertEqual(source.name, "hello_1")
        self.assertFalse(source.animated)
        self.assertIn("123456789012345678.png", source.url)

    def test_animated_emoji_accepts_new_name(self):
        source = parse_steal_source(
            "<a:dance:123456789012345678>",
            "new-dance",
        )

        self.assertEqual(source.name, "new_dance")
        self.assertTrue(source.animated)
        self.assertIn("123456789012345678.gif", source.url)

    def test_url_requires_name(self):
        with self.assertRaises(ValueError):
            parse_steal_source("https://example.com/image.png")

    def test_name_validation(self):
        self.assertEqual(validate_emoji_name("valid_name"), "valid_name")
        with self.assertRaises(ValueError):
            validate_emoji_name("x")


if __name__ == "__main__":
    unittest.main()
