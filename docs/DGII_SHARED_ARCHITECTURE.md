# Arquitectura DGII compartida, conciliación fiscal y preparación de QA

**Estado:** Commit 1 del servicio autorizado. Esqueleto `korventis-dgii-registry` e
esquema PostgreSQL independientes implementados; importador ZIP, API de lookup y
adaptador Odoo siguen pendientes.
**Fecha:** 2026-09-17.
**Rama:** `feature/partner-dgii-local`.
**Commit de referencia:** `1e362e9372703da397848101b19aea51b093e92d`.
**Módulos actuales:** `korventis_l10n_do_fiscal` `18.0.1.3.1`, `korventis_partner_dgii` `18.0.1.1.0`.

Este documento es la única entrega de esta fase. No autoriza conversión automática E31→E32, ni transmisión real a DGII, ni merge a `test`/`main`.

---

## 0. Decisión de diseño (resumen ejecutivo)

1. Extraer el padrón a un **servicio independiente** (`korventis-dgii-registry`) con PostgreSQL `korventis_dgii`.
2. Operar en dos modalidades de **despliegue**, no de producto: **SHARED** (una instancia para varias bases Odoo) y **LOCAL** (la misma imagen en la infraestructura del cliente).
3. Cada base Odoo conserva solo contactos, facturas, e-NCF, compañías y configuración. **No** replica ~790 000 filas.
4. `korventis_partner_dgii` pasa a ser **adaptador HTTP** + conciliación + registro manual. Deja de ser dueño del padrón.
5. Coincidencia con padrón y verificación fiscal son **máquinas de estados distintas**. El estado DGII literal (`ACTIVO`, `SUSPENDIDO`, …) es un tercer dato.
6. La aceptación de un e-CF es una **cuarta** máquina, en `korventis_l10n_do_ecf` (aún no existe). El padrón no emite e-CF.
7. **No** se implementa en esta fase ninguna conversión fiscal E31→E32. La matriz de la sección 6 marca lo verificado y lo pendiente.
8. El contexto de prueba `korventis_dgii_test_version_id` **desaparece** en el refactor. Las pruebas de lookup usarán un servicio desechable.

---

## 1. Auditoría del código actual

### 1.1 Qué existe hoy

| Pieza | Dónde | Observación |
| --- | --- | --- |
| Padrón completo en la base Odoo | `korventis.dgii.rnc` / `_version` / `_import.run` | Una copia por base. QA `korventis_fiscal_test`: ~789 577 filas, versión activa, SHA-256 del ZIP oficial. |
| Búsqueda | `search_active_registry()` | SQL directo a la tabla local. FTS + LIKE. Contexto de test para `staging`. |
| Alta DGII | `korventis_create_from_dgii` | País RD, `es_DO`, tipo E31, origen `dgii`, `verification_state=listed`. |
| Alta manual | `korventis_create_manual_customer` | Exige 9/11 dígitos y tipo explícito. Origen `manual`, `pending`. **No** consulta padrón ni guarda versión consultada. |
| Wizard | `korventis.partner.lookup.wizard` | Contactos de la base primero; luego padrón activo. |
| Cron e importador | `hooks.py`, `services/importer.py` | ZIP oficial, staging, una versión `active`, 01:00 Santo Domingo, cron apagado hasta autorización. |
| Núcleo fiscal | `korventis.fiscal.document` | Estados `draft` / `reserved` / `issued` / `cancelled`. e-NCF al **post** de `account.move`. Eventos append-only. **Sin** XML, firma ni TrackId. |
| POS Korventis | no existe | `docs/POS_GAP_ANALYSIS.md`. |
| e-CF | no existe | Previsto como `korventis_l10n_do_ecf`. |
| Docker | no existe en el repo | Los compose SHARED/LOCAL son trabajo nuevo; no reutilizar rutas de imagen inventadas. |

### 1.2 Problemas que este diseño corrige

- Duplicar ~790 000 filas en `korventis`, `baruchcafe` y cada cliente futuro.
- Un solo campo `korventis_verification_state` mezcla “está en el padrón” con “verificado para emitir”.
- Manual no deja rastro de “no encontrado en la versión X”.
- `REGISTRY_TEST_VERSION_CONTEXT` permite (en tests) consultar `staging`; no debe existir en producto.
- No hay conciliación cuando el padrón se actualiza.
- No hay API ni aislamiento multibase del padrón.

### 1.3 Lo que **no** se toca ahora

- Bases QA `korventis` y `baruchcafe` (sin autorización).
- Producción `198.199.80.184`.
- Borrado del padrón de `korventis_fiscal_test`.
- Numeración e-NCF del núcleo (`NcfService`).
- Flujo estándar de pagos Odoo.
- Emisión de NCF al abrir mesa o imprimir prefactura.

---

## 2. Arquitectura DGII: SHARED y LOCAL

### 2.1 Principio

El **mismo** servicio, el **mismo** esquema PostgreSQL y la **misma** API. Cambia solo el lugar de despliegue y qué bases Odoo tienen credenciales.

```
                    ┌─────────────────────────────────────┐
                    │  korventis_dgii (PostgreSQL)        │
                    │  padrón, versiones, importaciones   │
                    └─────────────────┬───────────────────┘
                                      │ solo el servicio
                    ┌─────────────────▼───────────────────┐
                    │  korventis-dgii-registry (API)      │
                    │  HTTPS interno · mTLS o token       │
                    └───────────┬─────────────┬───────────┘
                                │             │
                 SHARED         │             │ LOCAL
     ┌──────────▼──────┐  ┌─────▼─────┐  ┌───▼────────────┐
     │ Odoo korventis  │  │ Odoo      │  │ Odoo cliente   │
     │ Odoo baruchcafe │  │ fiscal_   │  │ (un solo tenant│
     │ futuros         │  │ test      │  │  en su VPS)    │
     └─────────────────┘  └───────────┘  └────────────────┘
```

