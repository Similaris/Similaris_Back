-- Campos necessarios para persistir e consultar o resultado do motor hibrido.
ALTER TABLE analysis_results
    ADD COLUMN IF NOT EXISTS lexical_score NUMERIC(5,4),
    ADD COLUMN IF NOT EXISTS is_suspicious BOOLEAN NOT NULL DEFAULT FALSE;

-- Mantem apenas o resultado mais recente caso uma base antiga contenha pares
-- duplicados, permitindo tornar o reprocessamento idempotente.
DELETE FROM analysis_results older
USING analysis_results newer
WHERE older.segment_id = newer.segment_id
  AND older.reference_segment_id = newer.reference_segment_id
  AND older.id < newer.id;

CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_results_segment_reference
    ON analysis_results (segment_id, reference_segment_id);
