from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.korventis_l10n_do_fiscal.services.ncf_service import NcfService


class AccountMove(models.Model):
    _inherit = "account.move"

    korventis_fiscal_document_type_id = fields.Many2one(
        "korventis.fiscal.document.type",
        string="Fiscal document type",
        copy=False,
        help="Snapshot for this invoice. Not recalculated from the partner after it is set.",
        ondelete="restrict",
    )
    korventis_fiscal_document_id = fields.Many2one(
        "korventis.fiscal.document",
        string="Fiscal document",
        copy=False,
        readonly=True,
        check_company=True,
    )
    korventis_fiscal_number = fields.Char(
        related="korventis_fiscal_document_id.fiscal_number",
        string="e-NCF / NCF",
        store=False,
    )
    korventis_fiscal_type_locked = fields.Boolean(
        compute="_compute_korventis_fiscal_type_locked",
    )

    @api.depends("korventis_fiscal_document_id", "korventis_fiscal_document_id.state")
    def _compute_korventis_fiscal_type_locked(self):
        for move in self:
            doc = move.korventis_fiscal_document_id
            move.korventis_fiscal_type_locked = bool(
                doc and doc.state in ("reserved", "issued", "cancelled")
            )

    def _korventis_e34(self):
        return self.env.ref("korventis_l10n_do_fiscal.document_type_e34")

    @api.onchange("partner_id")
    def _onchange_partner_korventis_fiscal_type(self):
        for move in self:
            if move.korventis_fiscal_type_locked:
                continue
            if move.move_type == "out_refund":
                move.korventis_fiscal_document_type_id = self._korventis_e34()
                continue
            if move.korventis_fiscal_document_type_id:
                continue
            partner = move.partner_id.commercial_partner_id
            if partner.korventis_fiscal_document_type_id:
                move.korventis_fiscal_document_type_id = (
                    partner.korventis_fiscal_document_type_id
                )

    @api.model_create_multi
    def create(self, vals_list):
        Partner = self.env["res.partner"]
        e34 = self._korventis_e34()
        for vals in vals_list:
            move_type = vals.get("move_type")
            if move_type == "out_refund":
                vals["korventis_fiscal_document_type_id"] = e34.id
                continue
            if not vals.get("korventis_fiscal_document_type_id") and vals.get("partner_id"):
                partner = Partner.browse(vals["partner_id"]).commercial_partner_id
                if partner.korventis_fiscal_document_type_id:
                    vals["korventis_fiscal_document_type_id"] = (
                        partner.korventis_fiscal_document_type_id.id
                    )
        return super().create(vals_list)

    def write(self, vals):
        if "partner_id" in vals:
            for move in self:
                if move.korventis_fiscal_type_locked and vals["partner_id"] != move.partner_id.id:
                    raise UserError(
                        _("The partner cannot be changed after fiscal emission.")
                    )
        if "korventis_fiscal_document_type_id" in vals:
            for move in self:
                if move.korventis_fiscal_type_locked:
                    raise UserError(
                        _("The fiscal document type cannot be changed after fiscal emission.")
                    )
        if (
            len(self) == 1
            and "partner_id" in vals
            and "korventis_fiscal_document_type_id" not in vals
            and not self.korventis_fiscal_type_locked
            and self.state == "draft"
        ):
            if self.move_type == "out_refund":
                if not self.korventis_fiscal_document_type_id:
                    vals = dict(vals, korventis_fiscal_document_type_id=self._korventis_e34().id)
            elif not self.korventis_fiscal_document_type_id:
                partner = self.env["res.partner"].browse(vals["partner_id"]).commercial_partner_id
                if partner.korventis_fiscal_document_type_id:
                    vals = dict(
                        vals,
                        korventis_fiscal_document_type_id=partner.korventis_fiscal_document_type_id.id,
                    )
        return super().write(vals)

    def _korventis_should_issue(self):
        self.ensure_one()
        if not self.company_id.korventis_fiscal_enabled:
            return False
        if self.move_type not in (
            "out_invoice",
            "out_refund",
            "in_invoice",
            "in_refund",
            "out_receipt",
            "in_receipt",
        ):
            return False
        return bool(self.korventis_fiscal_document_type_id)

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        service = NcfService(self.env)
        for move in posted:
            if move._korventis_should_issue() and not move.korventis_fiscal_document_id:
                service.create_and_issue_for_move(move)
        return posted

    def button_draft(self):
        for move in self:
            doc = move.korventis_fiscal_document_id
            if doc and doc.state in ("reserved", "issued", "cancelled"):
                raise UserError(
                    _(
                        "Invoice %(move)s has fiscal document %(number)s and cannot be reset to draft. "
                        "Use a credit/debit note according to DGII rules.",
                        move=move.name,
                        number=doc.fiscal_number,
                    )
                )
        return super().button_draft()

    def button_cancel(self):
        res = super().button_cancel()
        service = NcfService(self.env)
        for move in self:
            if move.korventis_fiscal_document_id and move.korventis_fiscal_document_id.state == "issued":
                service.cancel_document(
                    move.korventis_fiscal_document_id,
                    notes="Cancelled with account.move",
                )
        return res

    def unlink(self):
        for move in self:
            doc = move.korventis_fiscal_document_id
            if doc and doc.state != "draft":
                raise UserError(
                    _("Cannot delete an invoice with an issued or reserved fiscal document.")
                )
        return super().unlink()
