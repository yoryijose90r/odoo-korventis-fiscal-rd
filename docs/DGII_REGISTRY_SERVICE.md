# Servicio `korventis-dgii-registry` (Commit 2)

Esqueleto del padrón DGII independiente más importador local. PostgreSQL
`korventis_dgii` no vive en las bases Odoo. Este servicio **no** descarga el
ZIP oficial por sí solo, **no** migra los ~789 577 registros de Odoo, **no**
activa cron y **no** cambia emisión fiscal, POS ni e-NCF.

Imagen única: `korventis-dgii-registry:18.0.2.0`.
Modalidades: `docker-compose.shared.yml` (SHARED) y `docker-compose.local.yml`
(LOCAL). Solo cambia el modo y el volumen de datos.

## Qué queda fuera

- Producción y el VPS hasta autorización expresa.
- Bases Odoo `korventis`, `baruchcafe` y `korventis_fiscal_test`.
- Tablas del módulo `korventis_partner_dgii` (no se eliminan).
- Contexto de prueba `korventis_dgii_test_version_id`.
- Lookup HTTP (commit posterior; exigirá autenticación por instalación).
- Publicar PostgreSQL al host o a Internet.

## Salud

`GET /health` solo indica que el proceso responde:

```json
{"status":"ok","service":"korventis-dgii-registry"}
```

`GET /health/ready` no incluye URL, usuario, host, contraseñas, trazas ni
rutas. Códigos:

| HTTP | `registry` | Significado |
| --- | --- | --- |
| 200 | `pending` | PostgreSQL y esquema listos; no hay padrón activo con registros |
| 200 | `active` | Exactamente una versión `active`, con `record_count` > 0 e igual al número de filas |
| 503 | `unavailable` | PostgreSQL, esquema o integridad del padrón no disponibles |

Un padrón vacío o una versión `active` sin filas **no** se anuncia como `active`.

## Importación

El Registry **no** importa al arrancar. La carga es una orden CLI explícita
sobre un ZIP local. `--url` está rechazado en este commit.

```bash
# Validar ZIP/CSV y dejar la versión en staging (no activa)
python -m korventis_dgii_registry import --zip /ruta/padron.zip --source local-qa --validate-only

# Activar solo si pasan ZIP, CSV y umbrales de integridad
python -m korventis_dgii_registry import --zip /ruta/padron.zip --source local-qa --activate
```

CSV esperado (Latin-1, comas, campos entrecomillados):

`RNC`, `RAZÓN SOCIAL`, `ACTIVIDAD ECONÓMICA`, `FECHA DE INICIO OPERACIONES`, `ESTADO`, `RÉGIMEN DE PAGO`

Política de filas:

- RNC se guarda como texto. No se convierte a entero. Se conservan ceros iniciales.
- RNC válido: 9 u 11 dígitos, sin guiones.
- Filas vacías se ignoran. Campos obligatorios ausentes o RNC malformado se rechazan.
- Duplicados de RNC normalizado en el mismo archivo son un error crítico: no se activa.
- Fecha inválida: advertencia; la fila se acepta con fecha nula.
- `ESTADO` es descriptivo. `ACTIVO` no autoriza emitir e-NCF.
- Si hay errores críticos o se supera `KORVENTIS_DGII_IMPORT_MAX_REJECT_RATIO` (default 0.001), la importación falla y la versión anterior permanece activa.
- Mismo SHA-256: `unchanged`; no se crea otra versión. Si quedó en `staging`, `--activate` la activa.
- Dos importaciones a la vez: la segunda recibe `skipped` (candado `pg_try_advisory_lock`).

### Respaldo antes de una carga real (futura)

No ejecutar contra bases Odoo. Sobre el PostgreSQL del servicio:

```bash
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable exec postgres \
  pg_dump -U korventis_dgii -Fc korventis_dgii > korventis_dgii.dump
```

Conserve el ZIP local usado. No borre versiones `previous`.

### Rollback sin destruir la versión anterior

```bash
python -m korventis_dgii_registry restore-previous
```

Intercambia la `active` actual con la `previous` más reciente en una transacción.
No hace `DROP` ni borra filas históricas.

No reescriba `001_initial.sql` ni `002_hardening.sql`. El importador añade
`003_importer.sql` (una versión `active` no puede tener `record_count` 0).

## Instalación en un entorno desechable de QA

