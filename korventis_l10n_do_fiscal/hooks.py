"""Idempotent per-database access for the initial administrator.

Uses XML IDs and the ORM only. Does not assign groups to every internal user.
Does not restart the Odoo process.

``base.user_admin`` cannot be updated from XML on ``-u``: Odoo 18
``models._load_records`` skips writes when ``update and d_noupdate``. The
Administrator XML ID is created by ``base`` with ``noupdate=True``.
``post_init_hook`` runs only on ``new_install`` (``odoo/modules/loading.py``).
Both install and upgrade therefore call ``ensure_initial_admin_access`` from
Python: XML ``<function>``, ``post_init_hook``, and ``post-migrate``.
"""

import logging

from odoo import SUPERUSER_ID, api


_logger = logging.getLogger(__name__)

ADMIN_USER_XMLID = "base.user_admin"
# group_account_user implies group_account_readonly and group_account_invoice.
# group_fiscal_manager implies group_fiscal_user. Do not grant manager/all groups.
ADMIN_GROUP_XMLIDS = (
    "account.group_account_user",
    "korventis_l10n_do_fiscal.group_fiscal_manager",
)


def _ensure_env(env_or_cr, registry=None):
    if registry is None and hasattr(env_or_cr, "cr"):
        return env_or_cr
    return api.Environment(env_or_cr, SUPERUSER_ID, {})


def ensure_initial_admin_access(env):
    """Grant the minimum groups the initial Administrator needs.

    ``(4, id)`` is additive. Groups already present are left untouched, so a
    second run does not rewrite ``res.users`` or duplicate M2M rows. Other
    users are never written. Missing XML IDs are skipped, never hardcoded.
    """
    admin = env.ref(ADMIN_USER_XMLID, raise_if_not_found=False)
    if not admin:
        _logger.warning("Korventis fiscal: %s is missing; skip group grant", ADMIN_USER_XMLID)
        return []
    commands = []
    ensured = []
    for xmlid in ADMIN_GROUP_XMLIDS:
        group = env.ref(xmlid, raise_if_not_found=False)
        if not group:
            _logger.warning("Korventis fiscal: group %s is missing; skip", xmlid)
            continue
        ensured.append(xmlid)
        if group not in admin.groups_id:
            commands.append((4, group.id))
    if commands:
        admin.sudo().write({"groups_id": commands})
    return ensured


def post_init_hook(env_or_cr, registry=None):
    env = _ensure_env(env_or_cr, registry)
    granted = ensure_initial_admin_access(env)
    _logger.info(
        "korventis_l10n_do_fiscal: initial admin groups %s",
        ", ".join(granted) or "unchanged",
    )