El servicio **nunca** abre escritura hacia `res.partner` de un cliente. PostgreSQL del padrón **no** se publica a Internet ni se entrega a clientes como acceso SQL.

### 2.2 Modalidad SHARED

- Una instancia del servicio en el VPS Korventis (red privada / firewall).
- Una base `korventis_dgii`.
- N instalaciones Odoo, cada una con `install_id` + secreto.
- Importación oficial **una vez** al día, no N veces.
- Notificación “nueva versión” a cada instalación autorizada (cola o pull).

### 2.3 Modalidad LOCAL

- El cliente corre el mismo `docker-compose.local.yml` junto a su Odoo.
- API en loopback o red Docker interna (`korventis-dgii-registry:8443`).
- Un solo `install_id`.
- Misma política: no descarga en `-i` de Odoo; cron del **servicio**, no de cada módulo Odoo.

### 2.4 Límites de responsabilidad

| Componente | Hace | No hace |
| --- | --- | --- |
| Servicio padrón | Importar ZIP, versionar, consultar RNC/nombre, firmar notificaciones de versión | Emitir e-CF, escribir contactos, decidir E31/E32, guardar facturas |
| Adaptador Odoo | Buscar local, llamar API, crear contacto elegido, conciliar pendientes | Copiar el padrón, consultar `staging` |
| Núcleo fiscal | e-NCF al post, snapshot del partner, eventos | HTTP DGII e-CF |
| Futuro `korventis_l10n_do_ecf` | Firma, TrackId, consulta estado | Padrón de contribuyentes |
| Futuro `korventis_l10n_do_pos` | UX caja, prefactura sin NCF | Numeración ni padrón |

### 2.5 API privada (contrato)

Autenticación por **instalación**, no por usuario Odoo.

- Transporte: HTTPS. En SHARED, solo red privada. En LOCAL, red de compose.
- Credencial: `KORVENTIS_DGII_INSTALL_ID` + `KORVENTIS_DGII_INSTALL_SECRET` (archivo 0600 / Docker secret). El secreto **no** va a git ni a `ir.config_parameter` en claro si puede evitarse; si Odoo debe guardarlo, usar `ir.config_parameter` marcado y **nunca** loguearlo.
- Cada petición: timeout corto (p. ej. 3 s connect / 8 s read), `request_id`, rate limit por `install_id` (p. ej. 30 consultas/minuto, ráfaga de búsqueda de nombre más estricta).
- Respuestas de búsqueda: máximo 20 filas. Prefijo de RNC o FTS de nombre, mismos literales `%`/`_` que hoy.
- No hay endpoint de listado completo ni de `COPY` del padrón.

Endpoints previstos:

| Método | Ruta | Uso |
| --- | --- | --- |
| `GET` | `/health` | Liveness/readiness |
| `GET` | `/v1/registry/version` | Versión activa: id lógico, `activated_at`, `record_count`, `archive_sha256` |
| `GET` | `/v1/registry/lookup` | `q` (RNC o nombre), `limit` |
| `GET` | `/v1/registry/rnc/{rnc}` | Coincidencia exacta de identificador normalizado |
| `POST` | `/v1/installations/heartbeat` | Odoo informa que está viva |
| `GET` | `/v1/notifications/versions` | Pull de versiones nuevas desde `since` (idempotente) |
| `POST` | `/v1/admin/import` | Solo rol admin del servicio; no desde Odoo cliente |
| `POST` | `/v1/admin/cron/enable` | Tras primera importación correcta y autorización explícita |

Auditoría del servicio (tabla `api_audit`): `install_id`, ruta, código HTTP, `request_id`, duración, RNC consultado (texto), **nunca** el secreto ni cuerpos de ZIP.

Códigos de error estables: `401` credencial, `429` cuota, `503` padrón no activo, `504` timeout interno de descarga (solo admin).

### 2.6 Identificadores de versión

Odoo **no** guarda `Many2one` a `korventis.dgii.rnc.version` de otra base. Guarda:

- `korventis_dgii_version_token` (SHA-256 del ZIP o id opaco del servicio).
- `korventis_dgii_version_activated_at`.
- `korventis_dgii_record_count` (informativo).

Así el adaptador sobrevive a SHARED y LOCAL sin IDs de PostgreSQL ajenos (el id 61 de QA no es portable).

---

## 3. Registro manual de clientes ausentes del padrón

### 3.1 Regla de producto

Un RNC **ausente** del archivo DGII **no** es, por ese solo hecho, un RNC inválido. Un RNC de 9 u 11 dígitos **no** es, por ese solo hecho, un RNC válido ante DGII.

La creación estándar de `res.partner` (proveedores, contactos internos, direcciones hijas) **no** pasa por este asistente y **no** se bloquea.

### 3.2 Datos mínimos del contacto creado por el asistente

