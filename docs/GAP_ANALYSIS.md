# GAP Analysis — Korventis Fiscal RD vs Odoo 18 Community

Fecha: 2026-09-14. Rama: `feature/fiscal-core`.

Leyenda de origen:

- **Community:** existe en `github.com/odoo/odoo` rama `18.0`.
- **Enterprise:** documentado por Odoo / no está en el repositorio Community.
- **OCA:** asociación comunitaria; licencia típica AGPL-3 (riesgo comercial).
- **Korventis:** desarrollo propio requerido.
- **DGII:** fuente normativa (ver `DGII_SOURCES.md`).

| Requisito | Odoo Community | l10n_do (18.0 Community) | OCA | Korventis requerido | Fuente DGII |
| --- | --- | --- | --- | --- | --- |
| Catálogo de cuentas RD | No | Sí (CSV 8 dígitos, NIIF/DGII) | No específico 18.0 OCA l10n-do | Reutilizar `l10n_do`; no duplicar | Alineación contable, no sustituye NCF |
| Impuestos ITBIS/ISR/ISC/propina | `account.tax` genérico | Sí: 18%, 16%, 9%, 8%, exento, retenciones, 10% propina, ISC telco | No | Mapear impuestos a líneas e-CF; no reinventar tasas | Decreto/normas ITBIS; Guía FE |
| Posiciones fiscales | `account.fiscal.position` | Sí (gobierno, especial, restaurante, informal, exterior, etc.) | No | Extender si hace falta tipo de comprobante por posición | NG impuestos/retenciones |
| NCF tradicionales | No | Manifest histórico menciona secuencias **pero el código 18.0 no las implementa** | INDEXA `l10n-dominicana` (LGPL-3, default 17.0, **no validado 18**) | Sí: tipos, rangos, asignación transaccional | NG 06-18; Guía 5; portal secuencia |
| e-NCF | No | No | No oficial OCA | Sí (Fase 3-4) | Formato e-CF V1.0 |
| POS | `point_of_sale` | Solo cuenta POS receivable en chart | Varios POS OCA | Orquestar emisión fiscal al pagar | DGII: el comprobante nace al emitir, no al abrir mesa |
| Restaurante / mesa / cuenta | `pos_restaurant` (Community: mesas, bill print, split) | Posición fiscal Restaurantes + 10% propina | OCA pos extras | **No asignar NCF a cuenta/proforma** | RI es del e-CF, no de pre-cuenta |
| XML e-CF | No | No | `edi_xml_oca` genérico (AGPL) | Builder propio contra XSD DGII | Formato e-CF + XSD |
| XSD | No | No | No | Versionar XSD oficiales | Portal Documentación e-CF |
| Firma XMLDSig SHA-256 | No | No | No estándar DGII | Servicio `xml_signer` | Instructivo Firmado de e-CF |
| QR fiscal / código seguridad | QR de ticket POS **no es** timbre DGII | No | No | Implementar según Preguntas Técnicas | Preguntas Técnicas e-CF; Informe Técnico |
| TrackID / consulta estado | No | No | No | Cliente DGII + persistencia | Descripción Técnica Servicios DGII |
| API DGII directa | No | No | No | `DGIIProvider` | Mismos servicios; ambientes testecf/certecf/ecf |
| RNC | `res.partner.vat` | País DO; validación específica limitada en 18.0 (PR posterior de identificadores no es 18.0 estable) | `base_vat` Community | Validación estructural + estado DGII separado | Alertas 607; Consulta RNC |
| Cédula | Identificadores extra Community/`l10n_latam` según edición | **No hay modelo propio de cédula en l10n_do 18.0** | Posible `partner_identification` OCA | Campo/tipo de ID en partner | Longitud 11 en formatos DGII |
| 606 | No | Tax report ITBIS **no es** 606 | No 18.0 RD | Generador TXT + tests vs plantilla oficial | NG 07-18; instructivo 606 |
| 607 | No | No | No | Igual | NG 07-18 |
| 608 | No | No | No | Igual | Instructivo 608 |
| Notas crédito/débito | `account.move` refund | Impuestos de refund en chart | No fiscal RD | Tipo fiscal 33/34 o B03/B04 + referencia al documento origen | Formato e-CF 33/34 |
| Contingencia | No | No | No | Fase 5 | Instructivo Contingencia FE |
| Auditoría fiscal append-only | Chatter `mail.message` (editable/borrable según ACL) | No | `auditlog` OCA (AGPL) | Modelo evento inmutable propio | Trazabilidad operativa Korventis + DGII |
| Multiempresa | `res.company` nativo | Chart por compañía al instalar | `base_multi_company` | `company_id` + record rules en secuencias y documentos | Secuencias autorizadas por RNC/contribuyente |
| Secuencias genéricas | `ir.sequence` (no FOR UPDATE fiscal, no rango DGII, no vigencia) | No usable para NCF (el propio manifest 18.0 lo admite) | No | Modelo de rango fiscal + lock SQL | NG 06-18 |
| EDI RD Odoo | No | **`l10n_do_edi` no está en Community**; docs master lo describen con **Infile** (intermediario comercial, Enterprise) | `OCA/edi-framework` AGPL genérico | Implementación propia DGII; Infile/Alanube opcionales | Servicios DGII |
| Reportes financieros RD | QWeb Community limitado; `account_reports` avanzado es Enterprise | `account_tax_report_data.xml` (reporte de impuestos localización) | OCA account-financial-report | 606/607/608 en módulo reports | Formatos envío |
| Permisos | Groups `account`, `point_of_sale` | No grupos fiscales RD | No | Grupos Usuario / Supervisor / Administrador | Delegaciones roles FE (instructivo DGII; Fase 4+) |

## Lectura del gap

Community + `l10n_do` cubren **contabilidad de localización** (cuentas, impuestos, posiciones). **No cubren el ciclo fiscal DGII** (NCF/e-NCF, XML, firma, transmisión, RI, 606/607/608, contingencia).

Enterprise `l10n_do_edi` no es opción: no está en Community, usa Infile y es código propietario.

INDEXA y forks comerciales/comunitarios de NCF son **referencia secundaria**. Copiarlos viola la política del proyecto (validación 18, licencia, no sustituir DGII).
