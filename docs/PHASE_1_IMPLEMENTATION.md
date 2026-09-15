# FASE 1 — Implementación Fiscal Core

Fecha: 2026-09-15  
Rama: `feature/fiscal-core`  
Módulo: `korventis_l10n_do_fiscal`  
Despliegue QA: **no realizado** (pendiente de autorización).

## Modelos

| Modelo | Tipo |
| --- | --- |
| `korventis.fiscal.document.type` | Nuevo catálogo |
| `korventis.fiscal.sequence` | Nuevo rango por compañía/tipo |
| `korventis.fiscal.document` | Nuevo documento fiscal |
| `korventis.fiscal.event` | Nuevo, append-only |
| `res.company` | Extensión |
| `res.partner` | Extensión |
| `account.move` | Extensión |

No se creó `korventis.fiscal.company.config` (la bandera vive en `res.company`). No se extendió `account.journal` ni `pos.order` en esta fase.

## Campos agregados

### res.company

- `korventis_fiscal_enabled`

### res.partner

- `korventis_fiscal_document_type_id` (dominio `partner_assignable=True`)

Reutilizado: `vat`, `country_id`. No existe `l10n_latam_identification_type_id` en `l10n_do` 18.0 Community.

### account.move

- `korventis_fiscal_document_type_id` (snapshot)
- `korventis_fiscal_document_id`
- `korventis_fiscal_number` (related)
- `korventis_fiscal_type_locked` (compute)

Inicialización: `create` + `onchange` desde el partner **solo si el snapshot está vacío**. Un cambio posterior del partner no altera facturas existentes.

### korventis.fiscal.document.type

`code`, `name`, `electronic`, `sequence_length`, `prefix`, `direction`, `partner_assignable`, `active`, `dgii_source`

### korventis.fiscal.sequence

`company_id`, `document_type_id`, `prefix`, `range_start`, `range_end`, `next_number`, `valid_from`, `valid_until`, `active`

### korventis.fiscal.document

`company_id`, `move_id`, `partner_id`, `document_type_id`, `sequence_id`, `fiscal_number`, `sequence_number`, `state`, `issue_datetime`, `currency_id`, `amount_*`, `original_document_id`, `active`

Estados internos: `draft`, `reserved`, `issued`, `cancelled`. No hay `sent`/`accepted`/`TrackID`.

### korventis.fiscal.event

`document_id`, `event_type`, `event_datetime`, `user_id`, `old_value`, `new_value`, `notes`

## Constraints

- Tipo: `unique(code)`; prefix electrónico = code.
- Secuencia SQL: `range_start <= range_end`; `range_start >= 1`; `next_number` entre `range_start` y `range_end + 1`.
- Secuencia Python: fechas válidas; rangos activos no solapados (números + vigencia) por compañía/tipo; prefix = tipo.
- Documento: `unique(company_id, fiscal_number)`; `unique(move_id)`; no auto-referencia de `original_document_id`.
- Partner: solo tipos assignable; VAT DO 9 u 11 dígitos numéricos.

## Locking

`NcfService.allocate()`:

1. `SELECT … FROM korventis_fiscal_sequence WHERE id = %s FOR UPDATE`
2. Validar activo, vigencia, rango
3. Formatear e-NCF (`E31` + 10 dígitos)
4. `UPDATE … SET next_number = next_number + 1`

No se usa `search()` + `write()` sin lock. La UNIQUE de `fiscal_number` es red de seguridad.

## Emisión en account.move

Si `korventis_fiscal_enabled` y hay tipo fiscal, `_post()` reserva y emite. Reset a borrador bloqueado tras `reserved`/`issued`. Cancelar el asiento cancela el documento **sin reutilizar el número**.

## Multiempresa

`company_id` en secuencia/documento; `check_company` en relaciones; record rules `company_id in company_ids`.

## Seguridad

- Korventis Fiscal User: lectura operativa; crea/escribe documentos; no borra emitidos; no configura rangos.
- Korventis Fiscal Manager: configura tipos y rangos.
- Eventos: solo lectura en ACL; `write`/`unlink` Python denegados.

## Tests

Ver `tests/test_fiscal_core.py` y `tests/test_concurrency.py` (`test_concurrent_sequence_allocation`).

El test de concurrencia hace `commit()` para dos cursors PostgreSQL. Solo en BD de prueba.

## Decisiones [REQUIERE VALIDACIÓN DGII]

1. Checksum RNC/Cédula no implementado (solo longitud 9/11, alerta DGII CA3904).
2. Catálogo tradicional B01/B02/… no cargado; solo e-CF E31–E47 del Formato V1.0.
3. `partner_assignable=False` para E41, E43, E47 (el contribuyente es emisor de esos comprobantes, no perfil de cliente).
4. E33/E34 no son default de partner (notas, no perfil).
5. Consumidor Final = partner genérico con E32, sin VAT obligatorio.
6. Mapeo exacto E33/E34 ↔ `out_invoice` vs `out_refund` no se fuerza más allá de `direction`.

## Fuera de alcance (cumplido)

Sin POS, XML, PFX, JWT, DGII HTTP, QR, 606–608, Alanube, merge, VPS.
