import tempfile
import unittest
from unittest.mock import patch

from services.booking_service import BookingService
from services.settings_service import SettingsService
from services.user_service import UserService


class GuildDataIsolationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_patch = patch("utils.DATABASE_DIR", self.temp_dir.name)
        self.database_patch.start()

    def tearDown(self):
        self.database_patch.stop()
        self.temp_dir.cleanup()

    def test_points_and_legacy_luong_are_isolated_but_cash_is_global(self):
        service = UserService()
        service.get_or_create_user(10, "member", 111)
        service.get_or_create_user(10, "member", 222)

        service.add_points(10, 50, 111)
        service.add_points(10, 7, 222)
        service.add_luong(10, 9000, 111)
        service.add_cash(10, 1234)

        self.assertEqual(service.get_user(10, 111).points, 50)
        self.assertEqual(service.get_user(10, 222).points, 7)
        self.assertEqual(service.get_user(10, 111).luong, 9000)
        self.assertEqual(service.get_user(10, 222).luong, 0)
        self.assertEqual(service.get_user(10, 111).cash, 1234)
        self.assertEqual(service.get_user(10, 222).cash, 1234)
        service.db.close()

    def test_booking_data_and_config_are_isolated(self):
        first = BookingService(111)
        second = BookingService(222)
        first.set_hour_price_vnd(100_000)
        second.set_hour_price_vnd(25_000)
        first.add_booking_session(10, "member", 2)

        self.assertEqual(first.get_hour_price_vnd(), 100_000)
        self.assertEqual(second.get_hour_price_vnd(), 25_000)
        self.assertEqual(first.get_booking(10)["booking_hours"], 2)
        self.assertIsNone(second.get_booking(10))
        first.db.close()
        second.db.close()

    def test_prefix_is_isolated(self):
        service = SettingsService()
        service.set_prefix(111, "b")
        service.set_prefix(222, "!")

        self.assertEqual(service.get_prefix(111), "b")
        self.assertEqual(service.get_prefix(222), "!")
        self.assertNotEqual(service.get_prefix(111), service.get_prefix(222))
        service.db.close()
