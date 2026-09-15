from odoo import _, api, fields, models
from odoo.exceptions import UserError


class KorventisFiscalEvent(models.Model):
    _name = "korventis.fiscal.event"
    _description = "Korventis Fiscal Event"
    _order = "event_datetime desc, id desc"
    _rec_name = "event_type"

    document_id = fields.Many2one(
        "korventis.fiscal.document",
        required=True,
        index=True,
        ondelete="restrict",
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
        raise UserError(_("Fiscal events cannot be deleted."))

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(vals_list)
