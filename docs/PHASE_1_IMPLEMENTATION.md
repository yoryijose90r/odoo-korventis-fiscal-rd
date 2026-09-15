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

`company_id`, `move_id`, `partner_id`, snapshot `partner_*`, `document_type_id`, `sequence_id`, `fiscal_number`, `sequence_number`, `state`, `issue_datetime`, `currency_id`, `amount_*`, `original_document_id`, `active`

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

- Korventis Fiscal User: lectura operativa; **no** escribe documentos emitidos ni rangos.
- Korventis Fiscal Manager: configura tipos y rangos; **no** reescribe comprobantes emitidos (`perm_write=0` en documentos).
- `account.group_account_invoice`: lectura de tipos/secuencias/documentos/eventos. La creación fiscal ocurre en `NcfService` (sudo acotado).
- Eventos: ACL sin write/create/unlink; `write` Python denegado; `unlink` solo si el documento padre está en `draft`.

## Tests

Ver `tests/test_fiscal_core.py` (suite segura, `TransactionCase` rollback) y `tests/test_concurrency.py`.

- **Seguro en QA** (`korventis` / `baruchcafe`): todo lo etiquetado `post_install` **sin** `-standard`. Incluye `TestSequenceAllocationSafe`.
- **Solo BD desechable**: `TestConcurrentSequenceAllocationIsolated` (`-standard`, `korventis_pg_lock`). Hace `commit()`. Nunca contra `korventis` ni `baruchcafe`.

## Decisiones [REQUIERE VALIDACIÓN DGII]

1. Checksum RNC/Cédula no implementado (solo longitud 9/11, alerta DGII CA3904).
2. Catálogo tradicional B01/B02/… no cargado; solo e-CF E31–E47 del Formato V1.0.
3. `partner_assignable=False` para E41, E43, E47 (el contribuyente es emisor de esos comprobantes, no perfil de cliente).
4. E33/E34 no son default de partner (notas, no perfil).
5. Consumidor Final = partner genérico con E32, sin VAT obligatorio.
6. `out_refund` usa E34. E33 permanece en catálogo **sin** flujo automático de nota de débito.
7. Si una NC no tiene `reversed_entry_id` con documento fiscal, se bloquea la emisión (`[REQUIERE VALIDACIÓN DGII]`).

## Fuera de alcance (cumplido)

Sin POS, XML e-CF, XSD, PFX, JWT, Semilla, TrackID, DGII REST, QR, 606–608, Alanube, Alegra, contingencia, merge, VPS.

---

# FASE 1.1 HARDENING

Fecha: 2026-09-15

Commit esperado: `fix: harden Dominican fiscal core`

Rama: `feature/fiscal-core` (sin merge a `test`/`main`).

## Snapshot histórico del receptor

`partner_id` es vínculo operativo. Tras `reserve_for_move`, los datos usados se copian a:

`partner_name`, `partner_vat`, `partner_identification_type`, `partner_street`, `partner_street2`, `partner_city`, `partner_state`, `partner_zip`, `partner_country`.

No existe `l10n_latam_identification_type_id` en `l10n_do` 18.0 Community. `partner_identification_type` se deriva de la longitud del VAT (9 = RNC, 11 = Cédula). Dirección/país reutilizan `res.partner` estándar.

Cambio posterior de `res.partner` **no** altera el documento emitido.

## State machine

Transiciones permitidas (solo vía `NcfService` + token interno):

- `draft` → `reserved`
- `reserved` → `issued`
- `issued` → `cancelled`

Prohibidas: `issued` → `draft`, `cancelled` → `issued`/`reserved`, `reserved` → `draft`.

`document.write({'state': ...})` está bloqueado para callers normales. Un número reservado no se “devuelve”; cancelación fiscal solo después de `issued`.

## Inmutabilidad

No se usa `context['korventis_skip_immutability']` (el context RPC es controlado por el cliente).

