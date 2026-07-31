from app.services.llm import analyze_clause
from app.services.chunker import TextChunk


# Risk levels in order — used for sorting and aggregation
RISK_ORDER = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}


def analyze_contract_risks(chunks: list[TextChunk]) -> dict:
    """
    Run risk analysis on every chunk of a contract and
    return a structured risk report.

    Args:
        chunks: List of TextChunk objects from the chunker

    Returns:
        A dict with overall risk level, per-clause analysis,
        and a summary of findings
    """
    if not chunks:
        return {"error": "No chunks to analyze"}

    print(f"Analyzing {len(chunks)} chunks for risk...")

    clause_analyses = []

    for i, chunk in enumerate(chunks):
        print(f"  Analyzing chunk {i + 1}/{len(chunks)}...")
        analysis = analyze_clause(chunk.text)

        clause_analyses.append({
            "chunk_id": chunk.chunk_id,
            "page_num": chunk.page_num,
            "chunk_index": chunk.chunk_index,
            "text_preview": chunk.text[:150] + "..." if len(chunk.text) > 150 else chunk.text,
            "clause_type": analysis.get("clause_type", "other"),
            "risk_level": analysis.get("risk_level", "MEDIUM"),
            "reason": analysis.get("reason", ""),
            "recommendation": analysis.get("recommendation", ""),
        })

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

    return {
        "overall_risk": overall_risk,
        "risk_counts": risk_counts,
        "total_clauses_analyzed": len(clause_analyses),
        "high_risk_clauses": high_risk_clauses,
        "all_clauses": clause_analyses,
    }