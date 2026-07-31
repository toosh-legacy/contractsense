import os
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.core.config import settings
from app.services.benchmarks import (
    format_benchmark_table,
    get_industry,
    industry_keys,
    list_industries,
)
from app.services.chunker import chunk_document
from app.services.embedder import embed_chunks, embed_query
from app.services.market import (
    find_negotiation_levers,
    get_market_context,
    summarise_for_advice,
)
from app.services.pdf_parser import parse_pdf, get_document_stats
from app.services.report_store import load_report, save_report
from app.services.scoring import score_margin, score_risk, sort_levers
from app.services.vector_store import (
    collection_exists,
    get_all_chunks,
    search,
    store_embeddings,
)

from app.services.llm import answer_question, answer_with_advice, detect_industry, extract_key_terms
from app.services.risk_analyzer import analyze_contract_risks

router = APIRouter()


def safe_collection_name(filename: str) -> str:
    """
    Turn an uploaded filename into a safe collection name.

    The name ends up in a file path and in a ChromaDB collection name,
    so we strip it down to characters that are harmless in both rather
    than trusting whatever the browser sent us.
    """
    stem = Path(filename).stem.lower().replace(" ", "_")
    cleaned = re.sub(r"[^a-z0-9_-]", "", stem).strip("_-")

    # Chroma requires 3-63 characters starting and ending alphanumerically
    if len(cleaned) < 3:
        cleaned = f"doc_{cleaned}" if cleaned else "document"

    return cleaned[:63]


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


# ── Assessment models ────────────────────────────────────────
# The assessment is the headline feature: two 0-100 scores plus
# the evidence behind them.

class ScoreDetail(BaseModel):
    score: int             # 0-100
    band: str              # e.g. "MODERATE" / "STRONG_LEVERAGE"
    drivers: list[str]     # plain English reasons for the number


class HiddenClause(BaseModel):
    type: str
    severity: str
    quote: str
    why_it_matters: str
    page_num: int


class NegotiationLever(BaseModel):
    benchmark_key: str
    label: str
    contract_position: str
    market_norm: str
    position: str          # worse_than_market ... better_than_market
    ask: str
    rationale: str
    estimated_impact: str


class MarketSource(BaseModel):
    title: str
    url: str


class Industry(BaseModel):
    key: str
    display_name: str


class AssessRequest(BaseModel):
    collection_name: str
    industry: str | None = None    # override the auto-detected industry
    refresh: bool = False          # ignore the cache and recompute


class AssessmentResponse(BaseModel):
    collection_name: str
    industry: str
    industry_display_name: str
    contract_type: str
    risk: ScoreDetail
    margin: ScoreDetail
    hidden_clauses: list[HiddenClause]
    levers: list[NegotiationLever]
    market_summary: str
    market_trends: list[str]
    market_sources: list[MarketSource]
    risk_counts: dict
    total_clauses_analyzed: int
    cached: bool


class AdviceRequest(BaseModel):
    collection_name: str
    question: str


