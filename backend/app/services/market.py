"""
Work out where a contract sits against the market, and where to push.

Three sources feed this, deliberately, because none of them is enough
on its own:

  1. benchmarks.json — hand-curated industry norms. Always available,
     never wrong in the way a model can be wrong, but static.
  2. Web search — current conditions the model goes and looks up.
     Fresh, but flaky and sometimes irrelevant.
  3. The model's own knowledge — fills the gaps between the two.

The web step is best-effort. If it fails, or is switched off, we still
produce a full assessment from the benchmark table alone.
"""

from app.services.benchmarks import format_benchmark_table
from app.services.llm import chat_json, chat_with_web_search

# The only positions a lever may take. Scoring maps these to numbers,
# so anything outside the set would silently score as "at market".
VALID_POSITIONS = {
    "worse_than_market",
    "slightly_worse",
    "at_market",
    "better_than_market",
    "not_addressed",
}

VALID_IMPACTS = {"LOW", "MEDIUM", "HIGH"}


def get_market_context(contract_type: str, industry: dict) -> dict:
    """
    Ask the model what is going on in this market right now.

    Args:
        contract_type: e.g. "SaaS Subscription Agreement"
        industry: Output of benchmarks.get_industry()

    Returns:
        {"summary": str, "trends": list[str], "sources": [{"title", "url"}]}
        Empty values if the lookup fails — market context makes the
        advice better, but the assessment does not depend on it.
    """
    prompt = f"""A buyer is about to negotiate a {contract_type} in the {industry['display_name']} sector.

Search the web for current market conditions relevant to that negotiation: typical pricing, standard commercial terms, how much leverage buyers have right now, and any recent shifts in what suppliers are conceding. Base your answer on what you find rather than on general knowledge, and cite your sources.

Reply in plain text in this format, with no markdown:

SUMMARY: two or three sentences on the current state of this market and who holds the leverage.

TRENDS:
- one short, concrete trend
- another
- another

Be specific. Prefer numbers and named terms over general commentary."""

    try:
        result = chat_with_web_search(
            prompt=prompt,
            system=(
                "You are a procurement market analyst. You give concrete, current, "
                "commercially useful information. You never pad your answer."
            ),
        )
    except Exception as e:
        # Never let a flaky search break an assessment
        print(f"Market lookup failed, continuing without it: {e}")
        return {"summary": "", "trends": [], "sources": []}

    summary, trends = _split_summary_and_trends(result["text"])

    return {
        "summary": summary,
        "trends": trends,
        "sources": result["sources"],
    }


def find_negotiation_levers(
    commercial_clauses: list[str],
    industry: dict,
    market_context: dict,
) -> list[dict]:
    """
    Compare the contract's money terms to the industry benchmarks and
    turn each gap into something the buyer can actually ask for.

    One benchmark in, one lever out — including for terms the contract
    never mentions, which are usually the easiest wins.

    Args:
        commercial_clauses: Clause texts flagged as commercial by the analyser
        industry: Output of benchmarks.get_industry()
        market_context: Output of get_market_context()

    Returns:
        A list of lever dicts, one per benchmark
    """
    # A document with no commercial terms at all — an NDA, say — has
    # nothing to benchmark. Generating levers anyway would advise the
    # user to negotiate payment terms into a confidentiality agreement,
    # and would score it as high leverage for having none of them.
    if not commercial_clauses:
        print("No commercial clauses found — skipping negotiation levers.")
        return []

    benchmark_table = format_benchmark_table(industry)

    # Cap the input — a long contract's commercial clauses can still
    # run to thousands of words, and the benchmarks are what matter
    contract_terms = "\n\n---\n\n".join(commercial_clauses)[:12000]

    market_block = market_context.get("summary") or "(No current market data available.)"
    if market_context.get("trends"):
        market_block += "\n\nCurrent trends:\n" + "\n".join(
            f"- {t}" for t in market_context["trends"]
        )

    prompt = f"""You are advising a buyer negotiating a {industry['display_name']} contract.

Below are the contract's commercial terms, the industry benchmarks, and current market context. For EVERY benchmark listed, judge where this contract sits and what the buyer should ask for.

CONTRACT COMMERCIAL TERMS:
{contract_terms}

INDUSTRY BENCHMARKS:
{benchmark_table}

CURRENT MARKET CONTEXT:
{market_block}

Return a JSON object with a single key "levers", holding one object per benchmark. Each object must have:

- "benchmark_key": the benchmark's key, exactly as given above
- "label": the benchmark's label
- "contract_position": what this contract actually says about it, quoted or paraphrased in one sentence. Write "Not addressed in the contract." if it is silent.
- "market_norm": the market norm for this term
- "position": one of "worse_than_market", "slightly_worse", "at_market", "better_than_market", "not_addressed" — judged from the BUYER's point of view
- "ask": the specific change to request, phrased as something you could say across the table (one sentence)
- "rationale": why the buyer can credibly ask for it, referencing the benchmark or market context (one sentence)
- "estimated_impact": "LOW", "MEDIUM" or "HIGH" — how much money or risk this is worth

Judge only from the contract text provided. If a term is not in the text, its position is "not_addressed" — do not assume it exists elsewhere."""

    result = chat_json(
        prompt=prompt,
        system=(
            "You are a commercial negotiation advisor. You always respond with valid JSON only. "
            "You are concrete and you never soften an ask."
        ),
        # Roughly 200 tokens per lever
        max_tokens=250 * len(industry["benchmarks"]),
        fallback={"levers": []},
    )

    return _clean_levers(result.get("levers", []), industry)


