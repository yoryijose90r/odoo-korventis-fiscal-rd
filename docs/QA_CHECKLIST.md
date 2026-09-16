# Lista de comprobación QA

Base autorizada: `korventis_fiscal_test` (desechable). No usar `korventis`,
`baruchcafe` ni producción.

Rama: `feature/partner-dgii-local`.
Módulos: fiscal `18.0.1.3.1`, padrón `18.0.1.1.0`.

## Preparación

- [ ] Checkout de la rama en el servidor QA.
- [ ] `addons_path` incluye este repositorio.
- [ ] Variables `ODOO_BIN`, `ODOO_CONF`, `ODOO_DB=korventis_fiscal_test`.
- [ ] Respaldo opcional si la base QA no es recreable.

## Instalación / actualización

- [ ] `KORVENTIS_ACTION=install` o `upgrade` + `./scripts/install_korventis.sh` termina con código 0.
- [ ] `./scripts/verify_korventis.sh` imprime `VERIFY SUMMARY: pass`.
- [ ] El log no muestra descarga HTTP del ZIP durante `-i`/`-u`.
- [ ] Cron `Korventis: actualizar padrón DGII` inactivo si no se autorizó.

## Pruebas automatizadas

```bash
<ODOO_BIN> -c <ODOO_CONF> -d korventis_fiscal_test \
  --test-enable --stop-after-init \
  --test-tags=/korventis_partner_dgii
```

- [ ] La suite del módulo termina en verde (no basta `compileall`).
- [ ] `test_wizard_flow` pasa con fixtures locales (no depende del id 61).
- [ ] Si `korventis_fiscal_test` ya tiene el padrón oficial (~789 mil filas),
      `TestDgiiImporter` se omite a propósito; no borrar esa versión para
      forzar esos tests.

## Padrón (si ya hay importación QA)

Referencia observada, no un requisito de código: ~789 580 filas, versión activa
propia de esa base, SHA-256 del ZIP oficial, 0 duplicados.

- [ ] Una sola versión activa.
- [ ] Búsqueda por RNC y por razón social.
- [ ] `%` y `_` se tratan como literales.

## Asistente de clientes (manual)

- [ ] Un contacto existente aparece antes que el padrón.
- [ ] Confirmar un contribuyente crea **un** `res.partner`: RNC, razón social,
      país RD, `es_DO`, tipo E31.
- [ ] Estado y actividad DGII quedan en el contacto.
- [ ] Volver a elegir el mismo RNC no duplica.
- [ ] Cédula con ceros a la izquierda se conserva como texto.
- [ ] Registro manual exige tipo fiscal explícito.
- [ ] Crear el contacto **no** emite e-NCF.

## Fiscal

- [ ] Factura de cliente en borrador puede usar el botón de búsqueda.
- [ ] El e-NCF nace al **contabilizar**, no al crear el contacto.
- [ ] Una factura histórica conservó número y estado.

## Cron

- [ ] Sigue desactivado en QA salvo prueba expresa.
- [ ] `KORVENTIS_ENABLE_CRON=yes ./scripts/enable_dgii_cron.sh` sólo se prueba
      si hay padrón activo e importación correcta, y se vuelve a apagar después
      si QA debe permanecer sin descarga diaria.

## Criterios de aceptación para cerrar esta fase

1. Módulos instalables y actualizables por ORM, sin SQL por cliente.
2. Wizard cubierto por pruebas portables.
3. Instalador y verificador reutilizables, sin credenciales ni borrado de bases.
4. Documentación de instalación, multibase, importación y reversión.
5. `docs/POS_GAP_ANALYSIS.md` listo; **no** hay módulo POS Korventis todavía.

## No aceptar

- Merge a `test` o `main`.
- Tags.
- Despliegue a producción.
- Afirmar que las pruebas pasaron si sólo se compiló Python.
