# Runbook QA — `korventis-dgii-registry`

Procedimiento **probado** en QA el 2026-09-17 y las reglas para repetirlo.
No sustituye a `docs/DGII_REGISTRY_SERVICE.md`. No autoriza `--activate`.

Este documento no se ejecuta solo. Cada bloque es una decisión. Si un
comando falla, **detenerse**.

## Arquitectura (no negociable)

- Un Registry DGII independiente **por VPS**.
- PostgreSQL propio: base `korventis_dgii`. No vive en Odoo.
- Un único padrón compartido entre las bases Odoo **del mismo VPS**.
- Sin claves foráneas entre el Registry y Odoo.
- El Registry **no** escribe `res.partner`, facturas ni documentos fiscales.
- PostgreSQL **sin** puertos al host. API de health **solo** en loopback.
- No hay lookup HTTP anónimo. El padrón RNC **no** autoriza emitir e-CF.

## Variables (no rigidizar IPs ni nombres de QA)

Sustituya los valores. Los de QA se listan solo como referencia de esa
ejecución, no como destino de producción.

```bash
export COMPOSE_DIR="deploy/dgii-registry"
export COMPOSE_FILE="docker-compose.shared.yml"
export COMPOSE_PROJECT="korventis-dgii-test"   # QA usó este nombre
export REGISTRY_HOST="127.0.0.1"
export REGISTRY_PORT="8080"
export ODOO_WEB_CONTAINER="korventis_odoo"
export ODOO_DB_CONTAINER="korventis_db"
export ZIP_LOCAL_PATH="/ruta/local/RNC_CONTRIBUYENTES.zip"
export ZIP_REMOTE_DIR="/opt/korventis/dgii"
export BACKUP_DIR="/opt/korventis/backups/dgii"
```

Referencia de la ejecución QA (no copiar a producción):

| Dato | Valor de esa corrida |
| --- | --- |
| VPS | `143.198.119.38` |
| Proyecto Compose | `korventis-dgii-test` |
| Contenedores Registry | `korventis-dgii-test-registry-1`, `korventis-dgii-test-postgres-1` |
| API | `127.0.0.1:8080` |
| Contenedores Odoo (ajenos al Registry) | `korventis_odoo`, `korventis_db` |
| Bases Odoo (no tocar) | `korventis`, `baruchcafe`, `korventis_fiscal_test` |

**Prohibido** operar sobre producción `198.199.80.184` desde este runbook.

## Sincronizar código sin pisar el Compose de QA

QA tiene una modificación **manual** de `docker-compose.shared.yml` (inyección
de `KORVENTIS_DGII_IMPORT_MIN_RECORDS`) que puede no estar en el working tree
remoto. **No** ejecutar `git reset --hard`, `git clean` ni `git pull` a ciegas.

```bash
cd /ruta/del/repo
git fetch origin
git rev-parse HEAD
git status --short
git diff -- deploy/dgii-registry/docker-compose.shared.yml
# Comparar con el commit de feature/partner-dgii-local antes de actualizar.
```

Si el diff local de QA coincide con el commit, actualizar con `git merge` o
`git pull` **después** de revisar. Si no coincide, conservar el cambio QA y
resolver a mano.

## 1. Despliegue (sin `--volumes`, sin importar el padrón)

### 1.1 Rama, commit y árbol

```bash
git branch --show-current
git rev-parse HEAD
git status --short
```

Parar si la rama no es la autorizada, si HEAD no es el commit revisado, o si
hay cambios inesperados.

### 1.2 Revisar `.env` sin imprimir secretos

```bash
cd "$COMPOSE_DIR"
test -f .env
grep -E '^[A-Z0-9_]+=' .env | cut -d= -f1
grep -E '^KORVENTIS_DGII_IMPORT_MIN_RECORDS=' .env
grep -E '^KORVENTIS_DGII_AUTO_IMPORT=' .env
grep -E '^KORVENTIS_DGII_ALLOW_REMOTE=' .env
```

Parar si falta `KORVENTIS_DGII_IMPORT_MIN_RECORDS` en un despliegue `shared`,
si `AUTO_IMPORT` no es `false`, o si se imprime la contraseña (no use
`cat .env`).

