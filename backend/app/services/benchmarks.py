import json
from pathlib import Path

# The benchmark file lives next to the code, not in data/,
# because it is hand-maintained content we want in git —
# unlike data/, which is runtime scratch and gitignored.
BENCHMARKS_PATH = Path(__file__).parent.parent / "data" / "benchmarks.json"

# Used when we cannot work out the industry
DEFAULT_INDUSTRY = "default"

_benchmarks = None


def load_benchmarks() -> dict:
    """
    Lazy-load the industry benchmark table.
    Same pattern as the embedding model — read from disk once,
    then serve the cached copy on every call after.

    Returns:
        The whole benchmark table keyed by industry
    """
    global _benchmarks
    if _benchmarks is None:
        print(f"Loading industry benchmarks: {BENCHMARKS_PATH}")
        with open(BENCHMARKS_PATH, "r", encoding="utf-8") as f:
            _benchmarks = json.load(f)
        print(f"Loaded {len(_benchmarks)} industries.")
    return _benchmarks


def get_industry(industry_key: str | None) -> dict:
    """
    Look up one industry's benchmarks.

    Args:
        industry_key: e.g. "saas". Unknown or missing keys
                      fall back to the "default" industry so
                      scoring always has something to compare against.

    Returns:
        A dict with "key", "display_name" and "benchmarks"
    """
    table = load_benchmarks()
    key = (industry_key or "").strip().lower()

    if key not in table:
        key = DEFAULT_INDUSTRY

    industry = table[key]

    return {
        "key": key,
        "display_name": industry["display_name"],
        "benchmarks": industry["benchmarks"],
    }


def list_industries() -> list[dict]:
    """
    List every industry we hold benchmarks for.
    The frontend uses this to build the override dropdown.

    Returns:
        List of {"key", "display_name"} sorted with "default" last
    """
    table = load_benchmarks()

    industries = [
        {"key": key, "display_name": value["display_name"]}
        for key, value in table.items()
    ]

    # Keep the real industries alphabetical and push "default" to the bottom
    industries.sort(key=lambda i: (i["key"] == DEFAULT_INDUSTRY, i["display_name"]))

    return industries


def industry_keys() -> list[str]:
    """Just the keys — handed to the LLM so it can only pick a valid industry."""
    return list(load_benchmarks().keys())


def format_benchmark_table(industry: dict) -> str:
    """
    Render an industry's benchmarks as plain text for an LLM prompt.

    A compact text table costs far fewer tokens than raw JSON
    and the model follows it just as well.

    Args:
        industry: Output of get_industry()

    Returns:
        One line per benchmark
    """
    lines = []
    for b in industry["benchmarks"]:
        lines.append(
            f"- {b['key']} | {b['label']} | "
            f"market norm: {b['market_norm']} | "
            f"buyer-favourable: {b['buyer_favourable']} | "
            f"note: {b['note']}"
        )
    return "\n".join(lines)
