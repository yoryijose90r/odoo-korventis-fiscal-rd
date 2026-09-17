-- korventis-dgii-registry schema 001
-- Independent PostgreSQL database korventis_dgii. Not an Odoo module.
-- Idempotent. Does not download the official ZIP. Does not seed registry rows.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dgii_rnc_version (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    source_last_modified TEXT,
    source_etag TEXT,
    archive_size BIGINT,
    archive_sha256 TEXT NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL,
    activated_at TIMESTAMPTZ,
    record_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT dgii_rnc_version_state_check
        CHECK (state IN ('staging', 'active', 'previous')),
    CONSTRAINT dgii_rnc_version_archive_sha256_unique
        UNIQUE (archive_sha256)
);

CREATE UNIQUE INDEX IF NOT EXISTS dgii_rnc_version_one_active_idx
    ON dgii_rnc_version (state)
    WHERE state = 'active';

CREATE TABLE IF NOT EXISTS dgii_rnc (
    id BIGSERIAL PRIMARY KEY,
    version_id BIGINT NOT NULL REFERENCES dgii_rnc_version (id) ON DELETE CASCADE,
    rnc TEXT NOT NULL,
    rnc_normalizado TEXT NOT NULL,
    razon_social TEXT NOT NULL,
    razon_social_normalizada TEXT NOT NULL,
    actividad_economica TEXT,
    fecha_inicio_operaciones DATE,
    estado TEXT NOT NULL,
    regimen_pago TEXT NOT NULL,
    fecha_importacion TIMESTAMPTZ NOT NULL,
    CONSTRAINT dgii_rnc_version_rnc_unique UNIQUE (version_id, rnc)
);

CREATE INDEX IF NOT EXISTS dgii_rnc_rnc_normalizado_idx
    ON dgii_rnc (rnc_normalizado);

CREATE INDEX IF NOT EXISTS dgii_rnc_version_name_prefix_idx
    ON dgii_rnc (version_id, razon_social_normalizada text_pattern_ops);

CREATE INDEX IF NOT EXISTS dgii_rnc_name_fts_idx
    ON dgii_rnc
    USING gin (to_tsvector('simple'::regconfig, razon_social_normalizada));

CREATE TABLE IF NOT EXISTS dgii_import_run (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    state TEXT NOT NULL,
    source_url TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION,
    archive_sha256 TEXT,
    version_id BIGINT REFERENCES dgii_rnc_version (id) ON DELETE SET NULL,
    total_rows INTEGER NOT NULL DEFAULT 0,
    accepted_count INTEGER NOT NULL DEFAULT 0,
    rejected_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    details TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT dgii_import_run_state_check
        CHECK (state IN ('running', 'success', 'unchanged', 'failed', 'skipped'))
);

CREATE INDEX IF NOT EXISTS dgii_import_run_started_idx
    ON dgii_import_run (started_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS dgii_installation (
    install_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_heartbeat_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS dgii_api_audit (
    id BIGSERIAL PRIMARY KEY,
    install_id TEXT,
    path TEXT NOT NULL,
    http_status INTEGER,
    request_id TEXT,
    duration_ms INTEGER,
    queried_rnc TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS dgii_api_audit_created_idx
    ON dgii_api_audit (created_at DESC);

CREATE TABLE IF NOT EXISTS dgii_service_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO dgii_service_settings (key, value)
VALUES
    ('auto_import_enabled', 'false'),
    ('schema_product_version', '18.0.2.0-commit1')
ON CONFLICT (key) DO NOTHING;
