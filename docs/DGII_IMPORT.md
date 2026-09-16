# Importación del padrón DGII

La instalación del módulo **no** descarga el ZIP. La primera carga es una
operación de mantenimiento, reintentable, por base.

## Primera importación (asistente)

1. Espacio en disco: ZIP, adjunto, versión activa y una anterior.
2. Idioma español activo si va a crear contactos después.
3. Usuario con grupo `Administrador del padrón DGII`.
4. Contactos > Padrón DGII > Importar ahora.
5. URL principal (oficial, ya rellenada). URL alternativa **vacía** salvo que
   haya verificado otra URL HTTPS de `dgii.gov.do`.
6. Deje **desmarcada** “Activar actualización diaria” en la primera carga.
7. Ejecutar. Esperar el registro en Ejecuciones.

Criterio de éxito (referencia QA, no un identificador portable):

- Estado `Correcta`.
- Filas procesadas del orden de cientos de miles.
- Una sola versión `Activa`.
- SHA-256 del ZIP coincidente con el archivo descargado.
- Búsqueda por RNC y por razón social en el asistente de clientes.

Si la descarga falla, el módulo sigue instalado y el padrón anterior (si existía)
permanece. Reintente. Un padrón incompleto no se activa.

## Actualización diaria (sólo con autorización)

Requisitos:

1. Primera importación `Correcta` (o `Sin cambios` en una corrida posterior).
2. Una versión activa.
3. Autorización explícita del operador.

Desde la interfaz: vuelva a Importar ahora y marque
“Activar actualización diaria a la 1:00 a. m. (Santo Domingo)” **después** de
una corrida correcta, o use:

```bash
export ODOO_BIN=/usr/bin/odoo
export ODOO_CONF=/etc/odoo/odoo.conf
export ODOO_DB=nombre_de_la_base
KORVENTIS_ENABLE_CRON=yes ./scripts/enable_dgii_cron.sh
```

Sin `KORVENTIS_ENABLE_CRON=yes` el script se niega. Sin padrón activo o sin
importación correcta también se niega.

Efecto:

- `korventis_partner_dgii.auto_import_enabled=True`
- `ir.cron` activo
- `nextcall` = próxima 01:00 `America/Santo_Domingo`, almacenada en UTC naive
  (01:00 AST = 05:00 UTC)

El método del cron no descarga si el parámetro no es `True`.

En QA el cron puede permanecer desactivado a propósito.

## Recuperación de una importación mala

Si existe versión `Anterior recuperable`:

1. Contactos > Padrón DGII > Versiones.
2. Restaurar esta versión.

No modifica contactos, facturas ni e-NCF. Detalle en `docs/ROLLBACK.md`.

## Fallos frecuentes

| Síntoma | Qué hacer |
| --- | --- |
| Timeout o HTTP 5xx de DGII | Reintentar más tarde; el módulo no se desinstala |
| Volumen por debajo de `minimum_records` | No se activa; revisar el ZIP |
| Otra importación en curso | Estado `Omitida por concurrencia`; esperar |
| Host distinto de `dgii.gov.do` | El importador rechaza la URL |
| `shared_archive_path` relativa | Debe ser absoluta y terminar en `.zip` |

No pegue SQL para “arreglar” el padrón. Use el asistente o restaure la versión
anterior.
