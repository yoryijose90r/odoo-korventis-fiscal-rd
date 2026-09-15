from odoo.tests import tagged
from odoo.exceptions import UserError, ValidationError
from odoo.tools import mute_logger
from psycopg2 import IntegrityError

from odoo.addons.korventis_l10n_do_fiscal.services.ncf_service import NcfService
from odoo.addons.korventis_l10n_do_fiscal.tests.common import KorventisFiscalCommon


@tagged("post_install", "-at_install")
class TestFiscalCore(KorventisFiscalCommon):
    def test_module_document_types(self):
        codes = self.env["korventis.fiscal.document.type"].search([]).mapped("code")
        for code in ("E31", "E32", "E33", "E34", "E41", "E43", "E44", "E45", "E46", "E47"):
            self.assertIn(code, codes)
        self.assertTrue(self.type_e31.partner_assignable)
        self.assertTrue(self.type_e32.partner_assignable)
        self.assertFalse(self.type_e33.partner_assignable)
        self.assertFalse(self.type_e34.partner_assignable)
        self.assertFalse(self.type_e41.partner_assignable)

    def test_partner_default_assignable(self):
        self.assertEqual(self.partner_final.korventis_fiscal_document_type_id, self.type_e32)
        with self.assertRaises(ValidationError):
            self.partner_rnc.korventis_fiscal_document_type_id = self.type_e33

    def test_partner_identification_length(self):
        with self.assertRaises(ValidationError):
            self.env["res.partner"].create(
                {
                    "name": "Bad VAT",
                    "country_id": self.do.id,
                    "vat": "12345678",
                }
            )
        partner = self.env["res.partner"].create(
            {
                "name": "Cedula OK",
                "country_id": self.do.id,
                "vat": "00114272360",
            }
        )
        self.assertTrue(partner.vat)

    def test_account_move_snapshot(self):
        move = self._create_invoice(self.partner_rnc)
        self.assertEqual(move.korventis_fiscal_document_type_id, self.type_e31)
        self.partner_rnc.korventis_fiscal_document_type_id = self.type_e45
        self.assertEqual(move.korventis_fiscal_document_type_id, self.type_e31)
        move.korventis_fiscal_document_type_id = self.type_e32
        self.assertEqual(move.korventis_fiscal_document_type_id, self.type_e32)

    def test_sequence_normal_and_format(self):
        service = NcfService(self.env)
        fiscal_number, seq_no = service.allocate(self.sequence_e31)
        self.assertEqual(seq_no, 1)
        self.assertEqual(fiscal_number, "E310000000001")
        self.assertEqual(len(fiscal_number), 13)
        fiscal_number2, seq_no2 = service.allocate(self.sequence_e31)
        self.assertEqual(seq_no2, 2)
        self.assertEqual(fiscal_number2, "E310000000002")
        self.assertNotEqual(fiscal_number, fiscal_number2)

    def test_sequence_invalid_range(self):
        with self.assertRaises(Exception):
            self.env["korventis.fiscal.sequence"].create(
                {
                    "company_id": self.company.id,
                    "document_type_id": self.type_e45.id,
                    "prefix": "E45",
                    "range_start": 50,
                    "range_end": 10,
                    "next_number": 50,
                }
            )

    def test_sequence_end_of_range(self):
        seq = self.env["korventis.fiscal.sequence"].create(
            {
                "company_id": self.company.id,
                "document_type_id": self.type_e45.id,
                "prefix": "E45",
                "range_start": 5,
                "range_end": 5,
                "next_number": 5,
            }
        )
        service = NcfService(self.env)
        number, raw = service.allocate(seq)
        self.assertEqual(number, "E450000000005")
        with self.assertRaises(UserError):
            service.allocate(seq)

    def test_overlapping_range(self):
        with self.assertRaises(ValidationError):
            self.env["korventis.fiscal.sequence"].create(
                {
                    "company_id": self.company.id,
                    "document_type_id": self.type_e31.id,
                    "prefix": "E31",
                    "range_start": 50,
                    "range_end": 150,
                    "next_number": 50,
                }
            )

    def test_issue_on_post_and_events(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        self.assertTrue(move.korventis_fiscal_document_id)
        doc = move.korventis_fiscal_document_id
        self.assertEqual(doc.state, "issued")
        self.assertEqual(doc.fiscal_number, "E310000000001")
        self.assertEqual(doc.partner_id, self.partner_rnc)
        self.assertEqual(doc.company_id, self.company)
        events = doc.event_ids.mapped("event_type")
        self.assertIn("reserved", events)
        self.assertIn("issued", events)

    def test_immutability(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        doc = move.korventis_fiscal_document_id
        with self.assertRaises(UserError):
            doc.fiscal_number = "E310000000099"
        with self.assertRaises(UserError):
            move.korventis_fiscal_document_type_id = self.type_e32
        with self.assertRaises(UserError):
            move.button_draft()
        with self.assertRaises(UserError):
            doc.unlink()
        with self.assertRaises(UserError):
            doc.event_ids[0].unlink()
        with self.assertRaises(UserError):
            doc.event_ids[0].notes = "tamper"

    @mute_logger("odoo.sql_db")
    def test_duplicity_unique_fiscal_number(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        with self.assertRaises((IntegrityError, ValidationError)):
            with self.env.cr.savepoint():
                self.env["korventis.fiscal.document"].create(
                    {
                        "company_id": self.company.id,
                        "partner_id": self.partner_rnc.id,
                        "document_type_id": self.type_e31.id,
                        "fiscal_number": move.korventis_fiscal_document_id.fiscal_number,
                        "sequence_number": 1,
                        "state": "draft",
                    }
                )

    def test_multicompany_isolation(self):
        company_b = self.env["res.company"].create(
            {
                "name": "Korventis Company B",
                "country_id": self.do.id,
                "korventis_fiscal_enabled": True,
            }
        )
        seq_b = (
            self.env["korventis.fiscal.sequence"]
            .with_company(company_b)
            .create(
                {
                    "company_id": company_b.id,
                    "document_type_id": self.type_e31.id,
                    "prefix": "E31",
                    "range_start": 1,
                    "range_end": 10,
                    "next_number": 1,
                }
            )
        )
        service_b = NcfService(self.env)
        number_b, _ = service_b.allocate(seq_b)
        number_a, _ = NcfService(self.env).allocate(self.sequence_e31)
        self.assertEqual(number_a, "E310000000001")
        self.assertEqual(number_b, "E310000000001")
        user_a = self.env["res.users"].create(
            {
                "name": "Fiscal User A",
                "login": "korventis_fiscal_user_a",
                "email": "fiscal-a@example.com",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("korventis_l10n_do_fiscal.group_fiscal_user").id,
                        ],
                    )
                ],
                "company_ids": [(6, 0, [self.company.id])],
                "company_id": self.company.id,
            }
        )
        seq_b_as_a = (
            self.env["korventis.fiscal.sequence"]
            .with_user(user_a)
            .search([("id", "=", seq_b.id)])
        )
        self.assertFalse(seq_b_as_a)

    def test_permissions_sequence_write(self):
        user = self.env["res.users"].create(
            {
                "name": "Fiscal User Seq",
                "login": "korventis_fiscal_user_seq",
                "email": "fiscal-seq@example.com",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("korventis_l10n_do_fiscal.group_fiscal_user").id,
                        ],
                    )
                ],
                "company_ids": [(6, 0, [self.company.id])],
                "company_id": self.company.id,
            }
        )
        manager = self.env["res.users"].create(
            {
                "name": "Fiscal Manager Seq",
                "login": "korventis_fiscal_manager_seq",
                "email": "fiscal-mgr@example.com",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("korventis_l10n_do_fiscal.group_fiscal_manager").id,
                        ],
                    )
                ],
                "company_ids": [(6, 0, [self.company.id])],
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(Exception):
            self.sequence_e32.with_user(user).write({"next_number": 2})
        self.sequence_e32.with_user(manager).write({"next_number": 3})
        self.assertEqual(self.sequence_e32.next_number, 3)
