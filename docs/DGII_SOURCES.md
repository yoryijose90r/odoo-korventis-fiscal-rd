# Fuentes DGII — Korventis Fiscal RD

Registro de requisitos vs. fuentes oficiales. Las fuentes secundarias (Alegra, Alanube, GitHub, blogs, módulos Odoo) no determinan reglas fiscales.

Fecha de inventario: 2026-09-14.

Convención:

- **Autoridad:** portal, PDF, XSD, ley, norma o aviso DGII.
- **[REQUIERE VALIDACIÓN DGII]:** no hay evidencia normativa suficiente para implementar el detalle.

## Índice de portales oficiales

| Recurso | URL |
| --- | --- |
| Documentación sobre e-CF | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/documentacionSobreE-CF.aspx |
| Facturación electrónica (portal) | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/default.aspx |
| Asignación de secuencia NCF / e-NCF | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscales/Paginas/secuenciaNCF.aspx |
| Formatos de envío de datos (606/607/608) | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscales/Paginas/formatos-envio-datos.aspx |
| Remisión de información | https://dgii.gov.do/cicloContribuyente/obligacionesTributarias/remisionInformacion/Paginas/formatoEnvioDatos.aspx |
| Consulta RNC | https://dgii.gov.do/app/WebApps/ConsultasWeb2/ConsultasWeb/consultas/rnc.aspx |
| Ley 32-23 | https://dgii.gov.do/transparencia/baseLegal/Documents/Leyes/Ley%2032-23.pdf |

## Requisitos

### NCF tradicionales

| Campo | Valor |
| --- | --- |
| REQUISITO | Identificación alfanumérica autorizada por DGII para comprobantes no electrónicos. |
| FUENTE DGII | Guía 5 Comprobantes Fiscales; Norma General 06-18; portal Asignación de Secuencia. |
| URL | https://dgii.gov.do/publicacionesOficiales/bibliotecaVirtual/contribuyentes/facturacion/Documents/Comprobantes%20Fiscales/1-Guia%205-Comprobantes%20Fiscales.pdf |
| DOCUMENTO | Guía 5 Comprobantes Fiscales; NG 06-18; Aviso 29-25. |
| VERSIÓN/FECHA | NG 06-18; Aviso vencimiento secuencias 2024 (vigencia hasta 2025-12-31, aviso 2025). |
| SECCIÓN | Definición NCF; tipos B01/B02/B03/B04/B11 y homólogos electrónicos. |
| CONCLUSIÓN | Las secuencias las autoriza DGII. Vigencia general: hasta dos años calendario (hasta 31 de diciembre del año siguiente al de autorización), con excepciones documentadas para consumo, notas de crédito y RUI. No emitir fuera de rango ni vencidos. |

### e-CF / e-NCF

| Campo | Valor |
| --- | --- |
| REQUISITO | Comprobante fiscal electrónico firmado, con e-NCF y transmisión a DGII. |
| FUENTE DGII | Ley 32-23; Formato e-CF V1.0; Informe Técnico e-CF v1.0. |
| URL | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Formatos%20XML/Formato%20Comprobante%20Fiscal%20Electr%C3%B3nico%20(e-CF)%20V1.0.pdf |
| DOCUMENTO | Formato Comprobante Fiscal Electrónico (e-CF) V1.0 |
| VERSIÓN/FECHA | V1.0; página DGII indica modificación 30/10/2025. |
| SECCIÓN | Tabla de tipos 31, 32, 33, 34, 41, 43, 44, 45, 46, 47. |
| CONCLUSIÓN | Tipos electrónicos oficiales: 31 crédito fiscal, 32 consumo, 33 ND, 34 NC, 41 compras, 43 gastos menores, 44 regímenes especiales, 45 gubernamental, 46 exportaciones, 47 pagos al exterior. Todo e-CF debe ir firmado digitalmente. |

### Tipos de comprobante (catálogo)

| Campo | Valor |
| --- | --- |
| REQUISITO | Catálogo de tipos NCF vs e-CF. |
| FUENTE DGII | Formato e-CF V1.0; Guía 5. |
| URL | Documentación sobre e-CF (Formatos XML). |
| DOCUMENTO | Formato e-CF V1.0; Guía 5. |
| VERSIÓN/FECHA | V1.0 / Guía 5. |
| SECCIÓN | Tabla tipo / e-CF. |
| CONCLUSIÓN | Homologación Bxx ↔ Exx está en Guía 5 para los tipos principales. **[REQUIERE VALIDACIÓN DGII]** catálogo completo vigente de series B (p. ej. B12/B13/B15/B16/B17 y excepciones de vigencia) antes de hardcodear el maestro. |

