# Análisis de brecha POS — Korventis Fiscal RD

Fecha: 2026-09-16. Código inspeccionado: `korventis_l10n_do_fiscal` `18.0.1.3.1`,
`korventis_partner_dgii` `18.0.1.1.0`, y el diseño de `docs/ARCHITECTURE_PROPOSAL.md`.

**No existe** el módulo `korventis_l10n_do_pos` en este repositorio. Este
documento no cambia pagos estándar de Odoo ni emite NCF al abrir una orden o
al imprimir una prefactura.

## 1. Flujo de venta de restaurante (objetivo)

1. Abrir mesa / orden `pos.order` en borrador (`pos_restaurant` Community).
2. Cargar productos, notas, divisiones de cuenta.
3. Imprimir **cuenta o prefactura** para el comensal: total, mesa, líneas.
   **Sin** NCF, e-NCF, QR fiscal, TrackID ni código de seguridad.
4. Cobrar con el flujo estándar de pagos POS (efectivo, tarjeta, etc.).
   Korventis no debe reemplazar el registro de pagos.
5. Al **confirmar la factura fiscal** (policy recomendada: `pos.order` pagada
   → `account.move` posted), entonces sí nacer el comprobante E32 o E31.
6. Reimpresión del comprobante reutiliza el mismo `korventis.fiscal.document`.
7. Devolución: nota de crédito `out_refund` con E34 ligada al documento origen.

## 2. Qué ya funciona hoy

### Odoo 18 Community (`point_of_sale` + `pos_restaurant`)

- Mesas, cuenta abierta, impresión de bill no fiscal, split.
- `pos.order` en mesa se sincroniza en **draft** (`sync_from_ui`).
- Pago estándar y, si el cajero marca factura, creación de `account.move`.
- El bill / recibo POS **no** es representación impresa DGII.

Esos addons viven en Odoo, no en este repo. Korventis no los parchea todavía.

### Núcleo `korventis_l10n_do_fiscal`

| Capacidad | Estado |
| --- | --- |
| Tipos E31, E32, E34 (y catálogo e-CF) | Sí |
| e-NCF atómico `SELECT … FOR UPDATE` al **post** de `account.move` | Sí |
| Tipo tomado del partner en factura de cliente | Sí |
| `out_refund` fuerza E34 y exige documento origen | Sí |
| Bloqueo de reset a borrador / borrado tras emitir | Sí |
| Eventos de auditoría append-only | Sí |
| Transmisión e-CF / XML / firma / QR / TrackID | No (fase posterior) |
| Extensión de `pos.order` | No |

La emisión fiscal actual cuelga de `account.move._post()`. Si POS llegara a
contabilizar una factura de cliente con tipo fiscal, el núcleo **ya** asignaría
e-NCF. El hueco es orquestar *cuándo* POS crea y confirma esa factura, y
prohibir números en la prefactura.

### `korventis_partner_dgii`

| Capacidad | Backend / factura | Frontend POS |
| --- | --- | --- |
| Buscar contacto existente | Sí (asistente) | No |
| Buscar padrón activo RNC / razón social | Sí | No |
| Confirmar contribuyente → un partner E31, RD, `es_DO` | Sí | No |
| Alta manual con tipo explícito | Sí | No |
| Botón en `account.move` borrador (`out_invoice` / `out_refund`) | Sí | No aplica |

El cajero de restaurante hoy no tiene ese asistente dentro de la UI POS.

## 3. Cuenta o prefactura sin NCF

**Debe quedar así.** La cuenta de mesa es un documento operativo de Odoo, no un
comprobante fiscal.

Riesgo si se desarrolla mal: enganchar `NcfService` en `sync_from_ui`, en
`print_bill` o al abrir la orden. Eso violaría DGII y este proyecto.

Trabajo futuro en `korventis_l10n_do_pos`:

- Interceptar impresión de cuenta / recibo intermedio y garantizar ausencia de
  campos fiscales.
- Marcar la orden como “cuenta impresa” sin reservar secuencia.

## 4. Emisión sólo al confirmar la factura fiscal

Regla: el número nace en `account.move` posted, igual que en backoffice.

Recomendación de arquitectura (Fase POS):

```
pos.order draft  ──x──> NCF
pos.order paid  --> account.move posted --> korventis.fiscal.document
```

No emitir al:

- abrir mesa
- añadir líneas
- imprimir prefactura
- registrar el pago si la política aún no confirma factura (el pago Odoo puede
  existir sin move fiscal; Korventis no debe alterar ese pago, sólo el momento
  de `action_post` de la factura)

Hay que decidir en implementación POS si **toda** venta de restaurante genera
factura Odoo (recomendado para 607) o sólo cuando el cajero pide comprobante.
Eso es producto, no está codificado.

## 5. Selección de cliente (existente, DGII o manual)