Las escrituras privilegiadas requieren `context['_korventis_internal_write'] is INTERNAL_WRITE_TOKEN`, donde el token es `object()` de módulo: JSON/RPC no puede forjar identidad `is`.

Campos protegidos en `reserved` / `issued` / `cancelled`: compañía, move, partner, snapshot, tipo, secuencia, número, importes, moneda, `original_document_id`, `state`, `active`.

## Snapshot de importes

Al pasar a `issued` se congelan `currency_id`, `amount_untaxed`, `amount_tax`, `amount_total` desde el `account.move`. Un `write` normal posterior no puede cambiarlos.

## Notas de crédito E34

`out_refund` fuerza tipo E34 en `create`/`onchange`. No hereda E31/E32 del partner. `original_document_id` se toma de `reversed_entry_id.korventis_fiscal_document_id`. Sin origen seguro: no se emite. E33 no tiene flujo automático. Sin XML DGII.

## account.move write

Partner default = DEFAULT. Tipo en factura = snapshot de operación. Si draft, no bloqueada, tipo vacío y cambia `partner_id`, se carga el default del nuevo partner. Un tipo ya elegido no se pisa. Tras reserved/issued no se cambia partner ni tipo.

## Multiempresa / allocate

`allocate(sequence, company=...)` exige `sequence.company_id == company` en ORM y en SQL (`SELECT/UPDATE … AND company_id = %s FOR UPDATE`).

## next_number (monotonicidad)

| Secuencia | Regla |
| --- | --- |
| Nueva, sin documentos reserved/issued/cancelled | `next_number` editable dentro del rango |
| Utilizada | no rebobinar (`nuevo < actual` denegado); no cambiar bounds/compañía/tipo/prefix |
| Agotada | `next_number == range_end + 1`; allocate falla; no rebobinar |

Corrección administrativa de un contador (rebobinar) **no está implementada**. Operación excepcional futura: procedimiento controlado, no un boolean de context.

UNIQUE(`company_id`, `fiscal_number`) es red de seguridad, no el único control del contador.

## Rangos solapados

UX: constraint Python `_check_incompatible_ranges`.

Concurrencia: `pg_advisory_xact_lock(hashtext('korventis.fiscal.sequence.{company}.{type}'))` en create/write. Función built-in de PostgreSQL; **no** se instala extensión extra. El lock es por transacción y por par compañía/tipo, no un lock de tabla completa.

Limitación residual: un `INSERT` SQL crudo fuera de Odoo no toma el advisory lock. UNIQUE de números fiscales no cubre solape de rangos.

## Permisos y publicación

Separación: **uso** de secuencia (lectura + allocate interno) vs **administración** (manager write en rangos).

`_post()` llama `NcfService.create_and_issue_for_move`: valida compañía, factura, tipo, dirección, secuencia; `sudo` solo para crear el documento/evento y enlazar `korventis_fiscal_document_id`. Un contable con `account.group_account_invoice` puede publicar sin Fiscal Manager.

Superuser no es el flujo de negocio.

## Eventos

Append-only. `company_id` related desde el documento (se ignora un `company_id` enviado por cliente). `user_id` = `env.uid` real (sudo no cambia uid). `write` prohibido. `unlink` permitido solo si el documento está en `draft` (cascade/uninstall/tests). Documentos issued conservan auditoría.

## UNIQUE y NULL en PostgreSQL

`UNIQUE(company_id, fiscal_number)`: varios `fiscal_number` NULL son legales (drafts sin número). Un valor no nulo no se duplica en la misma compañía.

`UNIQUE(move_id)`: varios `move_id` NULL son legales. Un move tiene como máximo un documento fiscal.

## Concurrencia / política QA

Las bases `korventis` y `baruchcafe` **no** son desechables. Ningún test de la suite estándar hace `commit()` persistente.

`TransactionCase` no prueba locking real entre dos sesiones sin commit. Por eso:

