from odoo import api, models

from odoo.addons.korventis_l10n_do_fiscal.hooks import ensure_initial_admin_access


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _korventis_ensure_initial_admin_access(self):
        """XML data and tests call this; the grant logic lives in hooks."""
        ensure_initial_admin_access(self.env)
        return True
