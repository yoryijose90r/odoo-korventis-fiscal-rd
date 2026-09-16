# Korventis Fiscal RD

Localización fiscal de República Dominicana para Odoo 18 Community.

Arquitectura prevista:

* `korventis_l10n_do_fiscal` — núcleo (tipos, e-NCF, auditoría). Versión `18.0.1.3.1`.
* `korventis_partner_dgii` — padrón local y asistente de clientes. Versión `18.0.1.1.0`.
* `korventis_l10n_do_pos` — no existe aún; véase `docs/POS_GAP_ANALYSIS.md`.
* `korventis_l10n_do_ecf` / `korventis_l10n_do_reports` — no iniciados.

Estado:

Rama de desarrollo `feature/partner-dgii-local`. El núcleo fiscal de Fase 1.3
está integrado; el padrón DGII es instalable y no descarga en `-i`. Las pruebas
POS de restaurante aún no tienen módulo propio.

Entorno:

QA / Testing. Base desechable: `korventis_fiscal_test`. No modificar `korventis`
ni `baruchcafe`. No desplegar en producción.

Documentación:

* `docs/INSTALL.md` — instalación desde cero
* `docs/UPGRADE.md` — clientes existentes
* `docs/MULTIDB.md` — varias bases
* `docs/DGII_IMPORT.md` — primera carga y cron
* `docs/CONFIGURATION.md` — parámetros
* `docs/ROLLBACK.md` — recuperación
* `docs/QA_CHECKLIST.md` — aceptación
* `docs/POS_GAP_ANALYSIS.md` — brecha POS

Instalador: `scripts/install_korventis.sh`. Verificador: `scripts/verify_korventis.sh`.
