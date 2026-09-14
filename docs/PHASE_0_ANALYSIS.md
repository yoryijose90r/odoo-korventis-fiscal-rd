# FASE 0 — Análisis técnico y fiscal

**Proyecto:** Korventis Fiscal RD  
**Repositorio:** github.com/yoryijose90r/odoo-korventis-fiscal-rd  
**Rama:** `feature/fiscal-core`  
**Fecha:** 2026-09-14  
**Alcance:** documentación. Sin código Odoo, sin merge, sin llamadas DGII, sin despliegue QA.

Documentos hermanos:

- `docs/DGII_SOURCES.md`
- `docs/GAP_ANALYSIS.md`
- `docs/ARCHITECTURE_PROPOSAL.md`

---

## 1. Resumen ejecutivo

Odoo 18 Community + `l10n_do` entregan un **plan de cuentas, impuestos ITBIS/ISR y posiciones fiscales**. **No** entregan NCF, e-NCF, XML, firma, QR DGII, TrackID, contingencia ni formatos 606/607/608.

El EDI oficial Odoo (`l10n_do_edi`) **no está en Community**, está documentado con **Infile** y es **Enterprise/propietario**. No debe copiarse ni usarse como dependencia.

La ruta de producto es **core fiscal propio** + **integración directa DGII** (documentación oficial 2025–2026), con MockProvider en tests y Alanube **opcional**. El POS Community (`pos_restaurant`) ya imprime cuentas **sin** factura; Korventis debe **prohibir** NCF en ese punto.

QA (`http://143.198.119.38:8069`) **no fue inspeccionado**: no hay acceso al VPS desde este entorno. Ver sección 10.

---

## 2. A. Odoo 18 Community — qué existe de verdad

Clasificación: **COMMUNITY** | **ENTERPRISE** | **OCA** | **KORVENTIS**.

| Capacidad | Edición | Notas |
| --- | --- | --- |
| `account` / `account.move` / facturas, NC como refund | COMMUNITY | Invoicing. Asientos, impuestos, journals. |
| Contabilidad avanzada, bank sync, `account_reports` UI completa | ENTERPRISE (`accountant` / `account_accountant` / `account_reports`) | No asumir conciliación bancaria nativa Community. |
| `account.tax`, `account.fiscal.position`, chart templates | COMMUNITY | Localizaciones vía `account.chart.template`. |
| `res.company`, `res.partner`, `vat`, multiempresa | COMMUNITY | Record rules estándar. |
| `ir.sequence` | COMMUNITY | **Insuficiente** para rangos DGII + lock fiscal. |
| QWeb / `ir.actions.report` | COMMUNITY | Sirve para RI; el layout lo define DGII. |
| Chatter / `mail.message` | COMMUNITY | No es auditoría fiscal inmutable. |
| Grupos de acceso | COMMUNITY | Hay que crear grupos Korventis. |
| `point_of_sale`, `pos.order`, pagos, invoice-on-payment | COMMUNITY | Invoice requiere cliente. |
| Recibo POS, header/footer, QR de ticket | COMMUNITY | QR de ticket **≠** timbre DGII. |
| `pos_restaurant`: mesas, bill print, split | COMMUNITY (addon en `odoo/odoo` 18.0) | Cuenta abierta = draft. Blogs que niegan mesas en Community están **desactualizados**. |
| Kitchen Display / IoT Box / POS offline “Enterprise” | ENTERPRISE o terceros | No bloquear Fase 1. |
| `l10n_do` | COMMUNITY | Ver sección B. |
| `l10n_do_edi`, `l10n_do_reports` (docs master) | ENTERPRISE | Fuera de alcance. Infile. |
| EDI genérico | OCA AGPL | Evitar hasta decisión de licencia. |
| NCF/e-CF DGII | KORVENTIS | Gap total. |

### POS y facturación (Community)

Flujo real:

1. Mesa / orden draft → **sin** `account.move` fiscal DGII.
2. Print Bill → recibo no final.
3. Payment + Invoice → `account.move` estándar Odoo (número interno, no NCF).
4. Reimpresión de factura Odoo reutiliza el move; **tampoco** tiene NCF.

Korventis debe engancharse en (3) y en la política de “siempre emitir comprobante al cobrar en RD”, no en (1)-(2).

---

## 3. B. `l10n_do` Odoo 18 Community (código real)

Fuente: `https://github.com/odoo/odoo/tree/18.0/addons/l10n_do`.

### Manifest

