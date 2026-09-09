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
  na mesma ordem de linhas. As futuras consultas devem usar esse vocabulário/IDF,
  não reajustar TF-IDF para cada par.
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

O worker atual ainda extrai e segmenta documentos: não consulta este índice,
não executa o motor híbrido e não persiste resultados de similaridade.
As próximas entregas são busca Top-N na referência, integração lexical/SBERT,
combinação e persistência de resultados, endpoints de relatório e telas.

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
