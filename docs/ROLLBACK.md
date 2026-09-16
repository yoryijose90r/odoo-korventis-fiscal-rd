# Reversión

Objetivo: recuperar un fallo de instalación, actualización o importación **sin
perder facturas ni e-NCF**.

No borre bases, no ejecute `docker volume rm` y no use estos pasos en
producción sin autorización.

## Respaldo previo (obligatorio)

PostgreSQL:

```bash
pg_dump --format=custom --file=<RESPALDO>.dump <DB>
```

Filestore: copiar el directorio `data_dir` de esa instancia. El ZIP DGII vive
como `ir.attachment`.

Comprobar el respaldo en una base **temporal nueva**, nunca sobreescribiendo
`korventis`, `baruchcafe` ni producción:

```bash
createdb <DB_VERIFY>
pg_restore --dbname=<DB_VERIFY> <RESPALDO>.dump
```

## Padrón incorrecto (sin desinstalar)

Si existe versión `Anterior recuperable`:

1. Desactivar la tarea `Korventis: actualizar padrón DGII`.
2. Contactos > Padrón DGII > Versiones > Restaurar esta versión.

Eso cambia qué versión está `active`. No reescribe `res.partner`, no toca
`account.move` y no altera `korventis.fiscal.document`.

## Fallo durante `-i` o `-u`

Odoo corre la operación en una transacción. Si `pre-migrate` o `post-migrate`
fallan, la estructura no debe quedar a medias. Corrija la causa (por ejemplo
más de una versión activa) y repita el comando. No complete el esquema con SQL
ad hoc.

Si la transacción no revirtió (interrupción violenta del proceso):

1. Restaurar PostgreSQL y filestore desde el respaldo previo.
2. Dejar el código en la revisión anterior conocida.
3. Arrancar Odoo.
4. Verificar un e-NCF histórico y el estado del padrón.

## Reversión de una actualización de módulo

1. Desactivar el cron DGII.
2. Restaurar PostgreSQL y filestore del respaldo **previo al `-u`**.
3. Checkout del tag o commit anterior.
4. Arrancar contra la base restaurada.

No “deshaga” un `-u` editando filas a mano.

## Retirar el módulo (solo no productivo)

1. Desactivar la tarea diaria.
2. Desinstalar `korventis_partner_dgii` desde Aplicaciones.
3. Confirmar que `korventis_l10n_do_fiscal` sigue instalado.
4. Los contactos creados permanecen. Se retiran metadatos DGII del módulo.
   `vat` y `korventis_fiscal_document_type_id` pertenecen al núcleo fiscal.

No desinstale el núcleo fiscal si ya hay e-NCF emitidos.

## Lo que nunca debe hacerse

- `dropdb` sobre un cliente.
- Borrar el filestore para “liberar el ZIP”.
- `UPDATE` de `next_number` copiado de QA.
- Restaurar un dump de un cliente sobre otro.
