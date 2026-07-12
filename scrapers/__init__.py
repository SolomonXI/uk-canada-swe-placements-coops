"""Scraper package entry point."""

from __future__ import annotations

from .canada_coops import run as run_canada_coops
from .uk_industrial_placements import run as run_uk_industrial_placements
from .utils import cleanup_listings


def run_all() -> None:
    """Run all available scrapers without failing the whole update."""

    jobs = [
        ("Running UK industrial placements scraper", run_uk_industrial_placements),
        ("Running Canada co-ops scraper", run_canada_coops),
    ]
    for message, runner in jobs:
        print(message)
        try:
            runner()
        except Exception as exc:  # pragma: no cover - defensive wrapper
            print(f"[WARN] {message} failed: {exc}")

    removed = cleanup_listings()
    if removed:
        print(f"[CLEANUP] Removed {removed} stale or non-SWE listings")


def main() -> None:
    """Package CLI entry point."""

    run_all()


if __name__ == "__main__":
    main()
