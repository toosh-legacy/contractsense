import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.services.chunker import chunk_document
from app.services.embedder import embed_chunks, embed_query
from app.services.pdf_parser import parse_pdf, get_document_stats
from app.services.vector_store import search, store_embeddings

from app.services.llm import answer_question, extract_key_terms
from app.services.risk_analyzer import analyze_contract_risks
from app.services.vector_store import get_chroma_client, get_or_create_collection

router = APIRouter()


# ── Request / Response models ────────────────────────────────
# These are the shapes of data coming in and going out
# Pydantic validates them automatically — if a required field
# is missing, FastAPI returns a 422 error with a clear message

class SearchRequest(BaseModel):
    collection_name: str   # which document to search
    query: str             # the user's question
    n_results: int = 5     # how many chunks to return (default 5)


class ChunkResult(BaseModel):
    text: str
    page_num: int
    chunk_index: int
    similarity_score: float


class SearchResponse(BaseModel):
    query: str
    collection_name: str
    results: list[ChunkResult]


class UploadResponse(BaseModel):
    filename: str
    collection_name: str
    total_pages: int
    total_words: int
    total_chunks: int
    message: str

class KeyTermsResponse(BaseModel):
    filename: str
    contract_type: str
    parties: list[str]
    effective_date: str | None
    expiry_date: str | None
    governing_law: str | None
    key_obligations: list[str]


class RiskReport(BaseModel):
    collection_name: str
    overall_risk: str
    risk_counts: dict
    total_clauses_analyzed: int
    high_risk_clauses: list[dict]
    all_clauses: list[dict]


class AnswerResponse(BaseModel):
    question: str
    answer: str
    sources: list[str]


class AskRequest(BaseModel):
    collection_name: str
    question: str


# ── Endpoints ────────────────────────────────────────────────

@router.post("/upload", response_model=UploadResponse)
async def upload_contract(file: UploadFile = File(...)):
    """
    Upload a PDF contract.

    This endpoint:
    1. Saves the PDF to disk
    2. Parses it with pdfplumber / PyMuPDF
    3. Chunks the text
    4. Embeds the chunks
    5. Stores everything in ChromaDB

    Returns stats about the processed document.
    """
    # Validate file type before doing any work
    if not file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are supported."
        )

    # Make sure the upload directory exists
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Save the uploaded file to disk
    file_path = upload_dir / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Run the full pipeline
    try:
        # Parse
        doc = parse_pdf(file_path)
        stats = get_document_stats(doc)

        # Chunk
        chunks = chunk_document(
            doc,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

        # Embed
        embedded = embed_chunks(chunks)

        # Store — use filename (without .pdf) as collection name
        collection_name = file.filename.replace(".pdf", "").replace(" ", "_").lower()
        store_embeddings(collection_name, embedded)

    except ValueError as e:
        # Clean up the saved file if processing fails
        os.remove(file_path)
        raise HTTPException(status_code=422, detail=str(e))

    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

    return UploadResponse(
        filename=file.filename,
        collection_name=collection_name,
        total_pages=stats["total_pages"],
        total_words=stats["total_words"],
        total_chunks=len(chunks),
        message="Contract processed and ready to search.",
    )


@router.post("/search", response_model=SearchResponse)
async def search_contract(request: SearchRequest):
    """
    Search a processed contract with a natural language question.

    Embeds the query and finds the most semantically similar
    chunks from the specified collection.
    """
    if not request.query.strip():
        raise HTTPException(
            status_code=400,
            detail="Query cannot be empty."
        )

    if request.n_results < 1 or request.n_results > 20:
        raise HTTPException(
            status_code=400,
            detail="n_results must be between 1 and 20."
        )

    try:
        query_vector = embed_query(request.query)
        raw_results = search(
            collection_name=request.collection_name,
            query_embedding=query_vector,
            n_results=request.n_results,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )

    return SearchResponse(
        query=request.query,
        collection_name=request.collection_name,
        results=[ChunkResult(**r) for r in raw_results],
    )

@router.post("/extract", response_model=KeyTermsResponse)
async def extract_terms(file: UploadFile = File(...)):
    """
    Upload a PDF and extract key structured information:
    parties, dates, contract type, and key obligations.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        doc = parse_pdf(file_path)
        terms = extract_key_terms(doc.raw_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return KeyTermsResponse(
        filename=file.filename,
        contract_type=terms.get("contract_type", "Unknown"),
        parties=terms.get("parties", []),
        effective_date=terms.get("effective_date"),
        expiry_date=terms.get("expiry_date"),
        governing_law=terms.get("governing_law"),
        key_obligations=terms.get("key_obligations", []),
    )


@router.post("/analyze", response_model=RiskReport)
async def analyze_risks(file: UploadFile = File(...)):
    """
    Upload a PDF and get a full risk analysis report.
    Every clause is scored LOW / MEDIUM / HIGH with a plain
    English reason and recommendation.
    """
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / file.filename

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        doc = parse_pdf(file_path)
        chunks = chunk_document(
            doc,
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
        risk_report = analyze_contract_risks(chunks)
        collection_name = file.filename.replace(".pdf", "").replace(" ", "_").lower()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return RiskReport(
        collection_name=collection_name,
        **risk_report,
    )


@router.post("/ask", response_model=AnswerResponse)
async def ask_question(request: AskRequest):
    """
    Ask a natural language question about an already-uploaded contract.
    Retrieves relevant chunks via vector search then generates an answer.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        # Get relevant chunks via semantic search
        query_vector = embed_query(request.question)
        raw_results = search(
            collection_name=request.collection_name,
            query_embedding=query_vector,
            n_results=4,
        )

        # Extract just the text from the results
        context_chunks = [r["text"] for r in raw_results]

        # Generate an answer using the LLM
        result = answer_question(request.question, context_chunks)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return AnswerResponse(
        question=request.question,
        answer=result["answer"],
        sources=result["sources"],
    )