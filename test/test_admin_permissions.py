from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from cogs.admin_command_utils import AdminCommandBase
from cogs.help_cog import _role_management_commands
from cogs.role.role_cog import RoleCog
from services.admin_service import AdminService


class FakeAdminDb:
    def __init__(self):
        self.tables = {}

    def create_table(self, table_name, schema):
        self.tables.setdefault(table_name, [])
        return True

    def select_one(self, table_name, where, params=()):
        rows = self.tables.get(table_name, [])
        if table_name in {"guild_admins", "cash_admins"}:
            guild_id, user_id = params
            return next((row for row in rows if row["guild_id"] == guild_id and row["user_id"] == user_id), None)
        if table_name == "admins":
            user_id = params[0]
            return next((row for row in rows if row["user_id"] == user_id), None)
        return None

    def insert(self, table_name, data):
        self.tables.setdefault(table_name, []).append(dict(data))
        return True

    def delete(self, table_name, where, params=()):
        rows = self.tables.get(table_name, [])
        before = len(rows)
        if table_name in {"guild_admins", "cash_admins"}:
            guild_id, user_id = params
            self.tables[table_name] = [
                row for row in rows
                if not (row["guild_id"] == guild_id and row["user_id"] == user_id)
            ]
        else:
            user_id = params[0]
            self.tables[table_name] = [row for row in rows if row["user_id"] != user_id]
        return len(self.tables[table_name]) < before

    def fetch(self, sql, params=()):
        if "cash_admins" in sql:
            rows = list(self.tables.get("cash_admins", []))
        else:
            rows = list(self.tables.get("guild_admins", []))
        if params:
            rows = [row for row in rows if row["guild_id"] == params[0]]
        return rows


class TestAdminServicePermissions(unittest.TestCase):
    def make_service(self):
        with patch("services.admin_service.CogDatabase", return_value=FakeAdminDb()):
            return AdminService()

    def test_soft_admin_is_scoped_by_guild(self):
        service = self.make_service()

        self.assertTrue(service.add_admin(100, 1, 777))

        self.assertTrue(service.is_admin(100, 777))
        self.assertFalse(service.is_admin(100, 888))
        self.assertFalse(service.is_admin(100))

    def test_cash_admin_is_separate_from_regular_admin(self):
        service = self.make_service()

        service.add_admin(100, 1, 777)
        self.assertFalse(service.is_cash_admin(100, 777))

        self.assertTrue(service.add_cash_admin(100, 1, 777))
        self.assertTrue(service.is_cash_admin(100, 777))
        self.assertFalse(service.is_cash_admin(100, 888))


class TestAdminCommandBaseCashPermissions(unittest.TestCase):
    def make_ctx(self):
        role = SimpleNamespace(id=456, name="cashier")
        return SimpleNamespace(
            guild=SimpleNamespace(id=777),
            author=SimpleNamespace(id=100, roles=[role]),
        )

    def test_regular_admin_does_not_bypass_cash(self):
        base = AdminCommandBase.__new__(AdminCommandBase)
        base._admins = MagicMock()
        base._role_permissions = MagicMock()
        base._admins.is_cash_admin.return_value = False
        base._role_permissions.user_can_use.return_value = False

        self.assertFalse(base.can_use_role_or_admin(self.make_ctx(), "cash"))
        base._admins.is_admin.assert_not_called()

    def test_cash_role_can_use_cash(self):
        base = AdminCommandBase.__new__(AdminCommandBase)
        base._admins = MagicMock()
        base._role_permissions = MagicMock()
        base._admins.is_cash_admin.return_value = False
        base._role_permissions.user_can_use.return_value = True

        self.assertTrue(base.can_use_role_or_admin(self.make_ctx(), "cash"))
        base._role_permissions.user_can_use.assert_called_once_with(777, [456], "cash")


class TestRoleHelpPermissions(unittest.TestCase):
    def test_help_role_includes_admin_permission_commands(self):
        command_names = {command["name"] for command in _role_management_commands()}

        self.assertIn("addadmin", command_names)
        self.assertIn("rmadmin", command_names)
        self.assertIn("addcashadmin", command_names)
        self.assertIn("rmcashadmin", command_names)

    def test_admin_permission_commands_resolve_to_role_group(self):
        cog = RoleCog.__new__(RoleCog)
        cog.bot = MagicMock()
        command_names = {
            "addadmin",
            "rmadmin",
            "addcashadmin",
            "rmcashadmin",
        }
        cog.bot.get_command.side_effect = lambda name: (
            SimpleNamespace(name=name) if name in command_names else None
        )

        for command_name in command_names:
            with self.subTest(command_name=command_name):
                self.assertEqual(cog._resolve_command_name(command_name), "role")


if __name__ == "__main__":
    unittest.main()
