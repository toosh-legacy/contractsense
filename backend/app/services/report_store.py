"""
Cache finished assessments on disk as JSON.

A full assessment costs a dozen or more LLM calls, so recomputing it
every time somebody opens a tab would be slow and expensive. One JSON
file per contract is enough here — there is no database in this project
and adding one just to hold a handful of reports would be overkill.
"""

import json
from pathlib import Path

from app.core.config import settings


def _report_path(collection_name: str) -> Path:
    """Where a given contract's report lives on disk."""
    return Path(settings.reports_dir) / f"{collection_name}.json"


def save_report(collection_name: str, report: dict) -> None:
    """
    Write an assessment to disk, overwriting any earlier one.

    Args:
        collection_name: The contract's collection name
        report: The assessment dict to cache
    """
    reports_dir = Path(settings.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    path = _report_path(collection_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Saved assessment: {path}")


def load_report(collection_name: str) -> dict | None:
    """
    Read a cached assessment.

    Args:
        collection_name: The contract's collection name

    Returns:
        The cached report, or None if there isn't one.
        A corrupt file is treated as no cache — a stale report
        is never worth crashing a request over.
    """
    path = _report_path(collection_name)

    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Ignoring unreadable report {path}: {e}")
        return None


def delete_report(collection_name: str) -> None:
    """Drop a cached assessment so the next request recomputes it."""
    path = _report_path(collection_name)
    if path.exists():
        path.unlink()
        print(f"Deleted cached assessment: {path}")
