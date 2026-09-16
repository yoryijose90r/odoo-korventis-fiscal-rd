# Despliegue futuro en producción

No ejecutar este procedimiento durante la Fase B.1. No usar la rama de
desarrollo como origen de producción.

El despliegue de producción, cuando se autorice, debe ser:

1. Respaldo verificable de PostgreSQL y filestore, con prueba de restauración
   en un entorno no productivo.
2. Código aprobado desde `main` y un tag de versión (por ejemplo
   `korventis-partner-dgii-18.0.1.1.0`). No desplegar commits sueltos de
   `feature/*`.
3. Instalación o actualización estándar:

   ```bash
   <ODOO_BIN> -c <ODOO_CONF_PROD> -d <DB_PROD> \
     -i korventis_partner_dgii --stop-after-init
   ```

   o, si el módulo ya está instalado:

   ```bash
   <ODOO_BIN> -c <ODOO_CONF_PROD> -d <DB_PROD> \
     -u korventis_partner_dgii --stop-after-init
   ```

4. Las migraciones versionadas corren dentro de `-u`. No pegar SQL de QA.
5. Validaciones automáticas (`--test-enable` en una copia, no necesariamente
   en la base viva) y revisión de Contactos > Padrón DGII > Estado.
6. Primera importación DGII controlada, reintentable, fuera del `-i`.
7. Verificación funcional: búsqueda, alta DGII, registro manual, factura en
   borrador sin asignar e-NCF al crear el contacto.
8. Registrar la versión instalada (Apps + tag + SHA de `main`).

## Prohibiciones

- No `CREATE`/`ALTER`/`INDEX` manuales.
- No copiar SQL usado en desarrollo o en la corrección histórica de secuencias
  de QA.
- No activar el cron hasta que la primera carga sea correcta.
- No mezclar bases de clientes.
- No introducir comprobaciones de licencia en el módulo.

Si un SQL correctivo excepcional resultara imprescindible, convertirlo antes
en una migración versionada, idempotente y documentada en
`docs/DATABASE_CHANGES.md`.
