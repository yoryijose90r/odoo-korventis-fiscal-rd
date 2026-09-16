# Actualización de clientes existentes

Destino documentado: `korventis_l10n_do_fiscal` `18.0.1.3.1` y
`korventis_partner_dgii` `18.0.1.1.0`.

Use este procedimiento cuando la base **ya tiene datos** (contactos, facturas,
e-NCF o un padrón DGII). No borra documentos fiscales. No ejecute SQL de QA.

Prohibido sobre `korventis`, `baruchcafe` y producción sin autorización aparte.

## Antes de actualizar

1. Respaldo verificable de PostgreSQL y del filestore. Véase `docs/ROLLBACK.md`.
2. Confirmar que el código nuevo está en el `addons_path`.
3. Anotar Contactos > Padrón DGII > Estado (versión activa, conteos, cron).
4. Anotar un e-NCF ya emitido para compararlo después.

## Comando recomendado

```bash
export ODOO_BIN=/usr/bin/odoo
export ODOO_CONF=/etc/odoo/odoo.conf
export ODOO_DB=nombre_de_la_base_del_cliente
export KORVENTIS_ACTION=upgrade
./scripts/install_korventis.sh
./scripts/verify_korventis.sh
```

Equivalente manual (el orden de `-u` no desinstala; Odoo actualiza cada módulo
instalado):

```bash
<ODOO_BIN> -c <ODOO_CONF> -d <DB> \
  -u korventis_l10n_do_fiscal,korventis_partner_dgii \
  --stop-after-init
```

Si el núcleo fiscal ya está en `18.0.1.3.1` y sólo falta el padrón:

```bash
<ODOO_BIN> -c <ODOO_CONF> -d <DB> \
  -i korventis_partner_dgii --stop-after-init
```

Eso **instala** el padrón sin reinstalación destructiva del núcleo. Las tablas
fiscales existentes no se vacían.

## Qué hace Odoo en un `-u` de `korventis_partner_dgii`

1. `migrations/18.0.1.1.0/pre-migrate.py`: falla si hay más de una versión activa.
2. Actualización ORM de modelos, vistas, ACL y XML con `noupdate`.
3. `migrations/18.0.1.1.0/post-migrate.py`: índices y parámetros ausentes, un
   solo cron, `nextcall` a la próxima 01:00 de Santo Domingo (UTC naive).
4. `post_init_hook` **no** corre otra vez en `-u`.

Las migraciones son idempotentes. Reintentar un `-u` no duplica índices ni cron.

## Qué debe conservarse

- Padrón activo y versión anterior recuperable.
- Historial de `korventis.dgii.import.run`.
- Contactos, `vat`, tipo fiscal del núcleo.
- Facturas, e-NCF y eventos de auditoría.
- Parámetros de URL ya personalizados (`noupdate="1"`).

## Después de actualizar

1. Apps: versiones `18.0.1.3.1` y `18.0.1.1.0`.
2. El padrón activo y sus conteos no cambiaron por el `-u`.
3. Una sola tarea de sincronización. Sigue inactiva salvo que
   `korventis_partner_dgii.auto_import_enabled` sea `True`.
4. El e-NCF histórico anotado no cambió.
5. Pruebas del módulo, en una copia o en QA, no en producción:

```bash
<ODOO_BIN> -c <ODOO_CONF> -d <DB> \
  --test-enable --stop-after-init \
  --test-tags=/korventis_partner_dgii
```

## Núcleo fiscal

La corrección de caché de secuencias de QA (`5570d5a`) es código Python, no un
`UPDATE` para lanzar en todos los clientes.

Siguiente: `docs/DGII_IMPORT.md` si aún no hay padrón activo.
