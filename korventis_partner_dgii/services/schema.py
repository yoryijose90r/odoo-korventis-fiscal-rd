"""Idempotent PostgreSQL helpers used by install, upgrade and init()."""

CUSTOM_INDEXES = (
    {
        "name": "korventis_dgii_rnc_version_name_prefix_idx",
        "sql": """
            CREATE INDEX korventis_dgii_rnc_version_name_prefix_idx
                ON korventis_dgii_rnc
                (version_padron_id, razon_social_normalizada varchar_pattern_ops)
        """,
    },
    {
        "name": "korventis_dgii_rnc_name_fts_idx",
        "sql": """
            CREATE INDEX korventis_dgii_rnc_name_fts_idx
                ON korventis_dgii_rnc
                USING gin (
                    to_tsvector('simple'::regconfig, razon_social_normalizada)
                )
        """,
    },
    {
        "name": "korventis_dgii_rnc_version_one_active_idx",
        "sql": """
            CREATE UNIQUE INDEX korventis_dgii_rnc_version_one_active_idx
                ON korventis_dgii_rnc_version (state)
                WHERE state = 'active'
        """,
    },
)

EXPECTED_TABLES = (
    "korventis_dgii_rnc",
    "korventis_dgii_rnc_version",
    "korventis_dgii_import_run",
)

CONFIG_DEFAULTS = {
    "korventis_partner_dgii.source_url": (
        "https://dgii.gov.do/app/WebApps/Consultas/RNC/RNC_CONTRIBUYENTES.zip"
    ),
    "korventis_partner_dgii.fallback_url": "",
    "korventis_partner_dgii.shared_archive_path": "",
    "korventis_partner_dgii.minimum_records": "100000",
    "korventis_partner_dgii.minimum_volume_ratio": "0.70",
    "korventis_partner_dgii.maximum_volume_ratio": "1.30",
    "korventis_partner_dgii.auto_import_enabled": "False",
}


def pg_index_exists(cr, index_name):
    cr.execute(
        """
        SELECT 1
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'i'
           AND c.relname = %s
           AND n.nspname = current_schema()
        """,
        (index_name,),
    )
    return bool(cr.fetchone())


def pg_table_exists(cr, table_name):
    cr.execute(
        """
        SELECT 1
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE c.relkind = 'r'
           AND c.relname = %s
           AND n.nspname = current_schema()
        """,
        (table_name,),
    )
    return bool(cr.fetchone())


def ensure_custom_indexes(cr):
    created = []
    for index in CUSTOM_INDEXES:
        table = (
            "korventis_dgii_rnc_version"
            if "version_one_active" in index["name"]
            else "korventis_dgii_rnc"
        )
        if not pg_table_exists(cr, table):
            continue
        if pg_index_exists(cr, index["name"]):
            continue
        cr.execute(index["sql"])
        created.append(index["name"])
    return created


def count_active_versions(cr):
    if not pg_table_exists(cr, "korventis_dgii_rnc_version"):
        return 0
    cr.execute(
        """
        SELECT count(*)
          FROM korventis_dgii_rnc_version
         WHERE state = 'active'
        """
    )
    return int(cr.fetchone()[0])
