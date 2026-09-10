import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from types import SimpleNamespace

from services.currency_sync_service import CurrencySyncService
from services.user_service import UserService


class CurrencySyncServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cash_path = os.path.join(self.temp_dir.name, "users.db")

        with closing(sqlite3.connect(self.cash_path)) as conn, conn:
            conn.execute(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE NOT NULL,
                    username TEXT NOT NULL,
                    cash INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                "INSERT INTO users (user_id, username, cash) VALUES (123, 'alice', 10000)"
            )
            conn.execute(
                "INSERT INTO users (user_id, username, cash) VALUES (456, 'bob', 0)"
            )

        self.service = CurrencySyncService(self.cash_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_rate_converts_both_directions(self):
        self.assertEqual(self.service.cash_to_owo(10_000), 10_000_000)
        self.assertEqual(self.service.owo_to_cash(10_000_000), 10_000)
        self.assertEqual(self.service.cash_to_owo(-2_000), -2_000_000)
        self.assertEqual(self.service.owo_to_cash(-2_000_000), -2_000)

    def test_decimal_rate_accepts_comma(self):
        rate, updated_wallets = self.service.set_rate("1", "0,5", 999)
        self.assertEqual(rate.cash_unit_vnd, 1_000)
        self.assertEqual(rate.owo_unit, 500_000)
        self.assertEqual(updated_wallets, 0)
        self.assertEqual(self.service.cash_to_owo(10_000), 5_000_000)

    def test_rate_change_keeps_owo_and_revalues_cash(self):
        with closing(sqlite3.connect(self.cash_path)) as conn, conn:
            conn.executemany(
                """
                INSERT INTO currency_wallet_sync
                    (user_id, cash_balance, owo_balance, source, updated_at)
                VALUES (?, ?, ?, 'cash', datetime('now'))
                """,
                [
                    (123, 10_000, 10_000_000),
                    (456, -2_000, -2_000_000),
                ],
            )

        _, updated_wallets = self.service.set_rate("1", "0.25", 999)

        with closing(sqlite3.connect(self.cash_path)) as conn:
            cash_rows = conn.execute(
                "SELECT user_id, cash FROM users ORDER BY user_id"
            ).fetchall()
            sync_rows = conn.execute(
                """
                SELECT user_id, cash_balance, owo_balance, source
                FROM currency_wallet_sync
                ORDER BY user_id
                """
            ).fetchall()
        self.assertEqual(updated_wallets, 2)
        self.assertEqual(cash_rows, [(123, 40_000), (456, -8_000)])
        self.assertEqual(
            sync_rows,
            [
                (123, 40_000, 10_000_000, "rate"),
                (456, -8_000, -2_000_000, "rate"),
            ],
        )

    def test_invalid_rate_is_rejected(self):
        with self.assertRaises(ValueError):
            self.service.set_rate("1", "0", 999)

    def test_user_service_allows_negative_cash_debt(self):
        updates = []
        service = UserService.__new__(UserService)
        service.db = SimpleNamespace(
            update=lambda table, values, where, params: updates.append(values)
        )
        service.get_user = lambda user_id: SimpleNamespace(cash=-2_000)

        service._update_numeric_field(123, "cash", 500)
        self.assertEqual(updates[-1]["cash"], -1_500)

        service._set_numeric_field(123, "cash", -3_000)
        self.assertEqual(updates[-1]["cash"], -3_000)

        service.get_user = lambda user_id: SimpleNamespace(cash=0)
        with self.assertRaises(ValueError):
            service._update_numeric_field(123, "cash", -1)


if __name__ == "__main__":
    unittest.main()
