def migrate(cr, version):
    """Repair initial-admin groups on -u. Idempotent. No SQL on res.groups."""
    from odoo import SUPERUSER_ID, api

    from odoo.addons.korventis_l10n_do_fiscal.hooks import (
        ensure_initial_admin_access,
    )

    env = api.Environment(cr, SUPERUSER_ID, {})
    ensure_initial_admin_access(env)
