from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.korventis_l10n_do_fiscal.services.internal import INTERNAL_WRITE_TOKEN

ALLOWED_STATE_TRANSITIONS = {
    "draft": ("reserved",),
    "reserved": ("issued",),
    "issued": ("cancelled",),
    "cancelled": (),
}

PROTECTED_FIELDS = {
    "company_id",
    "move_id",
    "partner_id",
    "partner_name",
    "partner_vat",
    "partner_identification_type",
    "partner_street",
    "partner_street2",
    "partner_city",
    "partner_state",
    "partner_zip",
    "partner_country",
    "document_type_id",
    "sequence_id",
    "fiscal_number",
    "sequence_number",
    "issue_datetime",
    "currency_id",
    "amount_untaxed",
    "amount_tax",
    "amount_total",
    "original_document_id",
    "state",
    "active",
}


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
    partner_id = fields.Many2one(
        "res.partner",
        required=True,
        check_company=True,
        help="Operational link only. Historical identity is stored in partner_* snapshot fields.",
    )
    partner_name = fields.Char(copy=False)
    partner_vat = fields.Char(copy=False)
    partner_identification_type = fields.Char(copy=False)
    partner_street = fields.Char(copy=False)
    partner_street2 = fields.Char(copy=False)
    partner_city = fields.Char(copy=False)
    partner_state = fields.Char(copy=False)
    partner_zip = fields.Char(copy=False)
    partner_country = fields.Char(copy=False)
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
            "The fiscal number must be unique per company. "
            "PostgreSQL allows several NULL fiscal_number values (drafts without a number).",
        ),
        (
            "move_unique",
            "unique(move_id)",
            "An account move can have at most one fiscal document. "
            "PostgreSQL allows several NULL move_id values.",
        ),
    ]

    @api.model
    def _partner_snapshot_vals(self, partner):
        partner = partner.commercial_partner_id or partner
        vat = (partner.vat or "").replace("-", "").replace(" ", "")
        ident = False
        if len(vat) == 9:
            ident = "RNC"
        elif len(vat) == 11:
            ident = "Cedula"
        country = partner.country_id or partner.company_id.country_id
        state = partner.state_id
        return {
            "partner_name": partner.name or False,
            "partner_vat": vat or False,
            "partner_identification_type": ident,
            "partner_street": partner.street or False,
            "partner_street2": partner.street2 or False,
            "partner_city": partner.city or False,
            "partner_state": state.name if state else False,
            "partner_zip": partner.zip or False,
            "partner_country": country.name if country else False,
        }

    def _is_internal_write(self):
        return self.env.context.get("_korventis_internal_write") is INTERNAL_WRITE_TOKEN

    def _korventis_log_event(self, event_type, old_value=False, new_value=False, notes=False):
        Event = (
            self.env["korventis.fiscal.event"]
            .sudo()
            .with_context(_korventis_internal_write=INTERNAL_WRITE_TOKEN)
        )
        uid = self.env.uid
        for rec in self:
            Event.create(
                {
                    "document_id": rec.id,
                    "event_type": event_type,
                    "user_id": uid,
                    "old_value": old_value or False,
                    "new_value": new_value or False,
                    "notes": notes or False,
                }
            )

    @api.model_create_multi
    def create(self, vals_list):
        internal = self._is_internal_write()
        for vals in vals_list:
            if not internal:
                vals["state"] = "draft"
                vals.pop("fiscal_number", None)
                vals.pop("sequence_number", None)
        return super().create(vals_list)

    def write(self, vals):
        if not vals:
            return True
        internal = self._is_internal_write()
        if not internal:
            for rec in self:
                if rec.state == "draft":
                    forbidden = set(vals) & {"fiscal_number", "sequence_number", "state"}
                    if "state" in vals:
                        raise UserError(
                            _("Fiscal document state cannot be changed with write(). Use the fiscal service.")
                        )
                    if forbidden - {"state"}:
                        raise UserError(_("Draft documents cannot receive a fiscal number via write()."))
                else:
                    blocked = set(vals) & PROTECTED_FIELDS
                    if blocked:
                        raise UserError(
                            _(
                                "Fiscal document %(number)s in state %(state)s cannot be modified.",
                                number=rec.fiscal_number or rec.id,
                                state=rec.state,
                            )
                        )
        if internal and "state" in vals:
            for rec in self:
                target = vals["state"]
                if target != rec.state and target not in ALLOWED_STATE_TRANSITIONS.get(rec.state, ()):
                    raise UserError(
                        _(
                            "Illegal fiscal state transition %(old)s -> %(new)s.",
                            old=rec.state,
                            new=target,
                        )
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