def summarise_for_advice(assessment: dict) -> str:
    """
    Boil an assessment down to a short text block for the advice prompt.

    The chat endpoint injects this so answers are grounded in what we
    already found, rather than re-deriving it from scratch every turn.

    Args:
        assessment: A saved assessment report

    Returns:
        Plain text summary
    """
    risk = assessment.get("risk", {})
    margin = assessment.get("margin", {})

    lines = [
        f"Contract type: {assessment.get('contract_type', 'Unknown')}",
        f"Industry: {assessment.get('industry_display_name', 'General Commercial')}",
        f"Risk score: {risk.get('score', 0)}/100 ({risk.get('band', 'UNKNOWN')})",
        f"Margin / negotiating room: {margin.get('score', 0)}/100 ({margin.get('band', 'UNKNOWN')})",
    ]

    hidden = assessment.get("hidden_clauses", [])[:5]
    if hidden:
        lines.append("\nHidden clauses found:")
        for h in hidden:
            lines.append(f"- {h.get('type')} ({h.get('severity')}): {h.get('why_it_matters')}")

    levers = assessment.get("levers", [])[:6]
    if levers:
        lines.append("\nOff-market terms and suggested asks:")
        for l in levers:
            lines.append(
                f"- {l.get('label')} [{l.get('position')}]: "
                f"contract says {l.get('contract_position')} "
                f"vs market norm {l.get('market_norm')}. Ask: {l.get('ask')}"
            )

    if assessment.get("market_summary"):
        lines.append(f"\nMarket context: {assessment['market_summary']}")

    return "\n".join(lines)


# ── Helpers ──────────────────────────────────────────────────

def _split_summary_and_trends(text: str) -> tuple[str, list[str]]:
    """
    Pull the SUMMARY and TRENDS sections out of the model's reply.

    We ask for a simple labelled format rather than JSON here, because
    the web search tool returns prose with citations attached and forcing
    it into JSON tends to lose the citations.
    """
    summary_parts = []
    trends = []
    in_trends = False

    for line in text.splitlines():
        # Models write markdown as often as not, whatever the prompt says.
        # Bold markers would otherwise break the heading check and show up
        # verbatim in the UI as "**SUMMARY:**" and "Payment terms**: ...".
        stripped = line.replace("**", "").replace("__", "").strip().strip("#").strip()
        if not stripped:
            continue

        upper = stripped.upper()
        if upper.startswith("TRENDS"):
            in_trends = True
            continue
        if upper.startswith("SUMMARY"):
            in_trends = False
            # Keep whatever followed the heading on the same line
            rest = stripped.split(":", 1)[-1].strip("*# ").strip()
            if rest:
                summary_parts.append(rest)
            continue

        if in_trends:
            trends.append(stripped.lstrip("-•* ").strip())
        else:
            summary_parts.append(stripped)

    return " ".join(summary_parts).strip(), [t for t in trends if t]


def _clean_levers(levers: list, industry: dict) -> list[dict]:
    """
    Normalise the model's levers so scoring can rely on them.

    Scoring maps "position" through a fixed table, so an unexpected value
    would quietly distort the margin meter. Anything we do not recognise
    is forced to a known value and anything not matching a real benchmark
    is dropped.
    """
    known_keys = {b["key"]: b for b in industry["benchmarks"]}
    cleaned = []
    seen = set()

    for lever in levers:
        if not isinstance(lever, dict):
            continue

        key = lever.get("benchmark_key")
        if key not in known_keys or key in seen:
            continue
        seen.add(key)

        benchmark = known_keys[key]
        position = lever.get("position")
        impact = lever.get("estimated_impact")

        cleaned.append({
            "benchmark_key": key,
            "label": lever.get("label") or benchmark["label"],
            "contract_position": lever.get("contract_position", "Not addressed in the contract."),
            "market_norm": lever.get("market_norm") or benchmark["market_norm"],
            "position": position if position in VALID_POSITIONS else "at_market",
            "ask": lever.get("ask", ""),
            "rationale": lever.get("rationale", ""),
            "estimated_impact": impact if impact in VALID_IMPACTS else "MEDIUM",
        })

    return cleaned
