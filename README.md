# Similaris — Backend (API)

Servidor de aplicação do **Similaris**, protótipo web para apoio à detecção de plágio com foco em análise lexical, semântica e processamento em lote.

Projeto desenvolvido como Trabalho de Graduação (TG) do Curso Superior de Tecnologia em Análise e Desenvolvimento de Sistemas da **Faculdade de Tecnologia de Indaiatuba — Dr. Archimedes Lamoglia (FATEC Indaiatuba / Centro Paula Souza)**.

**Autores:**
- Pedro Henrique Denny Ré
- Rafael Tadeu Praça

**Orientador:** Prof. Me. Michel Moron Munhoz

---

## Descrição

O backend é responsável por receber os documentos acadêmicos enviados pela interface web (formatos PDF e DOCX), orquestrar o fluxo de análise e disponibilizar os resultados por meio de uma API REST. O fluxo completo de processamento contempla:

1. **Recebimento dos arquivos** — upload individual ou em lote;
2. **Extração de texto** — PyMuPDF (PDF) e python-docx (DOCX);
3. **Segmentação textual** — divisão do documento em trechos menores para análise granular;
4. **Pré-processamento diferenciado** — limpeza com NLTK (tokenização, remoção de stopwords, normalização) para a via lexical, preservando o texto original para a via semântica;
5. **Análise lexical** — TF-IDF com similaridade de cosseno e de Jaccard (scikit-learn), voltada à detecção de cópias literais;
6. **Análise semântica** — embeddings gerados com SBERT (sentence-transformers), voltada à detecção de paráfrases;
7. **Combinação das métricas** — score híbrido integrando os resultados lexical e semântico;
8. **Processamento em lote** — execução assíncrona com Celery e Redis, permitindo a análise de múltiplos documentos simultaneamente;
9. **Persistência** — armazenamento dos resultados em PostgreSQL via SQLAlchemy;
10. **Relatório final** — endpoints que expõem percentuais de similaridade e trechos suspeitos como apoio à análise humana.

> ⚠️ Os resultados gerados pelo sistema **não são conclusivos**: constituem apoio ao avaliador humano, a quem cabe a decisão final sobre a ocorrência de plágio.

## Tecnologias

| Componente | Tecnologia |
|---|---|
| Linguagem | Python 3.13 |
| Framework web | FastAPI |
| Servidor ASGI | Uvicorn |
| Banco de dados | PostgreSQL + SQLAlchemy |
| Fila / lote | Celery + Redis |
| Extração de texto | PyMuPDF, python-docx |
| PLN | NLTK |
| Similaridade lexical | scikit-learn (TF-IDF, cosseno, Jaccard) |
| Similaridade semântica | sentence-transformers (SBERT) |
| Containerização | Docker |

## Estrutura de pastas

```
backend/
├── app/
│   ├── main.py          # Ponto de entrada da aplicação FastAPI
│   ├── api/             # Rotas da API (health, uploads, lotes, relatórios)
│   ├── core/            # Configurações e conexões
│   ├── models/          # Modelos ORM (SQLAlchemy)
│   ├── schemas/         # Schemas de entrada/saída (Pydantic)
│   ├── services/        # Extração, segmentação, pré-processamento, TF-IDF, SBERT
│   └── workers/         # Tarefas assíncronas (Celery)
├── requirements.txt
└── README.md
```

## Como executar

Pré-requisitos: Python 3.11+ instalado.

```powershell
# 1. Criar e ativar o ambiente virtual
py -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Instalar as dependências
pip install -r requirements.txt

# 3. Iniciar o servidor de desenvolvimento
uvicorn app.main:app --reload --port 8000
```

A API ficará disponível em `http://localhost:8000` e a documentação interativa (Swagger UI) em `http://localhost:8000/docs`.

## Endpoints disponíveis

| Método | Rota | Descrição |
|---|---|---|
| GET | `/api/health` | Verifica o estado do servidor e retorna nome/versão da aplicação |

