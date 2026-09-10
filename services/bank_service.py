from __future__ import annotations

import os
import re
import time
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

import requests
from dotenv import load_dotenv

from utils import CogDatabase, get_timestamp

try:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass

load_dotenv()


ACB_API_URL = "https://apiapp.acb.com.vn"
DEFAULT_ACB_CLIENT_ID = "iuSuHYVufIUuNIREV0FB9EoLn9kHsDbm"


class BankPaymentService:
    """Quản lý cấu hình ngân hàng, QR pending và kiểm tra giao dịch ACB."""

    ACCOUNT_ENDPOINTS = (
        "/mb/legacy/ss/cs/bankservice/transfers/list/account-payment",
        "/mb/legacy/ss/cs/bankservice/account/list",
        "/mb/legacy/ss/cs/account/list",
    )
    BALANCE_KEYS = (
        "availableBalance",
        "available_balance",
        "availBalance",
        "currentBalance",
        "current_balance",
        "accountBalance",
        "account_balance",
        "ledgerBalance",
        "ledger_balance",
        "closingBalance",
        "closing_balance",
        "postBalance",
        "post_balance",
        "runningBalance",
        "running_balance",
        "balance",
    )
    ACCOUNT_NUMBER_KEYS = ("accountNumber", "account_number", "accountNo", "account_no", "account", "number")
    ACCOUNT_NAME_KEYS = ("accountName", "account_name", "ownerName", "owner_name", "customerName", "name")

    SETTING_KEYS = {
        "username": "username",
        "user": "username",
        "password": "password",
        "pass": "password",
        "account": "account_number",
        "account_number": "account_number",
        "stk": "account_number",
        "name": "account_name",
        "account_name": "account_name",
        "clientid": "client_id",
        "client_id": "client_id",
        "bank": "bank_code",
        "bankcode": "bank_code",
        "bank_code": "bank_code",
        "deposit_decor": "deposit_decor_url",
        "naptien_decor": "deposit_decor_url",
        "decor_naptien": "deposit_decor_url",
        "donate_decor": "donate_decor_url",
        "decor_donate": "donate_decor_url",
        "donate_channel": "donate_channel_id",
        "thank_channel": "donate_channel_id",
        "thanks_channel": "donate_channel_id",
        "leaderboard": "donate_leaderboard_channel_id",
        "leaderboard_channel": "donate_leaderboard_channel_id",
        "donate_leaderboard": "donate_leaderboard_channel_id",
        "top": "donate_leaderboard_channel_id",
        "topdonate": "donate_leaderboard_channel_id",
        "top_donate": "donate_leaderboard_channel_id",
        "bxh": "donate_leaderboard_channel_id",
        "rank": "donate_leaderboard_channel_id",
        "ranking": "donate_leaderboard_channel_id",
        "leaderboard_message": "donate_leaderboard_message_id",
        "leaderboard_message_id": "donate_leaderboard_message_id",
        "top_message": "donate_leaderboard_message_id",
        "auto": "auto_check_enabled",
    }

    def __init__(self):
        self.db = CogDatabase("bank_payments")
        self._init_database()

    def _init_database(self):
        self.db.create_table(
            "bank_settings",
            """
            guild_id INTEGER PRIMARY KEY,
            username TEXT,
            password TEXT,
            account_number TEXT,
            account_name TEXT,
            client_id TEXT,
            bank_code TEXT DEFAULT 'ACB',
            deposit_decor_url TEXT,
            donate_decor_url TEXT,
            donate_channel_id INTEGER,
            donate_leaderboard_channel_id INTEGER,
            donate_leaderboard_message_id INTEGER,
            donate_thank_template TEXT DEFAULT 'Cảm ơn {user} đã donate {amount} VNĐ cho {server}!',
            auto_check_enabled INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
            """,
        )
        self.db.create_table(
            "bank_tokens",
            """
            guild_id INTEGER PRIMARY KEY,
            access_token TEXT,
            updated_at TEXT
            """,
        )
        self.db.create_table(
            "bank_payments",
            """
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            kind TEXT NOT NULL,
            amount INTEGER NOT NULL,
            code TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'pending',
            message_id INTEGER,
            channel_id INTEGER,
            qr_url TEXT,
            bank_transaction_id TEXT,
            bank_description TEXT,
            donor_message TEXT,
            created_at TEXT,
            updated_at TEXT,
            paid_at TEXT
            """,
        )
        self.db.create_table(
            "donate_leaderboard",
            """
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            amount INTEGER DEFAULT 0,
            donate_count INTEGER DEFAULT 0,
            updated_at TEXT,
            PRIMARY KEY (guild_id, user_id)
            """,
        )
        self._ensure_schema()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        columns = {row["name"] for row in self.db.fetch(f"PRAGMA table_info({table})")}
        if column not in columns:
            self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _ensure_schema(self):
        self._ensure_column("bank_settings", "account_name", "TEXT")
        self._ensure_column("bank_settings", "client_id", "TEXT")
        self._ensure_column("bank_settings", "bank_code", "TEXT DEFAULT 'ACB'")
        self._ensure_column("bank_settings", "deposit_decor_url", "TEXT")
        self._ensure_column("bank_settings", "donate_decor_url", "TEXT")
        self._ensure_column("bank_settings", "donate_channel_id", "INTEGER")
        self._ensure_column("bank_settings", "donate_leaderboard_channel_id", "INTEGER")
        self._ensure_column("bank_settings", "donate_leaderboard_message_id", "INTEGER")
        self._ensure_column(
            "bank_settings",
            "donate_thank_template",
            "TEXT DEFAULT 'Cảm ơn {user} đã donate {amount} VNĐ cho {server}!'",
        )
        self._ensure_column("bank_settings", "auto_check_enabled", "INTEGER DEFAULT 1")
        self._ensure_column("bank_settings", "created_at", "TEXT")
        self._ensure_column("bank_settings", "updated_at", "TEXT")
        self._ensure_column("bank_payments", "message_id", "INTEGER")
        self._ensure_column("bank_payments", "channel_id", "INTEGER")
        self._ensure_column("bank_payments", "qr_url", "TEXT")
        self._ensure_column("bank_payments", "bank_transaction_id", "TEXT")
        self._ensure_column("bank_payments", "bank_description", "TEXT")
        self._ensure_column("bank_payments", "donor_message", "TEXT")
        self._ensure_column("bank_payments", "paid_at", "TEXT")

    def ensure_settings(self, guild_id: int) -> dict:
        existing = self.get_settings(guild_id, include_env=False)
        if existing:
            return existing
        now = get_timestamp()
        self.db.insert(
            "bank_settings",
            {
                "guild_id": guild_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        return self.get_settings(guild_id, include_env=False) or {"guild_id": guild_id}

    @staticmethod
    def _env_defaults() -> dict[str, Any]:
        return {
            "username": os.getenv("ACB_USERNAME", ""),
            "password": os.getenv("ACB_PASSWORD", ""),
            "account_number": os.getenv("ACB_ACCOUNT_NUMBER", ""),
            "account_name": os.getenv("ACB_ACCOUNT_NAME", os.getenv("ACB_BANK_NAME", "ACB")),
            "client_id": os.getenv("ACB_CLIENT_ID", DEFAULT_ACB_CLIENT_ID),
            "bank_code": os.getenv("ACB_BANK_CODE", "ACB"),
            "deposit_decor_url": os.getenv("NAPTIEN_DECOR_URL", ""),
            "donate_decor_url": os.getenv("DONATE_DECOR_URL", ""),
            "donate_channel_id": None,
            "donate_leaderboard_channel_id": None,
            "donate_leaderboard_message_id": None,
            "donate_thank_template": os.getenv(
                "DONATE_THANK_TEMPLATE",
                "Cảm ơn {user} đã donate {amount} VNĐ cho {server}!",
            ),
            "auto_check_enabled": 1,
        }

    def get_settings(self, guild_id: int, include_env: bool = True) -> dict | None:
        row = self.db.select_one("bank_settings", "guild_id = ?", (guild_id,))
        if not include_env:
            return row
        defaults = self._env_defaults()
        if not row:
            defaults["guild_id"] = guild_id
            return defaults
        merged = dict(defaults)
        merged.update({key: value for key, value in row.items() if value not in (None, "")})
        merged["guild_id"] = guild_id
        return merged

    def is_configured(self, guild_id: int) -> bool:
        settings = self.get_settings(guild_id) or {}
        return all(settings.get(key) for key in ("username", "password", "account_number"))

    def set_setting(self, guild_id: int, key: str, value: Any) -> bool:
        resolved = self.SETTING_KEYS.get(key.lower())
        if not resolved:
            raise ValueError("Khoá config không hợp lệ")
        self.ensure_settings(guild_id)
        if resolved == "auto_check_enabled":
            if isinstance(value, str):
                value = 1 if value.strip().lower() in {"on", "1", "true", "bat", "bật", "enable"} else 0
            else:
                value = 1 if value else 0
        if isinstance(value, str) and value.strip().lower() in {"off", "none", "null", "xoa", "xoá"}:
            value = None
        if resolved in {"donate_channel_id", "donate_leaderboard_channel_id", "donate_leaderboard_message_id"}:
            value = self._extract_id(value) if value is not None else None
        return self.db.update(
            "bank_settings",
            {resolved: value, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    @staticmethod
    def _extract_id(value: Any) -> int | None:
        if value is None:
            return None
        digits = re.sub(r"\D", "", str(value))
        return int(digits) if digits else None

    def set_donate_channel(self, guild_id: int, channel_id: int | None) -> bool:
        self.ensure_settings(guild_id)
        return self.db.update(
            "bank_settings",
            {"donate_channel_id": channel_id, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def set_donate_leaderboard_channel(self, guild_id: int, channel_id: int | None) -> bool:
        self.ensure_settings(guild_id)
        return self.db.update(
            "bank_settings",
            {
                "donate_leaderboard_channel_id": channel_id,
                "donate_leaderboard_message_id": None,
                "updated_at": get_timestamp(),
            },
            "guild_id = ?",
            (guild_id,),
        )

    def set_donate_leaderboard_message(self, guild_id: int, message_id: int | None) -> bool:
        self.ensure_settings(guild_id)
        return self.db.update(
            "bank_settings",
            {"donate_leaderboard_message_id": message_id, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def get_donate_leaderboard_messages(self) -> list[dict]:
        return self.db.fetch(
            """
            SELECT guild_id, donate_leaderboard_channel_id, donate_leaderboard_message_id
            FROM bank_settings
            WHERE donate_leaderboard_channel_id IS NOT NULL
              AND donate_leaderboard_message_id IS NOT NULL
            """
        )

    def set_donate_template(self, guild_id: int, template: str) -> bool:
        self.ensure_settings(guild_id)
        return self.db.update(
            "bank_settings",
            {"donate_thank_template": template, "updated_at": get_timestamp()},
            "guild_id = ?",
            (guild_id,),
        )

    def add_donate_leaderboard(self, guild_id: int, user_id: int, username: str, amount: int) -> None:
        now = get_timestamp()
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO donate_leaderboard
                (guild_id, user_id, username, amount, donate_count, updated_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                username = excluded.username,
                amount = amount + excluded.amount,
                donate_count = donate_count + 1,
                updated_at = excluded.updated_at
            """,
            (guild_id, user_id, username, int(amount), now),
        )
        self.db.conn.commit()

    def get_donate_leaderboard(self, guild_id: int, limit: int = 50) -> list[dict]:
        return self.db.fetch(
            """
            SELECT * FROM donate_leaderboard
            WHERE guild_id = ?
            ORDER BY amount DESC, donate_count DESC, updated_at ASC
            LIMIT ?
            """,
            (guild_id, max(1, min(int(limit), 50))),
        )

    def reset_donate_leaderboard(self, guild_id: int) -> list[dict]:
        rows = self.get_donate_leaderboard(guild_id, limit=50)
        self.db.delete("donate_leaderboard", "guild_id = ?", (guild_id,))
        return rows

    def get_token(self, guild_id: int) -> str | None:
        row = self.db.select_one("bank_tokens", "guild_id = ?", (guild_id,))
        return row.get("access_token") if row else None

    def save_token(self, guild_id: int, token: str | None) -> None:
        now = get_timestamp()
        if self.db.select_one("bank_tokens", "guild_id = ?", (guild_id,)):
            self.db.update("bank_tokens", {"access_token": token, "updated_at": now}, "guild_id = ?", (guild_id,))
            return
        self.db.insert("bank_tokens", {"guild_id": guild_id, "access_token": token, "updated_at": now})

    def clear_token(self, guild_id: int) -> None:
        self.db.delete("bank_tokens", "guild_id = ?", (guild_id,))

    @staticmethod
    def generate_code(guild_id: int, user_id: int) -> str:
        suffix = str(user_id)[-4:]
        return f"BL{str(guild_id)[-4:]}{suffix}{int(time.time()) % 100000}{uuid.uuid4().hex[:3]}".upper()

    def build_qr_url(self, settings: dict, amount: int, code: str) -> str:
        bank_code = str(settings.get("bank_code") or "ACB").upper()
        account_number = str(settings.get("account_number") or "").strip()
        account_name = quote_plus(str(settings.get("account_name") or "ACB").strip())
        add_info = quote_plus(code)
        return (
            f"https://img.vietqr.io/image/{bank_code}-{account_number}-compact2.png"
            f"?amount={int(amount)}&addInfo={add_info}&accountName={account_name}"
        )

    def create_payment(
        self,
        guild_id: int,
        user_id: int,
        username: str,
        kind: str,
        amount: int,
        donor_message: str = "",
    ) -> dict:
        if amount <= 0:
            raise ValueError("Số tiền phải lớn hơn 0 VNĐ")
        settings = self.get_settings(guild_id) or {}
        code = self.generate_code(guild_id, user_id)
        qr_url = self.build_qr_url(settings, amount, code)
        now = get_timestamp()
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO bank_payments
                (guild_id, user_id, username, kind, amount, code, status, qr_url, donor_message, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """,
            (
                guild_id,
                user_id,
                username,
                kind,
                int(amount),
                code,
                qr_url,
                str(donor_message or "")[:500],
                now,
                now,
            ),
        )
        self.db.conn.commit()
        return self.get_payment(int(cursor.lastrowid))

    def get_payment(self, payment_id: int) -> dict | None:
        return self.db.select_one("bank_payments", "id = ?", (payment_id,))

    def get_payment_by_code(self, code: str) -> dict | None:
        return self.db.select_one("bank_payments", "code = ?", (code.upper(),))

    def mark_message(self, payment_id: int, channel_id: int, message_id: int) -> bool:
        return self.db.update(
            "bank_payments",
            {"channel_id": channel_id, "message_id": message_id, "updated_at": get_timestamp()},
            "id = ?",
            (payment_id,),
        )

    def get_user_pending_payments(self, guild_id: int, user_id: int, limit: int = 10) -> list[dict]:
        return self.db.fetch(
            """
            SELECT * FROM bank_payments
            WHERE guild_id = ? AND user_id = ? AND status = 'pending'
            ORDER BY id DESC
            LIMIT ?
            """,
            (guild_id, user_id, max(1, min(int(limit), 50))),
        )

    def get_pending_payments(self, limit: int = 40) -> list[dict]:
        return self.db.fetch(
            """
            SELECT * FROM bank_payments
            WHERE status = 'pending'
            ORDER BY id ASC
            LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        )

    def mark_paid(self, payment_id: int, transaction: dict | None = None) -> dict | None:
        tx = transaction or {}
        now = get_timestamp()
        cursor = self.db.conn.cursor()
        cursor.execute(
            """
            UPDATE bank_payments
            SET status = 'paid',
                bank_transaction_id = ?,
                bank_description = ?,
                paid_at = ?,
                updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (
                self._transaction_id(tx),
                self._transaction_text(tx)[:900],
                now,
                now,
                payment_id,
            ),
        )
        self.db.conn.commit()
        if cursor.rowcount == 0:
            return None
        return self.get_payment(payment_id)

    def mark_cancelled(self, payment_id: int) -> dict | None:
        self.db.update(
            "bank_payments",
            {"status": "cancelled", "updated_at": get_timestamp()},
            "id = ?",
            (payment_id,),
        )
        return self.get_payment(payment_id)

    @staticmethod
    def _login_request(settings: dict) -> tuple[str | None, str | None]:
        try:
            response = requests.post(
                f"{ACB_API_URL}/mb/v2/auth/tokens",
                headers={"Content-Type": "application/json; charset=utf-8", "Host": "apiapp.acb.com.vn"},
                json={
                    "clientId": settings.get("client_id") or DEFAULT_ACB_CLIENT_ID,
                    "username": settings.get("username"),
                    "password": settings.get("password"),
                },
                verify=False,
                timeout=15,
            )
            data = response.json()
            token = data.get("accessToken")
            if token:
                return token, None
            return None, str(data)[:500]
        except Exception as exc:
            return None, str(exc)

    @staticmethod
    def _history_request(settings: dict, token: str, days: int = 2) -> tuple[dict | None, str | None]:
        current_time = int(time.time() * 1000)
        from_time = current_time - (max(1, int(days)) * 86400 * 1000)
        url = (
            f"{ACB_API_URL}/mb/legacy/ss/cs/person/transaction-history/list"
            f"?account={settings.get('account_number')}&transactionType=ALL"
            f"&from={from_time}&to={current_time}&min=&max="
        )
        try:
            response = requests.get(
                url,
                headers={
                    "Host": "apiapp.acb.com.vn",
                    "x-conversation-id": str(uuid.uuid4()),
                    "Authorization": f"bearer {token}",
                    "Cache-Control": "no-cache",
                    "Accept-Language": "vi",
                    "x-request-id": str(uuid.uuid4()),
                    "apikey": "null",
                    "User-Agent": "ACB-MBA/5 CFNetwork/1333.0.4 Darwin/21.5.0",
                    "x-app-version": "3.25.0",
                    "Accept": "application/json, text/plain, */*",
                },
                verify=False,
                timeout=15,
            )
            return response.json(), None
        except Exception as exc:
            return None, str(exc)

    @staticmethod
    def _auth_headers(token: str) -> dict[str, str]:
        return {
            "Host": "apiapp.acb.com.vn",
            "x-conversation-id": str(uuid.uuid4()),
            "Authorization": f"bearer {token}",
            "Cache-Control": "no-cache",
            "Accept-Language": "vi",
            "x-request-id": str(uuid.uuid4()),
            "apikey": "null",
            "User-Agent": "ACB-MBA/5 CFNetwork/1333.0.4 Darwin/21.5.0",
            "x-app-version": "3.25.0",
            "Accept": "application/json, text/plain, */*",
        }

    @classmethod
    def _request_json(cls, endpoint: str, token: str) -> tuple[dict | list | None, str | None]:
        try:
            response = requests.get(
                f"{ACB_API_URL}{endpoint}",
                headers=cls._auth_headers(token),
                verify=False,
                timeout=15,
            )
            try:
                data = response.json()
            except ValueError:
                return None, f"{response.status_code}: {response.text[:300]}"
            if response.status_code >= 400:
                return data, f"{response.status_code}: {str(data)[:300]}"
            return data, None
        except Exception as exc:
            return None, str(exc)

    @staticmethod
    def _walk_dicts(value: Any) -> list[dict]:
        found: list[dict] = []
        if isinstance(value, dict):
            found.append(value)
            for child in value.values():
                found.extend(BankPaymentService._walk_dicts(child))
        elif isinstance(value, list):
            for child in value:
                found.extend(BankPaymentService._walk_dicts(child))
        return found

    @staticmethod
    def _digits(value: Any) -> str:
        return re.sub(r"\D", "", str(value or ""))

    @staticmethod
    def _amount_to_int_optional(value: Any) -> int | None:
        if value is None or value == "":
            return None
        if isinstance(value, (int, float)):
            return int(value)
        cleaned = re.sub(r"[^\d.,-]", "", str(value))
        if not cleaned or cleaned in {"-", ".", ",", "-.", "-,"}:
            return None
        if "," in cleaned and "." in cleaned:
            if cleaned.rfind(",") > cleaned.rfind("."):
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            parts = cleaned.split(",")
            cleaned = cleaned.replace(",", "") if len(parts[-1]) == 3 else cleaned.replace(",", ".")
        elif "." in cleaned:
            parts = cleaned.split(".")
            if len(parts) > 1 and len(parts[-1]) == 3:
                cleaned = cleaned.replace(".", "")
        try:
            return int(float(cleaned))
        except ValueError:
            return None

    @classmethod
    def _record_account_number(cls, record: dict) -> str:
        for key in cls.ACCOUNT_NUMBER_KEYS:
            value = record.get(key)
            if value:
                return str(value)
        return ""

    @classmethod
    def _record_account_name(cls, record: dict) -> str:
        for key in cls.ACCOUNT_NAME_KEYS:
            value = record.get(key)
            if value:
                return str(value)
        return ""

    @classmethod
    def _record_balance(cls, record: dict) -> int | None:
        for key in cls.BALANCE_KEYS:
            if key in record:
                amount = cls._amount_to_int_optional(record.get(key))
                if amount is not None:
                    return amount
        return None

    @classmethod
    def _record_matches_account(cls, record: dict, account_number: str) -> bool:
        expected = cls._digits(account_number)
        if not expected:
            return False
        for key in cls.ACCOUNT_NUMBER_KEYS:
            value = cls._digits(record.get(key))
            if value and (value == expected or value.endswith(expected) or expected.endswith(value)):
                return True
        return False

    @classmethod
    def _extract_balance_from_response(cls, result: Any, account_number: str) -> dict | None:
        records = cls._walk_dicts(result)
        account_records = [record for record in records if cls._record_matches_account(record, account_number)]
        candidates = account_records or records
        for record in candidates:
            balance = cls._record_balance(record)
            if balance is None:
                continue
            return {
                "balance": balance,
                "account_number": cls._record_account_number(record) or account_number,
                "account_name": cls._record_account_name(record),
            }
        return None

    @classmethod
    def _balance_lookup(cls, settings: dict, token: str) -> dict:
        last_error = None
        for endpoint in cls.ACCOUNT_ENDPOINTS:
            result, error = cls._request_json(endpoint, token)
            extracted = cls._extract_balance_from_response(result, str(settings.get("account_number") or ""))
            if extracted:
                extracted.update({"matched": True, "source": endpoint, "token": token})
                return extracted
            last_error = error or "ACB không trả về balance trong endpoint tài khoản."

        history, history_error = cls._history_request(settings, token, days=1)
        extracted = cls._extract_balance_from_response(history, str(settings.get("account_number") or ""))
        if extracted:
            extracted.update({"matched": True, "source": "transaction-history", "token": token})
            return extracted
        return {
            "matched": False,
            "token": token,
            "error": history_error or last_error or "ACB không trả về thông tin số dư tài khoản.",
        }

    @staticmethod
    def _extract_transactions(result: Any) -> list[dict]:
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        if not isinstance(result, dict):
            return []
        data = result.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in ("transactions", "items", "list", "records", "transactionList"):
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        for key in ("transactions", "items", "list", "records", "transactionList"):
            value = result.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _amount_to_int(value: Any) -> int:
        if value is None:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        cleaned = re.sub(r"[^\d.-]", "", str(value))
        if not cleaned:
            return 0
        if "." in cleaned and "," not in str(value):
            parts = cleaned.split(".")
            if len(parts[-1]) == 3:
                cleaned = cleaned.replace(".", "")
        try:
            return int(float(cleaned.replace(",", "")))
        except ValueError:
            return 0

    @classmethod
    def _transaction_amount(cls, tx: dict) -> int:
        for key in ("amount", "transactionAmount", "creditAmount", "credit", "money", "value"):
            amount = cls._amount_to_int(tx.get(key))
            if amount:
                return abs(amount)
        return 0

    @staticmethod
    def _transaction_text(tx: dict) -> str:
        keys = (
            "description",
            "transactionDescription",
            "remark",
            "content",
            "narrative",
            "bankTransactionContent",
            "transferContent",
        )
        parts = [str(tx.get(key) or "") for key in keys if tx.get(key)]
        if not parts:
            parts = [str(value) for value in tx.values() if isinstance(value, str)]
        return " ".join(parts).strip()

    @staticmethod
    def _transaction_id(tx: dict) -> str:
        for key in ("transactionNumber", "reference", "trace", "transactionId", "id", "refNo"):
            value = tx.get(key)
            if value:
                return str(value)
        return ""

    @classmethod
    def _transaction_is_in(cls, tx: dict) -> bool:
        tx_type = str(tx.get("type") or tx.get("transactionType") or tx.get("dcSign") or "").upper()
        if tx_type in {"IN", "CR", "CREDIT", "C"}:
            return True
        return cls._amount_to_int(tx.get("creditAmount")) > 0

    @classmethod
    def _find_matching_transaction(cls, result: dict, code: str, amount: int) -> dict | None:
        code_upper = code.upper()
        for tx in cls._extract_transactions(result):
            if not cls._transaction_is_in(tx):
                continue
            tx_text = cls._transaction_text(tx).upper()
            tx_amount = cls._transaction_amount(tx)
            if code_upper in tx_text and tx_amount >= int(amount):
                return tx
        return None

    @classmethod
    def _check_with_settings(cls, settings: dict, token: str | None, code: str, amount: int) -> dict:
        if not all(settings.get(key) for key in ("username", "password", "account_number")):
            return {"matched": False, "error": "Chưa cấu hình ACB username/password/account_number."}

        active_token = token
        if not active_token:
            active_token, login_error = cls._login_request(settings)
            if not active_token:
                return {"matched": False, "error": f"Không đăng nhập được ACB: {login_error}"}

        result, history_error = cls._history_request(settings, active_token, days=2)
        transactions = cls._extract_transactions(result)
        if history_error or not transactions:
            active_token, login_error = cls._login_request(settings)
            if not active_token:
                return {"matched": False, "error": f"Không refresh được ACB: {login_error or history_error}"}
            result, history_error = cls._history_request(settings, active_token, days=2)
            if history_error:
                return {"matched": False, "token": active_token, "error": history_error}

        matched = cls._find_matching_transaction(result or {}, code, amount)
        return {
            "matched": bool(matched),
            "token": active_token,
            "transaction": matched,
            "error": None if matched is not None else None,
        }

    @classmethod
    def _balance_with_settings(cls, settings: dict, token: str | None) -> dict:
        if not all(settings.get(key) for key in ("username", "password", "account_number")):
            return {"matched": False, "error": "Chưa cấu hình ACB username/password/account_number."}

        active_token = token
        if not active_token:
            active_token, login_error = cls._login_request(settings)
            if not active_token:
                return {"matched": False, "error": f"Không đăng nhập được ACB: {login_error}"}

        result = cls._balance_lookup(settings, active_token)
        if result.get("matched"):
            return result

        refreshed_token, login_error = cls._login_request(settings)
        if not refreshed_token:
            result["error"] = f"Không refresh được ACB: {login_error or result.get('error')}"
            return result
        return cls._balance_lookup(settings, refreshed_token)

    async def check_payment_online(self, guild_id: int, code: str, amount: int) -> dict:
        import asyncio

        settings = self.get_settings(guild_id) or {}
        token = self.get_token(guild_id)
        result = await asyncio.to_thread(self._check_with_settings, settings, token, code, amount)
        if result.get("token"):
            self.save_token(guild_id, result["token"])
        return result

    async def get_bank_balance_online(self, guild_id: int) -> dict:
        import asyncio

        settings = self.get_settings(guild_id) or {}
        token = self.get_token(guild_id)
        result = await asyncio.to_thread(self._balance_with_settings, settings, token)
        if result.get("token"):
            self.save_token(guild_id, result["token"])
        if result.get("matched"):
            result.setdefault("account_number", settings.get("account_number") or "")
            result.setdefault("account_name", settings.get("account_name") or "")
            result["updated_at"] = get_timestamp()
        return result
