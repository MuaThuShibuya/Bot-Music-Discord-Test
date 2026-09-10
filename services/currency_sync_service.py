from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CASH_DB_PATH = os.path.join(BASE_DIR, "database", "users.db")
DEFAULT_CASH_UNIT_VND = 1_000
DEFAULT_OWO_UNIT = 1_000_000


@dataclass(frozen=True)
class CurrencyRate:
    cash_unit_vnd: int
    owo_unit: int
    updated_by: int | None = None
    updated_at: str = ""


class CurrencySyncService:
    """Quản lý tỷ giá trong users.db; casino tự đọc và đồng bộ số dư."""

    def __init__(self, cash_db_path: str | None = None):
        self.cash_db_path = os.path.abspath(
            cash_db_path or os.getenv("CASH_DB_PATH") or DEFAULT_CASH_DB_PATH
        )
        self._init_rate_schema()

    @staticmethod
    def _connect(path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(path, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    @classmethod
    @contextmanager
    def _connection(cls, path: str):
        conn = cls._connect(path)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_rate_schema(self) -> None:
        os.makedirs(os.path.dirname(self.cash_db_path), exist_ok=True)
        with self._connection(self.cash_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS currency_exchange_rate (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cash_unit_vnd INTEGER NOT NULL,
                    owo_unit INTEGER NOT NULL,
                    updated_by INTEGER,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO currency_exchange_rate
                    (id, cash_unit_vnd, owo_unit, updated_by, updated_at)
                VALUES (1, ?, ?, NULL, datetime('now'))
                """,
                (DEFAULT_CASH_UNIT_VND, DEFAULT_OWO_UNIT),
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS currency_wallet_sync (
                    user_id INTEGER PRIMARY KEY,
                    cash_balance INTEGER NOT NULL,
                    owo_balance INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def get_rate(self) -> CurrencyRate:
        with self._connection(self.cash_db_path) as conn:
            row = conn.execute(
                """
                SELECT cash_unit_vnd, owo_unit, updated_by, updated_at
                FROM currency_exchange_rate
                WHERE id = 1
                """
            ).fetchone()
        if not row:
            return CurrencyRate(DEFAULT_CASH_UNIT_VND, DEFAULT_OWO_UNIT)
        return CurrencyRate(
            cash_unit_vnd=int(row["cash_unit_vnd"]),
            owo_unit=int(row["owo_unit"]),
            updated_by=int(row["updated_by"]) if row["updated_by"] is not None else None,
            updated_at=str(row["updated_at"] or ""),
        )

    @staticmethod
    def parse_multiplier(raw_value: str | int | float | Decimal) -> Decimal:
        cleaned = str(raw_value).strip().replace(",", ".")
        try:
            value = Decimal(cleaned)
        except InvalidOperation as exc:
            raise ValueError(f"Tỷ lệ `{raw_value}` không hợp lệ") from exc
        if value <= 0:
            raise ValueError("Tỷ lệ phải lớn hơn 0")
        return value

    def set_rate(
        self,
        cash_multiplier: str | int | float | Decimal,
        owo_multiplier: str | int | float | Decimal,
        updated_by: int,
    ) -> tuple[CurrencyRate, int]:
        cash_value = self.parse_multiplier(cash_multiplier)
        owo_value = self.parse_multiplier(owo_multiplier)
        cash_unit_vnd = int(
            (cash_value * Decimal(DEFAULT_CASH_UNIT_VND)).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )
        owo_unit = int(
            (owo_value * Decimal(DEFAULT_OWO_UNIT)).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )
        if cash_unit_vnd <= 0 or owo_unit <= 0:
            raise ValueError("Tỷ lệ sau quy đổi phải lớn hơn 0")

        with self._connection(self.cash_db_path) as conn:
            conn.execute(
                """
                INSERT INTO currency_exchange_rate
                    (id, cash_unit_vnd, owo_unit, updated_by, updated_at)
                VALUES (1, ?, ?, ?, datetime('now'))
                ON CONFLICT(id) DO UPDATE SET
                    cash_unit_vnd = excluded.cash_unit_vnd,
                    owo_unit = excluded.owo_unit,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
                """,
                (cash_unit_vnd, owo_unit, int(updated_by)),
            )
            sync_rows = conn.execute(
                """
                SELECT user_id, owo_balance
                FROM currency_wallet_sync
                """
            ).fetchall()
            for row in sync_rows:
                user_id = int(row["user_id"])
                owo_balance = int(row["owo_balance"])
                cash_balance = self._rounded_ratio(
                    owo_balance,
                    cash_unit_vnd,
                    owo_unit,
                )
                conn.execute(
                    "UPDATE users SET cash = ? WHERE user_id = ?",
                    (cash_balance, user_id),
                )
                conn.execute(
                    """
                    UPDATE currency_wallet_sync
                    SET cash_balance = ?,
                        source = 'rate',
                        updated_at = datetime('now')
                    WHERE user_id = ?
                    """,
                    (cash_balance, user_id),
                )

        return self.get_rate(), len(sync_rows)

    @staticmethod
    def _rounded_ratio(value: int, numerator: int, denominator: int) -> int:
        if numerator <= 0 or denominator <= 0:
            raise ValueError("Tỷ lệ quy đổi phải lớn hơn 0")
        negative = value < 0
        absolute = abs(int(value))
        converted = (
            absolute * int(numerator) + int(denominator) // 2
        ) // int(denominator)
        return -converted if negative else converted

    def cash_to_owo(self, cash_balance: int, rate: CurrencyRate | None = None) -> int:
        current = rate or self.get_rate()
        return self._rounded_ratio(
            int(cash_balance),
            current.owo_unit,
            current.cash_unit_vnd,
        )

    def owo_to_cash(self, owo_balance: int, rate: CurrencyRate | None = None) -> int:
        current = rate or self.get_rate()
        return self._rounded_ratio(
            int(owo_balance),
            current.cash_unit_vnd,
            current.owo_unit,
        )
