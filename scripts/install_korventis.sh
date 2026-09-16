#!/usr/bin/env bash
# Install or upgrade Korventis fiscal + partner DGII on one Odoo database.
# Never drops databases, never prints passwords, never imports the DGII ZIP.
set -euo pipefail

PROTECTED_DATABASES="${KORVENTIS_PROTECTED_DATABASES:-korventis baruchcafe}"
ACTION="${KORVENTIS_ACTION:-install}"
MODULES="${KORVENTIS_MODULES:-korventis_l10n_do_fiscal,korventis_partner_dgii}"

fail() {
    echo "ERROR: $*" >&2
    exit 1
}

require_var() {
    local name="$1"
    if [ -z "${!name:-}" ]; then
        fail "Defina la variable de entorno $name. No ponga contraseñas en este script."
    fi
}

require_var ODOO_BIN
require_var ODOO_CONF
require_var ODOO_DB

if [ ! -x "$ODOO_BIN" ] && ! command -v "$ODOO_BIN" >/dev/null 2>&1; then
    fail "No se encontró ODOO_BIN=$ODOO_BIN"
fi
[ -f "$ODOO_CONF" ] || fail "No existe ODOO_CONF=$ODOO_CONF"

for protected in $PROTECTED_DATABASES; do
    if [ "$ODOO_DB" = "$protected" ]; then
        fail "La base $ODOO_DB está protegida. Use korventis_fiscal_test u otra base desechable."
    fi
done

case "$ACTION" in
    install)
        ODOO_FLAGS=(-i "$MODULES")
        ;;
    upgrade)
        ODOO_FLAGS=(-u "$MODULES")
        ;;
    *)
        fail "KORVENTIS_ACTION debe ser install o upgrade"
        ;;
esac

echo "Korventis: $ACTION en base $ODOO_DB"
echo "Módulos: $MODULES"
echo "El padrón DGII no se descarga en este paso."

"$ODOO_BIN" -c "$ODOO_CONF" -d "$ODOO_DB" \
    "${ODOO_FLAGS[@]}" \
    --stop-after-init
status=$?
if [ "$status" -ne 0 ]; then
    fail "odoo-bin terminó con código $status"
fi

echo "Korventis: $ACTION finalizado. Ejecute scripts/verify_korventis.sh"
exit 0
