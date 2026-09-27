-- Preserva a configuracao e a identidade da base usadas em cada analise.
ALTER TABLE documents
    ADD COLUMN IF NOT EXISTS analysis_profile JSONB,
    ADD COLUMN IF NOT EXISTS reference_fingerprint CHAR(64);