1. Test unitario seguro: varios `allocate()` en el mismo cursor (rollback).
2. Test de integración `korventis_pg_lock` (`-standard`): dos threads / dos cursors. Solo en una BD temporal futura, p. ej. concepto `korventis_fiscal_test`. **No creada en esta fase. No hay conexión VPS.**

## XML

xpath de `account.move`: `//sheet//field[@name='partner_id'][@widget='res_partner_many2one']` sobre `account.view_move_form`.

---

# FASE 1.1.1 — FIXTURE DE TESTS (QA runtime)

Fecha: 2026-09-15

Runtime QA (`korventis_fiscal_test`, commit `fe34926`): el módulo instaló bien; `TestFiscalCore` y `TestSequenceAllocationSafe` fallaron en `setUpClass` con `AccessError` al crear `korventis.fiscal.sequence`.

Causa: `AccountTestInvoicingCommon` deja `cls.env` en un usuario de facturación, no Fiscal Manager. Los ACL que exigen Manager para crear rangos son correctos; el fixture no debía crear rangos con ese usuario.

Corrección: secuencias (y otros datos de administración fiscal) se crean con `sudo()` **solo** en el fixture/tests de constraints. `cls.env` no se convierte en sudo. Los tests de permisos usan `with_user` (Fiscal User, Fiscal Manager, accountant). `korventis_pg_lock` sigue `-standard`. ACL/record rules sin cambios. Versión `18.0.1.1.1`.

---

# FASE 1.1.2 — assertRaises Odoo 18

Fecha: 2026-09-15

Runtime QA (`c9b0378`, `18.0.1.1.1`): 22 tests; 0 failed; 2 errors. `TestSequenceAllocationSafe` OK.

Causa: `odoo.tests.common._assertRaises` hace `issubclass(exception, AccessError)`. Una tupla no es una clase → `TypeError`. unittest estándar acepta tuplas; el wrapper de Odoo 18 no.

Usos encontrados y corrección (tests only):

- `test_duplicity_unique_fiscal_number`: UNIQUE SQL → `IntegrityError` (el `mute_logger('odoo.sql_db')` corresponde a esa vía).
- `test_permissions_sequence_and_issued_document`: create/write de rango por Fiscal User y write de documento issued por User/Manager → `AccessError` (ACL `perm_write=0` / `perm_create=0`). La inmutabilidad Python se cubre con `sudo()` en `test_immutability_and_state_machine`.

`test_sequence_invalid_range` usa `assertRaises(Exception)` (una clase) y capturó el CHECK PostgreSQL `next_in_range`; no se cambia el constraint.

Código productivo, ACL y record rules: sin cambios. Versión `18.0.1.1.2`.

---

# FASE 1.1.3 — ACL vs inmutabilidad en tests

Fecha: 2026-09-15

Runtime QA (`d794fce`, `18.0.1.1.2`): 22 tests; 0 failed; 1 error. `TestSequenceAllocationSafe` OK. Tuple `assertRaises` corregido.

Error restante: `test_permissions_sequence_and_issued_document` esperaba `AccessError` en `doc.with_user(user).write({'amount_total': 1})`. Odoo 18 ejecutó `korventis.fiscal.document.write()` y lanzó `UserError` (`Fiscal document E310000000001 in state issued cannot be modified.`).

Orden real: la inmutabilidad corre **antes** de `super().write()`, donde Odoo comprueba ACL. Un `issued` con campos protegidos no llega a `AccessError`. User y Manager (ambos `perm_write=0` en documentos) reciben el mismo `UserError` de dominio. Eso es el contrato: un emitido no se reescribe.

Separación de pruebas:

- ACL secuencia: Fiscal User create/write → `AccessError`; Fiscal Manager write rango → OK.
- Inmutabilidad documento issued: User y Manager `write` de campos protegidos → `UserError`.
- Bypass RPC: `test_immutability_and_state_machine`.
- Accountant `_post` sin Fiscal Manager: sin cambio.

