import unittest

from services.system_stats_service import format_bytes, format_duration, format_usage


class SystemStatsFormattingTest(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(0), "0 giây")
        self.assertEqual(format_duration(3661), "1 giờ 1 phút 1 giây")
        self.assertEqual(format_duration(90061), "1 ngày 1 giờ 1 phút 1 giây")
        self.assertEqual(format_duration(None), "Không xác định")

    def test_format_bytes(self):
        self.assertEqual(format_bytes(0), "0 B")
        self.assertEqual(format_bytes(1024), "1.00 KB")
        self.assertEqual(format_bytes(1024**3), "1.00 GB")
        self.assertEqual(format_bytes(None), "Không xác định")

    def test_format_usage(self):
        self.assertEqual(
            format_usage(512 * 1024**2, 1024**3),
            "512.00 MB / 1.00 GB (50.0%)",
        )
        self.assertEqual(format_usage(None, None), "Không xác định")


if __name__ == "__main__":
    unittest.main()