*Novos endpoints (upload, status de lote e relatórios) serão adicionados conforme a evolução do protótipo.*

---

## Preparação offline da PAN-PC-11

O motor SBERT já está implementado com `sentence-transformers/all-MiniLM-L6-v2`.
Esta etapa prepara a base uma única vez, sem executá-la durante uploads.
Somente os **documentos-fonte em inglês** do corpus externo entram em
`reference_docs` e `reference_segments`. Os documentos suspeitos e seus XMLs
ficam separados para avaliação; o corpus intrínseco não entra na referência.

### 1. Descompactar os volumes

Mantenha `pan-plagiarism-corpus-2011.part1.rar` e `part2.rar` juntos. Use
UnRAR ou 7-Zip com suporte a RAR multiparte, começando pelo **part1**;
não extraia os volumes como arquivos independentes.

Exemplo com UnRAR disponível no PATH, executado na pasta `backend`:

```powershell
New-Item -ItemType Directory -Force data\pan-pc-11
unrar x -o- -y -p- "..\pan-plagiarism-corpus-2011.part1.rar" "data\pan-pc-11\"
```

O leitor aceita a pasta de extração, `pan-plagiarism-corpus-2011` ou diretamente
`external-detection-corpus`. A estrutura preservada é:

```text
data\pan-pc-11\pan-plagiarism-corpus-2011\
    external-detection-corpus\
        source-document\partN\source-documentNNNNN.txt
        source-document\partN\source-documentNNNNN.xml
        suspicious-document\partN\suspicious-documentNNNNN.txt
        suspicious-document\partN\suspicious-documentNNNNN.xml
    intrinsic-detection-corpus\
```

Corpora, RARs, modelos e índices em `data` não são versionados nem copiados
para a imagem Docker. Confira o conteúdo sem precisar de banco, Redis ou JWT:

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_pan_corpus inspect `
    --corpus-dir data\pan-pc-11 --ground-truth
```

Os XMLs fornecem `reference`, `about.lang`, `about.title`, `md5Hash` e os
casos `plagiarism`, quando presentes. O leitor preserva os atributos e
offsets do ground truth, inclusive casos sem fonte externa. TXT é lido
como UTF-8 sem normalizar quebras de linha ou remover BOM.
O MD5 do PAN pode omitir zeros iniciais; a validação considera esse formato.
Anotações com comprimento zero também existem no corpus: são preservadas e
contadas em `empty_span_annotations`, não confundidas com trechos positivos.

### 2. Importar e indexar um subconjunto