| Dato | Campo previsto | Notas |
| --- | --- | --- |
| Identificador | `vat` + `korventis_identification_normalized` | Texto; conserva ceros a la izquierda |
| Nombre introducido | `name` | No se sustituye por el padrón hasta aprobación |
| Tipo fiscal | `korventis_fiscal_document_type_id` | Explícito; E31 no se infiere si el usuario eligió E32 |
| Origen | `korventis_registration_origin` | `manual` o `dgii` |
| Coincidencia padrón | `korventis_registry_match_state` | ver §4 |
| Verificación fiscal | `korventis_fiscal_verify_state` | ver §4 |
| Estado DGII literal | `korventis_dgii_status` | `ACTIVO` / `SUSPENDIDO` / vacío |
| Actividad DGII | `korventis_dgii_activity` | Solo si hubo match |
| Última consulta | `korventis_dgii_lookup_at` | |
| Versión consultada | `korventis_dgii_version_token` | |
| Nombre propuesto | `korventis_dgii_proposed_name` | Solo `name_mismatch` |
| Creación | `create_uid` / `create_date` | ORM |

Alta DGII (selección confirmada): origen `dgii`, match `matched`, verify `pending` (la emisión e-CF sigue pendiente de `korventis_l10n_do_ecf`). No se marca `verified` solo por aparecer en el ZIP.

Alta manual: origen `manual`, match `not_found` si la API respondió vacío, o `not_checked` si la API no estaba disponible. Verify `pending`.

### 3.3 Deduplicación

Sigue el lock advisory por identificador normalizado **dentro de la base Odoo**. Dos clientes Korventis/Baruch con el mismo RNC son **correctos**: viven en bases distintas. Dentro de una base, un RNC → un partner comercial.

---

## 4. Estados separados y conciliación

### 4.1 Máquina A — coincidencia con padrón

`korventis_registry_match_state`

| Estado | Significado |
| --- | --- |
| `not_checked` | No se ha consultado esta versión (o la API estaba caída). |
| `not_found` | Consulta hecha; el RNC no está en la versión. |
| `matched` | RNC exacto y nombre equivalente (normalizado). |
| `name_mismatch` | RNC exacto; razón social distinta. Hay propuesta. |
| `review_required` | Match de RNC pero el estado DGII literal no es `ACTIVO`, u otra regla de revisión. |

Transiciones permitidas:

```
not_checked --> not_found | matched | name_mismatch | review_required
not_found   --> not_found | matched | name_mismatch | review_required   (nueva versión)
matched     --> matched | name_mismatch | review_required | not_found
name_mismatch --> matched (tras aprobar nombre o coincidir tras edición)
name_mismatch --> name_mismatch (misma evidencia, no duplicar aviso)
review_required --> matched | name_mismatch | review_required | not_found
```

No hay transición a “inválido”. El padrón no declara validez fiscal del RNC más allá de su fila.

**Responsable:** proceso de conciliación (usuario técnico `korventis` / cron Odoo) o cajero al buscar.
**Evidencia:** `korventis.dgii.match.event` append-only: token de versión, RNC, nombre Odoo, nombre DGII, estado DGII literal, resultado, `request_id`.

### 4.2 Máquina B — verificación fiscal (emisor Korventis)

`korventis_fiscal_verify_state`

| Estado | Significado |
| --- | --- |
| `pending` | Aún no hay decisión interna de emitir crédito fiscal con estos datos. |
| `verified` | Un usuario autorizado aceptó los datos para operaciones futuras (no es aceptación e-CF). |
| `review_required` | Supervisor debe revisar (mismatch, suspendido, rechazo DGII de identificación). |
| `rejected` | Decisión interna de no usar esos datos para E31. El partner puede seguir existiendo. |

Transiciones:

```
pending --> verified | review_required | rejected
review_required --> verified | rejected | pending
verified --> review_required   (nueva evidencia: mismatch o rechazo e-CF por receptor)
rejected --> pending           (el cliente corrige RNC/nombre; nuevo ciclo)
```

`verified` **no** implica que DGII aceptará el e-CF. `matched` **no** implica `verified`.

### 4.3 Campo literal DGII

`korventis_dgii_status` copia `ACTIVO`, `SUSPENDIDO` u otro texto del archivo. No se mapea a las máquinas A/B.

Si el estado ≠ `ACTIVO` y hay match de RNC: match → `review_required` y verify permanece `pending` o pasa a `review_required`. **No** se bloquea automáticamente la emisión E31 en código hasta que la matriz §6 lo autorice; la UI de caja **sí** avisa.

### 4.4 Conciliación automática (después de una versión nueva)

El servicio **notifica** (pull recomendado: Odoo pregunta `GET /v1/notifications/versions?since=`). No escribe contactos.

Cada base Odoo:

1. Trabaja solo sus `res.partner` con origen Korventis y match en `{not_checked, not_found, name_mismatch, review_required}` o `matched` (revalidar nombre).
2. Lotes (p. ej. 100) con `FOR UPDATE SKIP LOCKED` sobre una cola `korventis.dgii.reconcile.job`.
3. Lookup **exacto** por RNC normalizado (`GET /v1/registry/rnc/{rnc}`).
4. Si 404: `not_found`, guardar token de versión. No tocar `name`.
5. Si 200 y nombres equivalentes: `matched`, guardar evidencia. **No** sobrescribir `name`, calle ni `vat`.
6. Si 200 y nombres distintos: `name_mismatch`, llenar `korventis_dgii_proposed_name`. Aviso único por `(partner_id, version_token)` (`unique` SQL).
7. Si estado DGII ≠ `ACTIVO`: además `review_required` en match y/o verify según §4.3.
8. Cero escrituras a `account.move`, `korventis.fiscal.document`, e-NCF.
9. Cero creación de partners.
10. Si API 5xx/timeout: job `retry` con backoff; no inventar filas de padrón.
11. Idempotencia: repetir el mismo `(partner, version_token)` no crea segundo aviso ni segundo evento con el mismo resultado.