Valor usado en QA: `KORVENTIS_DGII_IMPORT_MIN_RECORDS=750000`.

### 1.3 Render de Compose

```bash
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" config --quiet
```

Parar si el comando falla (en `shared` falla si falta el mínimo de registros).

### 1.4 PostgreSQL sin puertos; API solo loopback

```bash
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" config \
  | grep -E 'published|0\.0\.0\.0|5432' || true
```

Parar si aparece un `published` de `5432` o un bind `0.0.0.0` en el host.
El API debe quedar en `127.0.0.1:${REGISTRY_PORT}`.

### 1.5 Levantar solo Registry + su PostgreSQL

No usar `docker compose down --volumes`. Eso borra el padrón del servicio.

```bash
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" up -d --build
```

No levantar Odoo con este Compose. No recrear `korventis_odoo` / `korventis_db`.

### 1.6 Esperar healthcheck `healthy`

No consultar `/health/ready` al instante. El healthcheck del Registry tiene
`start_period`.

```bash
REGISTRY_CID="${COMPOSE_PROJECT}-registry-1"
for i in $(seq 1 36); do
  status=$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$REGISTRY_CID")
  echo "health=$status"
  if [ "$status" = "healthy" ]; then break; fi
  if [ "$i" -eq 36 ]; then echo "STOP: registry not healthy"; exit 1; fi
  sleep 5
done
```

### 1.7 HTTP health

```bash
curl -sS "http://${REGISTRY_HOST}:${REGISTRY_PORT}/health"
curl -sS "http://${REGISTRY_HOST}:${REGISTRY_PORT}/health/ready"
```

Esperado sin padrón activo: `/health` → `{"status":"ok",...}`; `/health/ready`
→ `registry` `pending` (HTTP 200) o `unavailable` (HTTP 503) si el esquema no
está. Tras `--validate-only` oficial, QA vio `pending`. `active` solo si hay
**una** versión `active` con filas físicas coincidentes.

### 1.8 Migraciones una sola vez

```bash
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres \
  psql -U korventis_dgii -d korventis_dgii -c \
  "SELECT version FROM schema_migrations ORDER BY version;"
```

Esperado: `001_initial`, `002_hardening`, `003_importer` (una fila cada una).
Parar si hay duplicados o checksum mismatch.

### 1.9 Flags efectivos dentro del contenedor

```bash
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T registry \
  python -c "import os; print(os.environ.get('KORVENTIS_DGII_AUTO_IMPORT')); print(os.environ.get('KORVENTIS_DGII_ALLOW_REMOTE')); print(os.environ.get('KORVENTIS_DGII_IMPORT_MIN_RECORDS'))"
```

Esperado: `false` / `false` / el mínimo de `.env` (QA: `750000`). Parar si el
mínimo es `1` en un despliegue shared/oficial.

### 1.10 Odoo sigue en pie

```bash
docker inspect -f '{{.State.Status}}' "$ODOO_WEB_CONTAINER"
docker inspect -f '{{.State.Status}}' "$ODOO_DB_CONTAINER"
```

Parar si no están `running`. No reiniciarlos “por si acaso”.

## 2. Fuente oficial DGII

URL de referencia (no automatizar mientras devuelva 403):

`https://dgii.gov.do/app/WebApps/Consultas/RNC/RNC_CONTRIBUYENTES.zip`

En QA el VPS recibió **HTTP 403** al descargar directo. El archivo se obtuvo
con navegador y se copió por SCP.

Copia validada **en esa ejecución** (no es un hash permanente de la DGII):

| Campo | Valor |
| --- | --- |
| Archivo | `RNC_CONTRIBUYENTES.zip` |
| Bytes | `26648575` |
| SHA256 | `1f51ed721d55f35758398385af3a27e5646ccc2d386210c7602cef3754d8f276` |
| CSV interno | `RNC_Contribuyentes_Actualizado_05_Sep_2026.csv` |

Cada publicación nueva de la DGII tendrá otro SHA256. Recalcularlo.

### 2.1 Verificar el ZIP en origen, VPS y contenedor

Equipo de origen:

