# Migrations

Scripts SQL de criação das tabelas do Similaris (PostgreSQL), numerados na ordem de execução:

| Arquivo | Tabela | Descrição |
|---|---|---|
| `001_create_users.sql` | `users` | Usuários (autenticação JWT) |
| `002_create_batches.sql` | `batches` | Lotes de análise |
| `003_create_documents.sql` | `documents` | Documentos suspeitos enviados |
| `004_create_segments.sql` | `segments` | Trechos dos documentos suspeitos |
| `005_create_reference_docs.sql` | `reference_docs` | Base de referência (PAN-PC-11 / PT) |
| `006_create_reference_segments.sql` | `reference_segments` | Trechos da base de referência |
| `007_create_analysis_results.sql` | `analysis_results` | Scores por par de trechos |

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
