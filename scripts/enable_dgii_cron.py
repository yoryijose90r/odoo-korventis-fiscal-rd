# Executed by: odoo-bin shell -c <conf> -d <db> --no-http < scripts/enable_dgii_cron.py
# Activates the daily DGII cron only when an active registry and a successful
# import already exist. Never prints credentials.

from odoo.addons.korventis_partner_dgii.hooks import ensure_single_cron
from odoo.addons.korventis_partner_dgii.services.schedule import (
    next_santo_domingo_import,
)


def _fail(message):
    raise SystemExit("ENABLE CRON FAIL: %s" % message)


active = env["korventis.dgii.rnc.version"].search_count([("state", "=", "active")])
if active != 1:
    _fail("se requiere exactamente una versión activa; hay %s" % active)

success = env["korventis.dgii.import.run"].search_count(
    [("state", "in", ("success", "unchanged"))]
)
if not success:
    _fail("no hay una importación correcta previa")

env["ir.config_parameter"].sudo().set_param(
    "korventis_partner_dgii.auto_import_enabled",
    "True",
)
ensure_single_cron(env, activate=True)
cron = env.ref("korventis_partner_dgii.ir_cron_import_dgii_registry").with_context(
    active_test=False
)
print(
    "ENABLE CRON OK: active=%s nextcall=%s expected_utc_hour_rule=01:00_Santo_Domingo next=%s"
    % (cron.active, cron.nextcall, next_santo_domingo_import())
)
raise SystemExit(0)