```bash
# Linux / Git Bash
sha256sum "$ZIP_LOCAL_PATH"
wc -c "$ZIP_LOCAL_PATH"

# PowerShell
Get-FileHash -Algorithm SHA256 $env:ZIP_LOCAL_PATH
(Get-Item $env:ZIP_LOCAL_PATH).Length
```

Transferencia (ejemplo; ajuste usuario y host):

```bash
scp "$ZIP_LOCAL_PATH" "${SSH_USER}@${SSH_HOST}:${ZIP_REMOTE_DIR}/RNC_CONTRIBUYENTES.zip"
```

En el VPS:

```bash
sha256sum "${ZIP_REMOTE_DIR}/RNC_CONTRIBUYENTES.zip"
```

Dentro del contenedor Registry (montar o copiar el ZIP; no descargar):

```bash
docker cp "${ZIP_REMOTE_DIR}/RNC_CONTRIBUYENTES.zip" \
  "${COMPOSE_PROJECT}-registry-1:/tmp/RNC_CONTRIBUYENTES.zip"
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T registry \
  sha256sum /tmp/RNC_CONTRIBUYENTES.zip
```

Parar si el tamaño o el SHA256 no coinciden en los tres puntos.

## 3. Respaldos antes de B o C

No usar `down --volumes`. Dump del PostgreSQL **del Registry**, no de Odoo.

```bash
mkdir -p "$BACKUP_DIR"
STAMP=$(date -u +%Y%m%d_%H%M%S)
DUMP="${BACKUP_DIR}/dgii_registry_${STAMP}.dump"
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres \
  pg_dump -U korventis_dgii -Fc korventis_dgii > "$DUMP"
sha256sum "$DUMP"
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres \
  pg_restore --list "$DUMP" | head
```

Parar si `pg_dump` o `pg_restore --list` fallan.

QA, **antes** de la carga oficial:

- Archivo: `dgii_registry_pre_oficial_20260917_162150.dump`
- SHA256: `20e6831f63fa4c24c0977e55a3677e6406ffa2517f819dd37593870462947562`

QA, **después** de staging:

- Archivo: `dgii_registry_post_staging_20260917_162749.dump`
- Tamaño aproximado: 33 MB
- SHA256: `fbf7d5333dac4746fbdde76a2b08b43a835b8cb3545463e4f0f839da8fba68a5`
- `pg_restore --list` OK

**La restauración completa no se ha probado.** No tratarla como validada.

### 3.1 Restauración de ensayo (pendiente de ejecutar)

Objetivo: restaurar en una base **aislada**, nunca sobre `korventis_dgii` de QA
ni sobre bases Odoo.

```bash
# PENDIENTE: no ejecutado en QA al documentar este runbook.
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres \
  psql -U korventis_dgii -d postgres -c "CREATE DATABASE korventis_dgii_restore_drill;"
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres \
  pg_restore -U korventis_dgii -d korventis_dgii_restore_drill --no-owner "$DUMP"
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres \
  psql -U korventis_dgii -d korventis_dgii_restore_drill -c \
  "SELECT state, id, record_count FROM dgii_rnc_version ORDER BY id;
   SELECT count(*) FROM dgii_rnc;"
# Comparar con los conteos del origen. Luego:
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres \
  psql -U korventis_dgii -d postgres -c "DROP DATABASE korventis_dgii_restore_drill;"
```

Hasta que esto se ejecute de verdad, el procedimiento de recuperación **no**
está cerrado.

## 4. Importación: tres decisiones separadas

No encadenar C después de A o B. Autorización explícita para cada letra.

Contadores de control (antes y después de cada paso):

```bash
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres \
  psql -U korventis_dgii -d korventis_dgii -tAc \
  "SELECT (SELECT count(*) FROM dgii_rnc_version)||'|'||
          (SELECT count(*) FROM dgii_import_run)||'|'||
          (SELECT count(*) FROM dgii_rnc WHERE version_id IN
             (SELECT id FROM dgii_rnc_version WHERE state='active'));"
```

### A. `--dry-run` (autorizado y ejecutado en QA)

Valida ZIP/CSV **sin** escrituras persistentes. Revalida aunque el SHA exista.

