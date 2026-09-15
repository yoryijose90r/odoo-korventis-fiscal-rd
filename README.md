# Korventis Fiscal RD

Localización fiscal de República Dominicana para Odoo 18 Community.

Proyecto:

Korventis ERP / Korventis Fiscal RD

Objetivo:

Desarrollar módulos propios para implementar funcionalidades fiscales de República Dominicana sobre Odoo 18 Community.

Arquitectura prevista:

* korventis_l10n_do_fiscal
* korventis_l10n_do_pos
* korventis_l10n_do_ecf
* korventis_l10n_do_reports

Estado:

En desarrollo (FASE 1.1 hardening en `feature/fiscal-core`).

Entorno inicial:

QA / Testing.

No desplegar automáticamente en producción.

Política de tests: las bases `korventis` y `baruchcafe` no son desechables. La suite estándar no hace `commit()` persistente. El tag `korventis_pg_lock` exige una BD temporal (concepto `korventis_fiscal_test`, no creada aquí). Ver `docs/PHASE_1_IMPLEMENTATION.md`.