- Nombre: Dominican Republic - Accounting.
- Versión módulo: `2.0`.
- `depends`: `account`, `base_iban`.
- `license`: LGPL-3.
- `auto_install`: con `account`.
- Autor histórico: Gustavo Valverde / iterativo (texto del manifest).
- **Nota del propio manifest:** las secuencias NCF mencionadas **no pueden usarse** sin módulos de terceros o desarrollo adicional.

### Modelos

- Único Python: `models/template_do.py` → hereda `account.chart.template`.
- **No** extiende `account.move`, `res.partner`, ni crea modelos NCF.

### Datos

- `data/template/account.account-do.csv` — catálogo 8 dígitos.
- `account.group-do.csv`
- `account.tax-do.csv` / `account.tax.group-do.csv`
- `account.fiscal.position-do.csv`
- `data/account_tax_report_data.xml` — reporte de impuestos.
- `demo/demo_company.xml`

### Impuestos (muestra)

ITBIS 18% venta/compra, 16% compra, 9%/8% (L690-16), exento, importación, 10% propina legal, ISC/CDT telecomunicaciones, retenciones ITBIS 100/30/75%, ISR 15/10/5/3/2/27% según caso.

### Posiciones fiscales

Incluyen restaurantes, para llevar, gubernamental, regímenes especiales, informal, servicios del exterior, no lucrativas, vigilancia, persona física servicios.

### Qué NO proporciona `l10n_do` 18.0

- NCF / e-NCF / rangos / vigencia.
- Tipos de identificación RNC vs Cédula como modelo.
- EDI, XML, firma, TrackID.
- 606/607/608.
- POS fiscal.
- `l10n_do_edi`, `l10n_do_ncf`, `l10n_do_reports` **no existen** en este árbol Community.

---

## 4. C. QA real — sin acceso

No hay SSH, Docker ni código del servidor `143.198.119.38` en este workspace. **No se inventan** módulos instalados ni versión patch.

### [INFORMACIÓN REQUERIDA DEL VPS QA]

Comandos **solo lectura** para el administrador (Linux típico). Ajustar usuario/rutas reales. **No ejecutar** cambios, **no** reiniciar, **no** `odoo-bin` con `--init`.

```bash
# Identidad y red
hostname; uname -a
curl -sI http://127.0.0.1:8069 | head

# Docker (si aplica)
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker compose ls

# Versión Odoo dentro del contenedor (nombre a sustituir)
docker exec <odoo_container> odoo --version
# o
docker exec <odoo_container> python3 -c "import odoo; print(odoo.release.version)"

# Configuración (leer, no editar)
docker exec <odoo_container> grep -E '^(addons_path|db_name|db_host|http_port|without_demo|workers)' /etc/odoo/odoo.conf
# ruta alternativa frecuente:
docker exec <odoo_container> grep -E '^(addons_path|db_name)' /etc/odoo.conf

# Addons montados
docker exec <odoo_container> ls -la /mnt/extra-addons /usr/lib/python3/dist-packages/odoo/addons 2>/dev/null | head

# PostgreSQL
docker exec <postgres_container> psql -U odoo -d postgres -c '\l'
```

SQL de solo lectura (reemplazar `DBNAME` y usuario):

```sql
SELECT latest_version FROM ir_module_module WHERE name = 'base';
SELECT name, state, latest_version
  FROM ir_module_module
 WHERE name IN (
   'account','l10n_do','point_of_sale','pos_restaurant','stock','sale'
 )
 ORDER BY name;
SELECT name, state, author, license
  FROM ir_module_module
 WHERE state = 'installed'
 ORDER BY name;
SELECT name FROM ir_module_module
 WHERE state = 'installed' AND name ILIKE '%oca%' OR name ILIKE '%l10n_do%';
```

Entregar: imagen Docker Odoo, tag exacto (`18.0-YYYYMMDD`), `addons_path`, lista installed, si hay forks `l10n_do_*`, OCA, y si el POS restaurante está instalado.

**Restricción QA de producto (aún no implementada):** `DGII_ENVIRONMENT=testecf`, `DGII_TRANSMISSION_ENABLED=False`, `DGII_ALLOW_PRODUCTION=False`.

---

## 5. D–F. DGII, descargas e integración directa

Ver `docs/DGII_SOURCES.md` (tablas por requisito).

Flujo oficial **sin llamadas realizadas**:

```
Odoo
  → build XML (tag raíz ECF)
  → validate XSD
  → sign XMLDSig RSA-SHA256
  → GET semilla
  → POST semilla firmada → JWT (~1 h)
  → POST recepción XML + Bearer
  → TrackId (acuse, no “aceptado”)
  → GET consulta estado / trackids
  → persistir respuesta
  → RI + QR + código seguridad (6 dígitos SignatureValue)
```

