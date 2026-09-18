import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from odoo.tests import TransactionCase, tagged
except ImportError:  # pragma: no cover - standalone pytest without Odoo
    TransactionCase = unittest.TestCase

    def tagged(*_args, **_kwargs):
        def decorator(cls):
            return cls

        return decorator

    _ODOO = False
else:
    _ODOO = True


MODULE = Path(__file__).resolve().parents[1]
CHILD_MENUS = (
    ("menu_korventis_fiscal_document", "menu_korventis_fiscal_root", "group_fiscal_user"),
    ("menu_korventis_fiscal_sequence", "menu_korventis_fiscal_root", "group_fiscal_manager"),
    ("menu_korventis_fiscal_type", "menu_korventis_fiscal_root", "group_fiscal_user"),
    ("menu_korventis_fiscal_event", "menu_korventis_fiscal_root", "group_fiscal_user"),
)


def _skip_without_odoo():
    return unittest.skipUnless(_ODOO, "Odoo is not available")


class TestMenuXmlContract(unittest.TestCase):
    def test_fiscal_root_is_independent_and_keeps_children(self):
        tree = ET.parse(MODULE / "views" / "menus.xml")
        menus = {node.get("id"): node for node in tree.findall("menuitem")}
        root = menus["menu_korventis_fiscal_root"]
        self.assertIsNone(root.get("parent"))
        self.assertEqual(root.get("groups"), "group_fiscal_user")
        self.assertNotEqual(root.get("parent"), "account.menu_finance")
        for xmlid, parent, groups in CHILD_MENUS:
            child = menus[xmlid]
            self.assertEqual(child.get("parent"), parent)
            self.assertEqual(child.get("groups"), groups)

    def test_accounting_menu_inherit_reuses_standard_xmlid(self):
        tree = ET.parse(MODULE / "views" / "account_menu.xml")
        record = tree.find("record")
        self.assertEqual(record.get("id"), "account.menu_finance_entries")
        self.assertEqual(record.get("model"), "ir.ui.menu")
        parent = record.find("field[@name='parent_id']")
        self.assertIsNotNone(parent)
        self.assertEqual((parent.get("eval") or "").strip(), "False")
        self.assertIsNone(
            tree.find("menuitem"),
            "do not create a second Accounting menu",
        )

    def test_admin_access_calls_orm_function_not_noupdate_user(self):
        tree = ET.parse(MODULE / "data" / "admin_access.xml")
        for record in tree.findall("record"):
            self.assertNotEqual(
                record.get("id"),
                "base.user_admin",
                "XML must not write base.user_admin; that XML ID is noupdate",
            )
        func = tree.find("function")
        self.assertIsNotNone(func)
        self.assertEqual(func.get("model"), "res.users")
        self.assertEqual(func.get("name"), "_korventis_ensure_initial_admin_access")
        self.assertNotIn("__", func.get("name"))
        self.assertEqual((func.get("eval") or "[]").strip(), "[]")

    def test_res_users_inherit_is_imported(self):
        init = (MODULE / "models" / "__init__.py").read_text(encoding="utf-8")
        self.assertIn("res_users", init)
        users = (MODULE / "models" / "res_users.py").read_text(encoding="utf-8")
        self.assertIn("def _korventis_ensure_initial_admin_access", users)
        self.assertIn("ensure_initial_admin_access", users)

    def test_hook_source_uses_xmlids_not_sql(self):
        text = (MODULE / "hooks.py").read_text(encoding="utf-8")
        start = text.index("ADMIN_GROUP_XMLIDS")
        end = text.index(")", start)
        granted = text[start:end]
        self.assertIn("base.user_admin", text)
        self.assertIn("account.group_account_user", granted)
        self.assertIn("korventis_l10n_do_fiscal.group_fiscal_manager", granted)
        self.assertNotIn("execute(", text)
        self.assertNotIn("account_accountant", granted)
        self.assertNotIn("group_account_manager", granted)
        self.assertNotIn("implied_ids", text)

    def test_upgrade_migration_calls_the_same_orm_helper(self):
        migrate = (
            MODULE / "migrations" / "18.0.1.3.3" / "post-migrate.py"
        ).read_text(encoding="utf-8")
        self.assertIn("ensure_initial_admin_access", migrate)
        self.assertIn("def migrate(", migrate)
        self.assertNotIn("cr.execute", migrate)
        self.assertNotIn("02_enable_accounting", migrate)

    def test_installer_is_per_database_and_does_not_restart(self):
        installer = MODULE.parent / "scripts" / "install_korventis.sh"
        text = installer.read_text(encoding="utf-8")
        self.assertIn("-d", text)
        self.assertIn("--stop-after-init", text)
        self.assertNotIn("docker restart", text)
        self.assertNotIn("systemctl restart", text)
        self.assertIn("There is no 02_enable_accounting.sh", text)


