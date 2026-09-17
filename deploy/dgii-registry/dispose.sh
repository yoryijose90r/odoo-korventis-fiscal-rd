#!/bin/sh
# Destroy a throwaway korventis-dgii-registry compose project.
# Refuses Odoo databases and any project that is not explicitly disposable.
# Default install/upgrade paths never call this script.

set -eu

if [ "${KORVENTIS_DGII_DISPOSABLE:-}" != "yes" ]; then
    echo "Refusing: set KORVENTIS_DGII_DISPOSABLE=yes only for a throwaway environment."
    exit 1
fi

PROJECT="${COMPOSE_PROJECT_NAME:-}"
case "$PROJECT" in
    korventis-dgii-disposable|korventis-dgii-test)
        ;;
    *)
        echo "Refusing: COMPOSE_PROJECT_NAME must be korventis-dgii-disposable or korventis-dgii-test."
        echo "This script never removes Odoo volumes or databases korventis, baruchcafe, korventis_fiscal_test."
        exit 1
        ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
COMPOSE_FILE="${KORVENTIS_DGII_COMPOSE_FILE:-$SCRIPT_DIR/docker-compose.local.yml}"

echo "Stopping disposable project $PROJECT (volumes of this project only)..."
docker compose -f "$COMPOSE_FILE" -p "$PROJECT" down --volumes --remove-orphans
echo "Done. Odoo databases were not touched."
