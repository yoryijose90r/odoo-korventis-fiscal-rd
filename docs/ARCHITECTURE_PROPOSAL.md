# Propuesta de arquitectura — Korventis Fiscal RD

Fecha: 2026-09-14. **No se crean módulos en esta fase.**

## 1. Evaluación de la arquitectura propuesta

La separación en cuatro addons es **correcta para Odoo 18 Community**:

| Módulo | Dependencias | Responsabilidad |
| --- | --- | --- |
| `korventis_l10n_do_fiscal` | `account`, `l10n_do` | Tipos, rangos NCF/e-NCF, partner, `account.move`, config, auditoría, seguridad QA |
| `korventis_l10n_do_pos` | `korventis_l10n_do_fiscal`, `point_of_sale`, `pos_restaurant` (opcional/auto) | Pago POS → documento fiscal; nunca NCF en cuenta abierta |
| `korventis_l10n_do_ecf` | `korventis_l10n_do_fiscal` | XML, XSD, firma, QR, providers DGII/Mock/(Alanube opcional) |
| `korventis_l10n_do_reports` | `korventis_l10n_do_fiscal` | 606/607/608 (y 609 más adelante) |

### Mejoras recomendadas (sin crear código)

1. **Capa `services/` dentro de cada módulo**, no un quinto addon al inicio. Los modelos orquestan.
2. **`FiscalProvider` vive en `korventis_l10n_do_ecf`**. El core fiscal no habla HTTP con DGII.
3. **Dependencia `l10n_do` obligatoria** en el core: reutilizar impuestos y chart.
4. **No depender de OCA EDI** en v1: AGPL-3 choca con `LICENSE_PENDING.md` hasta decisión legal.
5. **No depender de Alanube/Alegra/Infile**. Provider opcional detrás de interfaz.
6. **Hook POS débil:** `pos.order` guarda `fiscal_document_id` e idempotency key; la emisión la hace un servicio llamado al validar pago / al facturar, no al `sync_from_ui` de mesa draft.
7. **Posible split futuro** `korventis_l10n_do_dgii_psfe` si Korventis se certifica como PSFE; no hace falta ahora.
8. **Data master de tipos de comprobante** como XML/CSV versionado con cita DGII, no hardcode opaco.

Diagrama conceptual:

```
pos.order (draft mesa) ──x──> NCF
pos.order (paid) --> account.move --> korventis.fiscal.document
                                          |
                    core: reserva número  |  ecf: XML/firma/envío
                                          v
                               FiscalProvider (Mock | DGII | Alanube*)
```

## 2. Extender vs crear modelos

### Extender (no duplicar)

| Modelo | Qué añadir | Qué NO duplicar |
| --- | --- | --- |
| `res.company` | Flags fiscales, ambiente DGII, RNC emisor si no basta `company.vat`, bloqueo producción, provider seleccionado | Nombre, dirección, moneda (ya Odoo) |
| `res.partner` | Tipo ID (RNC/Cédula/Pasaporte), `format_valid`, `checksum_valid`, `dgii_verified`, fecha verificación | `vat`, nombre, calle |
| `account.move` | `fiscal_document_id`, tipo comprobante, inmutabilidad post-emisión | Totales, impuestos, partner |
| `account.journal` | Tipo fiscal por defecto (venta consumo vs crédito) | Secuencia de asiento Odoo (`name`) ≠ NCF |
| `pos.order` | `fiscal_document_id`, `fiscal_idempotency_key`, flag “cuenta impresa” | Líneas, pagos, mesa |

### Modelos nuevos necesarios

Nombres Odoo (`_name` con punto):

| `_name` propuesto | Tabla | Por qué no es un modelo Odoo existente |
| --- | --- | --- |
| `korventis.fiscal.document.type` | Tipos B01/E31… | Catálogo DGII, no `ir.sequence` |
| `korventis.fiscal.sequence.range` | Rango autorizado por compañía/tipo | `ir.sequence` no tiene vigencia DGII ni FOR UPDATE de negocio |
| `korventis.fiscal.document` | Comprobante fiscal 1:1 (o 1:N controlado) con move | Estados internos ≠ `account.move.state` ≠ estados DGII |
| `korventis.fiscal.document.event` | Append-only | Chatter no es inmutable ni suficiente |
| `korventis.fiscal.transmission` | Intentos HTTP (Fase 4) | Observabilidad sin JWT |

`korventis.fiscal.company.config` **no es necesario** si la config cabe en `res.company` + `ir.config_parameter` (parámetros globales QA: `DGII_ALLOW_PRODUCTION=False`). Preferir `res.company` para multiempresa.

`korventis.fiscal.sequence` separado de `sequence.range` solo si hay cabecera (autorización) vs líneas (tramos). Puede unificarse en `sequence.range` en Fase 1.

ACL: `ir.model.access` + record rules `company_id`. Grupos:

- `korventis_l10n_do_fiscal.group_user`
- `korventis_l10n_do_fiscal.group_supervisor`
- `korventis_l10n_do_fiscal.group_manager`

## 3. Flujo restaurante

### Lo que Odoo 18 Community ya hace

- `pos_restaurant`: mesas, impresión temprana de cuenta, split.
- Documentación Odoo: la cuenta impresa **no es factura final**.
- Factura Odoo: checkbox Invoice en pago, requiere cliente; crea `account.move`.
- Recibo POS ≠ representación impresa DGII.
- `pos.order` en mesa abierta se sincroniza en **draft** (`sync_from_ui`). Ese draft **no** debe reservar NCF.

