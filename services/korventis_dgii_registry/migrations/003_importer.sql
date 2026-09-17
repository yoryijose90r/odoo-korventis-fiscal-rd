-- korventis-dgii-registry schema 003
-- Importer hardening. Does not rewrite 001 or 002. Does not seed padrón rows.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'dgii_rnc_version_active_has_records'
    ) THEN
        ALTER TABLE dgii_rnc_version
            ADD CONSTRAINT dgii_rnc_version_active_has_records
            CHECK (state <> 'active' OR record_count > 0);
    END IF;
END
$$;

INSERT INTO dgii_service_settings (key, value)
VALUES
    ('schema_product_version', '18.0.2.0-commit2'),
    ('auto_import_enabled', 'false')
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value
WHERE dgii_service_settings.key = 'schema_product_version';