Manual: acción “Conciliar ahora” (grupo manager DGII).

Aprobación de nombre (§5): evento con usuario, fecha, versión, nombre anterior, nombre propuesto, decisión (`accepted` / `kept`). El cambio de `name` aplica **solo** al contacto, para documentos futuros. Los snapshots `partner_name` de documentos ya emitidos no se reescriben.

Normalización de comparación: mayúsculas, espacios, acentos. **Nunca** fuzzy match como sustituto del RNC exacto.

---

## 5. Revisión y aprobación de razón social

Pantalla Odoo (grupo manager):

- Nombre actual vs propuesto DGII.
- Estado DGII literal, token de versión, fecha de activación del padrón.
- Botones: “Usar razón social DGII” / “Conservar nombre Odoo” / “Dejar en revisión”.

Trazabilidad en `korventis.dgii.match.event`. Documentos históricos intactos.

---

## 6. Flujo POS: rechazo DGII, corrección y solicitud de comprobante de consumo

Esta sección es **diseño**. No hay módulo POS ni e-CF en el repo. No simular transmisión real en producto.

### 6.1 Investigación normativa

Fuentes oficiales usadas (portal DGII, descargas vigentes a 2026-09-17). Las fuentes secundarias (blogs, Alanube, Odoo `l10n_do_edi`) **no** mandan.

| Tema | Documento | Versión / fecha página DGII | Apartado | Conclusión verificada | Pendiente |
| --- | --- | --- | --- | --- | --- |
| Tipos 31/32 | Formato e-CF V1.0 | Modificado 30/10/2025 | Tabla tipos; área comprador | 31 = Factura de Crédito Fiscal Electrónica; 32 = Consumo. | — |
| RNC comprador E31 | Formato e-CF V1.0 p. 12 | 30/10/2025 | Campo `RNC Comprador`, columna 31 = obligatorio (`I 1`), 9 u 11 dígitos | E31 exige identificar comprador con RNC/cédula. | Si DGII rechaza E31 por RNC no inscrito: código exacto de `mensajes[]` **[REQUIERE VALIDACIÓN DGII]** contra catálogo de códigos del PDF de servicios / certificación. |
| RNC comprador E32 | Formato e-CF V1.0 p. 12 notas 4–6 | 30/10/2025 | ≥ DOP 250 000 exige RNC; &lt; 250 000 opcional | Consumo menor a 250 mil puede omitir RNC. | Umbral “250 mil” vs “250,000.00” unificado en el formato; URLs TesteCF del QR **[REQUIERE VALIDACIÓN DGII]** (ya en `docs/DGII_SOURCES.md`). |
| Razón social en RI | Informe Técnico e-CF v1.0 §18.2 | Página 06/04/2026 | “Nombre o Razón Social Cliente, **como consta en el RNC**”; nota 45 | La RI debe mostrar el nombre del RNC. Diferencia de nombre es riesgo de rechazo o de RI incorrecta, no una “corrección automática”. | ¿DGII compara string exacto del XML contra padrón en recepción? **[REQUIERE VALIDACIÓN DGII]** en CerteCF. |
| Firma | Firmado de e-CF | 22/11/2023 | XMLDSig RSA-SHA256 | Sin firma válida no hay e-CF. | — |
| Recepción ≠ aceptación | Descripción Técnica Servicios DGII | Página 29/05/2026; actualizaciones internas 18-05-2023 | Recepción e-CF | `TrackId` es **acuse**. Habilita envío al receptor / RI **después** de un estado de validación satisfactorio. HTTP 200 + TrackId **no** es aceptación fiscal. | — |
| Estados de consulta TrackId | Mismo PDF, Consulta de resultado e-CF | 29/05/2026 | ESTADOS SALIDA | `No encontrado (0)`, `Aceptado (1)` validez, `Rechazado (2)` nulidad tributaria, `En Proceso (3)` reconsultar (~200 ms promedio), `Aceptado Condicional (4)` validez con observaciones. | Mapear cada `codigo` de `mensajes[]` a causa (RNC, XML, firma). Catálogo completo **[REQUIERE VALIDACIÓN DGII]**. |
| Reutilización de e-NCF | Mismo PDF, `secuenciaUtilizada` | 18-05-2023 / 29/05/2026 | Consulta resultado | `true` = **no** reutilizar; `false` = **sí** reutilizar, y **solo** si el rechazo es por los motivos listados: certificado/firma inválida; XML inválido; firmante no delegado; e-NCF no autorizado o vencido; RNC **emisor** inexistente, inactivo o no emisor electrónico. | Rechazo por **RNC/razón social del comprador** **no** aparece en esa lista. **No autorizar reutilización** en ese caso hasta validar el código oficial. Gosocket resume true/false; no sustituye al PDF. |
| Entrega al receptor | Mismo PDF, Recepción | 29/05/2026 | Párrafo posterior al TrackId | RI / envío al receptor **después** de validación satisfactoria (`Aceptado` o `Aceptado Condicional`). | Comportamiento POS si `En Proceso` se alarga: reconsultar, no emitir otro e-NCF. |
| Consulta pública e-CF | Portal comprobantes electrónicos | Página DGII | Mensajes de consulta NCF | “NCF válido” ≠ estado final; “no encontrado” = aún no enviado; RNC/e-NCF incorrectos. Estados: Aceptado / Aceptado Condicional / Rechazado / En Proceso. | — |
| NC/ND | Formato e-CF tipos 33/34; Guía 5 | XSD 33/34 01/04/2026 | Tipos 33 y 34 | Son comprobantes **nuevos**, no edición del original. | Cuándo **debe** usarse E34 tras una E31 aceptada si el cliente quiere consumo: **[REQUIERE VALIDACIÓN DGII]**. No implementar conversión. |
| Anulación de rangos | Formato Anulación e-CF V1.0; servicio ANECF | 20/06/2022 / XSD 20/06/2023 | Anulación | Mecanismo de rangos, no “borrar un XML rechazado”. | Relación con un e-NCF ya `secuenciaUtilizada=true` **[REQUIERE VALIDACIÓN DGII]**. |
| Contingencia | Instructivo Contingencia FE | 25/02/2026 | Offline ≤ 72 h; NCF no electrónicos en incapacidad | Fuera de esta fase. | — |
| Checksum RNC | Comunidad DGII CA3904; consulta RNC | — | Longitud 9/11 | Dígito verificador **sin algoritmo oficial publicado**. No usarlo como prueba de invalidez. | Algoritmo **[REQUIERE VALIDACIÓN DGII]**. |
| Ley 32-23 | PDF DGII | Ley 32-23 | Marco e-CF | Base legal de FE. | Artículos operativos de rechazo/reemisión: citar en implementación e-CF, no en el adaptador de padrón. |