| Canal | Hoy | Falta |
| --- | --- | --- |
| Contactos / factura backoffice | Asistente completo | — |
| POS | Cliente genérico o `res.partner` ya existente vía UI estándar | Wizard DGII, prioridad de contactos, alta E31/E32, ceros a la izquierda |

El módulo POS deberá reutilizar `korventis_create_from_dgii` y
`korventis_create_manual_customer` (backend), no reimplementar reglas, y
exponerlas en el selector de cliente del TPV.

Consumidor final habitual: partner E32 (o el partner genérico de la compañía
si se define esa política). Crédito fiscal: partner E31 desde padrón o
contacto existente.

## 6. E32 vs E31

Hoy el tipo viaja del partner a la factura, con snapshot: cambiar el partner
después no recalcula un move ya tipado salvo escritura de `partner_id` en
borrador. E34 no es perfil de cliente.

Falta en POS:

- Mostrar y, si acaso, confirmar el tipo **antes** de postear.
- Impedir que una venta a consumidor final salga como E31 por un partner mal
  clasificado, y viceversa.
- No asignar tipo al imprimir la cuenta.

## 7. Numeración concurrente, idempotencia y auditoría

Ya en el núcleo, para `account.move`:

- Lock de secuencia por fila.
- Documento 1:1 con la factura.
- Eventos no editables.

Falta para POS:

- Clave de idempotencia `pos.order:{id}` (o unique `company_id, pos_order_id`)
  para que dos cajeros o un doble clic no pidan dos e-NCF.
- Reintento: si el move ya tiene `korventis_fiscal_document_id`, no llamar otra
  vez a `allocate`.
- Tests HttpCase / hilos: NCF en draft = 0; un número por orden pagada.

No usar `ir.sequence` de POS para e-NCF.

## 8. Impresión del comprobante

| Documento | Contenido fiscal | Estado |
| --- | --- | --- |
| Bill / prefactura restaurante | Ninguno | Odoo estándar; proteger en el módulo POS |
| Recibo de pago POS | No es e-CF | No usar como comprobante DGII |
| Factura Odoo / RI | e-NCF, RNC, totales | Núcleo emite el número; **falta** plantilla RI, QR, código seguridad (módulo e-CF) |
| Reimpresión | Mismo `fiscal.document` | Diseñado; no hay reporte POS Korventis |

Hasta `korventis_l10n_do_ecf`, la “impresión fiscal” será como máximo una
factura Odoo con el e-NCF del núcleo, no un XML firmado.

## 9. Devoluciones y E34

Backoffice: `out_refund` → E34, `original_document_id` desde
`reversed_entry_id`. Sin origen seguro no se emite.

POS Community puede devolver líneas / reembolsar. **No** está conectado a E34.

Falta:

- Mapear devolución POS a `out_refund` posted.
- Exigir el `korventis.fiscal.document` original.
- No emitir E34 al anular una orden draft ni al reimprimir la prefactura.
- No reutilizar el e-NCF de la venta.

## 10. Matriz: funciona vs requiere desarrollo

| Requisito | ¿Listo? | Dónde |
| --- | --- | --- |
| Venta de mesa sin NCF | Sí, por omisión de Odoo | `pos_restaurant` |
| Prefactura sin NCF | Sí, por omisión; hay que **prohibirlo** al integrar | futuro `korventis_l10n_do_pos` |
| Pagos estándar sin reescribirse | Sí | no tocar |
| e-NCF al post de factura | Sí | `korventis_l10n_do_fiscal` |
| Cliente DGII / manual | Sí en backoffice | falta UI POS |
| E32 consumidor / E31 crédito | Sí en factura | falta criterio y UI POS |
| Concurrencia de secuencia | Sí en move | falta idempotencia `pos.order` |
| Impresión RI / QR | No | `korventis_l10n_do_ecf` + POS |
| Devolución E34 desde POS | No | `korventis_l10n_do_pos` |
| 606/607 desde POS | No | reportes posteriores |

## 11. Preparación de pruebas POS (sin desarrollar el módulo)

En QA, con `korventis_fiscal_test`, se puede **observar** el hueco:

1. Instalar `point_of_sale` y `pos_restaurant` en esa base (Community).
2. Abrir una sesión, mesa, imprimir cuenta: no debe aparecer e-NCF.
3. Pagar sin factura: no debe nacer `korventis.fiscal.document`.
4. Pagar pidiendo factura Odoo a un partner E31/E32: **si** el move se poste a
   con `korventis_fiscal_enabled`, el núcleo emitirá e-NCF. Documentar el
   resultado real; no es el flujo restaurante acabado.
5. No activar cron DGII para esta prueba.

Eso valida el límite actual. El desarrollo POS queda para una fase autorizada,
en un módulo nuevo, sin merge a `main`.
