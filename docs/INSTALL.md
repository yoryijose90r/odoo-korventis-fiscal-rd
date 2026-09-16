# Instalación desde cero

Versiones: `korventis_l10n_do_fiscal` `18.0.1.3.1` y `korventis_partner_dgii` `18.0.1.1.0`.

Este documento es para una **base nueva** de Odoo 18 Community. Si el cliente ya tiene
Odoo y el núcleo fiscal, use `docs/UPGRADE.md`. Si hay varias bases en el mismo
servidor, lea también `docs/MULTIDB.md`.

La instalación **no** descarga el padrón DGII y **no** activa la tarea diaria.
Eso se hace después, de forma controlada: `docs/DGII_IMPORT.md`.

No ejecute estos comandos contra producción ni contra las bases `korventis` o
`baruchcafe`.

## 1. Qué necesita

- Odoo 18 Community en marcha (VPS dedicado o servidor multibase).
- PostgreSQL con permiso para crear tablas e índices **dentro de la base del cliente**.
- El repositorio Korventis en el `addons_path` de esa instancia.
- Módulos estándar: `contacts`, `partner_autocomplete`, `account`, `l10n_do`.
- Idioma español activado (`es_DO` recomendado) antes de usar el asistente de clientes.
- Disco libre para el ZIP DGII (~27 MB), su adjunto y dos versiones del padrón.
- El usuario del sistema que ejecuta Odoo debe poder leer los addons.

No se requiere Odoo Enterprise, ni un bloqueo de licencia, ni SQL escrito a mano.

## 2. Rutas y permisos

1. Clone o actualice este repositorio en el servidor.
2. Añada esa carpeta al `addons_path` de `/etc/odoo/odoo.conf` (o el archivo real
   de la instancia).
3. Confirme que el servicio Odoo ve ambos directorios de addons (el
   `addons_path` debe incluir este repositorio). En Aplicaciones deben poder
   instalarse `korventis_l10n_do_fiscal` y `korventis_partner_dgii`.

## 3. Variables (sin contraseñas)

Copie `scripts/env.example` a un archivo **fuera de git** (por ejemplo
`/etc/odoo/korventis.env`) y rellene rutas reales. Nunca ponga la clave de
PostgreSQL en el repositorio: Odoo la lee de `odoo.conf`.

```bash
export ODOO_BIN=/usr/bin/odoo
export ODOO_CONF=/etc/odoo/odoo.conf
export ODOO_DB=nombre_de_la_base_nueva
export KORVENTIS_ACTION=install
```

Los scripts rechazan las bases protegidas `korventis` y `baruchcafe`.

## 4. Instalar

El orden es fijo: primero el núcleo fiscal, después el padrón. El instalador
pasa ambos a `-i`; Odoo resuelve dependencias y crea tablas, campos, grupos,
menús e índices con el ORM, los manifiestos y `post_init_hook`.

```bash
chmod +x scripts/*.sh
KORVENTIS_ACTION=install ./scripts/install_korventis.sh
./scripts/verify_korventis.sh
```

Equivalente manual:

```bash
<ODOO_BIN> -c <ODOO_CONF> -d <DB> \
  -i korventis_l10n_do_fiscal,korventis_partner_dgii \
  --stop-after-init
```

Códigos de salida: `0` correcto; distinto de `0` significa que hay que leer el
log de Odoo. Los scripts no imprimen contraseñas.

## 5. Comprobar en la interfaz

1. Aplicaciones: ambos módulos en estado instalado.
2. Contactos > Padrón DGII > Estado: módulo instalado, padrón pendiente.
3. Una sola tarea `Korventis: actualizar padrón DGII`, **inactiva**.
4. Asignar `Usuario del padrón DGII` y `Administrador del padrón DGII`.
5. En la compañía, activar `Enable Korventis Fiscal Core` cuando vaya a emitir
   comprobantes (eso no descarga el padrón).

## 6. Qué no hace esta instalación

- No crea ni borra bases de datos.
- No elimina volúmenes Docker.
- No importa el ZIP de DGII.
- No enciende el cron.
- No modifica otras bases del mismo servidor.

Siguiente paso: `docs/DGII_IMPORT.md`. Parámetros: `docs/CONFIGURATION.md`.
Recuperación: `docs/ROLLBACK.md`. Pruebas: `docs/QA_CHECKLIST.md`.
