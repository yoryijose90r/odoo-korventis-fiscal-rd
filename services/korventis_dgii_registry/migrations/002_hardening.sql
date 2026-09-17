-- korventis-dgii-registry schema 002
-- Hardening only. Does not rewrite 001_initial. Does not seed or transform padrón rows.

CREATE UNIQUE INDEX IF NOT EXISTS dgii_rnc_version_rnc_normalizado_uidx
    ON dgii_rnc (version_id, rnc_normalizado);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'dgii_rnc_rnc_not_blank'
    ) THEN
        ALTER TABLE dgii_rnc
            ADD CONSTRAINT dgii_rnc_rnc_not_blank
            CHECK (length(btrim(rnc)) > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'dgii_rnc_rnc_normalizado_not_blank'
    ) THEN
        ALTER TABLE dgii_rnc
            ADD CONSTRAINT dgii_rnc_rnc_normalizado_not_blank
            CHECK (length(btrim(rnc_normalizado)) > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'dgii_rnc_rnc_normalizado_digits'
    ) THEN
        ALTER TABLE dgii_rnc
            ADD CONSTRAINT dgii_rnc_rnc_normalizado_digits
            CHECK (rnc_normalizado ~ '^[0-9]+$');
    END IF;
END
$$;

INSERT INTO dgii_service_settings (key, value)
VALUES ('schema_product_version', '18.0.2.0-commit1.1')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