Ambientes (Descripción Técnica Servicios DGII):

| Ambiente | Uso | Autenticación | Recepción |
| --- | --- | --- | --- |
| TesteCF | Pre-certificación | `https://ecf.dgii.gov.do/testecf/autenticacion` | `https://ecf.dgii.gov.do/testecf/recepcion` |
| CerteCF | Certificación | `.../certecf/autenticacion` | `.../certecf/recepcion` |
| eCF | **Producción — prohibido en QA** | `.../ecf/autenticacion` | `.../ecf/recepcion` |

RFCE consumo &lt; RD$250,000 usa dominio `fc.dgii.gov.do`.

Guardia QA: bloquear URLs de producción aunque el usuario las pegue.

Korventis puede certificarse como **emisor con software propio** (proceso DGII) o apoyarse en PSFE. La arquitectura no debe **obligar** PSFE.

---

## 6. G. Alanube — OPCIONAL

| Tema | Hallazgo | Clasificación |
| --- | --- | --- |
| Naturaleza | PSFE / BaaS; API REST JSON; ellos XML+firma+DGII | COMERCIAL |
| Docs | https://developer.alanube.co | Secundaria |
| Sandbox | `https://sandbox.alanube.co/dom/v1/` | Pruebas con JWT de Alanube |
| Producción | `https://api.alanube.co/dom/v1/` | No usar |
| Auth | Bearer JWT emitido por Alanube (no semilla DGII) | Dependencia externa |
| Costos | Sandbox “sin costo” según docs; producción: contacto comercial +1 829 956 0059 / soporte@alanube.co | **Precio lista no publicado** |
| Limitaciones | Token comercial; cambios de API ajenos; datos fiscales en tercero; no sustituye certificación DGII del contribuyente | Riesgo de vendor lock-in |
| Odoo | Integrable como `AlanubeProvider` | Nunca `depends` |
| Uso QA | Comparar XML/estados **si Korventis autoriza** | No Fase 1 |

## 7. H. Alegra — referencia funcional, no normativa

| Tema | Hallazgo |
| --- | --- |
| Producto | SaaS contable/POS RD con e-CF (E31/E32, etc.) |
| POS | Marketing: e-CF 32 B2C / 31 B2B; opera con corte de red y sincroniza (fuente comercial) |
| API | https://developer.alegra.com (tipos `INVOICE_E31`, `INVOICE_B01`, …) |
| Costos | Prueba sin tarjeta según sitio POS; planes de pago no auditados aquí |
| Dependencia | PSFE/plataforma Alegra, no DGII directa |
| Korventis | **No copiar código ni reglas.** Útil para UX de “cuenta vs factura” y selección de tipo al cobrar |

## 8. I. Alternativas

| Alternativa | Tipo | API | Sandbox | DGII | Odoo | Licencia | Riesgo | Recomendación |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| API DGII directa | GRATIS (servicios Estado; certificado y certificación tienen costo/proceso) | REST oficial | TesteCF/CerteCF | Nativa | A construir | N/A | Complejidad, XSD, certificación | **Camino principal** |
| Facturador gratuito DGII | GRATIS (criterios DGII) | No es API ERP | N/A | Oficial | No integrable como motor | N/A | No escala POS | No como backend Korventis |
| Alanube | COMERCIAL | Sí | Sí | Vía PSFE | Provider opcional | Propietaria | Lock-in, costo | Opcional post-Fase 4 |
| ef2.do | COMERCIAL | REST JSON documentado | Afirma sandbox | PSFE | Provider posible | Propietaria | Igual | No integrar ahora |
| Infile (Odoo Enterprise EDI) | COMERCIAL | Vía `l10n_do_edi` | Docs Odoo | Intermediario | Enterprise only | Propietaria Odoo | Ilegal copiar | **Excluir** |
| INDEXA `l10n-dominicana` | OPEN SOURCE | NCF local | N/A | No e-CF DGII completo 18 | 17.0 default | LGPL-3 | No validado 18; no copiar | Referencia de UX NCF |
| `OCA/edi-framework` | OPEN SOURCE | Genérico | N/A | No RD | 18.0 | **AGPL-3** | Copyleft | Evitar v1 |
| `python-stdnum` / checksum RNC | OPEN SOURCE | N/A | N/A | No es autoridad | Utilidad | LGPL/GPL según paquete | Algoritmo no publicado por DGII | Solo si se documenta y se marca checksum ≠ verificado |
| Consulta RNC web DGII | GRATIS | HTML, no API estable pública documentada aquí | N/A | Oficial | Scraping frágil | N/A | ToS, rotura | Preferir API/listados oficiales si existen; **[REQUIERE VALIDACIÓN DGII]** web service RNC |

