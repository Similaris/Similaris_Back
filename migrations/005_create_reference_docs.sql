-- Documentos da base de referência usada na comparação
-- (dataset PAN-PC-11 + sub-base de textos científicos em português)
CREATE TABLE IF NOT EXISTS reference_docs (
    id         SERIAL PRIMARY KEY,
    title      VARCHAR(500) NOT NULL,
    source     VARCHAR(100) NOT NULL,               -- pan-pc-11 | base-pt
    language   VARCHAR(10)  NOT NULL DEFAULT 'pt',  -- pt | en
    file_path  VARCHAR(500),
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_reference_docs_source ON reference_docs (source);
