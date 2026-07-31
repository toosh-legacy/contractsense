"""
Tests for the pure helpers in llm.py — no API calls.

_align_batch is worth pinning down because when it goes wrong it goes
wrong quietly. The caller zips its output against the original chunks,
so a misaligned list attaches each analysis to the wrong piece of text,
and a short list reports "nothing found" on clauses that were never
actually looked at.

The 1-based numbering exists because the model was returning one object
per numbered section of the contract (1. FEES, 2. TERM, ...) instead of
one per input excerpt.
"""

from app.services.llm import _align_batch


def entry(number: int | None, risk: str = "HIGH", commercial: bool = True) -> dict:
    item = {
        "clause_type": "pricing",
        "risk_level": risk,
        "reason": "Reason.",
        "recommendation": "Do something.",
        "is_commercial": commercial,
        "hidden_clauses": [{"type": "auto_renewal", "severity": "HIGH"}],
    }
    if number is not None:
        item["excerpt"] = number
    return item


def test_one_entry_per_excerpt_in_order():
    aligned = _align_batch([entry(1, "LOW"), entry(2, "HIGH")], 2)

    assert [a["risk_level"] for a in aligned] == ["LOW", "HIGH"]


def test_out_of_order_entries_are_placed_by_their_number():
    aligned = _align_batch([entry(2, "HIGH"), entry(1, "LOW")], 2)

    assert [a["risk_level"] for a in aligned] == ["LOW", "HIGH"]


def test_missing_numbers_fall_back_to_positional_order():
    aligned = _align_batch([entry(None, "LOW"), entry(None, "HIGH")], 2)

    assert [a["risk_level"] for a in aligned] == ["LOW", "HIGH"]


def test_short_output_is_padded_to_the_expected_length():
    aligned = _align_batch([entry(1)], 3)

    assert len(aligned) == 3
    assert aligned[1]["risk_level"] == "MEDIUM"
    assert aligned[1]["hidden_clauses"] == []


def test_extra_entries_beyond_the_batch_are_ignored():
    # The failure that started all this: the model returning one object
    # per numbered contract section instead of one per excerpt
    aligned = _align_batch([entry(i) for i in range(1, 13)], 1)

    assert len(aligned) == 1


def test_empty_output_still_yields_safe_defaults():
    aligned = _align_batch([], 2)

    assert len(aligned) == 2
    assert all(a["risk_level"] == "MEDIUM" for a in aligned)
    assert all(a["is_commercial"] is False for a in aligned)


def test_junk_entries_are_skipped():
    aligned = _align_batch(["not a dict", None, entry(1, "LOW")], 1)

    assert aligned[0]["risk_level"] == "LOW"


def test_non_dict_hidden_clauses_are_dropped():
    item = entry(1)
    item["hidden_clauses"] = ["auto_renewal", {"type": "exclusivity"}]

    aligned = _align_batch([item], 1)

    assert aligned[0]["hidden_clauses"] == [{"type": "exclusivity"}]
