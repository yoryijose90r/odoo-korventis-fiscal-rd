# Reversión

## Respaldo previo (obligatorio antes de instalar o actualizar)

PostgreSQL:

```bash
pg_dump --format=custom --file=<RESPALDO>.dump <DB>
```

Filestore de Odoo: copiar el directorio configurado en `data_dir` de esa
instancia. El ZIP DGII importado vive como `ir.attachment`.

Verificar el respaldo restaurando en una base temporal, no en producción.

```bash
createdb <DB_VERIFY>
pg_restore --dbname=<DB_VERIFY> <RESPALDO>.dump
```

## Reversión de datos del padrón (sin desinstalar)

Si la última importación es incorrecta y existe versión `Anterior recuperable`:

1. Contactos > Padrón DGII > Versiones.
2. Abrir la versión anterior.
3. Restaurar esta versión.

No modifica contactos, facturas ni e-NCF ya emitidos.

## Reversión de una actualización de módulo

1. Desactivar la tarea `Korventis: actualizar padrón DGII`.
2. Restaurar PostgreSQL y filestore desde el respaldo previo al `-u`.
3. Dejar el checkout de código en el tag anterior.
4. Arrancar Odoo contra la base restaurada.

No “deshacer” un `-u` a medias con SQL.

## Retirar el módulo de un entorno no productivo

1. Desactivar la tarea diaria.
2. Desinstalar `korventis_partner_dgii` desde Apps.
3. Confirmar que `korventis_l10n_do_fiscal` sigue instalado.
4. Los `res.partner` creados permanecen. Se retiran metadatos DGII del módulo.
   `vat` y `korventis_fiscal_document_type_id` pertenecen al núcleo fiscal.

## Fallo durante `-u`

Odoo ejecuta la actualización en una transacción. Si `pre-migrate` o
`post-migrate` lanzan un error, la estructura no debe quedar a medias.
Repita el `-u` después de corregir la inconsistencia (por ejemplo más de una
versión activa). No complete la corrección con scripts que asuman IDs de otro
cliente.