URL del índice oficial: [Documentación sobre e-CF](https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/documentacionSobreE-CF.aspx).

### 6.2 Validación previa en caja (diseño)

Cuando el cliente pide **E31**:

1. Pedir RNC y razón social.
2. Buscar `res.partner` en **esta** base (identificador normalizado).
3. Si la API del padrón está viva: `GET /v1/registry/rnc/{rnc}` y mostrar estado literal + fecha de la versión.
4. Si no aparece: mensaje de “no encontrado en la versión consultada”, **sin** decir “RNC inválido”.
5. Permitir registro manual si la política de verificación lo autoriza (`pending` + match `not_found`).
6. Mostrar el tipo (E31) antes de confirmar el cobro fiscal.
7. **Cero** e-NCF en cotización, proforma o prefactura (`docs/POS_GAP_ANALYSIS.md`).

La consulta al padrón Korventis **no** sustituye la validación de DGII al recibir el XML.

**Emisión E31 con match `not_found`:** el Formato e-CF exige RNC comprador en tipo 31. El ZIP local puede estar desfasado. **No** se prohíbe el registro manual. **Sí** se deja `fiscal_verify_state=pending` y se avisa. Autorizar o bloquear la **transmisión** e-CF en ese estado es decisión de `korventis_l10n_do_ecf` + certificación; **[REQUIERE VALIDACIÓN DGII / política Korventis]**. Hasta entonces, el diseño de caja es: permitir cobro y factura Odoo solo si un supervisor confirma `verified`, o emitir E32 si el cliente lo pide **antes** de consumir e-NCF E31.

### 6.3 Máquina C — documento electrónico (futuro `korventis_l10n_do_ecf`)

Separada de `korventis.fiscal.document.state` (`draft/reserved/issued/cancelled`), que hoy solo cubre numeración local.

Estados alineados a DGII (consulta TrackId) más estados técnicos propios:

| Estado Korventis | Origen | Validez tributaria |
| --- | --- | --- |
| `draft` | interno | no |
| `issued_local` | núcleo (e-NCF reservado/emitido, aún no XML) | no ante DGII |
| `signed` | interno | no |
| `sent` | HTTP recepción aceptó el POST | **no** (solo TrackId) |
| `received` | TrackId persistido | no |
| `in_process` | estado DGII `3` | no |
| `accepted` | estado DGII `1` | sí |
| `accepted_conditional` | estado DGII `4` | sí |
| `rejected` | estado DGII `2` | nulidad |
| `not_found` | estado DGII `0` | desconocido |
| `transport_error` | timeout, 5xx, red | desconocido; **no** es rechazo |
| `unknown` | respuesta ilegible | desconocido |

Campos por intento (`korventis.fiscal.transmission`, append-only): e-NCF, tipo, TrackId, timestamp, HTTP status, `codigo` DGII, `estado` DGII, `mensajes` JSON original, `secuenciaUtilizada`, estado interpretado, número de intento, `document_id`. **Nunca** borrar ni pisar un intento anterior.

HTTP 200 **no** se interpreta como `accepted`.

### 6.4 Tratamiento de rechazos (diseño, sin conversión automática)

1. Guardar respuesta original.
2. Clasificar por `mensajes[].codigo` cuando el catálogo esté validado; hasta entonces, guardar bruto y etiquetar `unknown_code`.
3. Distinguir familias: identificación receptor, XML, firma/certificado, numeración emisor, otros.
4. Mensajes de caja §6.6.
5. Si la familia es identificación: pedir confirmación al cliente; no marcar el partner como “RNC inválido” salvo que el texto oficial lo diga.
6. Corrección y reenvío **solo** si `secuenciaUtilizada=false` **y** el motivo está en la lista oficial del PDF. Si `true` o el motivo es del comprador: **no** reutilizar e-NCF.
7. Si no hay respuesta: `transport_error` / `in_process` / `unknown`. Consultar TrackId y `ConsultaTrackIds`. **No** emitir un segundo e-NCF.
8. No tocar facturas aceptadas ni snapshots.

### 6.5 Alternativa E32 (condicionada; no automática)

Nunca convertir E31 en E32.

