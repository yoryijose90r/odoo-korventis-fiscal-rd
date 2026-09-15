from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.korventis_l10n_do_fiscal.services.internal import INTERNAL_WRITE_TOKEN


class KorventisFiscalEvent(models.Model):
    _name = "korventis.fiscal.event"
    _description = "Korventis Fiscal Event"
    _order = "event_datetime desc, id desc"
    _rec_name = "event_type"

    document_id = fields.Many2one(
        "korventis.fiscal.document",
        required=True,
        index=True,
        ondelete="cascade",
    )
    company_id = fields.Many2one(
        related="document_id.company_id",
        store=True,
        index=True,
    )
    event_type = fields.Selection(
        [
            ("reserved", "Reserved"),
            ("issued", "Issued"),
            ("cancelled", "Cancelled"),
            ("manual_change", "Manual change"),
            ("sequence_change", "Sequence change"),
        ],
        required=True,
        index=True,
    )
    event_datetime = fields.Datetime(
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )
    user_id = fields.Many2one(
        "res.users",
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    old_value = fields.Char(readonly=True)
    new_value = fields.Char(readonly=True)
    notes = fields.Text(readonly=True)

    def write(self, vals):
        raise UserError(_("Fiscal events are append-only and cannot be modified."))

    def unlink(self):
        for rec in self:
            if rec.document_id and rec.document_id.state != "draft":
                raise UserError(
                    _("Fiscal events of reserved, issued or cancelled documents cannot be deleted.")
                )
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        uid = self.env.uid
        for vals in vals_list:
            vals.pop("company_id", None)
            vals["user_id"] = uid
            if self.env.context.get("_korventis_internal_write") is not INTERNAL_WRITE_TOKEN:
                if not self.env.su:
                    raise UserError(_("Fiscal events can only be created by the fiscal service."))
        return super().create(vals_list)
