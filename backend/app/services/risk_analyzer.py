from app.core.config import settings
from app.services.llm import analyze_clause_batch


# Risk levels in order — used for sorting and aggregation
RISK_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def analyze_contract_risks(chunks: list[dict]) -> dict:
    """
    Run risk analysis over every chunk of a contract and
    return a structured risk report.

    Chunks are analysed in batches rather than one at a time, so a long
    contract costs a handful of LLM calls instead of dozens.

    Args:
        chunks: Chunk dicts with chunk_id, text, page_num and chunk_index.
                These come either from the chunker or straight back out
                of ChromaDB via vector_store.get_all_chunks().

    Returns:
        A dict with overall risk level, per-clause analysis, the hidden
        clauses found across the whole document, and the commercial
        clauses the negotiation step needs.
    """
    if not chunks:
        return _empty_report()

    batch_size = settings.analysis_batch_size
    print(f"Analyzing {len(chunks)} chunks for risk in batches of {batch_size}...")

    clause_analyses = []
    hidden_clauses = []
    commercial_clauses = []

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        print(f"  Analyzing chunks {start + 1}-{start + len(batch)} of {len(chunks)}...")

        analyses = analyze_clause_batch([c["text"] for c in batch])

        for chunk, analysis in zip(batch, analyses):
            text = chunk["text"]

            clause_analyses.append({
                "chunk_id": chunk["chunk_id"],
                "page_num": chunk["page_num"],
                "chunk_index": chunk["chunk_index"],
                "text_preview": text[:150] + "..." if len(text) > 150 else text,
                "clause_type": analysis["clause_type"],
                "risk_level": analysis["risk_level"],
                "reason": analysis["reason"],
                "recommendation": analysis["recommendation"],
            })

            # Hidden clauses are collected into one flat list for the whole
            # document, each carrying the page it came from so the UI can
            # point the reader at it
            for hidden in analysis["hidden_clauses"]:
                hidden_clauses.append({
                    "type": hidden.get("type", "unknown"),
                    "severity": hidden.get("severity", "MEDIUM"),
                    "quote": hidden.get("quote", ""),
                    "why_it_matters": hidden.get("why_it_matters", ""),
                    "page_num": chunk["page_num"],
                })

            if analysis["is_commercial"]:
                commercial_clauses.append(text)

    # Calculate overall risk — take the highest risk found
    risk_levels = [RISK_ORDER.get(c["risk_level"], 1) for c in clause_analyses]
    max_risk = max(risk_levels)
    overall_risk = {v: k for k, v in RISK_ORDER.items()}[max_risk]

    # Count by risk level
    risk_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for analysis in clause_analyses:
        level = analysis["risk_level"]
        if level in risk_counts:
            risk_counts[level] += 1

    # Pull out just the high risk clauses for quick review
    high_risk_clauses = [
        c for c in clause_analyses
        if c["risk_level"] == "HIGH"
    ]

    # Worst hidden clauses first — that ordering survives into the UI
    hidden_clauses.sort(
        key=lambda h: RISK_ORDER.get(h["severity"], 1),
        reverse=True,
    )

    print(
        f"Done. {risk_counts['HIGH']} high risk clauses, "
        f"{len(hidden_clauses)} hidden clauses, "
        f"{len(commercial_clauses)} commercial clauses."
    )

    return {
        "overall_risk": overall_risk,
        "risk_counts": risk_counts,
        "total_clauses_analyzed": len(clause_analyses),
        "high_risk_clauses": high_risk_clauses,
        "all_clauses": clause_analyses,
        "hidden_clauses": hidden_clauses,
        "commercial_clauses": commercial_clauses,
    }


def _empty_report() -> dict:
    """
    A valid, empty report.

    Callers splat this straight into a response model, so returning an
    error dict here would just move the failure somewhere more confusing.
    """
    return {
        "overall_risk": "LOW",
        "risk_counts": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
        "total_clauses_analyzed": 0,
        "high_risk_clauses": [],
        "all_clauses": [],
        "hidden_clauses": [],
        "commercial_clauses": [],
    }
