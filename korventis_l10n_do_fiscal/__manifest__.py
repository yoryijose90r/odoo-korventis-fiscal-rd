# Korventis Fiscal RD — Fiscal Core
# License: pending (see LICENSE_PENDING.md at repository root).

{
    "name": "Korventis Fiscal RD",
    "summary": "Núcleo fiscal dominicano (tipos, secuencias, documentos) para Odoo 18 Community",
    "version": "18.0.1.1.3",
    "category": "Accounting/Localizations",
    "author": "Korventis",
    "website": "https://github.com/yoryijose90r/odoo-korventis-fiscal-rd",
    "license": "Other proprietary",
    "depends": [
        "base",
        "account",
        "l10n_do",
    ],
    "data": [
        "security/fiscal_security.xml",
        "security/ir.model.access.csv",
        "data/fiscal_document_types.xml",
        "views/fiscal_document_type_views.xml",
        "views/fiscal_sequence_views.xml",
        "views/fiscal_document_views.xml",
        "views/fiscal_event_views.xml",
        "views/res_partner_views.xml",
        "views/res_company_views.xml",
        "views/account_move_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
