def migrate(cr, version):
    from odoo.addons.korventis_partner_dgii.hooks import (
        validate_upgrade_preconditions,
    )

    validate_upgrade_preconditions(cr)
