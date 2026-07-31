# ContractSense

AI-powered contract analysis. Upload a PDF, then ask questions about it, score
every clause for risk, or extract the structured key terms.

- **backend/** — FastAPI. pdfplumber/PyMuPDF parsing → chunking →
  sentence-transformers embeddings → ChromaDB, with OpenAI for Q&A and risk
  scoring.
- **frontend/** — Next.js (App Router, TypeScript, Tailwind v4).

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

| Endpoint   | Method | Purpose                                            |
| ---------- | ------ | -------------------------------------------------- |
| `/upload`  | POST   | Parse, chunk, embed and index a PDF                 |
| `/ask`     | POST   | RAG answer to a question about an indexed contract  |
| `/search`  | POST   | Raw semantic search over indexed chunks             |
| `/analyze` | POST   | Per-clause LOW/MEDIUM/HIGH risk report              |
| `/extract` | POST   | Structured key terms (parties, dates, obligations)  |
| `/health`  | GET    | Liveness check                                      |

## Configuration

Backend env vars (`backend/.env` locally, compose `environment:` in Docker):

| Var              | Default                 | Notes                                       |
| ---------------- | ----------------------- | ------------------------------------------- |
| `OPENAI_API_KEY` | —                       | Required for `/ask`, `/analyze`, `/extract` |
| `UPLOAD_DIR`     | `data/uploads`          |                                             |
| `CHROMA_DIR`     | `data/chroma`           |                                             |
| `CHUNK_SIZE`     | `500`                   | Words per chunk                             |
| `CHUNK_OVERLAP`  | `50`                    |                                             |
| `CORS_ORIGINS`   | `http://localhost:3000` | Comma-separated                             |

Frontend reads `NEXT_PUBLIC_API_URL`. It is inlined at **build** time, so in
Docker it is passed as a build arg, not a runtime env var.
