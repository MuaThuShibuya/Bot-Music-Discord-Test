import unittest

from utils import match_case_insensitive_prefix


class CaseInsensitivePrefixTest(unittest.TestCase):
    def test_single_character_prefix(self):
        self.assertEqual(match_case_insensitive_prefix("Bhelp", "b"), "B")
        self.assertEqual(match_case_insensitive_prefix("bhelp", "b"), "b")

    def test_multi_character_prefix(self):
        self.assertEqual(match_case_insensitive_prefix("bOthelp", "Bot"), "bOt")

    def test_non_matching_prefix(self):
        self.assertIsNone(match_case_insensitive_prefix("ahelp", "b"))
        self.assertIsNone(match_case_insensitive_prefix("bo", "Bot"))


if __name__ == "__main__":
    unittest.main()
