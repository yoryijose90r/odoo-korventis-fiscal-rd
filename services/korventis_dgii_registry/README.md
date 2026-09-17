# korventis-dgii-registry

Independent DGII taxpayer registry service. Commit 2 adds a local ZIP importer
with staging, SHA-256 idempotency and atomic activation.

It does not download the official ZIP on boot, does not copy Odoo databases,
and does not write `res.partner`.

```bash
python -m korventis_dgii_registry import --zip FILE.zip --validate-only
python -m korventis_dgii_registry import --zip FILE.zip --activate
python -m korventis_dgii_registry restore-previous
```

See `docs/DGII_REGISTRY_SERVICE.md` for install, import policy, backup and rollback.
