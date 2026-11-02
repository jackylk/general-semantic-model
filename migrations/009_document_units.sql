-- Generic parser artifacts, immutable with their parse version. No domain fields.
ALTER TABLE parse_versions ADD COLUMN document_units jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE parse_versions ADD COLUMN coverage jsonb NOT NULL DEFAULT '{}'::jsonb;