@_skip_without_odoo()
@tagged("post_install", "-at_install")
class TestMenuAccess(TransactionCase):
    def _required_groups(self):
        return [
            self.env.ref("account.group_account_user"),
            self.env.ref("korventis_l10n_do_fiscal.group_fiscal_manager"),
        ]

    def _strip_required_groups(self, user):
        commands = []
        for group in self._required_groups():
            commands.append((3, group.id))
            for implied in group.implied_ids:
                commands.append((3, implied.id))
        user.sudo().write({"groups_id": commands})

    def test_clean_install_helper_grants_admin_groups(self):
        from odoo.addons.korventis_l10n_do_fiscal.hooks import (
            ensure_initial_admin_access,
        )

        admin = self.env.ref("base.user_admin")
        self._strip_required_groups(admin)
        self.assertFalse(admin.has_group("account.group_account_user"))
        self.assertFalse(
            admin.has_group("korventis_l10n_do_fiscal.group_fiscal_manager")
        )
        ensure_initial_admin_access(self.env)
        self.assertTrue(admin.has_group("account.group_account_user"))
        self.assertTrue(admin.has_group("account.group_account_readonly"))
        self.assertTrue(admin.has_group("korventis_l10n_do_fiscal.group_fiscal_manager"))
        self.assertTrue(admin.has_group("korventis_l10n_do_fiscal.group_fiscal_user"))

    def test_upgrade_repairs_missing_admin_groups(self):
        from odoo.addons.korventis_l10n_do_fiscal.hooks import (
            ensure_initial_admin_access,
        )

        admin = self.env.ref("base.user_admin")
        self._strip_required_groups(admin)
        self.env["res.users"].sudo()._korventis_ensure_initial_admin_access()
        self.assertTrue(admin.has_group("account.group_account_user"))
        self.assertTrue(
            admin.has_group("korventis_l10n_do_fiscal.group_fiscal_manager")
        )
        self.env.cr.execute(
            """
            SELECT COUNT(*) FROM res_groups_users_rel
             WHERE gid = %s AND uid = %s
            """,
            [self.env.ref("account.group_account_user").id, admin.id],
        )
        self.assertEqual(self.env.cr.fetchone()[0], 1)
        before = admin.groups_id.ids
        ensure_initial_admin_access(self.env)
        ensure_initial_admin_access(self.env)
        self.assertEqual(sorted(admin.groups_id.ids), sorted(before))

    def test_second_run_does_not_write_when_groups_already_present(self):
        from odoo.addons.korventis_l10n_do_fiscal.hooks import (
            ensure_initial_admin_access,
        )

        admin = self.env.ref("base.user_admin")
        ensure_initial_admin_access(self.env)
        write_date = admin.sudo().write_date
        self.assertEqual(
            ensure_initial_admin_access(self.env),
            [
                "account.group_account_user",
                "korventis_l10n_do_fiscal.group_fiscal_manager",
            ],
        )
        admin.invalidate_recordset(["write_date", "groups_id"])
        self.assertEqual(admin.sudo().write_date, write_date)

    def test_plain_internal_user_does_not_inherit_admin_groups(self):
        from odoo.addons.korventis_l10n_do_fiscal.hooks import (
            ensure_initial_admin_access,
        )

        user = (
            self.env["res.users"]
            .sudo()
            .create(
                {
                    "name": "Plain menu user",
                    "login": "korventis_plain_menu_user",
                    "email": "plain-menu@example.com",
                    "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
                }
            )
        )
        before = set(user.groups_id.ids)
        ensure_initial_admin_access(self.env)
        ensure_initial_admin_access(self.env)
        self.assertEqual(set(user.groups_id.ids), before)
        self.assertFalse(user.has_group("account.group_account_user"))
        self.assertFalse(user.has_group("account.group_account_readonly"))
        self.assertFalse(user.has_group("korventis_l10n_do_fiscal.group_fiscal_user"))
        self.assertFalse(user.has_group("korventis_l10n_do_fiscal.group_fiscal_manager"))

    def test_authorized_user_sees_independent_root_menus(self):
        from odoo.addons.korventis_l10n_do_fiscal.hooks import (
            ensure_initial_admin_access,
        )

        admin = self.env.ref("base.user_admin")
        ensure_initial_admin_access(self.env)
        finance = self.env.ref("account.menu_finance")
        entries = self.env.ref("account.menu_finance_entries")
        fiscal_root = self.env.ref("korventis_l10n_do_fiscal.menu_korventis_fiscal_root")
        self.assertFalse(finance.parent_id)
        self.assertFalse(entries.parent_id)
        self.assertFalse(fiscal_root.parent_id)
        menus = self.env["ir.ui.menu"].browse([finance.id, entries.id, fiscal_root.id])
        visible = menus.with_user(admin)._filter_visible_menus()
        self.assertIn(finance, visible)
        self.assertIn(entries, visible)
        self.assertIn(fiscal_root, visible)
        for xmlid in (
            "korventis_l10n_do_fiscal.menu_korventis_fiscal_document",
            "korventis_l10n_do_fiscal.menu_korventis_fiscal_sequence",
            "korventis_l10n_do_fiscal.menu_korventis_fiscal_type",
            "korventis_l10n_do_fiscal.menu_korventis_fiscal_event",
        ):
            child = self.env.ref(xmlid)
            self.assertEqual(child.parent_id, fiscal_root)
            self.assertIn(child, child.with_user(admin)._filter_visible_menus())

    def test_menus_are_independent_and_not_duplicated(self):
        finance = self.env.ref("account.menu_finance")
        entries = self.env.ref("account.menu_finance_entries")
        fiscal_root = self.env.ref("korventis_l10n_do_fiscal.menu_korventis_fiscal_root")
        self.assertFalse(finance.parent_id)
        self.assertFalse(entries.parent_id)
        self.assertFalse(fiscal_root.parent_id)
        self.assertNotEqual(entries.id, finance.id)
        self.assertNotEqual(fiscal_root.id, finance.id)
        self.assertNotEqual(fiscal_root.parent_id, finance)
        self.assertEqual(
            self.env["ir.ui.menu"].search_count(
                [
                    (
                        "id",
                        "in",
                        [
                            self.env.ref(
                                "korventis_l10n_do_fiscal.menu_korventis_fiscal_root"
                            ).id
                        ],
                    )
                ]
            ),
            1,
        )
        for xmlid in (
            "korventis_l10n_do_fiscal.menu_korventis_fiscal_document",
            "korventis_l10n_do_fiscal.menu_korventis_fiscal_sequence",
            "korventis_l10n_do_fiscal.menu_korventis_fiscal_type",
            "korventis_l10n_do_fiscal.menu_korventis_fiscal_event",
        ):
            child = self.env.ref(xmlid)
            self.assertEqual(child.parent_id, fiscal_root)
        fiscal_roots = self.env["ir.ui.menu"].search(
            [("name", "=", "Korventis Fiscal RD"), ("parent_id", "=", False)]
        )
        self.assertEqual(len(fiscal_roots), 1)
        accounting_roots = self.env["ir.ui.menu"].search(
            [("id", "=", entries.id), ("parent_id", "=", False)]
        )
        self.assertEqual(len(accounting_roots), 1)


if __name__ == "__main__":
    unittest.main()
