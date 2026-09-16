#!/usr/bin/env bash
# Enable the DGII daily cron only after a successful first import.
# Requires KORVENTIS_ENABLE_CRON=yes. Never prints passwords.
set -euo pipefail

PROTECTED_DATABASES="${KORVENTIS_PROTECTED_DATABASES:-korventis baruchcafe}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_var() {
    local name="$1"
    if [ -z "${!name:-}" ]; then
        fail "Defina la variable de entorno $name."
    fi
}

require_var ODOO_BIN
require_var ODOO_CONF
require_var ODOO_DB

if [ "${KORVENTIS_ENABLE_CRON:-}" != "yes" ]; then
    fail "Refused: set KORVENTIS_ENABLE_CRON=yes after a successful first import."
fi

for protected in $PROTECTED_DATABASES; do
    if [ "$ODOO_DB" = "$protected" ]; then
        fail "La base $ODOO_DB está protegida."
    fi
done

[ -f "$SCRIPT_DIR/enable_dgii_cron.py" ] || fail "Falta enable_dgii_cron.py"

echo "Korventis: autorización explícita de cron DGII en $ODOO_DB"
"$ODOO_BIN" shell -c "$ODOO_CONF" -d "$ODOO_DB" --no-http \
    < "$SCRIPT_DIR/enable_dgii_cron.py"
status=$?
if [ "$status" -ne 0 ]; then
    fail "La activación del cron terminó con código $status"
fi
echo "Korventis: cron DGII autorizado"
exit 0
