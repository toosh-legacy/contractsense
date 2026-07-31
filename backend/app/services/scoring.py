"""
Turn the LLM's findings into two numbers a pricing team can act on.

Everything here is a pure function — no LLM calls, no disk, no network.
That is deliberate. The scores are the headline output of the product,
so they have to be reproducible and explainable: the same findings must
always produce the same number, and we must be able to say exactly why.

The LLM's job is to spot things. This file's job is to weigh them.
"""

# ── Risk scoring ─────────────────────────────────────────────
# How much each clause risk level contributes, on a 0-100 scale.
# MEDIUM sits well below the midpoint because most contracts are
# mostly medium — if MEDIUM scored 50 every contract would look average.
CLAUSE_SEVERITY = {"HIGH": 100, "MEDIUM": 45, "LOW": 10}

HIDDEN_CLAUSE_PENALTY = 6    # points added per hidden clause found
HIDDEN_CLAUSE_CAP = 30       # hidden clauses alone can never max out the score

RISK_BANDS = [
    (33, "LOW"),
    (66, "MODERATE"),
    (100, "HIGH"),
]

# ── Margin scoring ───────────────────────────────────────────
# How much negotiating room each benchmark position implies.
# "not_addressed" scores high because a term the contract is silent on
# is usually easy to win — you are asking for something, not clawing back.
LEVER_OPPORTUNITY = {
    "worse_than_market": 90,
    "not_addressed": 70,
    "slightly_worse": 55,
    "at_market": 20,
    "better_than_market": 5,
}

# Only the strongest few levers count. A contract with three glaring
# problems has real leverage; averaging those away against twenty
# fine-as-they-are terms would hide it.
TOP_LEVERS_COUNTED = 5

MARGIN_BANDS = [
    (33, "TIGHT"),
    (66, "SOME_ROOM"),
    (100, "STRONG_LEVERAGE"),
]


def score_risk(clauses: list[dict], hidden_clauses: list[dict]) -> dict:
    """
    Score how risky a contract is, 0-100. Higher means riskier.

    The score is the average clause severity, plus a penalty for each
    hidden clause found. Hidden clauses are penalised separately because
    they are a different kind of problem — a clause can read as perfectly
    reasonable and still contain an auto-renewal that costs you a year.

    Args:
        clauses: Per-clause analyses, each with a "risk_level"
        hidden_clauses: Flagged hidden clauses, each with a "severity"

    Returns:
        {"score": int, "band": str, "drivers": list[str]}
    """
    if not clauses:
        return {
            "score": 0,
            "band": "LOW",
            "drivers": ["No clauses were analysed."],
        }

    severities = [
        CLAUSE_SEVERITY.get(c.get("risk_level", "MEDIUM"), CLAUSE_SEVERITY["MEDIUM"])
        for c in clauses
    ]
    base = sum(severities) / len(severities)

    penalty = min(HIDDEN_CLAUSE_CAP, HIDDEN_CLAUSE_PENALTY * len(hidden_clauses))

    score = _clamp(round(base + penalty), 0, 100)

    return {
        "score": score,
        "band": _band(score, RISK_BANDS),
        "drivers": _risk_drivers(clauses, hidden_clauses, base, penalty),
    }


def score_margin(levers: list[dict]) -> dict:
    """
    Score how much room there is to negotiate, 0-100.
    Higher means more leverage — this is the "margin meter".

    We average the strongest few levers rather than all of them,
    so a handful of genuinely bad terms still registers as leverage
    even in a contract that is otherwise at market.

    Args:
        levers: Negotiation levers, each with a "position" from the
                closed set in LEVER_OPPORTUNITY

    Returns:
        {"score": int, "band": str, "drivers": list[str]}
    """
    if not levers:
        return {
            "score": 0,
            "band": "UNKNOWN",
            "drivers": ["No commercial terms were found to benchmark."],
        }

    scored = [
        (LEVER_OPPORTUNITY.get(lever.get("position", "at_market"), 20), lever)
        for lever in levers
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = scored[:TOP_LEVERS_COUNTED]

    score = _clamp(round(sum(value for value, _ in top) / len(top)), 0, 100)

    return {
        "score": score,
        "band": _band(score, MARGIN_BANDS),
        "drivers": _margin_drivers(levers, top),
    }


def sort_levers(levers: list[dict]) -> list[dict]:
    """
    Order levers so the biggest wins come first.
    Sorted by how far off market the term is, then by estimated impact.
    """
    impact_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

    return sorted(
        levers,
        key=lambda l: (
            LEVER_OPPORTUNITY.get(l.get("position", "at_market"), 20),
            impact_rank.get(l.get("estimated_impact", "MEDIUM"), 2),
        ),
        reverse=True,
    )


# ── Helpers ──────────────────────────────────────────────────

def _risk_drivers(
    clauses: list[dict],
    hidden_clauses: list[dict],
    base: float,
    penalty: int,
) -> list[str]:
    """
    Explain the risk score in plain English.

    A 0-100 number nobody can interrogate is not useful to a pricing
    team defending a position, so every score ships with its reasons.
    """
    drivers = []

    high = sum(1 for c in clauses if c.get("risk_level") == "HIGH")
    medium = sum(1 for c in clauses if c.get("risk_level") == "MEDIUM")

    if high:
        drivers.append(f"{high} high-risk clause{_s(high)} found.")
    if medium:
        drivers.append(f"{medium} medium-risk clause{_s(medium)} found.")
    if not high and not medium:
        drivers.append("No high or medium risk clauses found.")

    if hidden_clauses:
        types = sorted({h.get("type", "unknown") for h in hidden_clauses})
        drivers.append(
            f"{len(hidden_clauses)} hidden clause{_s(len(hidden_clauses))} "
            f"adding {penalty} points: {', '.join(types[:4])}."
        )
    else:
        drivers.append("No hidden clauses detected.")

    drivers.append(f"Average clause severity {round(base)} of 100.")

    return drivers


def _margin_drivers(levers: list[dict], top: list[tuple]) -> list[str]:
    """Explain the margin meter in plain English."""
    drivers = []

    off_market = [
        l for l in levers
        if l.get("position") in ("worse_than_market", "slightly_worse")
    ]
    missing = [l for l in levers if l.get("position") == "not_addressed"]

    if off_market:
        drivers.append(
            f"{len(off_market)} term{_s(len(off_market))} below market: "
            f"{', '.join(l.get('label', 'term') for l in off_market[:3])}."
        )
    if missing:
        drivers.append(
            f"{len(missing)} standard protection{_s(len(missing))} missing entirely: "
            f"{', '.join(l.get('label', 'term') for l in missing[:3])}."
        )
    if not off_market and not missing:
        drivers.append("Every benchmarked term is at or above market.")

    drivers.append(f"{len(levers)} term{_s(len(levers))} benchmarked against the industry.")
    drivers.append(f"Score is the average of the top {len(top)} opportunities.")

    return drivers


def _band(score: int, bands: list[tuple]) -> str:
    """Map a 0-100 score onto its named band."""
    for ceiling, name in bands:
        if score <= ceiling:
            return name
    return bands[-1][1]


def _clamp(value: int, low: int, high: int) -> int:
    """Keep a value inside a range."""
    return max(low, min(high, value))


def _s(count: int) -> str:
    """Tiny pluraliser so the driver strings read naturally."""
    return "" if count == 1 else "s"
