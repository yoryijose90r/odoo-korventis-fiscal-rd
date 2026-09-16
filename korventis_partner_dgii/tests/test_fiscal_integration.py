from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.korventis_l10n_do_fiscal.tests.common import (
    KorventisFiscalCommon,
)
from odoo.addons.korventis_partner_dgii.tests.common import (
    park_active_registry_versions,
)


@tagged("post_install", "-at_install")
class TestPartnerDgiiFiscalIntegration(KorventisFiscalCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_DO")
        park_active_registry_versions(cls.env)
        cls.version = cls.env["korventis.dgii.rnc.version"].sudo().create(
            {
                "name": "fiscal-integration.csv",
                "state": "active",
                "source_url": "https://dgii.gov.do/fiscal-integration.zip",
                "source_filename": "fiscal-integration.csv",
                "archive_sha256": "b" * 64,
                "imported_at": fields.Datetime.now(),
                "activated_at": fields.Datetime.now(),
                "record_count": 1,
            }
        )
        cls.registry_record = cls.env["korventis.dgii.rnc"].sudo().create(
            {
                "rnc": "131000099",
                "rnc_normalizado": "131000099",
                "razon_social": "CLIENTE INTEGRACION DGII",
                "razon_social_normalizada": "CLIENTE INTEGRACION DGII",
                "estado": "ACTIVO",
                "regimen_pago": "NORMAL",
                "fecha_importacion": fields.Datetime.now(),
                "version_padron_id": cls.version.id,
            }
        )

    def test_dgii_partner_data_flows_to_draft_invoice_without_allocation(self):
        initial_next = self.sequence_e31.next_number
        partner = self.env["res.partner"].korventis_create_from_dgii(
            self.registry_record
        )
        move = self._create_invoice(partner)
        self.assertEqual(move.partner_id, partner)
        self.assertEqual(move.partner_id.vat, "131000099")
        self.assertEqual(move.korventis_fiscal_document_type_id, self.type_e31)
        self.assertFalse(move.korventis_fiscal_document_id)
        self.assertEqual(self.sequence_e31.next_number, initial_next)

    def test_existing_issued_document_is_unchanged_by_partner_registration(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        document = move.korventis_fiscal_document_id
        fiscal_number = document.fiscal_number
        sequence_next = self.sequence_e31.next_number

        self.env["res.partner"].korventis_create_from_dgii(self.registry_record)

        document.invalidate_recordset()
        self.sequence_e31.invalidate_recordset()
        self.assertEqual(document.fiscal_number, fiscal_number)
        self.assertEqual(document.state, "issued")
        self.assertEqual(self.sequence_e31.next_number, sequence_next)

    def test_lookup_is_rejected_on_vendor_bills(self):
        move = self.env["account.move"].create(
            {
                "move_type": "in_invoice",
                "partner_id": self.partner_rnc.id,
                "journal_id": self.company_data["default_journal_purchase"].id,
            }
        )
        with self.assertRaises(UserError):
            move.action_korventis_lookup_partner()
        wizard = self.env["korventis.partner.lookup.wizard"].with_context(
            active_model="account.move",
            active_id=move.id,
        ).create({})
        partner = self.env["res.partner"].korventis_create_from_dgii(
            self.registry_record
        )
        with self.assertRaises(UserError):
            wizard._use_partner(partner)
