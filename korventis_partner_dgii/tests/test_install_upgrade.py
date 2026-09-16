from datetime import datetime
from unittest.mock import patch
import ast
import os

from odoo.exceptions import UserError
from odoo.modules.module import get_module_path
from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import mute_logger

from odoo.addons.korventis_l10n_do_fiscal.tests.common import (
    KorventisFiscalCommon,
)
from odoo.addons.korventis_partner_dgii import hooks
from odoo.addons.korventis_partner_dgii.models.dgii_import_run import (
    PRIMARY_DGII_URL,
)
from odoo.addons.korventis_partner_dgii.services.importer import (
    DgiiRegistryImporter,
)
from odoo.addons.korventis_partner_dgii.services.schedule import (
    next_santo_domingo_import,
)
from odoo.addons.korventis_partner_dgii.services.schema import (
    CONFIG_DEFAULTS,
    CUSTOM_INDEXES,
    EXPECTED_TABLES,
    count_active_versions,
    ensure_custom_indexes,
    pg_index_exists,
    pg_table_exists,
)


@tagged("post_install", "-at_install")
class TestPartnerDgiiInstallUpgrade(TransactionCase):
    def _cron(self):
        return self.env.ref(
            "korventis_partner_dgii.ir_cron_import_dgii_registry"
        ).with_context(active_test=False)

    def test_a_clean_install_creates_expected_structures(self):
        cr = self.env.cr
        for table in EXPECTED_TABLES:
            self.assertTrue(pg_table_exists(cr, table), table)
        module = self.env["ir.module.module"].search(
            [("name", "=", "korventis_partner_dgii")],
            limit=1,
        )
        self.assertEqual(module.state, "installed")
        self.assertTrue(
            self.env.ref("korventis_partner_dgii.group_dgii_user", False)
        )
        self.assertTrue(
            self.env.ref("korventis_partner_dgii.group_dgii_manager", False)
        )
        self.assertTrue(
            self.env["ir.model.access"].search(
                [("name", "=", "korventis.dgii.rnc.user")],
                limit=1,
            )
        )
        self.assertTrue(
            self.env.ref("korventis_partner_dgii.menu_korventis_dgii_root", False)
        )
        self.assertTrue(
            self.env.ref("korventis_partner_dgii.ir_cron_import_dgii_registry", False)
        )
        for key in CONFIG_DEFAULTS:
            self.assertTrue(
                self.env["ir.config_parameter"].sudo().search(
                    [("key", "=", key)],
                    limit=1,
                ),
                key,
            )

    def test_b_repeated_schema_ensure_does_not_duplicate(self):
        first = ensure_custom_indexes(self.env.cr)
        second = ensure_custom_indexes(self.env.cr)
        self.assertEqual(second, [])
        self.assertTrue(isinstance(first, list))

    def test_c_upgrade_helpers_preserve_registry_and_partners(self):
        version = self.env["korventis.dgii.rnc.version"].sudo().create(
            {
                "name": "preserve.csv",
                "state": "active",
                "source_url": PRIMARY_DGII_URL,
                "source_filename": "preserve.csv",
                "archive_sha256": "c" * 64,
                "imported_at": datetime(2026, 9, 16, 5, 0, 0),
                "activated_at": datetime(2026, 9, 16, 5, 0, 0),
                "record_count": 1,
            }
        )
        record = self.env["korventis.dgii.rnc"].sudo().create(
            {
                "rnc": "101000077",
                "rnc_normalizado": "101000077",
                "razon_social": "CLIENTE CONSERVADO",
                "razon_social_normalizada": "CLIENTE CONSERVADO",
                "estado": "ACTIVO",
                "regimen_pago": "NORMAL",
                "fecha_importacion": datetime(2026, 9, 16, 5, 0, 0),
                "version_padron_id": version.id,
            }
        )
        partner = self.env["res.partner"].create(
            {
                "name": "Contacto conservado",
                "vat": "101000077",
                "country_id": self.env.ref("base.do").id,
            }
        )
        run = self.env["korventis.dgii.import.run"].sudo().create(
            {
                "name": "histórica",
                "state": "success",
                "started_at": datetime(2026, 9, 16, 5, 0, 0),
                "version_id": version.id,
            }
        )
        hooks.upgrade_module(self.env, "18.0.1.0.0")
        self.assertEqual(version.state, "active")
        self.assertTrue(record.exists())
        self.assertTrue(partner.exists())
        self.assertEqual(partner.vat, "101000077")
        self.assertTrue(run.exists())

    def test_d_database_isolation_contract(self):
        self.env.cr.execute("SELECT current_database()")
        database_name = self.env.cr.fetchone()[0]
        self.assertTrue(database_name)
        self.env.cr.execute(
            """
            SELECT count(*)
              FROM information_schema.tables
             WHERE table_name = 'korventis_dgii_rnc'
            """
        )
        self.assertEqual(self.env.cr.fetchone()[0], 1)

    def test_d_two_databases_require_runtime_harness(self):
        self.skipTest(
            "El aislamiento Base A / Base B requiere dos bases Odoo en el "
            "mismo servidor. Procedimiento en docs/INSTALL.md."
        )

    def test_e_migration_fails_closed_on_two_active_versions(self):
        self.env.cr.execute(
            "DROP INDEX IF EXISTS korventis_dgii_rnc_version_one_active_idx"
        )
        self.env["korventis.dgii.rnc.version"].invalidate_model()
        vals = {
            "name": "dup.csv",
            "state": "active",
            "source_url": PRIMARY_DGII_URL,
            "source_filename": "dup.csv",
            "imported_at": datetime(2026, 9, 16, 5, 0, 0),
            "activated_at": datetime(2026, 9, 16, 5, 0, 0),
            "record_count": 1,
        }
        self.env["korventis.dgii.rnc.version"].sudo().create(
            dict(vals, archive_sha256="d" * 64)
        )
        self.env["korventis.dgii.rnc.version"].sudo().create(
            dict(vals, archive_sha256="e" * 64, name="dup-2.csv")
        )
        with self.assertRaises(RuntimeError):
            hooks.validate_upgrade_preconditions(self.env.cr)
        self.assertGreater(count_active_versions(self.env.cr), 1)

    def test_f_install_and_cron_do_not_download_until_enabled(self):
        cron = self._cron()
        self.assertFalse(cron.active)
        self.assertEqual(
            self.env["ir.config_parameter"].sudo().get_param(
                "korventis_partner_dgii.auto_import_enabled"
            ),
            "False",
        )
        with patch.object(DgiiRegistryImporter, "_download") as download:
            self.env["korventis.dgii.import.run"]._cron_import_registry()
        download.assert_not_called()
        with patch.object(DgiiRegistryImporter, "_download") as download:
            hooks.post_init_hook(self.env)
        download.assert_not_called()

    def test_g_upgrade_does_not_duplicate_cron(self):
        hooks.ensure_single_cron(self.env, activate=False)
        hooks.ensure_single_cron(self.env, activate=False)
        crons = (
            self.env["ir.cron"]
            .sudo()
            .with_context(active_test=False)
            .search(
                [
                    ("model_id.model", "=", "korventis.dgii.import.run"),
                    ("code", "ilike", "_cron_import_registry"),
                ]
            )
        )
        self.assertEqual(len(crons), 1)

    def test_h_custom_indexes_and_sql_constraints_exist(self):
        cr = self.env.cr
        for index in CUSTOM_INDEXES:
            self.assertTrue(pg_index_exists(cr, index["name"]), index["name"])
        cr.execute(
            """
            SELECT conname
              FROM pg_constraint
             WHERE conrelid = 'korventis_dgii_rnc'::regclass
               AND contype = 'u'
            """
        )
        rnc_uniques = {row[0] for row in cr.fetchall()}
        self.assertTrue(
            any("version_rnc_unique" in name for name in rnc_uniques),
            rnc_uniques,
        )
        cr.execute(
            """
            SELECT conname
              FROM pg_constraint
             WHERE conrelid = 'korventis_dgii_rnc_version'::regclass
               AND contype = 'u'
            """
        )
        version_uniques = {row[0] for row in cr.fetchall()}
        self.assertTrue(
            any("archive_sha256_unique" in name for name in version_uniques),
            version_uniques,
        )

    def test_i_manifest_depends_on_fiscal_before_partner_dgii(self):
        manifest_path = os.path.join(
            get_module_path("korventis_partner_dgii"),
            "__manifest__.py",
        )
        with open(manifest_path, encoding="utf-8") as handle:
            manifest = ast.literal_eval(handle.read())
        self.assertIn("korventis_l10n_do_fiscal", manifest["depends"])
        self.assertEqual(manifest["depends"][-1], "korventis_l10n_do_fiscal")
        self.assertEqual(manifest["version"], "18.0.1.1.0")

    def test_status_reports_pending_registry_after_install(self):
        if self.env["korventis.dgii.rnc.version"].search(
            [("state", "=", "active")],
            limit=1,
        ):
            self.skipTest("El entorno de prueba ya tiene un padrón activo.")
        status = self.env["korventis.dgii.registry.status"].create(
            self.env["korventis.dgii.registry.status"]._status_values()
        )
        self.assertTrue(status.module_installed)
        self.assertEqual(status.registry_state, "pending")

    def test_schedule_uses_santo_domingo_not_os_timezone(self):
        now = datetime(2026, 9, 16, 18, 0, 0)
        nxt = next_santo_domingo_import(now)
        self.assertEqual(nxt.hour, 5)
        self.assertEqual(nxt.minute, 0)
        self.assertEqual(nxt.day, 17)

    def test_shared_archive_path_must_be_absolute_zip(self):
        importer = DgiiRegistryImporter(
            self.env,
            self.env["korventis.dgii.import.run"],
        )
        with self.assertRaises(UserError):
            importer._copy_shared_archive("relative.zip")


@tagged("post_install", "-at_install")
class TestPartnerDgiiInstallFiscalIntegrity(KorventisFiscalCommon):
    def test_j_historical_fiscal_documents_are_untouched_by_install_helpers(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        document = move.korventis_fiscal_document_id
        fiscal_number = document.fiscal_number
        sequence_next = self.sequence_e31.next_number
        with mute_logger("odoo.addons.korventis_partner_dgii.hooks"):
            hooks.upgrade_module(self.env, "18.0.1.0.0")
        document.invalidate_recordset()
        self.sequence_e31.invalidate_recordset()
        self.assertEqual(document.fiscal_number, fiscal_number)
        self.assertEqual(document.state, "issued")
        self.assertEqual(self.sequence_e31.next_number, sequence_next)
