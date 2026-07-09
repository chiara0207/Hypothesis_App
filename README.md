# Statistical Hypothesis Testing Assistant

A research tool for students and academics. Upload **PDFs** and **CSV/XLSX datasets**, ask questions in plain language, search across multiple academic databases, rank your literature by relevance, and chat with an AI about any hypothesis.

---

## Features

| Tab | What it does |
|-----|-------------|
| **Ask Questions** | Chat with an uploaded research PDF using RAG (retrieval-augmented generation) |
| **Statistical Analysis** | Describe a hypothesis in plain language — the AI picks the right test, SciPy runs it, the AI explains the results. Results come with an interactive Plotly chart suite (boxplot, violin, bell curve, histogram, scatter, correlation matrix, or contingency heatmap depending on the test), a plain-language caption and handbook per chart, and a mini chat to ask follow-up questions about any chart. Export to CSV or XLSX. |
| **Data Preview** | Inspect columns, types, and sample rows from your uploaded dataset |
| **Find Papers & Datasets** | Enter a research question — searches Semantic Scholar, arXiv, PubMed, and OpenAlex in parallel and summarises the literature with an LLM; or switch to dataset mode to search Zenodo, DataCite, and OpenAlex Datasets for open data matching your hypothesis |
| **Hypothesis Chat** | Chat about any hypothesis, scientific or wild — the AI engages thoughtfully and asks follow-up questions |
| **Rank Papers** | Upload up to 20 PDFs — the AI ranks them by relevance to your research question with explanations and key quotes. Export to Word or PDF. |
| **Statistics Handbook** | Look up core statistics concepts and every supported hypothesis test in plain language, or ask the built-in chatbot — answers ground themselves in your actual test result when one is available. |

The UI is a **Next.js** app (`frontend-web/`); all heavy logic lives in a **FastAPI** backend. They communicate over HTTP on `localhost`.

---

## Table of contents

