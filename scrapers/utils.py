"""Utility helpers for loading, saving, and normalizing listings."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_FILE = ROOT_DIR / "data" / "listings.json"

SWE_KEYWORDS = ("software", "developer", "engineer", "engineering")
AI_KEYWORDS = (
    "artificial intelligence",
    "agentic ai",
    "generative ai",
    "machine learning",
    "llm",
    " ai ",
)


def load_listings() -> dict[str, Any]:
    """Load the canonical listings JSON, creating a default structure if needed."""

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists() or not DATA_FILE.read_text(encoding="utf-8").strip():
        return {"listings": []}

    with DATA_FILE.open(encoding="utf-8") as handle:
        data = json.load(handle)

    if "listings" not in data or not isinstance(data["listings"], list):
        data["listings"] = []
    return data


def save_listings(data: dict[str, Any]) -> None:
    """Persist listings back to disk using stable pretty JSON formatting."""

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")


def _slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "listing"


def generate_listing_id(company: str, role: str, application_url: str) -> str:
    """Create a stable identifier from listing fields."""

    base = f"{company}|{role}|{application_url}"
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
    return f"{_slugify(company)}-{_slugify(role)}-{digest}"


def upsert_listing(listing: dict[str, Any]) -> None:
    """Insert or update a listing by id and save the canonical dataset."""

    data = load_listings()
    listings = data.setdefault("listings", [])
    listing_id = listing.get("id")
    if not listing_id:
        raise ValueError("listing must include an id")

    if listing.get("open") is False:
        listings[:] = [existing for existing in listings if existing.get("id") != listing_id]
        save_listings(data)
        return

    incoming_key = listing_key(listing)
    found = False
    for index, existing in enumerate(listings):
        if existing.get("id") == listing_id or listing_key(existing) == incoming_key:
            merged = {**existing, **listing}
            merged.setdefault("posted_date", existing.get("posted_date"))
            merged.setdefault("posted_age_text", existing.get("posted_age_text"))
            merged.setdefault("duration_text", existing.get("duration_text"))
            merged["last_seen_date"] = listing.get("last_seen_date", _utc_today())
            listings[index] = merged
            found = True
            break

    if not found:
        listings.append(listing)

    save_listings(data)


def remove_listings(predicate) -> int:
    """Remove listings matching a predicate and return the count removed."""

    data = load_listings()
    listings = data.setdefault("listings", [])
    before = len(listings)
    listings[:] = [listing for listing in listings if not predicate(listing)]
    removed = before - len(listings)
    if removed:
        save_listings(data)
    return removed


def listing_key(listing: dict[str, Any]) -> str:
    """Return a stable dedupe key for a listing."""

    company = _normalize_key_text(str(listing.get("company", "")))
    role = _normalize_key_text(str(listing.get("role", "")))
    country = _normalize_key_text(str(listing.get("country", "")))
    city = _normalize_key_text(str(listing.get("city", "")))
    region = _normalize_key_text(str(listing.get("region", "")))
    listing_type = _normalize_key_text(str(listing.get("type", "")))
    return "|".join([company, role, country, city, region, listing_type])


def _normalize_key_text(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\s+", " ", value)
    return value


def cleanup_listings() -> int:
    """Remove placeholder, expired, and clearly non-SWE rows from the dataset."""

    def should_remove(listing: dict[str, Any]) -> bool:
        company = str(listing.get("company", ""))
        role = str(listing.get("role", ""))
        title_blob = f"{company} {role}".lower()
        if listing.get("open") is False:
            return True
        if company.startswith("Example "):
            return True
        if company == "Acceldata" and not any(term in title_blob for term in ("software", "developer", "embedded", "platform", "backend", "frontend", "full stack", "research")):
            return True
        return False

    return remove_listings(should_remove)


def infer_category_and_ai_focus(
    title: str, description: str | None
) -> tuple[str | None, bool]:
    """Return SWE category and AI-focus flag, or ``(None, False)`` if irrelevant."""

    text = f"{title} {description or ''}".lower()
    if not any(keyword in text for keyword in SWE_KEYWORDS):
        return None, False

    ai_focus = any(keyword.strip() in text for keyword in AI_KEYWORDS)
    return "SWE", ai_focus


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()