ACL, CHECK `next_in_range` y código productivo: sin cambios. Versión `18.0.1.1.3`.

---

# FASE 1.2 — BIGINT para secuencial de 10 dígitos

Fecha: 2026-09-15

Runtime QA (`119aafe`, `18.0.1.1.3`): tests estándar 0/0. El test aislado `korventis_pg_lock` falló **antes** de los workers: `range_start/range_end/next_number = 8000000001` → `psycopg2.errors.NumericValueOutOfRange: integer out of range`. Sin residuos.

## Análisis Odoo 18

- ORM anterior: `fields.Integer`.
- PostgreSQL anterior: `int4` (`Integer._column_type = ('int4', 'int4')` en `odoo/fields.py` 18.0).
- No existe `fields.BigInt` oficial ni `Integer(bigint=True)` en 18.0-20260908.
- Mecanismo soportado: subclase de `Integer` con `_column_type = ('int8', 'int8')`. `Field.update_db_column` compara `udt_name` con `column_type[0]` y llama `sql.convert_column` si difieren.
- No se guardan contadores como string. `fiscal_number` sigue siendo `Char` (`E328000000001`).

Versión **`18.0.1.2.0`**: cambia esquema/capacidad (no es un parche 18.0.1.1.4).

## Constraints

- `range_start >= 0`
- `range_end` entre 0 y 9,999,999,999
- `range_start <= range_end`
- `next_number >= range_start` y `next_number <= range_end + 1`

Semántica de agotamiento **sin cambio**: tras el último número, `next_number = range_end + 1` (puede ser 10,000,000,000, cabe en BIGINT) y `allocate()` falla. No se rebobina.

## Migración

Un solo mecanismo: `-u korventis_l10n_do_fiscal`. Al cambiar `_column_type` de `int4` a `int8`, `Field.update_db_column` llama `sql.convert_column` (`ALTER` widen lossless). No hay `migrations/` paralelo (evitar doble ALTER).

También `korventis_fiscal_document.sequence_number` → int8, porque el secuencial crudo del documento puede superar 2^31-1.

## NcfService

Python `int` ilimitado; formato `f"{raw:010d}"`; e-NCF 13 caracteres; `SELECT … FOR UPDATE` / `next_number + 1` en BIGINT.

## Concurrencia / cleanup

Rango original `8000000001..8000000099`. Workers: dos cursores, Barrier, commits, raws ordenados `{8000000001, 8000000002}`, `next_number` persistido `8000000003`. `unlink()` de `res.company` suele fallar por el partner de compañía; el test intenta unlink y si no, `active=False`. Solo DB desechable.

## XML-RPC

Odoo 18 `Integer.convert_to_read` puede devolver `float` si el valor supera int32 (`MAXINT`). No se cambia el almacenamiento a string ni se añade workaround. El contador sigue siendo BIGINT; `fiscal_number` sigue siendo `Char`. JSON-RPC no tiene esa limitación.

---

# FASE 1.2.1 — korventis_pg_lock y TransactionCase

Fecha: 2026-09-15

QA (`4e20690`, `18.0.1.2.0`): BIGINT int8 correcto. Suite estándar 24/0/0. `korventis_pg_lock` falló **antes** de los workers: `self.env.cr.commit()` → Odoo 18 parchea `commit`/`rollback`/`close` del cursor de `TransactionCase` (`AssertionError: Cannot commit or rollback a cursor from inside a test`).

Savepoint del test **no** hace visibles los datos a otras sesiones. Setup, workers, verify y cleanup usan `Registry(dbname).cursor()` (conexiones independientes; `commit` no parcheado). `self.env.cr` no se confirma. Guard: aborta `korventis`/`baruchcafe`; exige `korventis_fiscal_test` o nombre `*_fiscal_test`. Versión `18.0.1.2.1` (solo test/docs).