No use estos comandos contra producción. El proyecto Compose debe llamarse
`korventis-dgii-disposable` para poder destruirlo después con el script
protegido.

### Linux / Git Bash

```bash
cd deploy/dgii-registry
cp env.example .env
```

Edite `.env` y ponga una contraseña local (nunca la suba a git). Puede
incluir `@ # / : % ? &`. Evite `$` porque Compose lo interpola.

```bash
openssl rand -base64 24
```

```bash
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable up -d --build
curl -sS http://127.0.0.1:8080/health
curl -sS http://127.0.0.1:8080/health/ready
```

SHARED usa la misma imagen:

```bash
docker compose -f docker-compose.shared.yml -p korventis-dgii-disposable up -d --build
```

No ejecute SHARED y LOCAL a la vez en el mismo puerto de loopback. Cambie
`KORVENTIS_DGII_PUBLISH_PORT` en `.env` si hace falta.

### PowerShell (estación Windows)

```powershell
Set-Location deploy\dgii-registry
Copy-Item env.example .env
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable up -d --build
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/health/ready
```

## Conexión futura desde Odoo

En esta etapa el API solo se publica en `127.0.0.1` para health de QA. Odoo
**no** debe consultar el padrón todavía: no hay lookup ni autenticación.

Cuando se autorice el adaptador, Odoo se unirá a la red Docker del proyecto
(`korventis-dgii-shared_default` o `korventis-dgii-local_default`) como red
externa y hablará con `registry:8080` **dentro** de esa red. No se publicará
PostgreSQL. Cada instalación Odoo usará `install_id` + secreto. No habilite
consultas anónimas.

## Actualización

El aplicador de migraciones es idempotente y usa un bloqueo transaccional
PostgreSQL. Recrear el contenedor del servicio aplica solo archivos SQL nuevos:

```bash
cd deploy/dgii-registry
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable build registry
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable up -d registry
curl -sS http://127.0.0.1:8080/health/ready
```

No reescriba `001_initial.sql` en instalaciones que ya lo aplicaron. El
endurecimiento de RNC está en `002_hardening.sql`. La activación no vacía está
en `003_importer.sql`.

## Parada (conserva datos del servicio)

```bash
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable down
```

Esto no toca volúmenes ni bases Odoo.

## Eliminación segura de un entorno desechable

Solo para el proyecto `korventis-dgii-disposable` o `korventis-dgii-test`.
El script exige el flag explícito y **no** acepta otros nombres. No elimina
volúmenes de Odoo ni las bases `korventis`, `baruchcafe` o
`korventis_fiscal_test`.

```bash
cd deploy/dgii-registry
KORVENTIS_DGII_DISPOSABLE=yes COMPOSE_PROJECT_NAME=korventis-dgii-disposable ./dispose.sh
```

Equivalente manual, mismo alcance:

```bash
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable down --volumes --remove-orphans
```

## Pruebas del esquema

Desde `services/korventis_dgii_registry`, con Docker disponible:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas levantan un PostgreSQL efímero en `127.0.0.1` (puerto libre) y lo
destruyen al terminar. No cargan el padrón oficial.

## Operación

| Variable | Uso |
| --- | --- |
| `KORVENTIS_DGII_POSTGRES_PASSWORD` | Contraseña de PostgreSQL. Obligatorio. Fuera de git. |
| `KORVENTIS_DGII_PGHOST` / `PGPORT` / `PGUSER` / `PGDATABASE` | Lo inyecta Compose; no use una URL única. |
| `KORVENTIS_DGII_MODE` | `shared` o `local`. |
| `KORVENTIS_DGII_PUBLISH_PORT` | Puerto loopback del API (default `8080`). |
| `KORVENTIS_DGII_AUTO_IMPORT` | Ignorado; el servicio no descarga al arrancar. |
| `KORVENTIS_DGII_ALLOW_REMOTE` | Debe permanecer en false. `--url` está deshabilitado. |
| `KORVENTIS_DGII_IMPORT_MIN_RECORDS` | Mínimo de filas aceptadas (default 1; subir antes de una carga oficial). |
| `KORVENTIS_DGII_IMPORT_MAX_REJECT_RATIO` | Tope de rechazos / total (default 0.001). |

PostgreSQL no tiene `ports:` hacia el host. El API escucha `127.0.0.1` en el
host y `0.0.0.0:8080` solo dentro del contenedor.
