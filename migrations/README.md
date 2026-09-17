# Migrations

Scripts SQL de criação das tabelas do Similaris (PostgreSQL), numerados na ordem de execução:

| Arquivo | Tabela | Descrição |
|---|---|---|
| `001_create_users.sql` | `users` | Usuários (autenticação JWT) |
| `002_create_batches.sql` | `batches` | Lotes de análise |
| `003_create_documents.sql` | `documents` | Documentos suspeitos enviados |
| `004_create_segments.sql` | `segments` | Trechos dos documentos suspeitos |
| `005_create_reference_docs.sql` | `reference_docs` | Base de referência |
| `006_create_reference_segments.sql` | `reference_segments` | Trechos da base de referência |
| `007_create_analysis_results.sql` | `analysis_results` | Scores por par de trechos |
| `008_prepare_reference_corpus.sql` | `reference_docs`, `reference_segments` | Identidade do corpus, hashes, idioma inglês e offsets originais |

## Atualização de um banco existente

Os scripts de inicialização não são reaplicados em volumes existentes.
Antes de importar a PAN-PC-11, aplique a migration 008 sem apagar o volume:

```powershell
Get-Content -Raw migrations\008_prepare_reference_corpus.sql |
    docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

As referências legadas são preservadas. Os novos campos de proveniência ficam
nulos nelas; apenas referências preparadas pelo importador compõem o novo índice.

## Execução automática (Docker)

O `docker-compose.yml` monta esta pasta em `/docker-entrypoint-initdb.d`, então o PostgreSQL executa todos os scripts **na primeira inicialização** do volume (ordem alfabética).

Para recriar o banco do zero:

```powershell
docker compose down -v   # apaga o volume
docker compose up -d db  # recria executando as migrations
```

## Execução manual

```powershell
docker exec -i similaris-db psql -U similaris -d similaris < migrations\001_create_users.sql
```

## Integração do motor híbrido

Em bancos já existentes, aplique a migration 009 antes de iniciar os workers
com o pipeline completo:

```powershell
Get-Content -Raw migrations\009_integrate_hybrid_analysis.sql |
    docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```
