-- Segmentos (trechos) dos documentos suspeitos, gerados pela segmentação textual.
-- text_original alimenta o SBERT; text_clean (pré-processado com NLTK) alimenta o TF-IDF.
CREATE TABLE IF NOT EXISTS segments (
    id            SERIAL PRIMARY KEY,
    document_id   INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    position      INTEGER NOT NULL,                -- ordem do trecho no documento
    start_offset  INTEGER,                          -- posição inicial no texto extraído
    end_offset    INTEGER,                          -- posição final no texto extraído
    text_original TEXT    NOT NULL,
    text_clean    TEXT,

    UNIQUE (document_id, position)
);

CREATE INDEX IF NOT EXISTS ix_segments_document_id ON segments (document_id);
