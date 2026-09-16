# Instalación de Korventis Partner DGII

Versión documentada: `18.0.1.1.0` (`korventis_partner_dgii`).

El módulo se instala con el mecanismo estándar de Odoo. No requiere `CREATE TABLE`,
`ALTER TABLE` ni `CREATE INDEX` manuales. No consulta licencias ni servicios de
Korventis para funcionar.

## Requisitos mínimos

- Odoo 18 Community.
- PostgreSQL 12 o superior, con privilegios para crear tablas e índices en la
  base del cliente.
- Módulos `contacts`, `partner_autocomplete` y `korventis_l10n_do_fiscal`
  (`18.0.1.3.1` o compatible).
- Idioma español instalado (`es_DO` recomendado) antes de usar el asistente
  de clientes.
- Espacio en disco para el ZIP DGII (~27 MB observados), su adjunto en el
  filestore, la versión activa y una versión anterior recuperable.
- El addons path debe incluir este repositorio.

Sustituya `<ODOO_BIN>`, `<ODOO_CONF>` y `<DB>` por los valores del entorno.
No use credenciales ni direcciones de producción en este documento.

## Instalación inicial (base nueva)

```bash
<ODOO_BIN> -c <ODOO_CONF> -d <DB> \
  -i korventis_l10n_do_fiscal,korventis_partner_dgii \
  --stop-after-init
```

Si el núcleo fiscal ya está instalado:

```bash
<ODOO_BIN> -c <ODOO_CONF> -d <DB> \
  -i korventis_partner_dgii --stop-after-init
```

La instalación debe terminar aunque DGII no esté accesible. No descarga el
padrón. La tarea diaria queda **inactiva**.

Comprobaciones inmediatas:

1. Apps: `korventis_partner_dgii` en estado instalado.
2. Contactos > Padrón DGII > Estado: módulo instalado, padrón pendiente.
3. Una sola tarea `Korventis: actualizar padrón DGII`, inactiva.
4. Asignar `Usuario del padrón DGII` y `Administrador del padrón DGII`.

## Primera carga (operación controlada)

1. Confirmar espacio en disco y ventana de mantenimiento.
2. Contactos > Padrón DGII > Importar ahora.
3. Conservar la URL principal oficial. La URL alternativa sólo si su
   procedencia oficial fue verificada.
4. No activar la tarea diaria hasta completar una importación correcta.
5. Revisar Estado: padrón activo, última sincronización correcta, sin error
   bloqueante.
6. Probar búsqueda por RNC y por razón social.

Si la descarga falla, el módulo sigue instalado. Reintente la importación.
No se activa un padrón incompleto.

## VPS dedicado

Una base, un filestore, un servicio Odoo. Instale sólo en esa base. La tarea
diaria, si se activa, corre en el proceso Odoo de esa instancia. El huso de
la importación es `America/Santo_Domingo`; no depende de la zona horaria del
sistema operativo.

## VPS compartido (multibase)

Cada base de cliente es un PostgreSQL independiente. Ejemplo de intención:

- Base A: Korventis.
- Base B: Baruch Café.

```bash
<ODOO_BIN> -c <ODOO_CONF> -d <DB_A> -i korventis_partner_dgii --stop-after-init
<ODOO_BIN> -c <ODOO_CONF> -d <DB_B> -i korventis_partner_dgii --stop-after-init
```

Instalar en `<DB_A>` no modifica `<DB_B>`. Cada base tiene sus tablas, contactos,
versiones, ejecuciones, parámetros y tarea `ir.cron`.

Los advisory locks de PostgreSQL son por base. No hay padrón compartido entre
clientes.

### Descarga del mismo ZIP por varias bases

Por defecto cada base descarga su propia copia y guarda su adjunto. No se
comparten filas ORM.

Estrategia opcional, no obligatoria: colocar un ZIP oficial ya validado en
una ruta absoluta del servidor y, **en cada base**, configurar

`korventis_partner_dgii.shared_archive_path`

Esa ruta es de sólo lectura compartida del sistema de archivos. Cada cliente
sigue importando a sus propias tablas. No usar un filestore ni una base
compartida entre clientes.

## Servidor local del cliente

El mismo comando `-i`. Active la tarea diaria sólo si el equipo permanecerá
encendido a la 1:00 a. m. de Santo Domingo o si acepta que Odoo ejecute el
cron en el siguiente arranque posterior a `nextcall`.

## Tarea programada

- Se crea exactamente una por base (`noupdate="1"`).
- Horario objetivo: 01:00 `America/Santo_Domingo` (sin DST; se almacena en
  UTC naive que usa Odoo).
- No se habilita en la instalación.
- El método del cron no descarga si
  `korventis_partner_dgii.auto_import_enabled` no es `True`.
