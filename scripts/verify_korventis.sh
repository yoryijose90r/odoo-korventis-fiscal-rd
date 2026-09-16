#!/usr/bin/env bash
# Verify Korventis fiscal + partner DGII on one database. Prints no passwords.
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

for protected in $PROTECTED_DATABASES; do
    if [ "$ODOO_DB" = "$protected" ]; then
        fail "La base $ODOO_DB está protegida contra este verificador."
    fi
done

[ -f "$SCRIPT_DIR/verify_korventis.py" ] || fail "Falta verify_korventis.py"

echo "Korventis: verificación en $ODOO_DB"
"$ODOO_BIN" shell -c "$ODOO_CONF" -d "$ODOO_DB" --no-http \
    < "$SCRIPT_DIR/verify_korventis.py"
status=$?
if [ "$status" -ne 0 ]; then
    fail "La verificación terminó con código $status"
fi
echo "Korventis: verificación correcta"
exit 0