class AdviceResponse(BaseModel):
    question: str
    answer: str
    sources: list[str]
    web_sources: list[MarketSource]


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

        # Store — the collection is named after the file
        collection_name = safe_collection_name(file.filename)
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
        risk_report = analyze_contract_risks([
            {
                "chunk_id": c.chunk_id,
                "text": c.text,
                "page_num": c.page_num,
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ])
        collection_name = safe_collection_name(file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return RiskReport(
        collection_name=collection_name,
        overall_risk=risk_report["overall_risk"],
        risk_counts=risk_report["risk_counts"],
        total_clauses_analyzed=risk_report["total_clauses_analyzed"],
        high_risk_clauses=risk_report["high_risk_clauses"],
        all_clauses=risk_report["all_clauses"],
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


# ── Assessment endpoints ─────────────────────────────────────

@router.get("/industries", response_model=list[Industry])
async def get_industries():
    """
    List the industries we hold negotiation benchmarks for.
    The UI uses this to let the user correct the detected industry.
    """
    return [Industry(**i) for i in list_industries()]


@router.post("/assess", response_model=AssessmentResponse)
async def assess_contract(request: AssessRequest):
    """
    Score an already-uploaded contract on risk and negotiating room.

    This is the main event. It:
    1. Reads the contract's chunks back out of ChromaDB
    2. Works out which industry to benchmark it against
    3. Analyses every clause for risk and for hidden terms
    4. Looks up current market conditions
    5. Compares the commercial terms to the industry benchmarks
    6. Turns all of that into two 0-100 scores

    Results are cached to disk, so opening the same contract again is
    instant. Pass refresh=true to recompute.
    """
    collection_name = request.collection_name

    if not collection_exists(collection_name):
        raise HTTPException(
            status_code=404,
            detail=f"No uploaded contract named '{collection_name}'. Upload it first.",
        )

    # Serve the cache unless we've been told not to, or the user picked
    # a different industry than the cached run used
    if not request.refresh:
        cached = load_report(collection_name)
        if cached and (not request.industry or cached["industry"] == request.industry):
            return AssessmentResponse(**cached, cached=True)

    try:
        chunks = get_all_chunks(collection_name)
        if not chunks:
            raise HTTPException(
                status_code=422,
                detail="This contract has no indexed text to assess.",
            )

        # 1. Which benchmarks apply?
        if request.industry:
            industry = get_industry(request.industry)
            contract_type = "Unknown"
        else:
            detected = detect_industry(chunks[0]["text"], industry_keys())
            industry = get_industry(detected["industry"])
            contract_type = detected["contract_type"]

        # 2. Clause risk + hidden clauses
        risk_report = analyze_contract_risks(chunks)

        # 3. Market context — best effort, never fatal
        market = get_market_context(contract_type, industry)

        # 4. Where can we push?
        levers = sort_levers(find_negotiation_levers(
            commercial_clauses=risk_report["commercial_clauses"],
            industry=industry,
            market_context=market,
        ))

        # 5. The two numbers
        risk = score_risk(risk_report["all_clauses"], risk_report["hidden_clauses"])
        margin = score_margin(levers)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assessment failed: {str(e)}")

    report = {
        "collection_name": collection_name,
        "industry": industry["key"],
        "industry_display_name": industry["display_name"],
        "contract_type": contract_type,
        "risk": risk,
        "margin": margin,
        "hidden_clauses": risk_report["hidden_clauses"],
        "levers": levers,
        "market_summary": market["summary"],
        "market_trends": market["trends"],
        "market_sources": market["sources"],
        "risk_counts": risk_report["risk_counts"],
        "total_clauses_analyzed": risk_report["total_clauses_analyzed"],
    }

    save_report(collection_name, report)

    return AssessmentResponse(**report, cached=False)


@router.get("/assess/{collection_name}", response_model=AssessmentResponse)
async def get_assessment(collection_name: str):
    """
    Fetch a previously computed assessment without recomputing it.

    The UI calls this on load so a contract that has already been
    assessed shows its scores immediately.
    """
    cached = load_report(collection_name)

    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="This contract has not been assessed yet.",
        )

    return AssessmentResponse(**cached, cached=True)


@router.post("/advise", response_model=AdviceResponse)
async def advise(request: AdviceRequest):
    """
    Ask for negotiation advice about an uploaded contract.

    Same retrieval as /ask, but the prompt also carries the cached
    assessment and the industry benchmarks, so answers come back as
    "that term is below market, ask for X" rather than a summary of
    what the contract already says. The model may search the web when
    the question is about current market conditions.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        query_vector = embed_query(request.question)
        raw_results = search(
            collection_name=request.collection_name,
            query_embedding=query_vector,
            n_results=4,
        )
        context_chunks = [r["text"] for r in raw_results]

        # Ground the answer in what we already know, if we know anything.
        # Without an assessment we still answer — just with less context.
        assessment = load_report(request.collection_name)
        if assessment:
            summary = summarise_for_advice(assessment)
            industry = get_industry(assessment["industry"])
        else:
            summary = "This contract has not been assessed yet."
            industry = get_industry(None)

        result = answer_with_advice(
            question=request.question,
            context_chunks=context_chunks,
            assessment_summary=summary,
            benchmark_table=format_benchmark_table(industry),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return AdviceResponse(
        question=request.question,
        answer=result["answer"],
        sources=result["sources"],
        web_sources=[MarketSource(**s) for s in result["web_sources"]],
    )