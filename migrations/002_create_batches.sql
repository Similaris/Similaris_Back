-- Lotes de análise: agrupam os documentos enviados juntos pelo usuário
-- (processamento em lote via Celery/Redis)
CREATE TABLE IF NOT EXISTS batches (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
    status      VARCHAR(20) NOT NULL DEFAULT 'pendente',
                -- pendente | processando | concluido | erro
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_batches_user_id ON batches (user_id);
CREATE INDEX IF NOT EXISTS ix_batches_status  ON batches (status);
