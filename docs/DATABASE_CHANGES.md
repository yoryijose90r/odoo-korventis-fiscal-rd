# Cambios de base de datos — korventis_partner_dgii 18.0.1.1.0

Todas las estructuras las crea el ORM o helpers idempotentes del módulo.
No hay SQL de instalación para ejecutar a mano.

## Tablas ORM

| Tabla | Modelo |
|---|---|
| `korventis_dgii_rnc` | `korventis.dgii.rnc` |
| `korventis_dgii_rnc_version` | `korventis.dgii.rnc.version` |
| `korventis_dgii_import_run` | `korventis.dgii.import.run` |

Los transientes (`korventis.partner.lookup.wizard`,
`korventis.dgii.import.wizard`, `korventis.dgii.registry.status`) no persisten
el padrón.

Columnas, `Many2one` e índices simples los crea `_auto_init` de Odoo.

## Restricciones SQL del ORM

- `unique(version_padron_id, rnc)` en `korventis_dgii_rnc`.
- `unique(archive_sha256)` en `korventis_dgii_rnc_version`.

## Índices personalizados

Creados sólo si no existen (`services/schema.py`):

- `korventis_dgii_rnc_version_name_prefix_idx`
- `korventis_dgii_rnc_name_fts_idx` (GIN)
- `korventis_dgii_rnc_version_one_active_idx` (único parcial, `state = 'active'`)

`init()` de los modelos y la migración `18.0.1.1.0` reutilizan la misma
función. Un arranque normal de Odoo sin `-i`/`-u` no debe recrearlos.

## Parámetros `ir.config_parameter`

Claves (noupdate; no se pisan en `-u` si ya existen):

- `korventis_partner_dgii.source_url`
- `korventis_partner_dgii.fallback_url`
- `korventis_partner_dgii.shared_archive_path`
- `korventis_partner_dgii.minimum_records`
- `korventis_partner_dgii.minimum_volume_ratio`
- `korventis_partner_dgii.maximum_volume_ratio`
- `korventis_partner_dgii.auto_import_enabled`
- `korventis_partner_dgii.last_migration` (escrito por hooks)

## Migraciones versionadas

`migrations/18.0.1.1.0/pre-migrate.py`:

- Detecta más de una versión activa.
- No modifica tablas fiscales.
- Falla explícitamente si hay inconsistencia.

`migrations/18.0.1.1.0/post-migrate.py`:

- Crea índices y parámetros ausentes.
- Deduplica el cron.
- Recalcula `nextcall` en `America/Santo_Domingo`.
- No borra padrón, contactos, facturas ni e-NCF.

Estas migraciones **no** se ejecutan en una instalación nueva `18.0.1.1.0`;
el ORM + XML + `post_init_hook` cubren ese caso.

## Núcleo fiscal

No hay cambios de esquema en `korventis_l10n_do_fiscal` en esta fase.

La corrección histórica de métricas de secuencia en QA (commit `5570d5a`,
`invalidate_recordset` / `modified` sobre `next_number`) es código Python del
núcleo. **No** convertirla en un `UPDATE` SQL genérico para todos los
clientes: dependería de datos reales y de IDs distintos en cada base. Si un
cliente concreto necesitara un ajuste de datos, sería una migración puntual
evaluada sobre su respaldo, no un script indiscriminado.

## Grupos y ACL

- Grupos: `group_dgii_user`, `group_dgii_manager`.
- ACL en `security/ir.model.access.csv`.
- No hay `ir.rule` por compañía: el padrón es uno por base de datos, coherente
  con una sola autoridad fiscal. En un VPS multibase el aislamiento es la
  propia base PostgreSQL.
