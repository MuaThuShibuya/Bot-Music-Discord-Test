import tempfile
import unittest
from unittest.mock import patch

from services.note_service import NoteService


class NoteSourceLinkTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        patcher = patch("utils.DATABASE_DIR", self.temp_dir.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.service = NoteService()

    def tearDown(self):
        self.service.close()
        self.temp_dir.cleanup()

    def test_reply_source_is_saved_with_txt_note(self):
        created = self.service.add_note(
            123,
            456,
            "Nội dung tin nhắn",
            title="Tin nhắn của Tester",
            kind="txt",
            source_url="https://discord.com/channels/123/789/999",
            source_message_id=999,
        )

        self.assertEqual(created["kind"], "txt")
        self.assertEqual(
            created["source_url"],
            "https://discord.com/channels/123/789/999",
        )
        self.assertEqual(created["source_message_id"], 999)


if __name__ == "__main__":
    unittest.main()
