from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class KorventisFiscalDocumentType(models.Model):
    _name = "korventis.fiscal.document.type"
    _description = "Korventis Fiscal Document Type"
    _order = "code"

    code = fields.Char(required=True, index=True)
    name = fields.Char(required=True, translate=True)
    electronic = fields.Boolean(default=True)
    sequence_length = fields.Integer(default=10, required=True)
    prefix = fields.Char(required=True)
    direction = fields.Selection(
        [
            ("sale", "Sale / outbound"),
            ("purchase", "Purchase / inbound"),
        ],
        required=True,
    )
    partner_assignable = fields.Boolean(
        default=False,
        help="If True, the type may be used as a partner default. This is a default, not an irrevocable rule.",
    )
    active = fields.Boolean(default=True)
    dgii_source = fields.Char(
        readonly=True,
        help="Official DGII source used for this catalog row (Phase 0).",
    )

    _sql_constraints = [
        ("code_unique", "unique(code)", "The fiscal document type code must be unique."),
        (
            "sequence_length_positive",
            "CHECK(sequence_length > 0)",
            "Sequence length must be positive.",
        ),
    ]

    @api.constrains("prefix", "code", "electronic")
    def _check_electronic_prefix(self):
        for rec in self:
            if rec.electronic and rec.prefix and rec.code and rec.prefix != rec.code:
                raise ValidationError(
                    _(
                        "For electronic types the prefix must match the official code (%s).",
                        rec.code,
                    )
                )
