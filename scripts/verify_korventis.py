# Executed by: odoo-bin shell -c <conf> -d <db> --no-http < scripts/verify_korventis.py
# Relies on the Odoo shell `env` global. Never prints credentials.


class VerifyError(Exception):
    pass


def _fail(message):
    raise VerifyError(message)


def _ok(message):
    print("VERIFY OK: %s" % message)


def _module_state(env, name):
    module = env["ir.module.module"].search([("name", "=", name)], limit=1)
    if not module:
        _fail("módulo ausente: %s" % name)
    if module.state != "installed":
        _fail("módulo %s en estado %s" % (name, module.state))
    _ok("%s %s" % (name, module.latest_version or module.installed_version))
    return module


def _param(env, key):
    record = env["ir.config_parameter"].sudo().search([("key", "=", key)], limit=1)
    if not record:
        _fail("falta ir.config_parameter %s" % key)
    return record.value


def main(env):
    fiscal = _module_state(env, "korventis_l10n_do_fiscal")
    partner = _module_state(env, "korventis_partner_dgii")
    _ok(
        "orden de dependencias: %s instalado; %s depende de él"
        % (fiscal.name, partner.name)
    )

    for model_name in (
        "korventis.fiscal.document",
        "korventis.dgii.rnc",
        "korventis.dgii.rnc.version",
        "korventis.dgii.import.run",
        "korventis.partner.lookup.wizard",
    ):
        env[model_name]
        _ok("modelo %s" % model_name)

    env.cr.execute(
        """
        SELECT c.relname
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'r'
           AND n.nspname = current_schema()
           AND c.relname IN (
                'korventis_fiscal_document',
                'korventis_dgii_rnc',
                'korventis_dgii_rnc_version',
                'korventis_dgii_import_run'
           )
        """
    )
    tables = {row[0] for row in env.cr.fetchall()}
    missing = {
        "korventis_fiscal_document",
        "korventis_dgii_rnc",
        "korventis_dgii_rnc_version",
        "korventis_dgii_import_run",
    } - tables
    if missing:
        _fail("tablas ausentes: %s" % ", ".join(sorted(missing)))
    _ok("tablas ORM presentes")

    for key in (
        "korventis_partner_dgii.source_url",
        "korventis_partner_dgii.fallback_url",
        "korventis_partner_dgii.auto_import_enabled",
        "korventis_partner_dgii.minimum_records",
    ):
        _ok("parámetro %s=%s" % (key, _param(env, key) or "(vacío)"))

    auto = _param(env, "korventis_partner_dgii.auto_import_enabled")
    cron = env.ref(
        "korventis_partner_dgii.ir_cron_import_dgii_registry",
        raise_if_not_found=False,
    )
    if not cron:
        _fail("falta ir.cron korventis_partner_dgii.ir_cron_import_dgii_registry")
    cron = cron.with_context(active_test=False)
    extras = (
        env["ir.cron"]
        .sudo()
        .with_context(active_test=False)
        .search(
            [
                ("model_id.model", "=", "korventis.dgii.import.run"),
                ("code", "ilike", "_cron_import_registry"),
            ]
        )
        - cron
    )
    if extras:
        _fail("hay %s cron DGII duplicados" % len(extras))
    if auto != "True" and cron.active:
        _fail("el cron DGII está activo antes de autorizar la importación diaria")
    _ok("cron DGII único; active=%s auto_import_enabled=%s" % (cron.active, auto))

    active_versions = env["korventis.dgii.rnc.version"].search_count(
        [("state", "=", "active")]
    )
    if active_versions > 1:
        _fail("hay %s versiones activas" % active_versions)
    if active_versions:
        _ok("padrón activo")
    else:
        _ok("padrón pendiente de importar")

    groups = [
        "korventis_partner_dgii.group_dgii_user",
        "korventis_partner_dgii.group_dgii_manager",
        "korventis_l10n_do_fiscal.group_fiscal_user",
        "korventis_l10n_do_fiscal.group_fiscal_manager",
    ]
    for xmlid in groups:
        if not env.ref(xmlid, raise_if_not_found=False):
            _fail("falta grupo %s" % xmlid)
    _ok("grupos de seguridad")

    for xmlid in (
        "korventis_partner_dgii.menu_korventis_dgii_root",
        "korventis_l10n_do_fiscal.document_type_e31",
        "korventis_l10n_do_fiscal.document_type_e32",
        "korventis_l10n_do_fiscal.document_type_e34",
    ):
        if not env.ref(xmlid, raise_if_not_found=False):
            _fail("falta xmlid %s" % xmlid)
    _ok("menús y tipos fiscales")
    print("VERIFY SUMMARY: pass")
    return 0


try:
    raise SystemExit(main(env))
except VerifyError as exc:
    print("VERIFY FAIL: %s" % exc)
    raise SystemExit(1)