### Lo que hay que desarrollar

1. Interceptar impresión de cuenta / recibo intermedio: **sin** NCF, e-NCF, TrackID, QR fiscal, código seguridad.
2. Al **pago/validación** (y solo entonces): elegir tipo (E32 consumo vs E31 crédito, etc.).
3. Crear/confirmar `account.move` si la política Korventis es “siempre asiento” (recomendado para 607) o emitir fiscal ligado al `pos.order` y asentar después. **Recomendación Fase 2:** `pos.order` → `account.move` posted → `fiscal.document`.
4. Idempotencia: unique `(company_id, pos_order_id)` o key explícita.
5. Reimpresión: mismo `fiscal.document`.
6. Doble clic / dos cajeros: lock de orden + unique constraint.
7. Kitchen Display / IoT: Enterprise o terceros; fuera del core fiscal.

## 4. Seguridad

| Activo | Diseño |
| --- | --- |
| PFX/P12 | Fuera de Git y de `static/`. Path en Docker secret / volumen 0600. Nunca adjunto en chatter. |
| Password certificado | `ir.config_parameter` cifrado no es suficiente (se lee en BD). Preferir env `KORVENTIS_CERT_PASSWORD` o Docker secret inyectado al worker. |
| JWT DGII | Caché en memoria / Redis con TTL &lt; `expira`. No columna permanente. No logs. |
| XML firmado | `ir.attachment` con `access_token` restringido; hash SHA-256 en `fiscal.document`. |
| QA | `DGII_ENVIRONMENT=testecf`, `DGII_TRANSMISSION_ENABLED=False`, `DGII_ALLOW_PRODUCTION=False`. Guardia de código: si env ≠ production y URL contiene `/ecf/` de producción (path `/ecf/` no `testecf`/`certecf`), `UserError`. |
| Permisos | Usuario emite; supervisor reintenta; admin configura. Nadie escribe eventos. Nadie DELETE físico post-emisión. |
| Multiempresa | Record rules; certificado y rangos por `company_id`. |
| Logs | `correlation_id`; http_status; track_id; nunca PFX, password, JWT, XML completo si contiene PII innecesaria en INFO. |

## 5. Concurrencia e idempotencia (diseño, sin código)

Objetivo: cajero A y B no obtienen el mismo NCF.

1. Transacción PostgreSQL de Odoo (`cr.execute` en el mismo cursor del `create`).
2. `SELECT ... FROM korventis_fiscal_sequence_range WHERE id=%s FOR UPDATE`.
3. Validar compañía, tipo, fechas, `next <= max`, estado activo.
4. `next_number += 1` en el mismo UPDATE.
5. INSERT documento con número formateado.
6. Constraints:
   - `UNIQUE(company_id, l10n_latam_document_number)` o `UNIQUE(company_id, document_type_id, number)`.
   - `UNIQUE(company_id, idempotency_key)` donde key = `pos.order:{id}` o `account.move:{id}`.
7. No usar solo `ir.sequence.next_by_code` (race en alta concurrencia POS).
8. Test: 20 threads / `HttpCase` concurrente esperando un solo número por iteración y unique violation controlada en retry de idempotencia.
9. Timeout DGII: estado `pending_send`/`sent` + consultar TrackId; **no** incrementar secuencia de nuevo.

## 6. Estrategia de testing

| Capa | Dónde | Nunca |
| --- | --- | --- |
| Unit | `tests/test_ncf_sequence.py`, partner validation | Red |
| Concurrencia | `tests/test_ncf_concurrency.py` | — |
| account.move | `tests/test_account_move_fiscal.py` | — |
| POS | `tests/test_pos_fiscal.py` (HttpCase) | NCF en draft |
| XML/XSD | `tests/test_ecf_xml.py` contra fixtures oficiales | Inventar XML |
| Firma | `tests/test_ecf_signature.py` cert de prueba generado en test | Cert real cliente |
| MockDGII | `tests/test_dgii_mock.py` | testecf real en CI |
| QA DGII | Manual/certificación TesteCF | Producción |
| Reports | `tests/test_reports.py` vs TXT de ejemplo DGII | — |

CI: `DGII_TRANSMISSION_ENABLED=False`. MockProvider por defecto.

## 7. Providers

| Provider | Fase | Obligatorio |
| --- | --- | --- |
| MockProvider | 1–3 tests | Sí en tests |
| DGIIProvider | 4 | Sí para producto Korventis |
| AlanubeProvider | Solo con autorización | No |
| Infile (Odoo Enterprise) | Nunca copiar | No |

## 8. Archivos previstos (Fase 1 en adelante, no crear ahora)

```
korventis_l10n_do_fiscal/
  __manifest__.py
  models/res_company.py
  models/res_partner.py
  models/account_move.py
  models/account_journal.py
  models/fiscal_document_type.py
  models/fiscal_sequence_range.py
  models/fiscal_document.py
  models/fiscal_document_event.py
  services/ncf_service.py
  security/ir.model.access.csv
  security/fiscal_record_rules.xml
  data/fiscal_document_type_data.xml
  tests/test_ncf_sequence.py
  tests/test_ncf_concurrency.py
  tests/test_partner_validation.py
  tests/test_account_move_fiscal.py
```

POS, ECF y reports se enumeran en sus fases.
