def migrate(cr, version):
    from odoo import SUPERUSER_ID, api

    from odoo.addons.korventis_partner_dgii.hooks import upgrade_module

    env = api.Environment(cr, SUPERUSER_ID, {})
    upgrade_module(env, version)
