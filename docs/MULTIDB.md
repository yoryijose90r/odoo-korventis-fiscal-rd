# Varias bases en el mismo servidor

Cada base PostgreSQL de Odoo es un cliente distinto. Instalar o importar en una
**no** debe tocar las demás.

## Aislamiento

| Recurso | Alcance |
| --- | --- |
| Tablas `korventis_*` | Una copia por base |
| `ir.config_parameter` DGII | Una copia por base |
| `ir.cron` del padrón | Una tarea por base |
| Contactos y facturas | Por base |
| Filestore / adjunto del ZIP | Por instancia y base |
| Advisory lock de importación | Por base PostgreSQL |

No existe un padrón compartido entre clientes. No hay límite por cantidad de
empresas (`res.company`) ni comprobación de licencia.

## VPS dedicado (una base)

Una base, un filestore, un servicio. Use `docs/INSTALL.md` o `docs/UPGRADE.md`
con `ODOO_DB` igual a esa única base (nunca `korventis` ni `baruchcafe` desde
estos scripts).

## VPS compartido (multibase)

Ejemplo de intención, no de producción:

```bash
export ODOO_BIN=/usr/bin/odoo
export ODOO_CONF=/etc/odoo/odoo.conf

export ODOO_DB=cliente_a
KORVENTIS_ACTION=install ./scripts/install_korventis.sh
./scripts/verify_korventis.sh

export ODOO_DB=cliente_b
KORVENTIS_ACTION=install ./scripts/install_korventis.sh
./scripts/verify_korventis.sh
```

Cada comando `-d` apunta a una sola base. Si `cliente_a` falla, `cliente_b` no
queda a medias por ese fallo.

## ZIP oficial compartido (opcional)

Por defecto cada base descarga su propia copia. Si varias bases del mismo
servidor deben evitar descargas repetidas:

1. Deje un ZIP oficial ya validado en una ruta absoluta de sólo lectura.
2. En **cada** base configure `korventis_partner_dgii.shared_archive_path`.

Esa ruta es del sistema de archivos, no una tabla compartida. Cada cliente
sigue importando a sus propias filas.

## Tarea diaria en multibase

Odoo ejecuta el cron de **la base en la que está definido**. En un worker
multibase, cada base tiene su propio `ir.cron`. Active el cron sólo después de
una importación correcta de **esa** base. Véase `docs/DGII_IMPORT.md`.

El horario 01:00 `America/Santo_Domingo` se calcula en código y se guarda como
fecha naive UTC de Odoo. No depende de `TZ` del sistema operativo.

## Lo que estos scripts no hacen

- No recorren todas las bases solas.
- No usan `--db-filter` para instalar en masa.
- No borran ni renombran bases.
- Rechazan `korventis` y `baruchcafe`.