Configure o `.env` normalmente. Para PostgreSQL existente, aplique primeiro a
[migration 008](migrations/README.md#atualização-de-um-banco-existente), sem apagar
volumes. O comando abaixo usa a conexão configurada e seleciona deterministicamente
20 fontes inglesas:

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_pan_corpus prepare `
    --corpus-dir data\pan-pc-11 --limit 20 --batch-size 64
```

Para uma base experimental **separada do PostgreSQL da aplicação**:

```powershell
.\.venv\Scripts\python.exe -m scripts.prepare_pan_corpus prepare `
    --corpus-dir data\pan-pc-11 --limit 20 `
    --database-url "sqlite:///data/pan-experiment.sqlite3" --init-db `
    --index-dir data\pan-experiment-index
```

Essa alternativa ainda utiliza as configurações normais do backend (`REDIS_URL`,
`JWT_SECRET_KEY`, modelo e tamanho dos segmentos), mas não se conecta ao Redis
nem altera o banco da aplicação. `--init-db` só é permitido para um SQLite
explicitamente escolhido; não substitui migrations de bancos existentes.

Também é possível executar `import` e `index` separadamente. O limite padrão da
importação é **100 documentos**, não 100 segmentos; `--limit` permite ampliá-lo e
`--all` solicita explicitamente todas as fontes inglesas. A indexação inclui
todas as referências PAN inglesas já importadas no banco escolhido, não apenas
as adicionadas na última execução. Comece pequeno: livros completos podem gerar
muitos segmentos, e a etapa SBERT é a mais custosa.

### Reexecução e artefatos

- A identidade é `(source, corpus_id)`, independente do caminho absoluto.
  Reexecutar preserva os IDs e não segmenta novamente fontes já preparadas.
- Cada documento é uma transação. Uma interrupção mantém os anteriores e
  permite retomar; erros não são tratados como importações bem-sucedidas.
- SHA-256 do conteúdo, código do pré-processamento, stopwords e limite de
  palavras identificam a preparação. Conteúdo ou configuração diferentes
  exigem uma base experimental separada, sem substituir referências que
  possam estar associadas a resultados antigos.
- TF-IDF é ajustado sobre a base inteira selecionada. São salvos a matriz
  esparsa, vocabulário e IDF, além dos embeddings normalizados e IDs dos segmentos
  na mesma ordem de linhas. A busca reutiliza esse vocabulário/IDF, sem
  reajustar TF-IDF para cada par.
- SBERT reutiliza `generate_embeddings()` existente, em lotes limitados.
  Os embeddings são gravados progressivamente e podem ser carregados com
  mapeamento de memória, sem carregar a matriz inteira na RAM.
- O manifesto registra modelo, versões, identidade do banco preparado e hashes
  dos artefatos. Uma repetição compatível reutiliza o índice sem chamar SBERT.
  Use `index --rebuild` para refazer um cache danificado ou após atualizar os
  pesos de um modelo mantendo o mesmo nome.
- A publicação é atômica via `current.json`; uma falha não substitui o índice
  anterior. Gerações anteriores são mantidas para não invalidar leitores ativos.

O diretório padrão é `REFERENCE_INDEX_DIR=data/reference-index`. Os arquivos
NPY/NPZ/JSON não usam pickle. O módulo `app.services.references.corpus_index`
expõe `load_corpus_index()`; seu `expected_fingerprint` permite recusar um índice
que não corresponda ao banco consultado.

### Docker e próximas integrações

API e worker compartilham `.\data` em `/app/data`, incluindo o cache do modelo.
Após reconstruir a imagem, a preparação também pode ser executada no ambiente
Docker já configurado:

```powershell
docker compose run --rm --no-deps api python -m scripts.prepare_pan_corpus prepare `
    --corpus-dir /app/data/pan-pc-11 --limit 20
```

A pasta no comando acima é o caminho Linux **dentro do container**. O comando
não inicia dependências; PostgreSQL deve estar disponível.

O worker extrai, segmenta e analisa cada documento por uma task Celery
independente. Ele consulta este índice nos modos lexical e semântico, executa o
motor híbrido e persiste os resultados por par de segmentos. A busca Top-N
também permanece disponível pelo serviço e pela CLI descritos a seguir.

## Busca de referências — etapa 10

`ReferenceSearchService` recebe o **texto original de um segmento** e recupera
segmentos das fontes PAN inglesas já preparadas. A consulta aplica `transform`
no TF-IDF persistido e gera somente o embedding SBERT da consulta, preservando
seu texto original. As matrizes CSR e os embeddings em memmap são reutilizados;
Jaccard usa os tokens lexicais persistidos, sem reprocessar cada referência.

### Ranking, filtros e configuração

| Modo | Elegibilidade | Ordenação |
|---|---|---|
| `semantic` (padrão) | Cosseno semântico ≥ limiar semântico | Cosseno semântico decrescente |
| `lexical` | Cosseno TF-IDF ≥ limiar lexical **e** Jaccard ≥ seu limiar | Cosseno TF-IDF decrescente |

Não há filtro lexical no modo semântico nem filtro semântico no modo lexical.
Assim, uma consulta sem tokens no vocabulário TF-IDF, inclusive composta apenas
de stopwords, ainda pode recuperar candidatos semânticos. O AND lexical
existente é preservado somente como elegibilidade do modo lexical.

Empates são resolvidos pelo ID do segmento crescente. O limite é aplicado
**depois** dos filtros, inclusive Jaccard: são retornados até Top-N
**segmentos**, podendo haver vários do mesmo documento. Não há combinação de
scores, bônus por fonte conhecida ou uso de ground truth no ranking.

| Configuração | Padrão | Valores aceitos |
|---|---|---|
| `REFERENCE_SEARCH_MODE` | `semantic` | `semantic` ou `lexical` |
| `REFERENCE_SEARCH_TOP_N` | `5` | Inteiro positivo |
| `REFERENCE_SEARCH_SEMANTIC_THRESHOLD` | `0.5` | Número finito entre -1 e 1 |
| `LEXICAL_COSINE_THRESHOLD` | `0.5` | Número finito entre 0 e 1 |
| `LEXICAL_JACCARD_THRESHOLD` | `0.2` | Número finito entre 0 e 1 |
| `REFERENCE_INDEX_DIR` | `data/reference-index` | Diretório do índice compatível com o banco |

Esses limiares são **parâmetros calibráveis de recuperação**, não valores
cientificamente validados nem regras finais do motor híbrido da etapa 11.
Os filtros são inclusivos, sem arredondamento prévio; scores semânticos
negativos são preservados. O resultado não classifica cópia, paráfrase ou plágio.

### CLI

Use `--text` ou `--text-file` (UTF-8, contendo um único segmento), nunca ambos.
O arquivo não é extraído nem segmentado automaticamente. O exemplo usa
explicitamente a base experimental, sem conectar ao PostgreSQL da aplicação:

```powershell
.\.venv\Scripts\python.exe -m scripts.search_references `
    --text "The student submitted the final assignment." `
    --database-url "sqlite:///data/pan-experiment.sqlite3" `
    --index-dir data\pan-experiment-index --mode semantic --top-n 5
```

Para a via lexical, mantendo a elegibilidade AND:

```powershell
.\.venv\Scripts\python.exe -m scripts.search_references `
    --text-file segmento.txt --mode lexical --top-n 10 `
    --lexical-cosine-threshold 0.5 --lexical-jaccard-threshold 0.2 `
    --database-url "sqlite:///data/pan-experiment.sqlite3" `
    --index-dir data\pan-experiment-index
```

`--semantic-threshold` também permite sobrescrever o limiar semântico.
Parâmetros omitidos usam as configurações do backend. `--help` não precisa de
configuração do banco ou do modelo; a busca usa o `.env` normal, como a
preparação PAN, sem se conectar ao Redis.

A saída é JSON em stdout. Erros vão para stderr, com código de saída não zero.
SQLite é aberto em **somente leitura**: arquivo ausente não é criado e esta
CLI não oferece `--init-db`, importação, migrations ou reconstrução do índice.
Não associe `pan-experiment-index` a outro banco: a identidade é validada antes
da primeira consulta.

Com o modelo já presente no cache local, é possível impedir acesso à rede
durante uma execução:

```powershell
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
```

As variáveis acima valem para o terminal atual; em modo offline, modelo ausente
é um erro, não um resultado vazio. API e worker já recebem as configurações de
busca pelo Compose. Após reconstruir a imagem, a CLI também pode ser executada
no container, sem iniciar dependências:

```powershell
docker compose run --rm --no-deps api python -m scripts.search_references `
    --text "The student submitted the final assignment." --mode semantic `
    --database-url "sqlite:///data/pan-experiment.sqlite3" `
    --index-dir /app/data/pan-experiment-index
```

Nesse comando, os caminhos são internos ao container e o modelo usa o cache
configurado nele (`/app/data/huggingface`), não automaticamente o cache do host.

### Contrato público e reutilização

```python
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.repositories.references import ReferenceRepository
from app.services.references.reference_search import ReferenceSearchService

engine = create_engine(
    "sqlite:///file:data/pan-experiment.sqlite3?mode=ro&uri=true"
)
try:
    with Session(engine, autoflush=False) as db:
        search = ReferenceSearchService(
            ReferenceRepository(db), Path(r"data\pan-experiment-index")
        )
        result = search.search(
            "The student submitted the final assignment.",
            mode="semantic",
            top_n=5,
            semantic_threshold=0.5,
        )
        # Reutilize search para os demais segmentos do documento/lote.
finally:
    engine.dispose()
```

`search()` também aceita `lexical_cosine_threshold` e
`lexical_jaccard_threshold`. O retorno é uma dataclass imutável,
`ReferenceSearchResult`, serializável com `dataclasses.asdict()`:

| Campo | Conteúdo |
|---|---|
| `options` | Modo, Top-N e os três limiares efetivamente usados |
| `index_fingerprint` | Identidade da base preparada correspondente ao índice |
| `matches` | Sequência ordenada de correspondências |
| `comparison_ms` | Tempo da consulta em milissegundos |

Cada correspondência contém `source_document` (id, corpus_id, source, language,
title), `source_segment` (id, position, start_offset, end_offset, text_original),
`lexical_score`, `semantic_score` e `jaccard_score`. Textos e offsets vêm do banco;
não são reconstruídos a partir de tokens. Não são retornados objetos ORM,
score híbrido ou rótulo `is_suspicious`.

`comparison_ms` inclui pré-processamento da consulta, seu embedding,
comparações e leitura dos candidatos. Exclui inicialização do serviço e
validação dos artefatos; a primeira consulta pode incluir a carga do modelo.
As consultas seguintes reutilizam o índice e o modelo em memória, buscando
metadados em lotes, sem uma consulta SQL por candidato.

O serviço trabalha com um **snapshot offline imutável durante seu uso**.
Fingerprint, alinhamento de IDs, hashes e validade dos vetores são conferidos
na abertura, não a cada segmento. Mantenha a sessão SQLAlchemy aberta e não
compartilhe a mesma instância entre execuções concorrentes. Antes de reutilizar
o serviço após uma importação ou alteração da referência, chame
`search.revalidate()` entre documentos/lotes ou crie uma nova instância.
Revalidação não importa nem reindexa: base e índice já precisam ser coerentes.

Candidatos ausentes ou com texto, offsets ou identidade de preparação alterados
invalidam a instância. Mudanças arbitrárias em candidatos não consultados só
são detectadas na revalidação integral; não há monitoramento concorrente da base.
Uma revalidação malsucedida não permite voltar silenciosamente ao snapshot antigo.
Base vazia, índice ausente/corrompido/desatualizado, modelo incompatível e vetores
inválidos são erros. `matches` vazio significa apenas que nenhum candidato do
snapshot validado atingiu os filtros.

O serviço de busca é reutilizado pelo motor híbrido no worker. O upload apenas
persiste os arquivos e publica uma task por documento; a análise ocorre fora da
requisição HTTP.

---

## Motor híbrido — etapa 11

`HybridAnalysisService` reúne, para cada segmento do documento, a união dos
candidatos retornados pelos modos `lexical` e `semantic` da busca de referências.
Resultados repetidos são consolidados pelo ID do segmento de referência antes
do cálculo, portanto scores de referências diferentes nunca são combinados.

```python
from app.services.analysis.hybrid_analysis import HybridAnalysisService

analysis = HybridAnalysisService(db).analyze_document(document)
```

O serviço produz dataclasses imutáveis e o worker persiste cada par em
`AnalysisResult`. A busca existente calcula TF-IDF, Jaccard e SBERT para cada
candidato recuperado, inclusive quando ele veio de apenas um dos modos.

As regras padrão são:

```text
lexical_score = 0.7 * tfidf_score + 0.3 * jaccard_score
final_score   = 0.5 * lexical_score + 0.5 * semantic_score
overall_score = média do melhor final_score de cada segmento
```

Scores semânticos negativos são limitados a zero no contrato híbrido, mantendo
todas as métricas e resultados calculados no intervalo de 0 a 1. A classificação
é `LOW` abaixo de 0.40, `MODERATE` a partir de 0.40, `HIGH` a partir de 0.60 e
`VERY_HIGH` a partir de 0.80. Um match é indicativamente suspeito quando o score
final é pelo menos 0.60, o semântico é pelo menos 0.80, ou TF-IDF e Jaccard são,
respectivamente, pelo menos 0.70 e 0.50.

Pesos, thresholds e o limite final por segmento são configuráveis por estas
variáveis: `HYBRID_TFIDF_WEIGHT`, `HYBRID_JACCARD_WEIGHT`,
`HYBRID_LEXICAL_WEIGHT`, `HYBRID_SEMANTIC_WEIGHT`,
`HYBRID_CLASSIFICATION_MODERATE_THRESHOLD`,
`HYBRID_CLASSIFICATION_HIGH_THRESHOLD`,
`HYBRID_CLASSIFICATION_VERY_HIGH_THRESHOLD`,
`HYBRID_SUSPICIOUS_FINAL_THRESHOLD`, `HYBRID_SUSPICIOUS_SEMANTIC_THRESHOLD`,
`HYBRID_SUSPICIOUS_TFIDF_THRESHOLD`, `HYBRID_SUSPICIOUS_JACCARD_THRESHOLD` e
`HYBRID_TOP_N`. Cada par de pesos deve somar 1.0 e os thresholds de
classificação devem estar em ordem crescente.

`DocumentAnalysis` contém os totais do documento, a sequência de
`SegmentAnalysis`, `overall_score` e `suspicious_segment_percentage`. Esta última
é uma proporção indicativa de segmentos, não um percentual confirmado de
plágio.

O pipeline completo é disparado por `documents.process_document`, com até três
retries exponenciais para falhas transitórias. Os resultados podem ser
consultados em:

```text
GET /api/documents/{document_id}/analysis
GET /api/batches/{batch_id}/analysis
POST /api/documents/{document_id}/retry
```

`GET /api/health` verifica somente se o processo da API está vivo. Use
`GET /api/ready` para confirmar PostgreSQL, Redis, workers Celery, documentos e
segmentos de referência e o índice ativo. Uma resposta 503 informa cada
dependência ausente.

Cada documento concluído registra `analysis_profile` e
`reference_fingerprint`. Assim, o relatório preserva a política de pontuação e
a base usadas na execução, mesmo após uma mudança de configuração.

Para medir a recuperação contra as anotações externas da PAN-PC-11:

```powershell
python -m scripts.evaluate_pan_retrieval `
    --corpus-dir data\pan-pc-11 `
    --database-url $env:DATABASE_URL `
    --index-dir data\reference-index `
    --limit 100
```

A saída apresenta precisão@N, recall@N, F1@N e MRR, além dos casos ignorados
porque a fonte ainda não foi importada. Em volumes PostgreSQL existentes,
aplique as migrations 009 e 010 antes de iniciar os workers.

---

## Padrão de commits

As mensagens de commit são validadas por um hook (`.githooks/commit-msg`) no formato **Conventional Commits**:

```
prefixo: descrição em minúsculo        (máx. 72 caracteres na primeira linha)
```

Prefixos aceitos: `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, `test`. Exemplo: `feat: adiciona endpoint de upload`.

Após clonar o repositório, ative a validação local com:

```powershell
git config core.hooksPath .githooks
```

Independentemente do hook local, o GitHub Actions (`.github/workflows/valida-commits.yml`) revalida todas as mensagens a cada push/PR na nuvem.

---

FATEC Indaiatuba — Dr. Archimedes Lamoglia · Centro Estadual de Educação Tecnológica Paula Souza · 2025/2026
