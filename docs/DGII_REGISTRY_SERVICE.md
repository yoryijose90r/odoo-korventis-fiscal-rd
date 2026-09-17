# Servicio `korventis-dgii-registry` (Commit 1)

Esqueleto del padrón DGII independiente. PostgreSQL `korventis_dgii` no vive
en las bases Odoo. Este commit **no** descarga el ZIP oficial, **no** migra
los ~789 577 registros, **no** activa cron y **no** cambia emisión fiscal,
POS ni e-NCF.

Imagen única: `korventis-dgii-registry:18.0.2.0`.
Modalidades: `docker-compose.shared.yml` (SHARED) y `docker-compose.local.yml`
(LOCAL). Solo cambia el modo y el volumen de datos.

## Qué queda fuera

- Producción y el VPS hasta autorización expresa.
- Bases Odoo `korventis`, `baruchcafe` y `korventis_fiscal_test`.
- Tablas del módulo `korventis_partner_dgii` (no se eliminan).
- Contexto de prueba `korventis_dgii_test_version_id`.
- Lookup HTTP autenticado (commit posterior).
- Publicar PostgreSQL al host o a Internet.

## Instalación en un entorno desechable de QA

No use estos comandos contra producción. El proyecto Compose debe llamarse
`korventis-dgii-disposable` para poder destruirlo después con el script
protegido.

### Linux / Git Bash

```bash
cd deploy/dgii-registry
cp env.example .env
```

Edite `.env` y ponga una contraseña local (nunca la suba a git):

```bash
# ejemplo de generación; pegue el valor en KORVENTIS_DGII_POSTGRES_PASSWORD
openssl rand -base64 24
```

```bash
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable up -d --build
curl -sS http://127.0.0.1:8080/health
curl -sS http://127.0.0.1:8080/health/ready
```

`/health` confirma que el proceso responde. `/health/ready` confirma PostgreSQL
y el esquema. Con padrón vacío el JSON lleva `"registry": "pending"`; eso no
es un fallo.

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

## Actualización

El aplicador de migraciones es idempotente. Recrear el contenedor del servicio
vuelve a aplicar solo archivos SQL nuevos:

```bash
cd deploy/dgii-registry
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable build registry
docker compose -f docker-compose.local.yml -p korventis-dgii-disposable up -d registry
curl -sS http://127.0.0.1:8080/health/ready
```

No hace falta `docker volume rm`. El volumen `korventis_dgii_*_pgdata` conserva
el esquema. Los archivos en `services/korventis_dgii_registry/migrations/` no
deben reescribirse una vez aplicados; se añade un `002_*.sql`.

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

No use `docker volume rm` contra volúmenes de Odoo. No ejecute `dropdb` contra
bases del ERP.

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
| `KORVENTIS_DGII_POSTGRES_PASSWORD` | Interpolación Compose. Obligatorio. |
| `KORVENTIS_DGII_MODE` | `shared` o `local`. |
| `KORVENTIS_DGII_PUBLISH_PORT` | Puerto loopback del API (default `8080`). |
| `KORVENTIS_DGII_AUTO_IMPORT` | Ignorado en commit 1; el servicio no descarga. |
| `KORVENTIS_DGII_DATABASE_URL` | Lo inyecta Compose dentro de la red Docker. |

PostgreSQL no tiene `ports:` hacia el host. El API escucha `127.0.0.1` en el
host y `0.0.0.0:8080` solo dentro del contenedor.