### Secuencias

| Campo | Valor |
| --- | --- |
| REQUISITO | Autorización, rango, vigencia y no reutilización indebida. |
| FUENTE DGII | NG 06-18 arts. 5-6; portal secuencia NCF; Aviso 29-25. |
| URL | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscales/Paginas/secuenciaNCF.aspx |
| DOCUMENTO | Norma General 06-18; Aviso vencimiento secuencias. |
| VERSIÓN/FECHA | NG 06-18; aviso 2025. |
| SECCIÓN | Asignación según actividad, volumen, cumplimiento y riesgo. |
| CONCLUSIÓN | El software no “inventa” rangos: consume rangos autorizados. Solicitar nuevas secuencias requiere haber reportado las emitidas del mismo tipo. **[REQUIERE VALIDACIÓN DGII]** reglas exactas de reutilización de e-NCF cuando recepción RFCE indica `secuenciaUtilizada` (existe en Descripción Técnica Servicios DGII, actualización 18-05-2023). |

### Firma digital

| Campo | Valor |
| --- | --- |
| REQUISITO | Firma XML del e-CF y de la semilla de autenticación. |
| FUENTE DGII | Firmado de e-CF; Descripción Técnica Servicios DGII. |
| URL | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Instructivos%20sobre%20Facturaci%C3%B3n%20Electr%C3%B3nica/Firmado%20de%20e-CF.pdf |
| DOCUMENTO | Firmado de e-CF |
| VERSIÓN/FECHA | Página DGII: modificado 22/11/2023. |
| SECCIÓN | SignatureMethod / DigestMethod SHA-256; XMLDSig; certificado .p12. |
| CONCLUSIÓN | Algoritmo obligatorio RSA-SHA256 / SHA-256. Certificado digital para procesos tributarios. No copiar el código Java de ejemplo de DGII a Korventis sin revisión de licencia del instructivo; sí seguir el estándar XMLDSig descrito. |

### XML / XSD

| Campo | Valor |
| --- | --- |
| REQUISITO | Estructura XML validada contra XSD oficiales por tipo. |
| FUENTE DGII | Documentación Técnica (XSD) en portal e-CF. |
| URL | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/documentacionSobreE-CF.aspx |
| DOCUMENTO | e-CF 31..47 v1.0; RFCE 32; ARECF; ANECF; ACECF; Semilla. |
| VERSIÓN/FECHA | XSD e-CF 31/32/41/43/44/45/46/47: 16/10/2025; e-CF 33/34: 01/04/2026; RFCE/ARECF/ANECF: 20/06/2023; ACECF: 21/12/2022; Semilla: 12/11/2020. |
| SECCIÓN | Documentación Técnica (XSD). |
| CONCLUSIÓN | Versionar XSD en `resources/xsd/<version>/` **después de autorización**. No incorporarlos en esta fase. Nombre de archivo XML: `RNC+e-NCF.xml` (ejemplo oficial `101672919E3100000001.xml`). |

### QR / código de seguridad / representación impresa

| Campo | Valor |
| --- | --- |
| REQUISITO | RI con campos obligatorios, QR y código de seguridad. |
| FUENTE DGII | Informe Técnico e-CF v1.0; Modelos ilustrativos RI; Preguntas Técnicas e-CF. |
| URL | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Preguntas%20frecuentes/T%C3%A9cnicas/Preguntas%20T%C3%A9cnicas%20e-CF.pdf |
| DOCUMENTO | Preguntas Técnicas e-CF (QR); Informe Técnico; Modelos ilustrativos (modificado 22/04/2025). |
| VERSIÓN/FECHA | Informe Técnico página DGII: 06/04/2026. |
| SECCIÓN | Preguntas 14-16 (RI y QR). |
| CONCLUSIÓN | Código de seguridad = primeros 6 dígitos del hash `SignatureValue`. QR e-CF general: `https://ecf.dgii.gov.do/ecf/ConsultaTimbre?` con RncEmisor, RncComprador, ENCF, FechaEmision (dd-mm-aaaa), MontoTotal, FechaFirma, CodigoSeguridad. QR consumo &lt; RD$250,000: `https://fc.dgii.gov.do/eCF/ConsultaTimbreFC` con RNCEmisor, ENCF, MontoTotal, Código Seguridad. **[REQUIERE VALIDACIÓN DGII]** URLs equivalentes de TesteCF/CerteCF para RI de certificación, encoding exacto de querystring y umbral 250,000 vs 250 mil en distintos documentos. |

