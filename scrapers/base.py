"""Common scraper scaffolding for placement and co-op scrapers."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Scraper(ABC):
    """Base scraper contract.

    Subclasses should implement ``run()`` to fetch target pages, parse listings,
    normalize them, and persist them via ``scrapers.utils.upsert_listing``.
    """

    source_name: str = "unknown"

    @abstractmethod
    def run(self) -> None:
        """Execute the scraper and persist any normalized listings."""
        raise NotImplementedError
