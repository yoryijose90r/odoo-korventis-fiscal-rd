import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# DGII help community (CA3904): RNC 9 digits, Cédula 11 digits.
# Checksum algorithm is NOT implemented: [REQUIERE VALIDACIÓN DGII]
_DO_ID_DIGITS = re.compile(r"^\d+$")


class ResPartner(models.Model):
    _inherit = "res.partner"

    korventis_fiscal_document_type_id = fields.Many2one(
        "korventis.fiscal.document.type",
        string="Tipo de comprobante fiscal predeterminado",
        domain="[('partner_assignable', '=', True), ('active', '=', True)]",
        help="Default only. Each invoice stores its own fiscal type snapshot.",
        ondelete="restrict",
    )

    def _korventis_is_dominican(self):
        self.ensure_one()
        country = self.country_id or self.company_id.country_id
        return bool(country and country.code == "DO")

    @api.constrains("korventis_fiscal_document_type_id")
    def _check_korventis_partner_type_assignable(self):
        for partner in self:
            dtype = partner.korventis_fiscal_document_type_id
            if dtype and not dtype.partner_assignable:
                raise ValidationError(
                    _(
                        "Fiscal type %(type)s cannot be used as a partner default.",
                        type=dtype.code,
                    )
                )

    @api.constrains("vat", "country_id")
    def _check_korventis_do_identification_length(self):
        """Structural length only. No checksum. [REQUIERE VALIDACIÓN DGII]"""
        for partner in self:
            if not partner.vat or not partner._korventis_is_dominican():
                continue
            vat = partner.vat.replace("-", "").replace(" ", "")
            if not _DO_ID_DIGITS.match(vat):
                raise ValidationError(
                    _(
                        "Dominican RNC/Cédula on partner %(partner)s must be numeric (found %(vat)s).",
                        partner=partner.display_name,
                        vat=partner.vat,
                    )
                )
            if len(vat) not in (9, 11):
                raise ValidationError(
                    _(
                        "Dominican identification must have 9 digits (RNC) or 11 digits (Cédula). "
                        "Checksum is not validated. [REQUIERE VALIDACIÓN DGII]"
                    )
                )
