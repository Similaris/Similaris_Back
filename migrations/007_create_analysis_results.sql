-- Resultados da análise: um registro por par (segmento suspeito × segmento
-- de referência) marcado como suspeito. Combina as métricas lexicais
-- (TF-IDF: cosseno >= 0.5 ou Jaccard >= 0.2) e semântica (SBERT: cosseno).
CREATE TABLE IF NOT EXISTS analysis_results (
    id                   SERIAL PRIMARY KEY,
    document_id          INTEGER NOT NULL REFERENCES documents(id)          ON DELETE CASCADE,
    segment_id           INTEGER NOT NULL REFERENCES segments(id)           ON DELETE CASCADE,
    reference_segment_id INTEGER NOT NULL REFERENCES reference_segments(id) ON DELETE CASCADE,

    lexical_cosine       NUMERIC(5,4),    -- similaridade de cosseno sobre TF-IDF
    lexical_jaccard      NUMERIC(5,4),    -- similaridade de Jaccard
    semantic_cosine      NUMERIC(5,4),    -- similaridade de cosseno sobre embeddings SBERT
    final_score          NUMERIC(5,4) NOT NULL,  -- combinação híbrida (maior valor)
    plagiarism_type      VARCHAR(20)  NOT NULL,  -- literal | parafrase

    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_analysis_results_document_id ON analysis_results (document_id);
CREATE INDEX IF NOT EXISTS ix_analysis_results_segment_id  ON analysis_results (segment_id);