- [Architecture overview](#architecture-overview)
- [Project structure](#project-structure)
- [Startup](#startup)
- [Flow 1: PDF upload and Q&A](#flow-1-pdf-upload-and-qa)
- [Flow 2: Dataset upload and statistical analysis](#flow-2-dataset-upload-and-statistical-analysis)
- [Flow 3: Find Papers & Datasets](#flow-3-find-papers--datasets)
- [Flow 4: Hypothesis Chat](#flow-4-hypothesis-chat)
- [Flow 5: Rank Papers](#flow-5-rank-papers)
- [Export options](#export-options)
- [Frontend state](#frontend-state)
- [Backend modules reference](#backend-modules-reference)
- [API endpoints](#api-endpoints)
- [Supported statistical tests](#supported-statistical-tests)
- [Environment variables](#environment-variables)

---

## Architecture overview

```mermaid
flowchart TD
    Browser(["Browser"]) --> UI["Next.js frontend-web\nsrc/app/* — :3000"]
    UI -- "HTTP (fetch via lib/api.ts)" --> API["FastAPI backend\napp_backend/main.py — :8000"]

    subgraph Routers["FastAPI routers"]
        RUpload["/upload/pdf\n/upload/csv"]
        RQA["/qa/ask"]
        RStats["/stats/analyze\n/stats/examples"]
        RViz["/visualization/suite\n/visualization/ask"]
        RSearch["/search/papers\n/search/datasets"]
        RChat["/chat/message"]
        RRank["/rank/papers"]
        RHandbook["/handbook/concepts\n/handbook/ask"]
    end
    API --> RUpload & RQA & RStats & RViz & RSearch & RChat & RRank & RHandbook

    RUpload --> PdfPipe["parser → chunker → embedder"] --> VecStore[("VectorStore\nFAISS IndexFlatIP")]
    RUpload --> SessionStore[("session_store\nsession_id → DataFrame")]

    RQA --> QAEngine["qa_engine.py — RAG"] --> VecStore
    QAEngine --> OpenAI

    RStats --> StatsService["stats_service.py\nprofile → LLM select → SciPy → LLM explain"]
    StatsService --> SessionStore
    StatsService --> OpenAI

    RViz --> VizService["visualization_service.py\nPlotly charts + handbook + Q&A context"]
    VizService --> SessionStore
    VizService --> OpenAI

    RSearch --> Academic["Semantic Scholar · arXiv\nPubMed · OpenAlex (papers, free, no keys)"]
    RSearch --> DataReg["Zenodo · DataCite\nOpenAlex Datasets (free, no keys)"]
    RSearch --> OpenAI

    RChat --> OpenAI

    RRank --> RankLogic["PyPDF2 extract → embeddings → cosine rank → LLM explain"] --> OpenAI

    RHandbook --> HandbookService["handbook_service.py\nconcept glossary + grounded test-result Q&A"]
    HandbookService --> OpenAI

    OpenAI["OpenAI API\ngpt-4o-mini · text-embedding-3-small"]
```

*(Renders automatically on GitHub. A downloadable image is also kept at [`docs/architecture.png`](docs/architecture.png) — regenerate it after editing the diagram above with:*

```bash
awk '/^```mermaid$/{f=1;next} /^```$/{if(f){f=0;next}} f' README.md > /tmp/arch.mmd
npx @mermaid-js/mermaid-cli -i /tmp/arch.mmd -o docs/architecture.png -w 1600 -H 1200 -s 3 -b white
```

*Or paste the block into [mermaid.live](https://mermaid.live) to export SVG/PNG by hand.)*

| Layer | Technology | Role |
|-------|------------|------|
| Frontend | Next.js (App Router), TypeScript | Pages/nav, file uploads, chat UI, results display, export |
| API | FastAPI | REST endpoints, CORS, shared singletons |
| PDF pipeline | PyPDF2, chunker, OpenAI embeddings | Index document for search |
| Vector search | FAISS (or numpy fallback) | Similarity search over chunk embeddings |
| Data | pandas | Load CSV/XLSX, profile schema, run tests |
| Statistics | SciPy, statsmodels | Actual hypothesis tests |
| Visualization | Plotly (`graph_objects`) | Gauge, boxplot, violin, bell curve, histogram, scatter, correlation matrix, contingency heatmap |
| Intelligence | OpenAI (`gpt-4o-mini`, `text-embedding-3-small`) | Test selection, Q&A, explanations, summaries, chat, chart Q&A, handbook Q&A |
| Academic search | Semantic Scholar, arXiv, PubMed, OpenAlex APIs | Free paper search — no API keys required |
| Dataset search | Zenodo, DataCite, OpenAlex Datasets APIs | Free open-dataset search — no API keys required |
| Handbook | `handbook_service.py` | Statistics concept glossary + grounded chatbot over a computed result |
| Export | python-docx, reportlab, openpyxl | Word, PDF, XLSX file generation |

---

## Project structure

```
Hypothesis_App/
├── frontend-web/                       # Next.js (App Router) UI
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                # Landing page
│   │   │   ├── hypothesis-chat/        # Flow 4
│   │   │   ├── ask-questions/          # Flow 1
│   │   │   ├── find/                   # Flow 3 (papers + datasets)
│   │   │   ├── rank-papers/            # Flow 5
│   │   │   ├── statistical-analysis/   # Flow 2
│   │   │   ├── handbook/               # Statistics Handbook
│   │   │   └── data-preview/           # Dataset column/row inspection
│   │   ├── components/
│   │   │   ├── AppShell.tsx            # Sidebar nav + PDF/CSV upload tiles
│   │   │   ├── ChartCard.tsx           # Plotly chart + handbook/Q&A expanders
│   │   │   └── PlotlyChart.tsx         # Plotly.js wrapper
│   │   └── lib/
│   │       ├── api.ts                  # fetch wrapper (BACKEND_URL, JSON/multipart)
│   │       ├── store.ts                # Zustand — PDF/CSV/stats global state
│   │       ├── nav.ts                  # Sidebar nav items
│   │       └── types.ts                # Shared TS types
│   └── .env.local                      # NEXT_PUBLIC_BACKEND_URL
├── app_backend/
│   ├── main.py                 # FastAPI app factory, wires routers + singletons
│   ├── config.py               # Loads .env, OpenAI and path settings
│   ├── models/schema.py        # Pydantic request/response models
│   ├── routers/
│   │   ├── upload.py           # POST /upload/pdf, /upload/csv
│   │   ├── qa.py               # POST /qa/ask
│   │   ├── stats.py            # POST /stats/analyze, /stats/examples
│   │   ├── visualization.py    # POST /visualization/suite, /visualization/ask
│   │   ├── search.py           # POST /search/papers, /search/datasets (multi-source search)
│   │   ├── chat.py             # POST /chat/message (hypothesis chatbot)
│   │   ├── rank.py             # POST /rank/papers (PDF relevance ranking)
│   │   └── handbook.py         # GET /handbook/concepts, POST /handbook/ask
│   ├── services/
│   │   ├── parser.py           # PDF → text
│   │   ├── chunker.py          # Text → overlapping chunks
│   │   ├── embedder.py         # Text → OpenAI vectors
│   │   ├── qa_engine.py        # RAG question answering
│   │   ├── stats_service.py    # Profile → select test → run → explain
│   │   ├── visualization_service.py  # Test result → Plotly chart suite +
│   │   │                              # handbook + LLM chart Q&A context
│   │   └── handbook_service.py # Concept glossary + grounded test-result Q&A
│   └── utils/
│       ├── vector_store.py     # FAISS IndexFlatIP or numpy fallback
│       └── session_store.py    # session_id → DataFrame
├── requirements.txt
├── .env.example
└── README.md
```

---

## Startup

Both processes must run simultaneously.

### 1. Create and activate virtual environment

```bash
# Create
python -m venv myenv

# Activate (macOS / Linux)
source myenv/bin/activate

# Activate (Windows PowerShell)
./myenv/Scripts/Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

Copy `.env.example` to `.env` and add your OpenAI API key:

```
OPENAI_API_KEY=sk-...
```

`frontend-web/.env.local` already points at the local backend by default:

```
NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

### 4. Start the backend (Terminal 1)

```bash
uvicorn app_backend.main:app --reload --port 8000
```

### 5. Install and start the frontend (Terminal 2)

```bash
cd frontend-web
npm install   # first time only
npm run dev
```

Open **http://localhost:3000** in your browser.

### Restarting after changes

```bash
# Backend: stop with Ctrl+C, then:
source myenv/bin/activate && uvicorn app_backend.main:app --reload --port 8000

# Frontend: Next.js hot-reloads on save; restart only if it hangs:
cd frontend-web && npm run dev
```

---

## Flow 1: PDF upload and Q&A

Use this to **chat with a research paper** — ask about methods, findings, definitions, or limitations.

```
User picks PDF in sidebar
    → POST /upload/pdf (multipart)
        → parser.py: PyPDF2 extracts text per page
        → chunker.py: ~1000-token chunks with 200-token overlap
        → embedder.py: OpenAI text-embedding-3-small for all chunks
        → vector_store.py: FAISS IndexFlatIP stores normalised vectors
    → Zustand store marks the PDF as uploaded (sidebar tile in AppShell)

User asks a question
    → POST /qa/ask { question, top_k: 5 }
        → embed question → cosine search → top_k chunks
        → OpenAI chat with retrieved context
    → Answer + source cards with relevance bars shown in chat
```

**Note:** Clicking "Remove PDF" clears frontend state only. Backend vectors persist until server restart.

---

## Flow 2: Dataset upload and statistical analysis

Use this for **automated hypothesis testing** on tabular data.

```
User picks CSV/XLSX in sidebar
    → POST /upload/csv
        → pandas read_csv / read_excel
        → session_store creates session_id → DataFrame
    → Preview, column types, and example questions shown

User types a question → "Run Analysis"
    → POST /stats/analyze { session_id, question }
        → Phase A: profile_dataframe (dtypes, nulls, uniques, ranges)
        → Phase B: LLM selects test + column mapping (temperature 0)
        → Phase C: SciPy / statsmodels runs the test
        → Phase D: LLM writes technical + plain-language explanation
    → Results: test badge, p-value, significance, rationale,
               variables used, assumption checks, interpretations
    → Result persisted in the Zustand store (survives navigating to other
      tabs and back) and added to stats history → exportable as CSV or XLSX

Result renders → POST /visualization/suite { session_id, test_name,
                                              variables_used, p_value, alpha }
    → visualization_service picks charts by test shape:
        • independent_ttest / one_way_anova → boxplot, violin plot,
          bell curves (per-group normal approximation), grouped histogram
        • pearson_correlation / simple_linear_regression → scatterplot
          with trend line, histograms, correlation matrix (all numeric cols)
        • chi_square → contingency heatmap
        • every suite always includes the p-value-vs-alpha gauge
    → Each chart returns: Plotly figure JSON, a data-grounded plain-language
      caption, and a general "handbook" entry (what it is / how to read it /
      when it's used)
    → Rendered as tabs, each with a "📖 Learn more" expander (handbook) and
      a "💬 Ask about this chart" expander

User asks a follow-up question in a chart's Q&A box
    → POST /visualization/ask { session_id, test_name, variables_used,
                                 chart_key, question, history, p_value, alpha }
        → describe_chart_context() rebuilds the concrete numbers behind
          that specific chart (group means/stds, r, contingency counts…)
        → OpenAI chat answers using only those numbers — grounded, not guessed
    → Answer appended to a per-chart conversation thread
```

| Phase | Who decides | Output |
|-------|-------------|--------|
| A | Code | Schema JSON |
| B | LLM | Test name + column mapping + rationale |
| C | SciPy | p-value, statistic, assumption checks |
| D | LLM | Human-readable interpretations |
| Visualization | Code (Plotly) | Chart suite + captions + handbook |
| Chart Q&A | LLM (grounded in real numbers) | Follow-up explanations per chart |

---

## Flow 3: Find Papers & Datasets

Use this to **discover relevant academic papers, or open datasets**, for a research question. A mode toggle on the page switches between the two.

```
User types research question → selects sources → "Search Papers"
    → POST /search/papers { question, limit, sources }
        → LLM extracts focused search keywords (gpt-4o-mini)
        → Selected sources queried in parallel (ThreadPoolExecutor):
            • Semantic Scholar API (all fields, citation counts, open-access PDFs)
            • arXiv API (physics, math, CS, biology — parsed from Atom XML)
            • PubMed/NCBI eSearch + eSummary (medical & life sciences)
            • OpenAlex API (250M+ works; abstract reconstructed from inverted index)
        → Results deduplicated by DOI and normalised title
        → Sorted: papers with abstracts and high citations first
        → LLM generates a 3-5 sentence literature synthesis
    → UI shows: source badge, authors, year, citations, abstract,
                links (Semantic Scholar, PDF, DOI), LLM summary above list

User switches to "Datasets" mode → selects sources → "Search Datasets"
    → POST /search/datasets { question, limit, sources }
        → Same keyword-extraction step, queried against open dataset registries:
            • Zenodo API
            • DataCite API
            • OpenAlex API filtered to type=dataset
        → Results deduplicated by DOI and normalised title
        → Sorted: datasets with a description first, then most recent
        → LLM generates a short synthesis of what's available
    → UI shows: source badge, authors, year, description, file formats,
                dataset link, LLM summary above list
```

All seven sources (four paper, three dataset) are free — no API keys required.

---

## Flow 4: Hypothesis Chat

Use this to **explore any hypothesis conversationally** — scientific or completely wild.

```
User types a hypothesis (or picks a starter prompt)
    → POST /chat/message { message, history }
        → OpenAI chat with system prompt tuned for hypothesis engagement:
            • Serious hypotheses: evidence, plausibility, relevant science
            • Wild hypotheses: creative but informed exploration
            • Always ends with a follow-up question
        → Last 10 messages sent as history for context
    → Reply shown in chat; conversation continues
```

---

## Flow 5: Rank Papers

Use this to **rank your literature collection** by relevance to your thesis — saves time when deciding which papers to read first.

```
User uploads PDFs (up to 20) + types research question → "Rank Papers"
    → POST /rank/papers (multipart: files + question form field)
        → PyPDF2 extracts text from first 6 pages of each PDF (max 4000 chars)
        → OpenAI embeddings for question + all papers in one batch call
        → Cosine similarity computed per paper
        → LLM generates per-paper explanation (2 sentences) + key quote
        → Papers sorted highest → lowest similarity score
    → UI shows: colour-coded label, % match bar, explanation, key quote
                Top 3 expanded automatically
    → Exportable as Word (.docx) or PDF
```

**Relevance labels:**

| Label | Score range |
|-------|------------|
| Highly Relevant | ≥ 82% |
| Relevant | 70–81% |
| Somewhat Relevant | 55–69% |
| Less Relevant | < 55% |

---

## Export options

| Feature | Formats | What's included |
|---------|---------|-----------------|
| Statistical Analysis | CSV, XLSX | Question, test name, p-value, statistic, alpha, significance, variables, interpretation, plain explanation, rationale |
| Paper Rankings | Word (.docx), PDF | Title, research question, ranked papers with label, match %, explanation, key quote |

Export buttons appear automatically once results are available.

---

## Frontend state

`frontend-web` splits state into a small global **Zustand** store (`lib/store.ts`) for what needs to survive moving between pages, and plain **React `useState`** local to each page for everything else.

| Store | Key | Purpose |
|-------|-----|---------|
| Zustand (global) | `pdfUploaded`, `pdfFilename` | Drives the PDF upload tile in `AppShell`'s sidebar, visible on every page |
| Zustand (global) | `csvSessionId`, `csvFilename`, `csvColumns`, `csvDtypes`, `csvPreview`, `csvRows` | Dataset identity/preview, shared by the sidebar tile, Data Preview, and Statistical Analysis pages |
| Zustand (global) | `lastStatsResult` | Most recent analysis result, so it's still shown if the user navigates away and back |
| Zustand (global) | `statsHistory` | Past analyses for the history list and CSV/XLSX export |
| Local (`ask-questions`) | chat messages `{role, content, sources?}` | Q&A conversation — resets on navigation away |
| Local (`statistical-analysis`) | per-chart Q&A thread, keyed by chart | Chart follow-up conversations — resets on navigation away |
| Local (`find`) | `mode`, `queryUsed`, `summary`, `paperResults`/`datasetResults` | Find Papers & Datasets results — resets on navigation away |
| Local (`hypothesis-chat`) | chat history | Hypothesis Chat conversation — resets on navigation away |
| Local (`rank-papers`) | `question`, `files`, `papers` | Rank Papers results — resets on navigation away |
| Local (`handbook`) | chat history | Handbook chatbot conversation — resets on navigation away |

---

## Backend modules reference

| Module | Role |
|--------|------|
| `main.py` | App factory, CORS, singleton wiring, router mounting |
| `config.py` | `.env` loading, model names, token/context limits |
| `routers/upload.py` | Multipart PDF and CSV handling |
| `routers/qa.py` | Delegates to `QAEngine` |
| `routers/stats.py` | Loads session DataFrame, calls stats pipeline |
| `routers/visualization.py` | Loads session DataFrame, calls chart-suite builder / chart Q&A |
| `routers/search.py` | Keyword extraction, parallel multi-source search (papers and datasets), deduplication, LLM summary |
| `routers/chat.py` | Hypothesis chatbot with conversation history |
| `routers/rank.py` | PDF text extraction, embedding, cosine ranking, LLM explanations |
| `routers/handbook.py` | Concept glossary endpoint; grounded Q&A over a computed test result |
| `services/parser.py` | PDF → text (PyPDF2) |
| `services/chunker.py` | Overlapping text chunks for RAG |
| `services/embedder.py` | OpenAI embedding batches |
| `services/qa_engine.py` | Retrieve chunks + generate answer |
| `services/stats_service.py` | Profile → LLM select → SciPy → LLM explain |
| `services/visualization_service.py` | Test result → Plotly chart suite, plain-language captions, chart handbook, and grounded context for chart Q&A |
| `services/handbook_service.py` | Statistics concept glossary + describes a test result's numbers for grounded chatbot answers |
| `utils/vector_store.py` | FAISS `IndexFlatIP` or numpy fallback |
| `utils/session_store.py` | In-memory `session_id` → `{df, filename}` |

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload/pdf` | Upload PDF → chunk → embed → FAISS |
| `POST` | `/upload/csv` | Upload CSV/XLSX → `session_id` + metadata |
| `POST` | `/qa/ask` | RAG question over indexed PDF |
| `POST` | `/stats/analyze` | LLM + SciPy analysis on session dataset |
| `POST` | `/stats/examples` | Generate example questions for a dataset |
| `POST` | `/visualization/suite` | Build the Plotly chart suite + captions + handbook for a result |
| `POST` | `/visualization/ask` | Answer a follow-up question about one chart, grounded in its real numbers |
| `POST` | `/search/papers` | Multi-source academic paper search |
| `POST` | `/search/datasets` | Multi-source open dataset search |
| `POST` | `/chat/message` | Hypothesis chatbot turn |
| `POST` | `/rank/papers` | Rank uploaded PDFs by relevance to a question |
| `GET` | `/handbook/concepts` | Full statistics concept + test glossary |
| `POST` | `/handbook/ask` | Answer a statistics question, grounded in a test result if supplied |
| `GET` | `/health` | `{ "status": "ok" }` |

Interactive docs: **http://localhost:8000/docs**

---

## Supported statistical tests

Only **active** tests are selectable by the LLM (`SUPPORTED_TESTS` in `stats_service.py`) and get a visualization suite. The rest are implemented but disabled — commented out of the active list — and are listed here for reference.

| Identifier | Display name | Status | Visualization suite |
|------------|--------------|--------|----------------------|
| `independent_ttest` | Independent Samples T-Test | Active | boxplot, violin, bell curve, histogram |
| `pearson_correlation` | Pearson Correlation | Active | scatterplot, histograms, correlation matrix |
| `simple_linear_regression` | Simple Linear Regression | Active | scatterplot, histograms, correlation matrix |
| `chi_square` | Chi-Square Test of Independence | Active | contingency heatmap |
| `one_way_anova` | One-Way ANOVA | Active | boxplot, violin, bell curve, histogram |
| `paired_ttest` | Paired Samples T-Test | Inactive | — |
| `one_sample_ttest` | One-Sample T-Test | Inactive | — |
| `spearman_correlation` | Spearman Correlation | Inactive | — |
| `multiple_linear_regression` | Multiple Linear Regression | Inactive | — |
| `logistic_regression` | Logistic Regression (binary outcome) | Inactive | — |
| `mann_whitney_u` | Mann-Whitney U Test | Inactive | — |
| `kruskal_wallis` | Kruskal-Wallis Test | Inactive | — |
| `wilcoxon_signed_rank` | Wilcoxon Signed-Rank Test | Inactive | — |

Every active test also gets the p-value-vs-alpha gauge. Parametric tests include assumption checks (Shapiro-Wilk normality, Levene's equal variance) returned in the result.

---

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | — | **Required** — used for embeddings, Q&A, stats, search summaries, chat, and ranking |
| `OPENAI_CHAT_MODEL` | `gpt-4o-mini` | Chat completions model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings for RAG and paper ranking |
| `OPENAI_MAX_CONTEXT_CHARS` | `12000` | Max retrieved context length for Q&A |
| `OPENAI_MAX_OUTPUT_TOKENS` | `1500` | Max tokens for generated answers/explanations |
| `UPLOAD_DIR` | `/tmp/stat_app_uploads` | Upload directory (created automatically) |

`frontend-web/.env.local` (frontend, not backend):

| Variable | Default | Description |
|----------|---------|--------------|
| `NEXT_PUBLIC_BACKEND_URL` | `http://localhost:8000` | Base URL the Next.js app calls for all API requests (`lib/api.ts`) |
