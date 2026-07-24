-- Segmentos dos documentos de referência, pré-processados e indexados
-- uma única vez na ingestão da base (vetores TF-IDF e embeddings SBERT
-- são serializados fora do banco).
CREATE TABLE IF NOT EXISTS reference_segments (
    id               SERIAL PRIMARY KEY,
    reference_doc_id INTEGER NOT NULL REFERENCES reference_docs(id) ON DELETE CASCADE,
    position         INTEGER NOT NULL,
    text_original    TEXT    NOT NULL,
    text_clean       TEXT,

    UNIQUE (reference_doc_id, position)
);

CREATE INDEX IF NOT EXISTS ix_reference_segments_doc_id
    ON reference_segments (reference_doc_id);
