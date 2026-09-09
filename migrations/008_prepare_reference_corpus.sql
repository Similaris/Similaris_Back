-- Identidade estavel e proveniencia da preparacao offline da PAN-PC-11.
-- Campos novos aceitam NULL para preservar referencias anteriores.
ALTER TABLE reference_docs ADD COLUMN IF NOT EXISTS corpus_id VARCHAR(500);
ALTER TABLE reference_docs ADD COLUMN IF NOT EXISTS content_sha256 VARCHAR(64);
ALTER TABLE reference_docs ADD COLUMN IF NOT EXISTS import_signature VARCHAR(64);
ALTER TABLE reference_docs ALTER COLUMN language SET DEFAULT 'en';

CREATE UNIQUE INDEX IF NOT EXISTS uq_reference_docs_source_corpus_id
    ON reference_docs (source, corpus_id);

ALTER TABLE reference_segments ADD COLUMN IF NOT EXISTS start_offset INTEGER;
ALTER TABLE reference_segments ADD COLUMN IF NOT EXISTS end_offset INTEGER;