| Situación | ¿E32 nuevo? | Base |
| --- | --- | --- |
| Aún **no** se consumió e-NCF E31 (prefactura / borrador) | Sí, si el cliente lo pide y el cajero/supervisor confirma | No hay documento fiscal 31 |
| E31 `in_process` / `transport_error` / `unknown` / `not_found` | **No** | PDF: reconsultar; riesgo de doble comprobante |
| E31 `accepted` o `accepted_conditional` | **No** automático | Haría falta NC E34 u otro procedimiento **[REQUIERE VALIDACIÓN DGII]** |
| E31 `rejected` y `secuenciaUtilizada=false` por XML/firma (lista oficial) | Reenviar **el mismo tipo** corregido, no cambiar a 32 | PDF `secuenciaUtilizada` |
| E31 `rejected` por datos del comprador | **No implementado** | Motivo no está en la lista de reutilización; no inventar E32 “de consuelo” |
| Cliente pide consumo **antes** de confirmar E31 | Sí, con confirmación expresa, trazabilidad, un solo asiento | Producto POS |

Doble facturación: unique `(company_id, pos_order_id)` previsto en arquitectura POS. Un `account.move` posted por orden.

### 6.6 Mensajes de caja

| Caso | Mensaje cajero | Supervisor |
| --- | --- | --- |
| RNC no en padrón | «No encontramos este RNC en la versión del padrón consultada. Confirme los datos del cliente.» | Token de versión, fecha, `request_id` |
| Rechazo DGII por identificación | «DGII rechazó el comprobante por un problema con los datos de identificación del receptor. Verifique el RNC y la razón social con el cliente.» | `codigo` + `mensajes` originales |
| Rechazo por otra causa | «DGII rechazó el comprobante: [mensaje oficial]. Solicite asistencia para corregirlo.» | JSON completo del intento |
| Sin respuesta / en proceso | «Estamos verificando el estado del comprobante con DGII. No emita otro documento todavía.» | TrackId, último HTTP, reintentos |
| Solicitud E32 | «El cliente solicita cambiar a factura de consumo. Se requiere confirmar que el procedimiento fiscal permite emitir un nuevo comprobante.» | Estado real de la E31; bloqueo si no está en “sin e-NCF” |

No decir “RNC inválido” salvo cita expresa de DGII.

### 6.7 Separación de responsabilidades

Ya cubierta en §2.4. El servicio compartido **no** decide E31/E32. Mocks de DGII **solo** en tests (`MockProvider`), nunca en producción ni en QA como si fueran CerteCF.

### 6.8 Diagrama de estados (e-CF)

```
[borrador Odoo / prefactura] --x--> e-NCF
[post factura] --> issued_local --> signed --> sent --> received
received --> in_process
in_process --> accepted
in_process --> accepted_conditional
in_process --> rejected
sent/received --> transport_error --> (reconsulta TrackId, no nuevo e-NCF)
rejected + secuenciaUtilizada=false + motivo de lista oficial --> reenvío mismo e-NCF
rejected + secuenciaUtilizada=true --> e-NCF muerto; no reutilizar
accepted --> (solo NC/procedimiento DGII para anular efectos)  [PENDIENTE]
```

### 6.9 Matriz de decisiones POS (implementar solo celdas “Sí” verificadas)

| # | Condición | Acción permitida | ¿Verificado? |
| --- | --- | --- | --- |
| D1 | Prefactura | Imprimir sin e-NCF | Sí (Odoo + política Korventis) |
| D2 | API padrón caída | Cobro interno + alta manual; no mostrar filas DGII inventadas | Sí (producto) |
| D3 | E31 sin post | Cambiar a E32 con confirmación | Sí (aún no hay e-NCF) |
| D4 | TrackId + En Proceso | Esperar / reconsultar | Sí (PDF servicios, estado 3) |
| D5 | Aceptado / Aceptado condicional | Entregar RI; no segundo e-NCF | Sí (PDF recepción + estados 1 y 4) |
| D6 | Rechazo XML/firma + `secuenciaUtilizada=false` | Corregir y reenviar **mismo** e-NCF | Sí (PDF lista) |
| D7 | Rechazo + `secuenciaUtilizada=true` | No reutilizar | Sí (PDF true = no reutilizar) |
| D8 | Rechazo por RNC comprador → emitir E32 | **No** | Pendiente; no implementar |
| D9 | E31 aceptada → E32 | **No** | Pendiente NC E34 |
| D10 | Timeout → “rechazado” | **No** | PDF: consultar estado |

---

## 7. Servicio e importador

Proceso actual de `services/importer.py` **se mueve** al servicio (staging, COPY, volumen mínimo, SHA-256, una `active`, anterior recuperable, advisory lock). Odoo deja de descargar el ZIP.

- Cron del **servicio** a las 01:00 `America/Santo_Domingo` (naive UTC 05:00), inactivo hasta importación inicial correcta **y** flag explícito.
- Compose: `deploy/dgii-registry/docker-compose.shared.yml` y `docker-compose.local.yml`. Imágenes: PostgreSQL oficial + imagen del servicio construida desde este repo (`Dockerfile` nuevo). Healthcheck HTTP `/health`. Volúmenes nombrados para datos y backups; **no** `docker volume rm` en scripts.
- Backup: `pg_dump` de `korventis_dgii` + copia del ZIP adjunto. Restore documentado en `docs/ROLLBACK.md` (ampliación posterior).

---

## 8. Adaptador Odoo

Flujo del wizard (igual de intención, distinto backend):

1. Contactos de **esta** base.
2. API lookup (si 503/timeout: banner “padrón no disponible”, cero resultados DGII).
3. Usuario elige o pasa a manual.
4. Crear un solo `res.partner`.
5. Conciliación posterior (§4.4).

Eliminar:

- Modelos operativos de padrón como fuente de búsqueda (`korventis.dgii.rnc` deja de llenarse).
- Cron de importación en Odoo.
- `REGISTRY_TEST_VERSION_CONTEXT`.

Conservar menús de **estado del adaptador** (versión remota, último heartbeat, jobs de conciliación), no el explorador de 790 000 filas.

Tablas antiguas: **no** `DROP`. Quedan `legacy` para auditoría y rollback.

---

## 9. Plan de migración (idempotente, no destructiva)

Objetivo: Korventis y Baruch Café podrán probar **después** de aprobar este diseño, sin perder contactos ni e-NCF.

### 9.1 Orden

1. Levantar `korventis_dgii` **vacío** en un compose QA **aparte** (no sobreescribir `korventis_fiscal_test`).
2. Cargar el padrón **una vez**:
   - Preferido: ETL desde las tablas ya importadas en `korventis_fiscal_test` (conteo, SHA-256, estado `active`) hacia `korventis_dgii`, en transacción del servicio.
   - Alternativa: importación oficial nueva y comparar SHA/conteo con la versión de QA.
3. Congelar criterios de aceptación: mismos `record_count`, `archive_sha256`, una sola `active`.
4. Instalar adaptador en una **copia** desechable de QA (no `korventis` / `baruchcafe`).
5. Backfill de contactos existentes:
   - `origin=dgii` → match `matched` (o `review_required` si estado ≠ ACTIVO), verify `pending`.
   - `origin=manual` + `pending` → match `not_checked`, luego conciliar.
   - No reescribir `name` ni `vat`.
6. Apuntar el adaptador al servicio. Búsqueda deja de usar SQL local.
7. Dejar tablas `korventis_dgii_rnc*` en la base Odoo **sin borrar**. Marcar módulo de datos legacy como no usadas.
8. Solo tras N días y autorización: job opcional de archivo (no parte de esta aprobación).

### 9.2 Rollback

- Restaurar `odoo.conf` / parámetros del adaptador a “no remoto” no rehidrata 790 000 filas si ya no se importan; por eso las tablas legacy **permanecen** hasta decisión explícita.
- Servicio: restaurar dump `korventis_dgii`.
- Núcleo fiscal: no participa; no hay rollback de e-NCF.

### 9.3 Impacto en `korventis_fiscal_test`

Solo **lectura** para ETL o comparación. Prohibido `DELETE`/`UPDATE` masivo del padrón oficial.

---

## 10. Plan de pruebas

| Capa | Dónde | Base |
| --- | --- | --- |
| A | Servicio + importador | PostgreSQL desechable `korventis_dgii_test` |
| B | Adaptador Odoo | Base Odoo desechable (no `korventis`/`baruchcafe`) |
| C | Compatibilidad padrón real | Lectura de SHA/conteo vs `korventis_fiscal_test` |
| D | Aislamiento | Dos bases Odoo + un servicio |
| E | Conciliación | Fixtures de partners pendientes |
| F | Facturación / e-CF | Mocks identificados; CerteCF **fuera** de esta fase |

Escenarios obligatorios del adaptador/servicio: RNC ausente; RNC nuevo en versión siguiente; match exacto; mismatch de nombre; `SUSPENDIDO`; API caída; mismo RNC en dos bases Odoo; reejecución; partner con factura histórica; aprobación y rechazo de nombre; retry de sync.

Escenarios e-CF/POS (capa F, con mocks): manual pendiente pide E31; ausente; incorporado después; aceptado; rechazo RNC; rechazo XML; rechazo firma; sin respuesta; recibido sin aceptar (`En Proceso`); retry de red; doble clic; corrección de RNC; solicitud E32; E31→E32 bloqueado; E31 ya aceptada; numeración y auditoría; sin doble asiento; mensajes cajero/supervisor.

No omitir tests para esconder UniqueViolation u otros errores. El servicio de prueba es la vía de aislamiento, no un contexto `staging` en producción.

---

## 11. Instaladores

Ampliar `scripts/` **después** de aprobar:

- `KORVENTIS_DGII_MODE=shared|local`
- Verificar `/health` y versión activa **sin** descargar ZIP desde Odoo.
- Instalar/actualizar `korventis_l10n_do_fiscal` y el adaptador por `-d`.
- Rechazar `korventis` y `baruchcafe` salvo flag de autorización futura.
- Cron del **servicio** con `KORVENTIS_ENABLE_CRON=yes` análogo al actual.
- No `dropdb`, no `docker volume rm`, no contraseñas en el repo.
- Compose con nombres de imagen **reales** (`postgres:16`, imagen construida `korventis-dgii-registry:${VERSION}`). Hoy no hay Dockerfile; no referenciar `odoo:18` paths que esta imagen Korventis no tenga.

---

## 12. Lista de cambios por archivo (prevista, no aplicada)

### 12.1 Nuevo

| Ruta | Rol |
| --- | --- |
| `services/korventis_dgii_registry/` | API, importador, modelos SQL del padrón |
| `deploy/dgii-registry/Dockerfile` | Imagen del servicio |
| `deploy/dgii-registry/docker-compose.shared.yml` | SHARED |
| `deploy/dgii-registry/docker-compose.local.yml` | LOCAL |
| `deploy/dgii-registry/env.example` | Sin secretos |
| `korventis_partner_dgii/models/dgii_match.py` | Eventos de coincidencia |
| `korventis_partner_dgii/models/dgii_reconcile.py` | Jobs de conciliación |
| `korventis_partner_dgii/services/registry_client.py` | Cliente HTTP |
| `korventis_partner_dgii/wizard/name_approval.py` | Aprobación de razón social |
| `korventis_partner_dgii/migrations/18.0.2.0.0/` | Backfill estados; no DROP |
| `docs/DGII_SHARED_ARCHITECTURE.md` | Este documento |
| Tests A en `services/korventis_dgii_registry/tests/` | |
| Tests B/E en `korventis_partner_dgii/tests/` | |