**Recomendación de alternativa gratuita útil:** los **servicios TesteCF de DGII** y el **Facturador gratuito** para comparar RI/XML durante certificación humana. Ninguna API comercial es necesaria para Fase 1.

---

## 9. Riesgos

1. Certificación DGII del software (set de pruebas, RI, acuse, aprobación comercial) es un proyecto en sí; Fase 4 no es “un cliente HTTP”.
2. XSD 33/34 actualizados 01/04/2026: el builder debe versionar.
3. `ir.sequence` → duplicados NCF bajo POS concurrente.
4. Draft `pos.order` en mesa dispara `sync_from_ui`: riesgo de emisión prematura si se engancha mal.
5. Enterprise `l10n_do_edi`/Infile como “atajo”.
6. AGPL OCA vs distribución comercial Korventis.
7. Secretos PFX en filestore Odoo o Git.
8. Confundir TrackId con “aceptado”.
9. QR de ticket POS vs timbre DGII.
10. 606/607/608: plantillas Excel/TXT cambian; no hardcodear de memoria.
11. Checksum RNC de internet ≠ contribuyente activo.
12. Producción DGII (`/ecf/` sin `testecf`) si un admin pega URL.
13. INDEXA/forks 16–17 incompatibles con ORM POS 18.
14. Contingencia 72 h / 15 días mal implementada → incumplimiento. Dejar Fase 5.
15. VPS QA desconocido: puede ya tener módulos conflictivos.

---

## 10. Información que hace falta del VPS QA

Ver sección 4. Mínimo: versión Odoo exacta, `addons_path`, módulos installed (account, l10n_do, POS, OCA), Docker/Postgres 15, addons custom, si hay certificado de prueba (sin copiar el archivo).

---

## 11. [REQUIERE VALIDACIÓN DGII]

Lista no exhaustiva; detalle en `DGII_SOURCES.md`:

1. Catálogo completo vigente de tipos **B** (no electrónicos) y excepciones de vigencia (RUI, etc.).
2. Algoritmo oficial del dígito verificador RNC/Cédula.
3. Existencia de API estable de consulta RNC (vs web).
4. Encoding exacto del querystring del QR y URLs de timbre en TesteCF/CerteCF.
5. Cuándo `secuenciaUtilizada` permite reutilizar e-NCF.
6. Layout binario/columnas TXT vigentes 606/607/608/609.
7. API vs solo OFV para declarar contingencia.
8. Umbral RFCE: documentos dicen RD$250,000 / 250 mil; confirmar regla vigente y redondeo.
9. Obligación de enviar e-CF al receptor electrónico vs solo DGII según tipo.
10. Conservación 10 años y medio de almacenamiento (Ley 32-23 / reglamento): implicación filestore.
11. Listado oficial actualizado de PSFE (si Korventis evalúa certificación propia vs PSFE).
12. Condiciones de reproducción de XSD/PDF en un repo privado comercial.

---

## 12. Recomendación para FASE 1

**Autorizar Fase 1 solo sobre `feature/fiscal-core`**, módulo `korventis_l10n_do_fiscal`, **sin** XML ni HTTP DGII.

Alcance Fase 1:

1. Catálogo de tipos (mínimo B01/B02/B03/B04/B11 y E31/E32/E33/E34/E41… según tabla e-CF, marcando B restantes como data incompleta si aplica).
2. Rangos por `company_id` + `SELECT FOR UPDATE` + UNIQUE.
3. Extensiones `res.company`, `res.partner`, `account.move`, `account.journal`.
4. `korventis.fiscal.document` estados `draft/reserved` (+ cancelación simple).
5. Eventos append-only.
6. Validación estructural RNC (9) / Cédula (11); checksum detrás de flag experimental.
7. Guardas QA de environment (aunque transmisión aún no exista).
8. Tests secuencia, concurrencia, partner, account.move.
9. Record rules y tres grupos.

**Fuera de Fase 1:** POS, XSD, firma, DGII, Alanube, 606, contingencia, merge a `test`/`main`.

Siguiente autorización humana requerida: diseño detallado de campos Python/XML de Fase 1 (regla 37) e implementación.
