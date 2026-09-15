from odoo.tests import tagged
from odoo.exceptions import AccessError, UserError, ValidationError
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

    def test_account_move_snapshot_and_write_default(self):
        move = self._create_invoice(self.partner_rnc)
        self.assertEqual(move.korventis_fiscal_document_type_id, self.type_e31)
        self.partner_rnc.korventis_fiscal_document_type_id = self.type_e45
        self.assertEqual(move.korventis_fiscal_document_type_id, self.type_e31)
        move.korventis_fiscal_document_type_id = self.type_e32
        self.assertEqual(move.korventis_fiscal_document_type_id, self.type_e32)
        empty = self.env["account.move"].create(
            {
                "move_type": "out_invoice",
                "partner_id": self.partner_final.id,
                "invoice_date": move.invoice_date,
                "journal_id": self.company_data["default_journal_sale"].id,
            }
        )
        empty.korventis_fiscal_document_type_id = False
        empty.write({"partner_id": self.partner_rnc.id})
        self.assertEqual(empty.korventis_fiscal_document_type_id, self.type_e45)
        explicit = self._create_invoice(self.partner_rnc, doc_type=self.type_e32)
        explicit.write({"partner_id": self.partner_final.id})
        self.assertEqual(explicit.korventis_fiscal_document_type_id, self.type_e32)
        onchange_move = self.env["account.move"].new(
            {"move_type": "out_invoice", "partner_id": self.partner_final.id}
        )
        onchange_move._onchange_partner_korventis_fiscal_type()
        self.assertEqual(onchange_move.korventis_fiscal_document_type_id, self.type_e32)

    def test_historical_partner_snapshot(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        doc = move.korventis_fiscal_document_id
        self.assertEqual(doc.partner_name, "Cliente ABC")
        self.assertEqual(doc.partner_vat, "101672919")
        self.assertEqual(doc.partner_identification_type, "RNC")
        self.partner_rnc.write({"vat": "132000001", "name": "ABC SRL NUEVO"})
        self.assertEqual(doc.partner_vat, "101672919")
        self.assertEqual(doc.partner_name, "Cliente ABC")
        self.assertEqual(doc.partner_id.vat.replace("-", "").replace(" ", ""), "132000001")

    def test_sequence_normal_and_format(self):
        service = NcfService(self.env)
        fiscal_number, seq_no = service.allocate(self.sequence_e31, company=self.company)
        self.assertEqual(seq_no, 1)
        self.assertEqual(fiscal_number, "E310000000001")
        self.assertEqual(len(fiscal_number), 13)
        fiscal_number2, seq_no2 = service.allocate(self.sequence_e31, company=self.company)
        self.assertEqual(seq_no2, 2)
        self.assertEqual(fiscal_number2, "E310000000002")

    def test_sequence_company_mismatch(self):
        company_b = self.env["res.company"].sudo().create(
            {"name": "Mismatch Co", "country_id": self.do.id}
        )
        with self.assertRaises(UserError):
            NcfService(self.env).allocate(self.sequence_e31, company=company_b)

    def test_sequence_invalid_range(self):
        with self.assertRaises(Exception):
            self.env["korventis.fiscal.sequence"].sudo().create(
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
        seq = self.env["korventis.fiscal.sequence"].sudo().create(
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
        number, raw = service.allocate(seq, company=self.company)
        self.assertEqual(number, "E450000000005")
        with self.assertRaises(UserError):
            service.allocate(seq, company=self.company)

    def test_overlapping_range(self):
        with self.assertRaises(ValidationError):
            self.env["korventis.fiscal.sequence"].sudo().create(
                {
                    "company_id": self.company.id,
                    "document_type_id": self.type_e31.id,
                    "prefix": "E31",
                    "range_start": 50,
                    "range_end": 150,
                    "next_number": 50,
                }
            )

    def test_next_number_rewind(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        with self.assertRaises(UserError):
            self.sequence_e31.sudo().write({"next_number": 1})
        unused = self.sequence_e32.sudo()
        unused.write({"next_number": 10})
        unused.write({"next_number": 3})
        self.assertEqual(unused.next_number, 3)

    def test_issue_on_post_and_events(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        doc = move.korventis_fiscal_document_id
        self.assertEqual(doc.state, "issued")
        self.assertEqual(doc.fiscal_number, "E310000000001")
        self.assertIn("reserved", doc.event_ids.mapped("event_type"))
        self.assertIn("issued", doc.event_ids.mapped("event_type"))

    def test_immutability_and_state_machine(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        doc = move.korventis_fiscal_document_id
        amounts = (doc.amount_untaxed, doc.amount_tax, doc.amount_total)
        with self.assertRaises(UserError):
            doc.sudo().write({"fiscal_number": "E310000000099"})
        with self.assertRaises(UserError):
            doc.sudo().write({"state": "draft"})
        with self.assertRaises(UserError):
            doc.sudo().write({"amount_total": 1})
        with self.assertRaises(UserError):
            doc.sudo().with_context(korventis_skip_immutability=True).write({"state": "draft"})
        with self.assertRaises(UserError):
            move.korventis_fiscal_document_type_id = self.type_e32
        with self.assertRaises(UserError):
            move.button_draft()
        with self.assertRaises(UserError):
            doc.sudo().unlink()
        with self.assertRaises(UserError):
            doc.event_ids[0].sudo().unlink()
        with self.assertRaises(UserError):
            doc.event_ids[0].sudo().write({"notes": "tamper"})
        self.assertEqual((doc.amount_untaxed, doc.amount_tax, doc.amount_total), amounts)

    def test_credit_note_e34_and_original(self):
        invoice = self._create_invoice(self.partner_rnc)
        invoice.action_post()
        original = invoice.korventis_fiscal_document_id
        refunds = invoice._reverse_moves()
        refund = refunds[0]
        self.assertEqual(refund.move_type, "out_refund")
        self.assertEqual(refund.korventis_fiscal_document_type_id, self.type_e34)
        refund.action_post()
        credit = refund.korventis_fiscal_document_id
        self.assertEqual(credit.document_type_id, self.type_e34)
        self.assertEqual(credit.original_document_id, original)
        self.assertTrue(credit.fiscal_number.startswith("E34"))

    def test_credit_note_without_origin_blocked(self):
        from odoo import fields as odoo_fields

        refund = self.env["account.move"].create(
            {
                "move_type": "out_refund",
                "partner_id": self.partner_rnc.id,
                "invoice_date": odoo_fields.Date.today(),
                "journal_id": self.company_data["default_journal_sale"].id,
                "invoice_line_ids": [
                    (0, 0, {"product_id": self.product_a.id, "quantity": 1, "price_unit": 10})
                ],
            }
        )
        self.assertEqual(refund.korventis_fiscal_document_type_id, self.type_e34)
        with self.assertRaises(UserError):
            refund.action_post()

    @mute_logger("odoo.sql_db")
    def test_duplicity_unique_fiscal_number(self):
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                from odoo.addons.korventis_l10n_do_fiscal.services.internal import (
                    INTERNAL_WRITE_TOKEN,
                )

                self.env["korventis.fiscal.document"].sudo().with_context(
                    _korventis_internal_write=INTERNAL_WRITE_TOKEN
                ).create(
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
        company_b = self.env["res.company"].sudo().create(
            {
                "name": "Korventis Company B",
                "country_id": self.do.id,
                "korventis_fiscal_enabled": True,
            }
        )
        seq_b = (
            self.env["korventis.fiscal.sequence"]
            .sudo()
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
        number_b, _ = NcfService(self.env).allocate(seq_b, company=company_b)
        number_a, _ = NcfService(self.env).allocate(self.sequence_e31, company=self.company)
        self.assertEqual(number_a, "E310000000001")
        self.assertEqual(number_b, "E310000000001")
        user_a = self.env["res.users"].sudo().create(
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

    def test_permissions_sequence_and_issued_document(self):
        user = self.env["res.users"].sudo().create(
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
        manager = self.env["res.users"].sudo().create(
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
        with self.assertRaises(AccessError):
            self.env["korventis.fiscal.sequence"].with_user(user).create(
                {
                    "company_id": self.company.id,
                    "document_type_id": self.type_e45.id,
                    "prefix": "E45",
                    "range_start": 200,
                    "range_end": 300,
                    "next_number": 200,
                }
            )
        with self.assertRaises(AccessError):
            self.sequence_e32.with_user(user).write({"next_number": 2})
        self.sequence_e32.with_user(manager).write({"next_number": 3})
        move = self._create_invoice(self.partner_rnc)
        move.action_post()
        doc = move.korventis_fiscal_document_id
        # Domain immutability runs in write() before super()/ACL. Issued + protected
        # fields raise UserError for every non-internal caller, including Manager.
        with self.assertRaises(UserError):
            doc.with_user(user).write({"amount_total": 1})
        with self.assertRaises(UserError):
            doc.with_user(manager).write({"amount_total": 1})

    def test_accountant_posting_without_fiscal_manager(self):
        accountant = self.env["res.users"].sudo().create(
            {
                "name": "Accountant Poster",
                "login": "korventis_accountant_poster",
                "email": "acc-poster@example.com",
                "groups_id": [
                    (
                        6,
                        0,
                        [
                            self.env.ref("base.group_user").id,
                            self.env.ref("account.group_account_invoice").id,
                        ],
                    )
                ],
                "company_ids": [(6, 0, [self.company.id])],
                "company_id": self.company.id,
            }
        )
        with self.assertRaises(AccessError):
            self.env["korventis.fiscal.sequence"].with_user(accountant).create(
                {
                    "company_id": self.company.id,
                    "document_type_id": self.type_e45.id,
                    "prefix": "E45",
                    "range_start": 400,
                    "range_end": 500,
                    "next_number": 400,
                }
            )
        move = self._create_invoice(self.partner_rnc)
        move.with_user(accountant).action_post()
        self.assertEqual(move.korventis_fiscal_document_id.state, "issued")
        self.assertEqual(move.korventis_fiscal_document_id.partner_vat, "101672919")
        self.assertTrue(
            all(
                event.user_id == accountant
                for event in move.korventis_fiscal_document_id.event_ids
            )
        )

    def test_draft_document_event_cleanup(self):
        doc = self.env["korventis.fiscal.document"].sudo().create(
            {
                "company_id": self.company.id,
                "partner_id": self.partner_rnc.id,
                "document_type_id": self.type_e31.id,
            }
        )
        doc._korventis_log_event("manual_change", notes="draft cleanup")
        self.assertTrue(doc.event_ids)
        event_ids = doc.event_ids.ids
        doc.sudo().unlink()
        leftover = self.env["korventis.fiscal.event"].browse(event_ids).exists()
        self.assertFalse(leftover)

    def test_drafts_without_fiscal_number_coexist(self):
        vals = {
            "company_id": self.company.id,
            "partner_id": self.partner_rnc.id,
            "document_type_id": self.type_e31.id,
        }
        first = self.env["korventis.fiscal.document"].sudo().create(vals)
        second = self.env["korventis.fiscal.document"].sudo().create(vals)
        self.assertFalse(first.fiscal_number)
        self.assertFalse(second.fiscal_number)
        self.assertNotEqual(first.id, second.id)

    def _sudo_sequence(self, start, end, next_number=None, dtype=None):
        dtype = dtype or self.type_e45
        return self.env["korventis.fiscal.sequence"].sudo().create(
            {
                "company_id": self.company.id,
                "document_type_id": dtype.id,
                "prefix": dtype.prefix,
                "range_start": start,
                "range_end": end,
                "next_number": next_number if next_number is not None else start,
            }
        )

    def test_ten_digit_sequence_above_int32(self):
        service = NcfService(self.env)
        cases = (
            (2147483647, "E452147483647"),
            (2147483648, "E452147483648"),
            (8000000001, "E458000000001"),
            (9999999999, "E459999999999"),
        )
        for raw, expected in cases:
            seq = self._sudo_sequence(raw, raw)
            number, allocated = service.allocate(seq, company=self.company)
            self.assertEqual(allocated, raw)
            self.assertEqual(number, expected)
            self.assertEqual(len(number), 13)
            with self.assertRaises(UserError):
                service.allocate(seq, company=self.company)
            self.assertEqual(seq.next_number, raw + 1)

    @mute_logger("odoo.sql_db")
    def test_reject_eleven_digit_range_end(self):
        with self.assertRaises(IntegrityError):
            with self.env.cr.savepoint():
                self._sudo_sequence(1, 10_000_000_000)
