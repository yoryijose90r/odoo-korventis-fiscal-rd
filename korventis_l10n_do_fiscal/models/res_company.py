from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    korventis_fiscal_enabled = fields.Boolean(
        string="Enable Korventis Fiscal Core",
        help="When enabled, customer/vendor bills can reserve and issue Dominican fiscal numbers. "
        "Does not transmit to DGII.",
    )
