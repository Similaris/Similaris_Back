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

## Padrão de commits

As mensagens de commit são validadas por um hook (`.githooks/commit-msg`) no formato **Conventional Commits**:

```
prefixo: descrição em minúsculo        (máx. 72 caracteres na primeira linha)
```

Prefixos aceitos: `build`, `chore`, `ci`, `docs`, `feat`, `fix`, `perf`, `refactor`, `revert`, `style`, `test`. Exemplo: `feat: adiciona endpoint de upload`.

Após clonar o repositório, ative a validação com:

```powershell
git config core.hooksPath .githooks
```

---

FATEC Indaiatuba — Dr. Archimedes Lamoglia · Centro Estadual de Educação Tecnológica Paula Souza · 2025/2026
