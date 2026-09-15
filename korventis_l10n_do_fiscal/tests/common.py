from odoo import fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


class KorventisFiscalCommon(AccountTestInvoicingCommon):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.do = cls.env.ref("base.do")
        cls.company.country_id = cls.do
        cls.company.korventis_fiscal_enabled = True
        cls.type_e31 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e31")
        cls.type_e32 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e32")
        cls.type_e33 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e33")
        cls.type_e34 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e34")
        cls.type_e41 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e41")
        cls.type_e45 = cls.env.ref("korventis_l10n_do_fiscal.document_type_e45")
        cls.partner_final = cls.env["res.partner"].create(
            {
                "name": "Consumidor Final",
                "country_id": cls.do.id,
                "korventis_fiscal_document_type_id": cls.type_e32.id,
            }
        )
        cls.partner_rnc = cls.env["res.partner"].create(
            {
                "name": "Cliente ABC",
                "country_id": cls.do.id,
                "vat": "101672919",
                "korventis_fiscal_document_type_id": cls.type_e31.id,
            }
        )
        cls.sequence_e31 = cls.env["korventis.fiscal.sequence"].create(
            {
                "company_id": cls.company.id,
                "document_type_id": cls.type_e31.id,
                "prefix": "E31",
                "range_start": 1,
                "range_end": 100,
                "next_number": 1,
            }
        )
        cls.sequence_e32 = cls.env["korventis.fiscal.sequence"].create(
            {
                "company_id": cls.company.id,
                "document_type_id": cls.type_e32.id,
                "prefix": "E32",
                "range_start": 1,
                "range_end": 100,
                "next_number": 1,
            }
        )
        cls.sequence_e34 = cls.env["korventis.fiscal.sequence"].create(
            {
                "company_id": cls.company.id,
                "document_type_id": cls.type_e34.id,
                "prefix": "E34",
                "range_start": 1,
                "range_end": 100,
                "next_number": 1,
            }
        )

    def _create_invoice(self, partner, doc_type=None, extra_vals=None):
        vals = {
            "move_type": "out_invoice",
            "partner_id": partner.id,
            "invoice_date": fields.Date.today(),
            "journal_id": self.company_data["default_journal_sale"].id,
            "invoice_line_ids": [
                (
                    0,
                    0,
                    {
                        "product_id": self.product_a.id,
                        "quantity": 1,
                        "price_unit": 100.0,
                    },
                )
            ],
        }
        if doc_type:
            vals["korventis_fiscal_document_type_id"] = doc_type.id
        if extra_vals:
            vals.update(extra_vals)
        return self.env["account.move"].create(vals)
