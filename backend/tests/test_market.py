"""
Tests for the parts of market.py that do not call an LLM.

Both of these caught real bugs: the model labels its headings in
markdown often enough that "**SUMMARY:**" was reaching the UI verbatim,
and an NDA with no commercial terms was being scored as having strong
negotiating leverage for lacking payment terms it never needed.
"""

from app.services.benchmarks import get_industry
from app.services.market import (
    _clean_levers,
    _split_summary_and_trends,
    find_negotiation_levers,
    summarise_for_advice,
)


# ── Parsing the market reply ─────────────────────────────────

def test_splits_plain_summary_and_trends():
    summary, trends = _split_summary_and_trends(
        "SUMMARY: Buyers hold the leverage this year.\n"
        "TRENDS:\n"
        "- Uplift caps settling at 4%\n"
        "- Net 45 becoming common\n"
    )

    assert summary == "Buyers hold the leverage this year."
    assert trends == ["Uplift caps settling at 4%", "Net 45 becoming common"]


def test_markdown_headings_do_not_leak_into_the_summary():
    summary, trends = _split_summary_and_trends(
        "**SUMMARY:** Buyers hold the leverage.\n"
        "**TRENDS:**\n"
        "* Uplift caps settling at 4%\n"
    )

    assert summary == "Buyers hold the leverage."
    assert trends == ["Uplift caps settling at 4%"]


def test_bold_inside_a_trend_is_stripped():
    _, trends = _split_summary_and_trends(
        "TRENDS:\n- **Price escalation caps**: vendors now cap at 7%\n"
    )

    assert trends == ["Price escalation caps: vendors now cap at 7%"]


def test_unlabelled_reply_is_all_summary():
    summary, trends = _split_summary_and_trends("Just some prose with no headings.")

    assert summary == "Just some prose with no headings."
    assert trends == []


# ── Levers ───────────────────────────────────────────────────

def test_no_commercial_clauses_means_no_levers():
    # An NDA has nothing to price-negotiate. Inventing levers would both
    # give nonsense advice and score it as high leverage.
    levers = find_negotiation_levers(
        commercial_clauses=[],
        industry=get_industry("default"),
        market_context={"summary": "", "trends": [], "sources": []},
    )

    assert levers == []


def test_unknown_benchmark_keys_are_dropped():
    cleaned = _clean_levers(
        [
            {"benchmark_key": "payment_terms", "position": "at_market"},
            {"benchmark_key": "invented_by_the_model", "position": "at_market"},
        ],
        get_industry("default"),
    )

    assert [l["benchmark_key"] for l in cleaned] == ["payment_terms"]


def test_invalid_position_is_forced_to_a_known_value():
    cleaned = _clean_levers(
        [{"benchmark_key": "payment_terms", "position": "catastrophic"}],
        get_industry("default"),
    )

    assert cleaned[0]["position"] == "at_market"


def test_missing_fields_fall_back_to_the_benchmark():
    cleaned = _clean_levers(
        [{"benchmark_key": "payment_terms", "position": "worse_than_market"}],
        get_industry("default"),
    )

    assert cleaned[0]["label"] == "Payment terms"
    assert cleaned[0]["market_norm"] == "Net 30"
    assert cleaned[0]["estimated_impact"] == "MEDIUM"


def test_duplicate_benchmarks_are_collapsed():
    cleaned = _clean_levers(
        [
            {"benchmark_key": "payment_terms", "position": "worse_than_market"},
            {"benchmark_key": "payment_terms", "position": "at_market"},
        ],
        get_industry("default"),
    )

    assert len(cleaned) == 1
    assert cleaned[0]["position"] == "worse_than_market"


# ── Advice summary ───────────────────────────────────────────

def test_advice_summary_carries_the_scores_and_asks():
    summary = summarise_for_advice({
        "contract_type": "SaaS Subscription Agreement",
        "industry_display_name": "SaaS / Software",
        "risk": {"score": 72, "band": "HIGH"},
        "margin": {"score": 61, "band": "SOME_ROOM"},
        "hidden_clauses": [
            {"type": "auto_renewal", "severity": "HIGH", "why_it_matters": "Locks in a year."},
        ],
        "levers": [
            {
                "label": "Payment terms",
                "position": "worse_than_market",
                "contract_position": "Net 15",
                "market_norm": "Net 30",
                "ask": "Move to Net 45.",
            },
        ],
        "market_summary": "Buyers hold the leverage.",
    })

    assert "72/100" in summary
    assert "61/100" in summary
    assert "auto_renewal" in summary
    assert "Move to Net 45." in summary
