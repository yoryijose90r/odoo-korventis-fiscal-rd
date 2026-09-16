import time
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPartnerDgii(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["res.lang"]._activate_lang("es_DO")
        cls.e31 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e31")
        cls.e32 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e32")
        cls.version = cls.env["korventis.dgii.rnc.version"].sudo().create(
            {
                "name": "fixture.csv",
                "state": "active",
                "source_url": "https://dgii.gov.do/fixture.zip",
                "source_filename": "fixture.csv",
                "archive_sha256": "a" * 64,
                "imported_at": fields.Datetime.now(),
                "activated_at": fields.Datetime.now(),
                "record_count": 2,
            }
        )
        cls.active_record = cls._registry_record(
            "101000001",
            "PORTAL DOMINICANA SRL",
            "ACTIVO",
        )
        cls.suspended_record = cls._registry_record(
            "00114272360",
            "PERSONA SUSPENDIDA",
            "SUSPENDIDO",
        )

    @classmethod
    def _registry_record(cls, rnc, name, status):
        return cls.env["korventis.dgii.rnc"].sudo().create(
            {
                "rnc": rnc,
                "rnc_normalizado": rnc,
                "razon_social": name,
                "razon_social_normalizada": name,
                "actividad_economica": "SERVICIOS",
                "estado": status,
                "regimen_pago": "NORMAL",
                "fecha_importacion": fields.Datetime.now(),
                "version_padron_id": cls.version.id,
            }
        )

    def test_searches_existing_contact_before_registry(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Portal Dominicana existente",
                "vat": "131000001",
                "country_id": self.env.ref("base.do").id,
            }
        )
        wizard = self.env["korventis.partner.lookup.wizard"].create(
            {"query": "Portal Dominicana"}
        )
        wizard.action_search()
        self.assertTrue(wizard.result_ids)
        self.assertEqual(wizard.result_ids[0].source, "partner")
        self.assertEqual(wizard.result_ids[0].partner_id, partner)
        self.assertIn("dgii", wizard.result_ids.mapped("source"))

    def test_searches_registry_by_name_and_rnc(self):
        Registry = self.env["korventis.dgii.rnc"]
        self.assertEqual(
            Registry.search_active_registry("Portal Dominicana"),
            self.active_record,
        )
        self.assertEqual(
            Registry.search_active_registry("101000001"),
            self.active_record,
        )
        self.assertFalse(Registry.search_active_registry("%"))
        self.assertFalse(Registry.search_active_registry("PORTAL%"))

    def test_like_percent_and_underscore_are_literal(self):
        record = self._registry_record(
            "101000077",
            "COMERCIAL 50% OFERTA_ESPECIAL",
            "ACTIVO",
        )
        Registry = self.env["korventis.dgii.rnc"]
        self.assertEqual(
            Registry.search_active_registry("COMERCIAL 50% OFERTA_ESPECIAL"),
            record,
        )
        self.assertEqual(
            Registry.search_active_registry("COMERCIAL 50%"),
            record,
        )
        self.assertNotIn(record, Registry.search_active_registry("%OFERTA"))
        self.assertFalse(Registry.search_active_registry("%"))
        self.assertFalse(Registry.search_active_registry("PORTAL D_MINICANA"))
        self.assertEqual(
            Registry.search_active_registry("COMERCIAL 50% OFERTA_ESPECIAL"),
            record,
        )

    def test_search_does_not_create_contact(self):
        before = self.env["res.partner"].search_count([])
        wizard = self.env["korventis.partner.lookup.wizard"].create(
            {"query": "Persona Suspendida"}
        )
        wizard.action_search()
        self.assertIn("dgii", wizard.result_ids.mapped("source"))
        self.assertEqual(self.env["res.partner"].search_count([]), before)

    def test_create_from_dgii_assigns_e31_spanish_and_source(self):
        partner = self.env["res.partner"].korventis_create_from_dgii(
            self.active_record
        )
        self.assertEqual(partner.name, self.active_record.razon_social)
        self.assertEqual(partner.vat, "101000001")
        self.assertEqual(partner.korventis_fiscal_document_type_id, self.e31)
        self.assertEqual(partner.lang, "es_DO")
        self.assertEqual(partner.korventis_registration_origin, "dgii")
        self.assertEqual(partner.korventis_verification_state, "listed")
        self.assertEqual(partner.korventis_dgii_version_id, self.version)

    def test_suspended_contributor_is_allowed_and_visible(self):
        partner = self.env["res.partner"].korventis_create_from_dgii(
            self.suspended_record
        )
        self.assertEqual(partner.korventis_dgii_status, "SUSPENDIDO")
        self.assertEqual(partner.vat, "00114272360")
        self.assertEqual(partner.korventis_fiscal_document_type_id, self.e31)

    def test_existing_identification_prevents_duplicate(self):
        first = self.env["res.partner"].korventis_create_from_dgii(
            self.active_record
        )
        second = self.env["res.partner"].korventis_create_from_dgii(
            self.active_record
        )
        self.assertEqual(first, second)
        self.assertEqual(
            self.env["res.partner"].search_count(
                [("korventis_identification_normalized", "=", "101000001")]
            ),
            1,
        )

    def test_manual_registration_requires_all_values(self):
        Partner = self.env["res.partner"]
        with self.assertRaises(UserError):
            Partner.korventis_create_manual_customer("", "131000002", self.e31)
        with self.assertRaises(UserError):
            Partner.korventis_create_manual_customer("Manual", "", self.e31)
        with self.assertRaises(UserError):
            Partner.korventis_create_manual_customer(
                "Manual",
                "131000002",
                self.env["korventis.fiscal.document.type"],
            )
        with self.assertRaises(ValidationError):
            Partner.korventis_create_manual_customer(
                "Manual",
                "12345678",
                self.e31,
            )

    def test_manual_registration_uses_explicit_type_and_pending_state(self):
        partner = self.env["res.partner"].korventis_create_manual_customer(
            "Cliente manual",
            "131000003",
            self.e32,
        )
        self.assertEqual(partner.korventis_fiscal_document_type_id, self.e32)
        self.assertEqual(partner.korventis_registration_origin, "manual")
        self.assertEqual(partner.korventis_verification_state, "pending")
        self.assertEqual(partner.lang, "es_DO")

    def test_manual_requirements_do_not_apply_globally(self):
        supplier = self.env["res.partner"].create(
            {
                "name": "Proveedor técnico sin clasificación Korventis",
                "supplier_rank": 1,
            }
        )
        self.assertTrue(supplier)
        self.assertFalse(supplier.korventis_registration_origin)

    def test_local_search_does_not_call_iap(self):
        IapApi = type(self.env["iap.autocomplete.api"])
        wizard = self.env["korventis.partner.lookup.wizard"].create(
            {"query": "Portal Dominicana"}
        )
        with patch.object(
            IapApi,
            "_contact_iap",
            side_effect=AssertionError("IAP must not be called"),
        ) as contact_iap:
            wizard.action_search()
        contact_iap.assert_not_called()

    def test_partner_form_removes_only_autocomplete_widget(self):
        arch, _view = self.env["res.partner"]._get_view(
            self.env.ref("base.view_partner_form").id,
            "form",
        )
        nodes = arch.xpath("//field[@name='name' or @name='vat']")
        self.assertTrue(nodes)
        self.assertFalse(
            any(node.get("widget") == "field_partner_autocomplete" for node in nodes)
        )

    def test_company_form_removes_only_autocomplete_widget(self):
        arch, _view = self.env["res.company"]._get_view(
            self.env.ref("base.view_company_form").id,
            "form",
        )
        nodes = arch.xpath("//field[@name='name' or @name='vat']")
        self.assertTrue(nodes)
        self.assertFalse(
            any(node.get("widget") == "field_partner_autocomplete" for node in nodes)
        )

    def test_registry_queries_are_limited_and_fast_on_fixture(self):
        values = []
        now = fields.Datetime.now()
        for index in range(200):
            rnc = str(200000000 + index)
            values.append(
                {
                    "rnc": rnc,
                    "rnc_normalizado": rnc,
                    "razon_social": "EMPRESA PRUEBA %03d" % index,
                    "razon_social_normalizada": "EMPRESA PRUEBA %03d" % index,
                    "estado": "ACTIVO",
                    "regimen_pago": "NORMAL",
                    "fecha_importacion": now,
                    "version_padron_id": self.version.id,
                }
            )
        self.env["korventis.dgii.rnc"].sudo().create(values)
        started = time.monotonic()
        by_name = self.env["korventis.dgii.rnc"].search_active_registry(
            "Empresa Prueba",
            limit=20,
        )
        by_rnc = self.env["korventis.dgii.rnc"].search_active_registry(
            "200000050",
            limit=20,
        )
        elapsed = time.monotonic() - started
        self.assertEqual(len(by_name), 20)
        self.assertEqual(by_rnc.rnc, "200000050")
        self.assertLess(elapsed, 2.0)
