from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


from odoo.addons.korventis_partner_dgii.tests.common import (
    park_active_registry_versions,
)


@tagged("post_install", "-at_install")
class TestDgiiWizardIntegration(TransactionCase):
    """Portable wizard flow. Fixtures are local; they do not use QA version 61."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_DO")
        cls.e31 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e31")
        cls.e32 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e32")
        cls.country_do = cls.env.ref("base.do")
        park_active_registry_versions(cls.env)
        cls.version = cls.env["korventis.dgii.rnc.version"].sudo().create(
            {
                "name": "wizard-fixture.csv",
                "state": "active",
                "source_url": "https://dgii.gov.do/wizard-fixture.zip",
                "source_filename": "wizard-fixture.csv",
                "archive_sha256": "aa" + ("11" * 31),
                "imported_at": fields.Datetime.now(),
                "activated_at": fields.Datetime.now(),
                "record_count": 2,
            }
        )
        cls.company_record = cls._registry_record(
            "131998877",
            "KORVENTIS WIZARD ACME SRL",
            "ACTIVO",
            activity="COMERCIO",
        )
        cls.person_record = cls._registry_record(
            "00199887766",
            "KORVENTIS WIZARD JUANA TEST",
            "SUSPENDIDO",
            activity="SERVICIOS PROFESIONALES",
        )

    @classmethod
    def _registry_record(cls, rnc, name, status, activity="SERVICIOS"):
        return cls.env["korventis.dgii.rnc"].sudo().create(
            {
                "rnc": rnc,
                "rnc_normalizado": rnc,
                "razon_social": name,
                "razon_social_normalizada": name,
                "actividad_economica": activity,
                "estado": status,
                "regimen_pago": "NORMAL",
                "fecha_importacion": fields.Datetime.now(),
                "version_padron_id": cls.version.id,
            }
        )

    def _iap_guard(self):
        return patch.object(
            type(self.env["iap.autocomplete.api"]),
            "_contact_iap",
            side_effect=AssertionError("IAP must not be called"),
        )

    def test_wizard_creates_unique_spanish_e31_contact_from_active_registry(self):
        self.assertNotEqual(self.version.id, 61)
        existing = self.env["res.partner"].create(
            {
                "name": "KORVENTIS WIZARD ACME Contacto",
                "vat": "101777888",
                "country_id": self.country_do.id,
            }
        )

        with self._iap_guard() as contact_iap:
            wizard = self.env["korventis.partner.lookup.wizard"].create(
                {"query": "131998877"}
            )
            wizard.action_search()
            self.assertTrue(
                wizard.result_ids.filtered(
                    lambda line: line.source == "dgii"
                    and line.identification == "131998877"
                )
            )

            wizard.query = "KORVENTIS WIZARD ACME"
            wizard.action_search()
            self.assertEqual(wizard.result_ids[0].source, "partner")
            self.assertEqual(wizard.result_ids[0].partner_id, existing)
            dgii_line = wizard.result_ids.filtered(lambda line: line.source == "dgii")
            self.assertTrue(dgii_line)
            self.assertEqual(dgii_line[0].identification, "131998877")

            action = dgii_line[0].action_select()
            self.assertEqual(wizard.state, "confirm_dgii")
            self.assertEqual(wizard.selected_registry_rnc, "131998877")
            self.assertEqual(
                wizard.selected_registry_name, "KORVENTIS WIZARD ACME SRL"
            )
            self.assertEqual(wizard.selected_registry_status, "ACTIVO")
            self.assertEqual(wizard.selected_registry_activity, "COMERCIO")
            self.assertEqual(action["res_model"], wizard._name)

            confirm = wizard.action_confirm_dgii()
            partner = self.env["res.partner"].browse(confirm["res_id"])
            self.assertEqual(partner.name, "KORVENTIS WIZARD ACME SRL")
            self.assertEqual(partner.vat, "131998877")
            self.assertEqual(partner.country_id, self.country_do)
            self.assertEqual(partner.lang, "es_DO")
            self.assertEqual(partner.korventis_fiscal_document_type_id, self.e31)
            self.assertEqual(partner.korventis_dgii_status, "ACTIVO")
            self.assertEqual(partner.korventis_dgii_activity, "COMERCIO")
            self.assertEqual(partner.korventis_registration_origin, "dgii")
            self.assertFalse(
                self.env["korventis.fiscal.document"].search(
                    [("partner_id", "=", partner.id)]
                )
            )

            wizard.query = "131998877"
            wizard.action_search()
            self.assertTrue(
                wizard.result_ids.filtered(
                    lambda line: line.source == "partner" and line.partner_id == partner
                )
            )
            self.assertFalse(
                wizard.result_ids.filtered(
                    lambda line: line.registry_id == self.company_record
                )
            )
            second = self.env["res.partner"].korventis_create_from_dgii(
                self.company_record
            )
            self.assertEqual(second, partner)
            self.assertEqual(
                self.env["res.partner"].search_count(
                    [("korventis_identification_normalized", "=", "131998877")]
                ),
                1,
            )
            contact_iap.assert_not_called()

    def test_wizard_preserves_leading_zeros_and_manual_explicit_type(self):
        with self._iap_guard() as contact_iap:
            wizard = self.env["korventis.partner.lookup.wizard"].create(
                {"query": "00199887766"}
            )
            wizard.action_search()
            line = wizard.result_ids.filtered(lambda rec: rec.source == "dgii")
            self.assertEqual(line.identification, "00199887766")
            line.action_select()
            confirm = wizard.action_confirm_dgii()
            person = self.env["res.partner"].browse(confirm["res_id"])
            self.assertEqual(person.vat, "00199887766")
            self.assertEqual(person.korventis_dgii_status, "SUSPENDIDO")
            self.assertEqual(person.korventis_fiscal_document_type_id, self.e31)

            wizard.action_manual()
            wizard.manual_name = "Cliente mostrador"
            wizard.manual_identification = "131556677"
            wizard.manual_fiscal_type_id = self.e32
            manual_action = wizard.action_create_manual()
            manual = self.env["res.partner"].browse(manual_action["res_id"])
            self.assertEqual(manual.korventis_fiscal_document_type_id, self.e32)
            self.assertEqual(manual.korventis_registration_origin, "manual")
            self.assertEqual(manual.korventis_verification_state, "pending")
            self.assertNotEqual(manual, person)
            contact_iap.assert_not_called()
