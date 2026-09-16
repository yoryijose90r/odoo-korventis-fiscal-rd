# Actualización de Korventis Partner DGII

Versión de destino documentada: `18.0.1.1.0`.

## Antes de actualizar

1. Respaldo verificable de PostgreSQL y del filestore. Véase
   `docs/ROLLBACK.md`.
2. Confirmar que `korventis_l10n_do_fiscal` permanece instalado.
3. Anotar el estado visible en Contactos > Padrón DGII > Estado.
4. No ejecutar SQL manual de desarrollo o de QA.

## Comando estándar

```bash
<ODOO_BIN> -c <ODOO_CONF> -d <DB> \
  -u korventis_partner_dgii --stop-after-init
```

Odoo aplica, en este orden:

1. `migrations/18.0.1.1.0/pre-migrate.py` (si había una versión anterior).
2. Actualización ORM de modelos, vistas, ACL y XML con `noupdate`.
3. `migrations/18.0.1.1.0/post-migrate.py`.
4. `post_init_hook` no vuelve a ejecutarse en un `-u`; la migración post sí.

La pre-migración valida que no haya más de una versión activa. Si hay
inconsistencia, falla de forma explícita y la transacción de actualización
se revierte.

## Qué debe conservarse

- Padrón activo y versión anterior recuperable.
- Historial de `korventis.dgii.import.run`.
- Contactos, `vat`, tipos fiscales del núcleo.
- Facturas, e-NCF y eventos de auditoría del núcleo fiscal.
- Parámetros de URL ya personalizados (`noupdate="1"`).

## Qué cambia en 18.0.1.1.0

- Índices personalizados se aseguran de forma idempotente.
- Parámetros de configuración ausentes se crean sin pisar valores existentes.
- La tarea diaria se unifica a un solo `ir.cron` por base.
- La tarea queda inactiva salvo que
  `korventis_partner_dgii.auto_import_enabled` sea `True`.
- El `nextcall` se recalcula a la próxima 01:00 de Santo Domingo.

## Reintentos

`ensure_custom_indexes`, `ensure_config_parameters` y `ensure_single_cron`
son seguros ante reintentos. No borran filas del padrón ni documentos
fiscales.

## Después de actualizar

1. Apps: versión `18.0.1.1.0`.
2. Estado del padrón: misma versión activa y mismos conteos.
3. Una sola tarea de sincronización.
4. Una factura histórica y su e-NCF sin cambios.
5. Ejecutar las pruebas del módulo cuando el entorno lo permita:

```bash
<ODOO_BIN> -c <ODOO_CONF> -d <DB> \
  --test-enable --stop-after-init \
  --test-tags=/korventis_partner_dgii
```

## Núcleo fiscal

Esta actualización no modifica `korventis_l10n_do_fiscal`. La corrección de
caché de secuencias de QA (`5570d5a`) es código de aplicación, no un SQL
para lanzar en todos los clientes. No incorporarla como parche indiscriminado.
