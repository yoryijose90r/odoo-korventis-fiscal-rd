# Korventis Partner DGII

Módulo independiente para Odoo 18 Community que mantiene un padrón DGII local,
permite buscar clientes y ofrece un registro asistido. Depende del núcleo
`korventis_l10n_do_fiscal`, pero no modifica su contabilización, secuencias,
notas E34, documentos ni eventos.

## Fuente y formato

Fuente principal:

`https://dgii.gov.do/app/WebApps/Consultas/RNC/RNC_CONTRIBUYENTES.zip`

El importador acepta dos adaptadores comprobados y los valida por separado:

- CSV Latin-1 con seis encabezados oficiales.
- TXT alternativo delimitado por `|`, únicamente cuando una URL oficial
  alternativa es configurada.

Sólo se aceptan URLs HTTPS cuyo host sea `dgii.gov.do` o `www.dgii.gov.do`.
Cada ZIP debe contener un único CSV/TXT regular, no cifrado, sin rutas y dentro
de los límites configurados. El archivo original se conserva como adjunto de la
versión activa/anterior.

## Importación

- Descarga temporal con límites, timeouts, tres intentos y reanudación HTTP.
- SHA-256 y soporte de `ETag`/`Last-Modified`.
- Lectura streaming y `COPY` por lotes hacia una tabla temporal PostgreSQL.
- Validación de volumen, duplicados, rechazos y estructura.
- Activación atómica después de completar staging.
- Advisory lock para evitar ejecuciones simultáneas.
- Se conserva una versión anterior recuperable.
- Un fallo conserva la versión activa y queda registrado sin detener Odoo.

Política de anomalías:

- Identificador distinto de 9/11 dígitos comprobados: fila rechazada.
- Fecha inválida: registro importado con fecha vacía y advertencia.
- Carácter de control inseguro: fila rechazada, sin sustitución arbitraria.
- ACTIVO, SUSPENDIDO y los demás estados se conservan; no crean bloqueos
  fiscales ni representan autorización para emitir comprobantes.

La tarea diaria se programa a las 05:00 UTC, equivalente a la 01:00 en
`America/Santo_Domingo` (UTC-4, sin horario estacional).

## Primera carga exclusivamente en QA

1. Confirmar espacio libre para la versión activa, candidata, adjuntos e índices.
2. Instalar el módulo con el comando indicado abajo.
3. Asignar `Usuario del padrón DGII` a usuarios de consulta y
   `Administrador del padrón DGII` al responsable de importación.
4. Abrir **Contactos > Padrón DGII > Importar ahora**.
5. Revisar la URL principal y, sólo si fue verificada, la alternativa oficial.
6. Ejecutar la importación.
7. Abrir **Ejecuciones** y comprobar estado, aceptados, rechazados,
   advertencias, duplicados, duración y SHA-256.
8. Abrir **Versiones** y confirmar una única versión activa.
9. Probar búsquedas exactas por RNC y por prefijo de razón social.
10. Medir `pg_total_relation_size('korventis_dgii_rnc')` y tiempos reales.

La búsqueda DGII permanece inactiva mientras no exista una versión activa; el
registro manual sigue disponible.

El adjunto de cada versión conserva el ZIP original (~27 MB observados). En QA
deben coexistir como máximo la versión activa y una anterior.

Los identificadores de 11 dígitos con cero inicial se guardan como texto. El
núcleo fiscal clasifica 9 dígitos como RNC y 11 como cédula; este módulo no
altera esa regla.

## Comandos para publicar la rama

Ejecutar localmente sólo después de aprobación:

```bash
git switch feature/partner-dgii-local
git status --short
git push -u origin feature/partner-dgii-local
```

## Instalación exclusivamente en QA

Los nombres de servicio, ruta y base deben sustituirse por los valores de QA.
No reutilizar estos comandos en producción.

```bash
cd <RUTA_REPOSITORIO_QA>
git fetch origin
git switch feature/partner-dgii-local
git pull --ff-only origin feature/partner-dgii-local
<ODOO_BIN> -c <ODOO_CONF_QA> -d <QA_DB> \
  -i korventis_partner_dgii --stop-after-init
```

Después, reiniciar únicamente el servicio Odoo de QA según su procedimiento
operacional y realizar la primera carga desde la interfaz.

## Reversión

### Reversión de datos

En **Versiones**, abrir la versión `Anterior recuperable` y pulsar
**Restaurar esta versión**. La operación usa el mismo advisory lock que el
importador y no modifica contactos ya creados.

### Retirar el módulo de QA

1. Desactivar la tarea `Korventis: actualizar padrón DGII`.
2. Desinstalar `korventis_partner_dgii` desde Apps en QA.
3. Confirmar que `korventis_l10n_do_fiscal` continúa instalado.
4. Sólo entonces cambiar el checkout de QA a la referencia anterior.

Los contactos creados son `res.partner` normales y no se eliminan
automáticamente. Al desinstalar se retiran los metadatos DGII del módulo, pero
se conservan los campos fiscales pertenecientes al núcleo fiscal.

## IAP

La herencia `_get_view()` elimina únicamente
`widget="field_partner_autocomplete"` de `name` y `vat` en formularios de
`res.partner` y `res.company`. La búsqueda Korventis no llama métodos IAP.

Permanecen instalados `iap`, `iap_mail` y `partner_autocomplete`:

- El cron estándar `Partner Autocomplete: Sync with remote DB` sigue definido
  cada hora, aunque en Odoo 18 su método `start_sync()` está deprecado y es
  un no-op.
- La creación de `res.company` realizada por usuario sistema puede ejecutar
  enriquecimiento automático por dominio y contactar IAP.
- La pantalla estándar de configuración puede consultar créditos IAP.

Por tanto, retirar el widget evita el autocompletado remoto en esos formularios,
pero no equivale a desactivar todas las comunicaciones IAP de Odoo.
