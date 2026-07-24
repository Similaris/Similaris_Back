-- Documentos suspeitos enviados para análise (PDF ou DOCX)
CREATE TABLE IF NOT EXISTS documents (
    id                 SERIAL PRIMARY KEY,
    batch_id           INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    filename           VARCHAR(255) NOT NULL,
    file_type          VARCHAR(10)  NOT NULL,          -- pdf | docx
    file_path          VARCHAR(500) NOT NULL,
    content_hash       CHAR(64),                        -- sha-256 do arquivo
    status             VARCHAR(20)  NOT NULL DEFAULT 'pendente',
                       -- pendente | processando | concluido | erro
    error_message      TEXT,
    plagiarism_percent NUMERIC(5,2),                    -- percentual global de similaridade

    -- tempos de execução por etapa (métricas para o capítulo de resultados)
    extraction_ms      INTEGER,
    lexical_ms         INTEGER,
    semantic_ms        INTEGER,

    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at         TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_documents_batch_id ON documents (batch_id);
CREATE INDEX IF NOT EXISTS ix_documents_status   ON documents (status);
