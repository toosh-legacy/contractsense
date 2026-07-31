# ContractSense

Contract negotiation intelligence for pricing teams. Upload a PDF and get two
0-100 scores — how risky the contract is, and how much room there is to
negotiate — plus the evidence behind both.

- **Risk score** — every clause is scored LOW/MEDIUM/HIGH and checked against a
  watchlist of *hidden clauses*: auto-renewals, uncapped price escalation,
  evergreen terms, indemnity carve-outs, exclusivity, minimum commitments.
- **Margin meter** — the contract's commercial terms are compared against
  cached industry benchmarks and current market conditions, and each gap
  becomes a specific ask you can take to the table.
- **Advice chat** — RAG over the contract, grounded in its assessment and the
  benchmarks, with web search when the question is about the market.

Scores come from a deterministic formula in `backend/app/services/scoring.py`,
not from the model, so the same findings always produce the same number and
every score ships with the reasons behind it.

- **backend/** — FastAPI. pdfplumber/PyMuPDF parsing → chunking →
  sentence-transformers embeddings → ChromaDB, with OpenAI for clause analysis,
  market lookup and Q&A.
- **frontend/** — Next.js (App Router, TypeScript, Tailwind v4).

> 📖 **[CODEBASE_GUIDE.md](CODEBASE_GUIDE.md)** — a file-by-file walkthrough of
> how it all works, with code snippets and the reasoning behind each decision.
> Start there if you want to understand or modify the code.

## Run with Docker

```bash
cp .env.example .env        # add your OPENAI_API_KEY
docker compose up --build
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

The first backend build is slow — it installs CPU torch and bakes the
`all-MiniLM-L6-v2` embedding model into the image. Uploads and the Chroma index
live in named volumes, so they survive rebuilds.

## Run locally

Backend:

```bash
cd backend
python -m venv venv && venv/Scripts/activate   # source venv/bin/activate on Unix
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env.local   # points at http://localhost:8000
npm run dev
```

## API

| Endpoint             | Method | Purpose                                                  |
| -------------------- | ------ | -------------------------------------------------------- |
| `/upload`            | POST   | Parse, chunk, embed and index a PDF                       |
| `/assess`            | POST   | **Risk score + margin meter, hidden clauses and levers**  |
| `/assess/{name}`     | GET    | A cached assessment, without recomputing it               |
| `/advise`            | POST   | Negotiation advice grounded in the contract and market    |
| `/industries`        | GET    | Industries we hold benchmarks for                         |
| `/ask`               | POST   | RAG answer to a question about an indexed contract        |
| `/search`            | POST   | Raw semantic search over indexed chunks                   |
| `/analyze`           | POST   | Per-clause LOW/MEDIUM/HIGH risk report                    |
| `/extract`           | POST   | Structured key terms (parties, dates, obligations)        |
| `/health`            | GET    | Liveness check                                            |

`/assess` reads the contract's chunks back out of ChromaDB rather than asking
for the file again, and caches the finished report to `data/reports/`, so
reopening a contract is instant. Pass `refresh: true` to recompute, or
`industry` to override the auto-detected one.

## Industry benchmarks

`backend/app/data/benchmarks.json` holds the negotiation norms each contract is
judged against — payment terms, uplift caps, liability caps, termination
notice and so on, for six industries plus a general fallback. It is plain JSON
and meant to be edited: add an industry, or tune a norm, and the margin meter
follows.

## Configuration

Backend env vars (`backend/.env` locally, compose `environment:` in Docker):

| Var                   | Default                 | Notes                                              |
| --------------------- | ----------------------- | -------------------------------------------------- |
| `OPENAI_API_KEY`      | —                       | Required for every endpoint that calls the model    |
| `OPENAI_MODEL`        | `gpt-4o-mini`           |                                                     |
| `UPLOAD_DIR`          | `data/uploads`          |                                                     |
| `CHROMA_DIR`          | `data/chroma`           |                                                     |
| `REPORTS_DIR`         | `data/reports`          | Cached assessments                                  |
| `CHUNK_SIZE`          | `500`                   | Words per chunk                                     |
| `CHUNK_OVERLAP`       | `50`                    |                                                     |
| `ANALYSIS_BATCH_SIZE` | `5`                     | Chunks per LLM call during an assessment            |
| `ENABLE_WEB_SEARCH`   | `true`                  | Set false to skip the market lookup and save cost   |
| `CORS_ORIGINS`        | `http://localhost:3000` | Comma-separated                                     |

Market context uses OpenAI's hosted `web_search` tool via the Responses API, so
it needs no key beyond `OPENAI_API_KEY`. It is best-effort: if the search fails
or is disabled, the assessment still completes from the benchmarks alone.

Frontend reads `NEXT_PUBLIC_API_URL`. It is inlined at **build** time, so in
Docker it is passed as a build arg, not a runtime env var.
