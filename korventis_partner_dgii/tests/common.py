"""Transactional fixtures that do not demote or replace an official active padrón."""

import random
import uuid
from unittest.mock import patch

from odoo import fields

from odoo.addons.korventis_partner_dgii.services.schema import (
    REGISTRY_TEST_VERSION_CONTEXT,
)


OFFICIAL_REGISTRY_RECORD_THRESHOLD = 1000


def unique_test_sha256():
    return uuid.uuid4().hex + uuid.uuid4().hex


def unused_test_identification(env, length=9):
    Registry = env["korventis.dgii.rnc"].sudo()
    Partner = env["res.partner"].sudo()
    for _ in range(200):
        value = "%0*d" % (length, random.randint(1, 10 ** length - 1))
        if Registry.search([("rnc_normalizado", "=", value)], limit=1):
            continue
        if Partner.search(
            [("korventis_identification_normalized", "=", value)],
            limit=1,
        ):
            continue
        return value
    raise AssertionError("No se pudo reservar un identificador de prueba libre.")


def create_isolated_registry_version(env, name, record_count=1):
    return env["korventis.dgii.rnc.version"].sudo().create(
        {
            "name": name,
            "state": "staging",
            "source_url": "https://dgii.gov.do/%s" % name,
            "source_filename": name,
            "archive_sha256": unique_test_sha256(),
            "imported_at": fields.Datetime.now(),
            "record_count": record_count,
        }
    )


def isolated_registry_env(env, version):
    return env(
        context=dict(
            env.context,
            **{REGISTRY_TEST_VERSION_CONTEXT: version.id},
        )
    )


def protect_large_registry_versions(env):
    """Keep official high-volume versions from being unlinked in importer tests."""
    Version = env["korventis.dgii.rnc.version"]
    protected_ids = set(
        Version.sudo().search(
            [("record_count", ">=", OFFICIAL_REGISTRY_RECORD_THRESHOLD)]
        ).ids
    )
    original_unlink = type(Version).unlink

    def unlink(self):
        rest = self.filtered(lambda rec: rec.id not in protected_ids)
        if rest:
            return original_unlink(rest)
        return True

    patcher = patch.object(type(Version), "unlink", unlink)
    patcher.start()
    return patcher