### Autenticación, semilla, JWT

| Campo | Valor |
| --- | --- |
| REQUISITO | GET semilla → firmar → POST validarsemilla → JWT (~1 hora). |
| FUENTE DGII | Descripción Técnica Servicios DGII. |
| URL | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Informe%20y%20Descripci%C3%B3n%20T%C3%A9cnica/Descripcion%20Tecnica%20Servicios%20DGII.pdf |
| DOCUMENTO | Descripción Técnica Servicios DGII (modificado 29/05/2026). |
| VERSIÓN/FECHA | Actualizaciones internas del PDF hasta al menos 12-06-2023; página 29/05/2026. |
| SECCIÓN | Autenticación. |
| CONCLUSIÓN | Ambientes: `testecf` (pre-certificación), `certecf` (certificación), `ecf` (producción). Base: `https://ecf.dgii.gov.do/{ambiente}/autenticacion`. GET `/api/autenticacion/semilla`. POST `/api/autenticacion/validarsemilla` multipart xml. Token no permanente. |

### Transmisión, TrackID, consulta, RFCE, aprobación, anulación

| Campo | Valor |
| --- | --- |
| REQUISITO | Recepción XML firmado, TrackId, consulta de estado, RFCE &lt; 250,000, aprobación comercial, anulación de rangos. |
| FUENTE DGII | Descripción Técnica Servicios DGII. |
| URL | Mismo PDF de servicios. |
| DOCUMENTO | Descripción Técnica Servicios DGII. |
| VERSIÓN/FECHA | 29/05/2026 (página). |
| SECCIÓN | Recepción; Consulta resultado; Consulta trackids; RFCE; Aprobación comercial; Anulación rangos. |
| CONCLUSIÓN | Recepción TesteCF: `https://ecf.dgii.gov.do/testecf/recepcion` recurso `/api/facturaselectronicas`. Consulta resultado: `.../consultaresultado/api/consultas/estado` con TrackId. TrackId es acuse, no aceptación fiscal. Timeout no implica rechazo: consultar estado / trackids antes de reemitir. RFCE en dominio `fc.dgii.gov.do`. **No se realizaron llamadas.** |

### Contingencia

| Campo | Valor |
| --- | --- |
| REQUISITO | Operar cuando no se puede emitir y/o enviar e-CF. |
| FUENTE DGII | Instructivo de Contingencia de FE; Guía básica emisor; Modelos RI. |
| URL | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Documentacin%20sobre%20eCF/Instructivos%20sobre%20Facturaci%C3%B3n%20Electr%C3%B3nica/Instructivo-Contingencia-FE.pdf |
| DOCUMENTO | Instructivo Contingencia FE (página: 25/02/2026). |
| VERSIÓN/FECHA | 25/02/2026. |
| SECCIÓN | Falta de conectividad vs incapacidad técnica; declaración en OFV. |
| CONCLUSIÓN | Conectividad: e-CF offline, envío ≤ 72 horas, leyenda específica en RI. Incapacidad de emitir e-CF: NCF no electrónicos autorizados, reemplazo e-CF ≤ 30 días, contingencia no mayor a 15 días calendario (según instructivo/guía). Declaración entrada en contingencia vía OFV. **Fase 5; no implementar ahora.** Detalle de API de contingencia vs solo OFV: **[REQUIERE VALIDACIÓN DGII]**. |

### 606 / 607 / 608

| Campo | Valor |
| --- | --- |
| REQUISITO | Remisión mensual de compras, ventas y NCF anulados. |
| FUENTE DGII | Portal formatos; NG 07-18; instructivos de llenado. |
| URL | https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscales/Paginas/formatos-envio-datos.aspx |
| DOCUMENTO | Instructivos 606 y 608; paso a paso 606/607/608/609. |
| VERSIÓN/FECHA | NG 07-18 / 05-2019; formatos a partir período mayo 2018. |
| SECCIÓN | Plazo: primeros 15 días del mes siguiente. |
| CONCLUSIÓN | 606 compras/costos/retenciones; 607 ventas; 608 anulados. También existe 609 pagos al exterior. Archivos TXT prevalidables. Períodos sin operaciones: informativos en cero. **No implementar campos de memoria; versionar plantillas oficiales en Fase 6.** Layout exacto de columnas TXT: **[REQUIERE VALIDACIÓN DGII]** mediante descarga de plantillas vigentes (no hechas en Fase 0). |

### Notas de crédito y débito

