from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    KORVENTIS_LOOKUP_MOVE_TYPES = ("out_invoice", "out_refund")

    def action_korventis_lookup_partner(self):
        self.ensure_one()
        self.env["res.partner"]._korventis_check_lookup_access()
        if (
            self.state != "draft"
            or self.korventis_fiscal_document_id
            or self.move_type not in self.KORVENTIS_LOOKUP_MOVE_TYPES
        ):
            raise UserError(
                _("La búsqueda de clientes sólo está disponible en facturas de cliente en borrador.")
            )
        wizard = self.env["korventis.partner.lookup.wizard"].create({})
        return {
            "type": "ir.actions.act_window",
            "name": _("Buscar o registrar cliente"),
            "res_model": wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
            "context": {
                "active_model": self._name,
                "active_id": self.id,
            },
        }
