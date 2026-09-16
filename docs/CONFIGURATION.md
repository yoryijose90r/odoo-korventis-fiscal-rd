# Configuración

Parámetros por **base de datos**. Un `-u` no pisa valores ya guardados
(`noupdate="1"` más `ensure_config_parameters`).

No ponga secretos en estos parámetros: las URLs DGII son públicas.

## `ir.config_parameter` de `korventis_partner_dgii`

| Clave | Predeterminado | Significado |
| --- | --- | --- |
| `korventis_partner_dgii.source_url` | `https://dgii.gov.do/app/WebApps/Consultas/RNC/RNC_CONTRIBUYENTES.zip` | URL oficial principal. Sólo HTTPS de `dgii.gov.do` o `www.dgii.gov.do`. |
| `korventis_partner_dgii.fallback_url` | *(vacío)* | ZIP oficial alternativo. Déjelo vacío salvo verificación expresa. |
| `korventis_partner_dgii.shared_archive_path` | *(vacío)* | Ruta absoluta de un ZIP ya validado en el servidor. Opcional en multibase. |
| `korventis_partner_dgii.minimum_records` | `100000` | Mínimo de filas aceptadas para activar una versión nueva. |
| `korventis_partner_dgii.minimum_volume_ratio` | `0.70` | No activar si el volumen cae por debajo de este ratio frente a la versión activa. |
| `korventis_partner_dgii.maximum_volume_ratio` | `1.30` | No activar si el volumen sube por encima de este ratio. |
| `korventis_partner_dgii.auto_import_enabled` | `False` | El cron no descarga hasta que sea `True`. |
| `korventis_partner_dgii.last_migration` | escrito por hooks | Auditoría de última instalación o `-u`. No es un interruptor. |

## Tarea programada

XMLID: `korventis_partner_dgii.ir_cron_import_dgii_registry`

| Campo | Valor de instalación |
| --- | --- |
| Activa | No |
| Intervalo | 1 día |
| `nextcall` inicial | Un año hacia adelante (el hook lo recalcula a la próxima 01:00 Santo Domingo) |
| Código | `model._cron_import_registry()` |

Horario de negocio: 01:00 `America/Santo_Domingo` (sin horario de verano). Odoo
almacena `ir.cron.nextcall` como datetime naive en UTC, por eso 01:00 AST se
guarda como 05:00.

Activación: `docs/DGII_IMPORT.md`. Los scripts de instalación no la encienden.

## Núcleo fiscal (`res.company`)

| Campo | Predeterminado | Significado |
| --- | --- | --- |
| `korventis_fiscal_enabled` | desactivado | Permite reservar e-NCF al **contabilizar** facturas. No transmite a DGII. No descarga el padrón. |

## Asistente de clientes

No tiene parámetros globales. Reglas fijas:

- Mínimo 3 caracteres.
- Contactos de Odoo primero; el padrón activo después.
- Alta DGII: país RD, idioma español, tipo E31, estado y actividad del padrón.
- Alta manual: tipo fiscal obligatorio y explícito.
- No llama a IAP en este flujo.

## Dónde se edita

- URLs y cron: asistente **Importar ahora** y Ajustes técnicos > Parámetros.
- Compartir ZIP: parámetro `shared_archive_path` (ruta absoluta).
- Fiscal: ficha de la compañía.

No use SQL para cambiar estos valores en un cliente.
