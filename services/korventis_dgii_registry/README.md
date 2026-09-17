# korventis-dgii-registry

Independent DGII taxpayer registry service. Commit 1 is the skeleton: versioned
PostgreSQL schema, env config, health HTTP, SHARED/LOCAL Compose.

It does not download the official ZIP, does not copy Odoo databases, and does
not write `res.partner`.

See `docs/DGII_REGISTRY_SERVICE.md` for install, upgrade and disposable teardown.
