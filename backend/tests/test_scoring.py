"""
Tests for the scoring formula.

scoring.py is pure — no LLM, no disk, no network — which is exactly why
it is worth testing. The two 0-100 scores are the headline output of the
product, so if the formula drifts we want to know here rather than from
a customer asking why the same contract scored differently twice.
"""

from app.services.scoring import (
    HIDDEN_CLAUSE_CAP,
    LEVER_OPPORTUNITY,
    score_margin,
    score_risk,
    sort_levers,
)


def clauses(*risk_levels: str) -> list[dict]:
    """Build a minimal clause list — scoring only looks at risk_level."""
    return [{"risk_level": level} for level in risk_levels]


def hidden(count: int, severity: str = "HIGH") -> list[dict]:
    """Build a list of hidden clause findings."""
    return [
        {"type": f"hidden_type_{i}", "severity": severity}
        for i in range(count)
    ]


def levers(*positions: str) -> list[dict]:
    """Build a lever list — scoring only looks at position."""
    return [
        {"label": f"Term {i}", "position": position, "estimated_impact": "MEDIUM"}
        for i, position in enumerate(positions)
    ]


# ── Risk score ───────────────────────────────────────────────

def test_all_low_risk_scores_in_the_low_band():
    result = score_risk(clauses("LOW", "LOW", "LOW"), [])

    assert result["score"] == 10
    assert result["band"] == "LOW"


def test_all_high_risk_scores_in_the_high_band():
    result = score_risk(clauses("HIGH", "HIGH"), [])

    assert result["score"] == 100
    assert result["band"] == "HIGH"


def test_medium_risk_sits_in_the_moderate_band():
    result = score_risk(clauses("MEDIUM", "MEDIUM", "MEDIUM"), [])

    assert result["score"] == 45
    assert result["band"] == "MODERATE"


def test_hidden_clauses_push_the_score_up():
    without = score_risk(clauses("LOW", "LOW"), [])
    with_hidden = score_risk(clauses("LOW", "LOW"), hidden(2))

    assert with_hidden["score"] > without["score"]


def test_hidden_clause_penalty_is_capped():
    # Twenty hidden clauses must not add twenty times the penalty
    result = score_risk(clauses("LOW"), hidden(20))

    assert result["score"] == 10 + HIDDEN_CLAUSE_CAP


def test_risk_score_never_exceeds_100():
    result = score_risk(clauses("HIGH", "HIGH", "HIGH"), hidden(10))

    assert result["score"] == 100


def test_no_clauses_does_not_divide_by_zero():
    result = score_risk([], [])

    assert result["score"] == 0
    assert result["band"] == "LOW"
    assert result["drivers"]


def test_unknown_risk_level_is_treated_as_medium():
    result = score_risk(clauses("CATASTROPHIC"), [])

    assert result["score"] == 45


def test_risk_drivers_explain_the_number():
    result = score_risk(clauses("HIGH", "MEDIUM"), hidden(1))
    joined = " ".join(result["drivers"])

    assert "1 high-risk clause" in joined
    assert "1 medium-risk clause" in joined
    assert "1 hidden clause" in joined


# ── Margin meter ─────────────────────────────────────────────

def test_no_levers_is_unknown_rather_than_zero_leverage():
    result = score_margin([])

    assert result["score"] == 0
    assert result["band"] == "UNKNOWN"


def test_every_position_maps_to_its_opportunity_value():
    for position, expected in LEVER_OPPORTUNITY.items():
        result = score_margin(levers(position))

        assert result["score"] == expected, position


def test_off_market_terms_mean_strong_leverage():
    result = score_margin(levers(
        "worse_than_market", "worse_than_market", "not_addressed",
    ))

    assert result["band"] == "STRONG_LEVERAGE"


def test_at_market_contract_leaves_little_room():
    result = score_margin(levers("at_market", "at_market", "better_than_market"))

    assert result["band"] == "TIGHT"


def test_only_the_strongest_levers_count():
    # A few bad terms must still register as leverage even when most of
    # the contract is fine. Averaging all 17 would give 28 and read as
    # TIGHT; averaging the top 5 gives 48 and reads as SOME_ROOM.
    at_market_only = score_margin(levers(*(["at_market"] * 17)))
    with_two_bad = score_margin(levers(
        "worse_than_market", "worse_than_market",
        *(["at_market"] * 15),
    ))

    assert with_two_bad["score"] > at_market_only["score"]
    assert with_two_bad["band"] == "SOME_ROOM"


def test_unknown_position_falls_back_to_at_market():
    result = score_margin(levers("wildly_off"))

    assert result["score"] == LEVER_OPPORTUNITY["at_market"]


def test_margin_drivers_name_the_off_market_terms():
    result = score_margin([
        {"label": "Payment terms", "position": "worse_than_market", "estimated_impact": "HIGH"},
    ])

    assert any("Payment terms" in d for d in result["drivers"])


# ── Lever ordering ───────────────────────────────────────────

def test_levers_sort_worst_first_then_by_impact():
    ordered = sort_levers([
        {"label": "fine", "position": "at_market", "estimated_impact": "HIGH"},
        {"label": "bad-low", "position": "worse_than_market", "estimated_impact": "LOW"},
        {"label": "bad-high", "position": "worse_than_market", "estimated_impact": "HIGH"},
    ])

    assert [l["label"] for l in ordered] == ["bad-high", "bad-low", "fine"]
