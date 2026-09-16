import logging
from datetime import datetime, timezone

from odoo import SUPERUSER_ID, api

from odoo.addons.korventis_partner_dgii.services.schedule import (
    next_santo_domingo_import,
)
from odoo.addons.korventis_partner_dgii.services.schema import (
    CONFIG_DEFAULTS,
    count_active_versions,
    ensure_custom_indexes,
)


_logger = logging.getLogger(__name__)

CRON_XMLID = "korventis_partner_dgii.ir_cron_import_dgii_registry"
LAST_MIGRATION_KEY = "korventis_partner_dgii.last_migration"


def _ensure_env(env_or_cr, registry=None):
    if registry is None and hasattr(env_or_cr, "cr"):
        return env_or_cr
    return api.Environment(env_or_cr, SUPERUSER_ID, {})


def post_init_hook(env_or_cr, registry=None):
    """Finish a standard -i without contacting DGII."""
    env = _ensure_env(env_or_cr, registry)
    operations = configure_install(env)
    _record_operations(env, "18.0.1.1.0-install", operations)
    _logger.info("korventis_partner_dgii installed: %s", ", ".join(operations))


def configure_install(env):
    operations = []
    operations.extend(ensure_config_parameters(env))
    operations.extend(ensure_schema(env))
    operations.extend(ensure_single_cron(env, activate=False))
    return operations


def upgrade_module(env, from_version):
    validate_upgrade_preconditions(env.cr)
    operations = []
    operations.extend(ensure_config_parameters(env))
    operations.extend(ensure_schema(env))
    auto_enabled = (
        env["ir.config_parameter"].sudo().get_param(
            "korventis_partner_dgii.auto_import_enabled",
            "False",
        )
        == "True"
    )
    operations.extend(ensure_single_cron(env, activate=auto_enabled))
    _record_operations(
        env,
        "18.0.1.1.0-upgrade-from-%s" % (from_version or "unknown"),
        operations,
    )
    return operations


def validate_upgrade_preconditions(cr):
    active = count_active_versions(cr)
    if active > 1:
        raise RuntimeError(
            "Inconsistencia: hay %s versiones activas del padrón DGII. "
            "Corrija los datos antes de actualizar korventis_partner_dgii."
            % active
        )
    return active


def ensure_config_parameters(env):
    parameters = env["ir.config_parameter"].sudo()
    created = []
    for key, value in CONFIG_DEFAULTS.items():
        if parameters.search([("key", "=", key)], limit=1):
            continue
        parameters.set_param(key, value)
        created.append("config:%s" % key)
    return created


def ensure_schema(env):
    created = ensure_custom_indexes(env.cr)
    return ["index:%s" % name for name in created]


def ensure_single_cron(env, activate=False):
    operations = []
    Cron = env["ir.cron"].sudo().with_context(active_test=False)
    xml_cron = env.ref(CRON_XMLID, raise_if_not_found=False)
    crons = Cron.search(
        [
            ("model_id.model", "=", "korventis.dgii.import.run"),
            ("code", "ilike", "_cron_import_registry"),
        ]
    )
    keep = xml_cron or crons[:1]
    extras = crons - keep
    if extras:
        extras.unlink()
        operations.append("cron:removed-duplicates:%s" % len(extras))
    if keep:
        keep.write(
            {
                "active": bool(activate),
                "nextcall": next_santo_domingo_import(),
                "interval_number": 1,
                "interval_type": "days",
            }
        )
        operations.append("cron:%s" % ("enabled" if activate else "disabled"))
    return operations


def _record_operations(env, label, operations):
    payload = "%s %s %s" % (
        datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        label,
        ",".join(operations) or "noop",
    )
    env["ir.config_parameter"].sudo().set_param(LAST_MIGRATION_KEY, payload)