```bash
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T registry \
  python -m korventis_dgii_registry import \
  --zip /tmp/RNC_CONTRIBUYENTES.zip --source local-qa --dry-run
```

Esperado: exit 0; JSON con conteos; tablas persistentes iguales que antes.

Resultado real QA:

| Métrica | Valor |
| --- | --- |
| Filas procesadas | 789580 |
| Aceptados | 789577 |
| Rechazados | 3 |
| Advertencias | 1 |
| Duplicados | 0 |
| Exit | 0 |
| Contadores antes/después | `1\|3\|2` |
| `/health/ready` | `pending` |
| Mínimo configurado | 750000 |

Incidencias (sin nombres ni RNC completos), según `_validate_row()`:

| Línea CSV | Tipo | Motivo |
| --- | --- | --- |
| 129733 | Rechazo | Caracteres de control inseguros |
| 146788 | Advertencia | Fecha inválida (fila aceptada con fecha nula) |
| 154894 | Rechazo | RNC malformado |
| 185303 | Rechazo | Caracteres de control inseguros |

### B. `--validate-only` (autorizado y ejecutado en QA)

Persiste `staging`. **No** activa. Exige respaldo previo (sección 3).

```bash
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T registry \
  python -m korventis_dgii_registry import \
  --zip /tmp/RNC_CONTRIBUYENTES.zip --source local-qa --validate-only
```

Resultado real QA:

| Campo | Valor |
| --- | --- |
| Versión oficial | ID `2`, estado `staging` |
| Registros | 789577 |
| RNC distintos | 789577 |
| Rechazados | 3 |
| Advertencias | 1 |
| Versiones `active` | 0 |
| `/health/ready` | `pending` |

Versión ficticia previa: ID `1`, `staging`, 3 registros. **No activarla.**

Comprobación:

```bash
docker compose -f "$COMPOSE_FILE" -p "$COMPOSE_PROJECT" exec -T postgres \
  psql -U korventis_dgii -d korventis_dgii -c \
  "SELECT id, state, record_count FROM dgii_rnc_version ORDER BY id;
   SELECT state, count(*) FROM dgii_rnc_version GROUP BY state;"
```

Parar si `state = 'active'` o si el ID `1` deja de ser la versión ficticia.

### C. `--activate` (no ejecutado; no autorizar aquí)

Activa solo con autorización **nueva**, respaldo reciente e integridad
(`count(*)` = `record_count`, umbral, una sola `active`).

```bash
# NO EJECUTAR sin autorización expresa por escrito.
# docker compose ... exec -T registry python -m korventis_dgii_registry import \
#   --zip /tmp/RNC_CONTRIBUYENTES.zip --source local-qa --activate
```

Staging **no** equivale a padrón activo. Readiness `active` exige versión
`active` con filas físicas.

## 5. Promoción controlada

Cadena:

`feature/partner-dgii-local` → `test` → QA aprobada → `main` → tag → producción

No fusionar ni etiquetar desde este commit. Preproducción se clonará desde
producción cuando se autorice.

Antes de clonar producción hacia preproducción:

1. Respaldar PostgreSQL **y** filestore de Odoo.
2. Sanitizar datos y credenciales según política.
3. No enviar documentos fiscales reales (e-CF) desde el clon.
4. Deshabilitar cron, correo y conexiones DGII de producción hasta validar.
5. No compartir volúmenes Docker entre QA, preproducción y producción.
6. Arrancar imagen y commit identificables (`korventis-dgii-registry:18.0.2.0`
   más SHA de git).
7. Probar restauración (sección 3.1) **antes** de declarar el procedimiento
   recuperable.
8. Cualquier cambio en producción exige autorización explícita.

Producción `198.199.80.184` queda fuera de este runbook.

## 6. Qué no hacer

- `docker compose down --volumes` en un despliegue normal.
- `git reset --hard` / `git pull` a ciegas sobre QA.
- Descargar el ZIP oficial desde el VPS mientras la DGII responda 403.
- Activar la versión ficticia ID `1`.
- Ejecutar `--activate` porque `--validate-only` “fue bien”.
- Publicar PostgreSQL o lookup sin autenticación.
- Tocar bases Odoo `korventis`, `baruchcafe`, `korventis_fiscal_test`.