| Campo | Valor |
| --- | --- |
| REQUISITO | NC/ND electrónicas tipos 34 y 33; tradicionales B04/B03. |
| FUENTE DGII | Formato e-CF V1.0; Guía 5. |
| URL | Formato e-CF V1.0. |
| DOCUMENTO | Formato e-CF; Guía 5. |
| VERSIÓN/FECHA | V1.0. |
| SECCIÓN | Tipos 33 y 34. |
| CONCLUSIÓN | NC/ND son comprobantes propios, no “editar” el original. Relación con e-CF modificado está en el formato XML. Campos obligatorios de referencia: implementar contra XSD 33/34 (actualizados 01/04/2026). |

### RNC / Cédula

| Campo | Valor |
| --- | --- |
| REQUISITO | Identificación del emisor/comprador; longitud 9 (RNC) u 11 (cédula). |
| FUENTE DGII | Comunidad de ayuda DGII (alertas 607); consulta RNC; formatos de envío. |
| URL | https://ayuda.dgii.gov.do/conversations/formatos-de-envo-de-datos/ca3904-cules-son-las-principales-alertas-que-se-pueden-presentar-al-validar-el-formato-607-en-la-herramienta-de-excel/5f3c17998cd858ce87a20d04 |
| DOCUMENTO | Alertas prevalidación 607; consulta RNC. |
| VERSIÓN/FECHA | Pregunta CA3904 (comunidad oficial DGII). |
| SECCIÓN | Encabezado RNC/Cédula. |
| CONCLUSIÓN | Estructura: 9 u 11 dígitos; alerta de dígito verificador incorrecto en herramienta DGII. **No se encontró algoritmo oficial publicado del dígito verificador.** Tratar checksum como validación estructural a confirmar. Consulta de existencia: portal Consulta RNC. `format_valid`, `checksum_valid` y `dgii_verified` son conceptos distintos. |

### Aprobación comercial / acuse / anulación de secuencias

| Campo | Valor |
| --- | --- |
| REQUISITO | ACECF, ARECF, ANECF. |
| FUENTE DGII | Formatos XML + XSD correspondientes; servicios DGII. |
| URL | Portal Documentación sobre e-CF. |
| DOCUMENTO | Formato Aprobación Comercial V1.0; Acuse v1.0; Anulación e-CF V1.0. |
| VERSIÓN/FECHA | ACECF formato 10/01/2020; ARECF 30/10/2025; ANECF 20/06/2022. |
| SECCIÓN | Formatos XML. |
| CONCLUSIÓN | Necesarios para emisor-receptor electrónico. Fuera de Fase 1. |

## Recursos oficiales a conservar (aún no descargados)

Propuesta de destino futuro (Fase 3+), sin incorporar archivos ahora:

```
docs/dgii/
  README.md                 # índice, fecha de descarga, URL, hash
  leyes/Ley_32-23.pdf
  normas/NG_06-18.pdf
  normas/NG_07-18.pdf
  ecf/Informe_Tecnico_e-CF_v1.0.pdf
  ecf/Descripcion_Tecnica_Servicios_DGII.pdf
  ecf/Descripcion_Tecnica_Facturacion_Electronica.pdf
  ecf/Descripcion_Tecnica_Emisores_Electronicos.pdf
  ecf/Formato_e-CF_V1.0.pdf
  ecf/Firmado_e-CF.pdf
  ecf/Instructivo_Contingencia_FE.pdf
  ecf/Representacion_Impresa_modelos.pdf
  ecf/Preguntas_Tecnicas_e-CF.pdf
  ncf/Guia_5_Comprobantes_Fiscales.pdf
  reportes/instructivo_606.pdf
  reportes/instructivo_608.pdf
  reportes/paso_a_paso_formatos.pdf
resources/xsd/<fecha-version>/
  eCF31.xsd ... eCF47.xsd
  RFCE.xsd ARECF.xsd ANECF.xsd ACECF.xsd Semilla.xsd
```

**Por qué son necesarios:** son la fuente estructural (XSD), de servicios (endpoints), de RI/QR y de reportes. **Por qué no se descargan ahora:** Fase 0 solo identifica; hace falta registrar licencia/condiciones de reproducción DGII y hash SHA-256 al incorporar.

## Fuentes explícitamente no normativas

- Documentación Odoo `l10n_do_edi` / Infile.
- Alanube, Alegra, ef2, INDEXA, blogs, StackOverflow.
- Algoritmos de dígito verificador en librerías comunitarias (`python-stdnum`, `dgii-ts`) hasta contrastarlos con DGII.
