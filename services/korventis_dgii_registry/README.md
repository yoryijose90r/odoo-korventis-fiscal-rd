# korventis-dgii-registry

Independent DGII taxpayer registry service. Commit 2.1 hardens the local ZIP
importer: shared import/restore lock with timeout, SHA-256 state matrix,
staging row-count integrity, bounded decompressed reads, and `--dry-run`.

`--validate-only` (and the default without flags) still persists a staging
version. `--dry-run` always revalidates ZIP/CSV (even if the SHA-256 already
exists) without persistent writes. `previous` SHA-256 is not reactivated by
`--activate`; use `restore-previous`.

It does not download the official ZIP on boot, does not copy Odoo databases,
and does not write `res.partner`.

```bash
python -m korventis_dgii_registry import --zip FILE.zip --validate-only
python -m korventis_dgii_registry import --zip FILE.zip --dry-run
python -m korventis_dgii_registry import --zip FILE.zip --activate
python -m korventis_dgii_registry restore-previous
```

See `docs/DGII_REGISTRY_SERVICE.md` for install, import policy, backup and rollback.