### 12.2 Modificar (cuando se autorice implementar)

| Ruta | Cambio |
| --- | --- |
| `korventis_partner_dgii/__manifest__.py` | Versión `18.0.2.0.0`; quitar data de cron de importación; no depender de tablas de padrón como operativas |
| `korventis_partner_dgii/models/res_partner.py` | Dos máquinas de estados; quitar contexto staging; cliente HTTP |
| `korventis_partner_dgii/wizard/partner_lookup.py` | Lookup remoto + manual enriquecido |
| `korventis_partner_dgii/hooks.py` | Sin descarga; heartbeat opcional |
| `korventis_partner_dgii/services/schema.py` | Quitar `REGISTRY_TEST_VERSION_CONTEXT` |
| `korventis_partner_dgii/models/dgii_rnc.py` | Dejar de ser fuente operativa (legacy) |
| `scripts/install_korventis.sh` / `verify_korventis.sh` | Modo SHARED/LOCAL |
| `docs/INSTALL.md`, `UPGRADE.md`, `MULTIDB.md`, `DGII_IMPORT.md`, `CONFIGURATION.md`, `ROLLBACK.md`, `QA_CHECKLIST.md` | Servicio + adaptador |
| `korventis_l10n_do_fiscal` | **Sin cambio** en esta oleada salvo, más adelante, enlace a transmisiones |
| `korventis_l10n_do_ecf` / `korventis_l10n_do_pos` | **Módulos nuevos** en fases posteriores, no este refactor |

### 12.3 No tocar

`korventis` / `baruchcafe` / producción / padrón oficial de `korventis_fiscal_test` (salvo SELECT para comparar SHA).

---

## 13. Secuencia de implementación por commits

Cada commit en `feature/partner-dgii-local` (o rama hija). Sin merge a `test`/`main` hasta autorización.

| # | Commit previsto | Contenido | Criterio de salida |
| --- | --- | --- | --- |
| 0 | *(este)* | Solo documentación de arquitectura | Aprobación escrita |
| 1 | `feat(dgii-svc): add registry service skeleton and schema` | Postgres `korventis_dgii`, tablas, una `active`, health | Tests A vacíos en verde |
| 2 | `feat(dgii-svc): port official ZIP importer` | Staging, SHA, activación atómica, cron off | Import fixture ZIP; no HTTP DGII en CI |
| 3 | `feat(dgii-svc): add authenticated lookup API` | Token por instalación, límites, audit | Tests A lookup + 401/429 |
| 4 | `feat(dgii-svc): add compose SHARED/LOCAL` | Dockerfiles reales, health, backup scripts | `compose config` válido |
| 5 | `test(dgii-svc): compare SHA with fiscal_test snapshot` | Capa C de solo lectura | Informe de conteo/SHA; **sin** escribir QA |
| 6 | `feat(partner-dgii): add HTTP adapter without dropping legacy tables` | Cliente + wizard remoto; tablas viejas intactas | Tests B en base desechable |
| 7 | `feat(partner-dgii): split match and fiscal verify states` | Campos, eventos, alta manual | Tests B manual/ausente |
| 8 | `feat(partner-dgii): add reconciliation jobs` | Pull de versión, lotes, unique aviso | Tests E |
| 9 | `feat(partner-dgii): add name approval wizard` | Trazabilidad | Tests E aprobación/rechazo |
| 10 | `feat(partner-dgii): migrate 18.0.2.0.0 backfill` | Idempotente | Legacy counts estables |
| 11 | `test(partner-dgii): two-database isolation` | Capa D | Mismo RNC, dos partners, un padrón |
| 12 | `chore: update install/verify scripts and beginner docs` | SHARED/LOCAL | Scripts rechazan bases protegidas |
| 13 | `docs: POS e-CF decision matrix freeze` | Solo si hay nueva fuente DGII | Sin código de conversión |
| 14+ | `feat(ecf)` / `feat(pos)` | **Otras fases** | CerteCF real antes de afirmar integración |

El commit 0 no incluye código de servicio. Los commits 13+ no arrancan sin autorización expresa.

---

## 14. Riesgos y no afirmaciones

- No se ejecutó la suite Odoo ni el importador del servicio en esta entrega.
- No hay integración e-CF certificada.
- `secuenciaUtilizada` no cubre, en el texto oficial citado, el rechazo por comprador: **no** se reutilizará e-NCF en ese caso hasta validar códigos.
- El ZIP DGII puede desfasarse respecto al Registro en línea; “no encontrado” ≠ inválido.
- SHARED concentra un secreto de instalación por cliente: rotación y firewall son obligatorios antes de producción.

---

## 15. Criterio de aprobación para pasar a implementación

- [ ] SHARED/LOCAL y “el servicio no escribe contactos” aceptados.
- [ ] Máquinas A/B (y C diferida) aceptadas.
- [ ] Matriz §6.9: celdas pendientes **no** se implementan como reglas fiscales.
- [ ] Migración sin DROP y sin tocar `korventis` / `baruchcafe` / padrón de `korventis_fiscal_test`.
- [ ] Eliminación del contexto `staging` aceptada.
- [ ] Autorización explícita para el commit 1.
