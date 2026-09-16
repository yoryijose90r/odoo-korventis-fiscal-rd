"""Shared helpers so tests stay portable on databases that already have a padrón."""


def park_active_registry_versions(env):
    """Demote the official active version for the current test transaction."""
    env["korventis.dgii.rnc.version"].sudo().search(
        [("state", "=", "active")]
    ).write({"state": "previous"})


def official_registry_present(env, minimum_records=1000):
    return bool(
        env["korventis.dgii.rnc.version"].sudo().search(
            [("record_count", ">=", minimum_records)],
            limit=1,
        )
    )
