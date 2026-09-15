from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class KorventisFiscalDocument(models.Model):
    _name = "korventis.fiscal.document"
    _description = "Korventis Fiscal Document"
    _order = "id desc"
    _check_company_auto = True
    _rec_name = "fiscal_number"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        index=True,
        default=lambda self: self.env.company,
    )
    move_id = fields.Many2one(
        "account.move",
        index=True,
        ondelete="restrict",
        check_company=True,
    )
    partner_id = fields.Many2one("res.partner", required=True, check_company=True)
    document_type_id = fields.Many2one(
        "korventis.fiscal.document.type",
        required=True,
        ondelete="restrict",
    )
    sequence_id = fields.Many2one(
        "korventis.fiscal.sequence",
        ondelete="restrict",
        check_company=True,
    )
    fiscal_number = fields.Char(index=True, copy=False)
    sequence_number = fields.Integer(copy=False)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("reserved", "Reserved"),
            ("issued", "Issued"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        index=True,
        copy=False,
    )
    issue_datetime = fields.Datetime(copy=False)
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    amount_untaxed = fields.Monetary()
    amount_tax = fields.Monetary()
    amount_total = fields.Monetary()
    original_document_id = fields.Many2one(
        "korventis.fiscal.document",
        ondelete="restrict",
        check_company=True,
    )
    event_ids = fields.One2many("korventis.fiscal.event", "document_id")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "fiscal_number_company_unique",
            "unique(company_id, fiscal_number)",
            "The fiscal number must be unique per company.",
        ),
        (
            "move_unique",
            "unique(move_id)",
            "An account move can have at most one fiscal document.",
        ),
    ]

    def _korventis_log_event(self, event_type, old_value=False, new_value=False, notes=False):
        Event = self.env["korventis.fiscal.event"].sudo()
        for rec in self:
            Event.create(
                {
                    "document_id": rec.id,
                    "event_type": event_type,
                    "user_id": self.env.uid,
                    "old_value": old_value or False,
                    "new_value": new_value or False,
                    "notes": notes or False,
                }
            )

    def write(self, vals):
        if self.env.context.get("korventis_skip_immutability"):
            return super().write(vals)
        protected_issued = {
            "fiscal_number",
            "sequence_number",
            "document_type_id",
            "sequence_id",
            "company_id",
            "move_id",
            "partner_id",
        }
        for rec in self:
            if rec.state in ("reserved", "issued") and protected_issued.intersection(vals):
                raise UserError(
                    _("Issued or reserved fiscal documents cannot change number, type or partner.")
                )
            if rec.state == "cancelled" and set(vals) - {"active"}:
                raise UserError(_("Cancelled fiscal documents are immutable."))
        if "document_type_id" in vals:
            for rec in self:
                if rec.state == "draft" and rec.document_type_id.id != vals.get("document_type_id"):
                    rec._korventis_log_event(
                        "manual_change",
                        old_value=rec.document_type_id.code,
                        new_value=str(vals.get("document_type_id")),
                    )
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(
                    _("Fiscal documents that are not draft cannot be deleted. Cancel them instead.")
                )
        return super().unlink()

    def action_cancel(self):
        from odoo.addons.korventis_l10n_do_fiscal.services.ncf_service import NcfService

        service = NcfService(self.env)
        for rec in self:
            service.cancel_document(rec)
        return True

    @api.constrains("original_document_id")
    def _check_original_document(self):
        for rec in self:
            if rec.original_document_id and rec.original_document_id == rec:
                raise ValidationError(_("A fiscal document cannot reference itself."))
            if (
                rec.original_document_id
                and rec.original_document_id.company_id != rec.company_id
            ):
                raise ValidationError(
                    _("The original fiscal document must belong to the same company.")
                )
