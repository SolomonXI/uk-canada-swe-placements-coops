"""UK industrial placement scraper for SWE roles."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import Scraper
from .utils import generate_listing_id, infer_category_and_ai_focus, upsert_listing

STARTING_URLS = [
    # Real public job pages. Update or extend this list as new placement pages appear.
    "https://konecranes.careers/job/placement-software-engineer-in-leicester-england-united-kingdom-jid-2162",
    "https://jobs.accel.com/companies/pismo/jobs/61729613-software-engineer-12-months-placement-student",
    "https://careers.crane.vc/companies/pqshield/jobs/60817731-software-engineering-internship-placement-year-2026",
    "https://careers.lucygroup.com/en/job/26057",
    "https://careers.baesystems.com/locations/uk/internships/industrial-placements",
]

TARGET_DURATION_MONTHS = 12


class UKIndustrialPlacementsScraper(Scraper):
    source_name = "UKIndustrialPlacements"

    def run(self) -> None:
        """Fetch live placement pages, extract SWE industrial placements, and save them."""

        for url in STARTING_URLS:
            try:
                response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
            except requests.RequestException as exc:
                print(f"[UK] Skipping {url}: {exc}")
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            listing = _parse_uk_listing(soup, url)
            if not listing or listing.get("duration_months") != TARGET_DURATION_MONTHS:
                print(f"[UK] No matching {TARGET_DURATION_MONTHS}-month SWE placement found at {url}")
                continue
            upsert_listing(listing)
            print(f"[UK] Upserted {listing['id']}")


def _parse_uk_listing(soup: BeautifulSoup, page_url: str) -> dict | None:
    host = urlparse(page_url).netloc.lower()
    if "konecranes.careers" in host:
        return _parse_konecranes(soup, page_url)
    if "jobs.accel.com" in host or "careers.crane.vc" in host:
        return _parse_getro_style_job(soup, page_url)
    if "careers.lucygroup.com" in host:
        return _parse_generic_single_job(soup, page_url)
    if "careers.baesystems.com" in host:
        return _parse_bae_systems(soup, page_url)
    return _parse_generic_single_job(soup, page_url)


def _parse_konecranes(soup: BeautifulSoup, page_url: str) -> dict | None:
    title = _meta_content(soup, "og:title") or _title_text(soup) or ""
    description = _meta_content(soup, "description") or ""
    body_text = _normalized_text(soup)
    combined = f"{title} {description} {body_text}"

    category, ai_focus = infer_category_and_ai_focus(title, combined)
    if category is None or not _looks_like_placement(combined):
        return None

    company = _meta_content(soup, "og:site_name") or _company_from_title(title) or "Konecranes"
    location = _extract_location_from_title(title) or _extract_location_from_body(body_text) or "Leicester, England, United Kingdom"
    city, region = _split_location(location)
    duration_months = _extract_duration_months(combined)
    duration_text = _extract_duration_text(combined)
    posted_date, posted_age_text = _extract_posted_metadata(soup, combined)
    open_ = not _looks_closed(combined)

    return {
        "id": generate_listing_id(company, title or "Placement Software Engineer", page_url),
        "company": company,
        "role": title or "Placement Software Engineer",
        "short_role": _short_role(title or "Placement Software Engineer"),
        "type": "industrial_placement",
        "category": "SWE",
        "ai_focus": ai_focus,
        "duration_months": duration_months,
        "country": "UK",
        "city": city,
        "region": region,
        "locations": [location] if location else [],
        "application_url": _find_apply_url(soup) or page_url,
        "source": "Konecranes",
        "posted_date": posted_date,
        "posted_age_text": posted_age_text,
        "last_seen_date": _utc_today(),
        "open": open_,
        "sponsorship": "Unknown",
        "duration_text": duration_text,
        "notes": _build_notes(combined, duration_months, duration_text),
    }


def _parse_getro_style_job(soup: BeautifulSoup, page_url: str) -> dict | None:
    title = _first_relevant_heading(soup) or _meta_content(soup, "og:title") or _title_text(soup) or ""
    company = _company_from_getro_page(soup, page_url)
    text = _normalized_text(soup)
    category, ai_focus = infer_category_and_ai_focus(title, text)
    if category is None or not _looks_like_placement(text):
        return None

    location = _location_from_getro_page(soup, text)
    city, region = _split_location(location)
    duration_months = _extract_duration_months(text)
    duration_text = _extract_duration_text(text)
    posted_date, posted_age_text = _extract_posted_metadata(soup, text)
    open_ = not _looks_closed(text)

    return {
        "id": generate_listing_id(company, title, page_url),
        "company": company,
        "role": title,
        "short_role": _short_role(title),
        "type": "industrial_placement",
        "category": "SWE",
        "ai_focus": ai_focus,
        "duration_months": duration_months,
        "country": "UK",
        "city": city,
        "region": region,
        "locations": [location] if location else [],
        "application_url": _find_apply_url(soup) or page_url,
        "source": _get_source_label(page_url),
        "posted_date": posted_date,
        "posted_age_text": posted_age_text,
        "last_seen_date": _utc_today(),
        "open": open_,
        "sponsorship": "Unknown",
        "duration_text": duration_text,
        "notes": _build_notes(text, duration_months, duration_text),
    }


def _parse_generic_single_job(soup: BeautifulSoup, page_url: str) -> dict | None:
    title = _first_relevant_heading(soup) or _meta_content(soup, "og:title") or _title_text(soup) or ""
    text = _normalized_text(soup)
    combined = f"{title} {text}"
    category, ai_focus = infer_category_and_ai_focus(title, combined)
    if category is None or not _looks_like_placement(combined):
        return None

    site_name = _meta_content(soup, "og:site_name") or ""
    company = _company_from_title(_meta_content(soup, "og:title") or title) or site_name.replace(" Careers", "").strip() or "Unknown Company"
    location = _extract_location_from_body(text)
    city, region = _split_location(location)
    duration_months = _extract_duration_months(combined)
    duration_text = _extract_duration_text(combined)
    posted_date, posted_age_text = _extract_posted_metadata(soup, combined)

    return {
        "id": generate_listing_id(company, title or "Placement", page_url),
        "company": company,
        "role": title or "Placement",
        "short_role": _short_role(title or "Placement"),
        "type": "industrial_placement",
        "category": "SWE",
        "ai_focus": ai_focus,
        "duration_months": duration_months,
        "country": "UK",
        "city": city,
        "region": region,
        "locations": [location] if location else [],
        "application_url": _find_apply_url(soup) or page_url,
        "source": _get_source_label(page_url),
        "posted_date": posted_date,
        "posted_age_text": posted_age_text,
        "last_seen_date": _utc_today(),
        "open": not _looks_closed(text),
        "sponsorship": "Unknown",
        "duration_text": duration_text,
        "notes": _build_notes(combined, duration_months, duration_text),
    }


def _parse_bae_systems(soup: BeautifulSoup, page_url: str) -> dict | None:
    text = _normalized_text(soup)
    lowered = text.lower()
    if "software engineer" not in lowered or "placement" not in lowered:
        return None
    if "12 month" not in lowered:
        return None

    company = "BAE Systems"
    title = "Software Engineer"
    duration_months = 12
    duration_text = "12 month placement"
    location = _extract_bae_location(text)
    city, region = _split_location(location)
    posted_date, posted_age_text = _extract_posted_metadata(soup, text)

    return {
        "id": generate_listing_id(company, title, page_url),
        "company": company,
        "role": title,
        "short_role": _short_role(title),
        "type": "industrial_placement",
        "category": "SWE",
        "ai_focus": False,
        "duration_months": duration_months,
        "duration_text": duration_text,
        "country": "UK",
        "city": city,
        "region": region,
        "locations": [location] if location else [],
        "application_url": _find_apply_url(soup) or page_url,
        "source": "BAESystems",
        "posted_date": posted_date,
        "posted_age_text": posted_age_text,
        "last_seen_date": _utc_today(),
        "open": not _looks_closed(text),
        "sponsorship": "Unknown",
        "notes": _build_notes(text, duration_months, duration_text),
    }


def _looks_like_placement(text: str) -> bool:
    lowered = text.lower()
    placement_terms = (
        "industrial placement",
        "placement year",
        "placement student",
        "placement software engineer",
        "software engineer intern",
        "software engineering intern",
        "software intern",
        "internship",
        "intern ",
        "12 month",
        "12-month",
        "12 months",
        "year long internship",
        "year-long internship",
        "internship (placement year",
        "placement year 2026",
    )
    return any(term in lowered for term in placement_terms)


def _looks_closed(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "no longer accepting applications",
            "applications are now closed",
            "applications closed",
            "job is no longer accepting applications",
            "opportunity expired",
        )
    )


def _meta_content(soup: BeautifulSoup, property_name: str) -> str | None:
    tag = soup.find("meta", attrs={"property": property_name}) or soup.find("meta", attrs={"name": property_name})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def _title_text(soup: BeautifulSoup) -> str | None:
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(" ", strip=True)
    return None


def _first_heading(soup: BeautifulSoup) -> str | None:
    for tag_name in ("h1", "h2", "h3"):
        tag = soup.find(tag_name)
        if tag:
            text = tag.get_text(" ", strip=True)
            if text:
                return text
    return None


def _first_relevant_heading(soup: BeautifulSoup) -> str | None:
    keywords = ("software", "engineer", "developer", "intern", "co-op", "coop", "placement")
    skip = {"careers", "company description", "job description", "qualifications", "additional information"}
    for tag_name in ("h1", "h2", "h3"):
        for tag in soup.find_all(tag_name):
            text = tag.get_text(" ", strip=True)
            lowered = text.lower()
            if text and any(keyword in lowered for keyword in keywords) and lowered not in skip:
                return text
    return _first_heading(soup)


def _normalized_text(soup: BeautifulSoup) -> str:
    return " ".join(soup.get_text(" ", strip=True).split())


def _company_from_title(title: str | None) -> str | None:
    if not title:
        return None
    if "@" in title:
        return title.split("@", 1)[1].split("|")[0].strip()
    return None


def _company_from_getro_page(soup: BeautifulSoup, page_url: str) -> str:
    title = _title_text(soup) or ""
    if "@" in title:
        return title.split("@", 1)[1].split("|")[0].strip()
    img = soup.find("img", alt=True)
    if img and img.get("alt"):
        return img["alt"].strip()
    if "|" in title:
        return title.split("|")[-1].strip()
    return urlparse(page_url).netloc.split(".")[0].title()


def _location_from_getro_page(soup: BeautifulSoup, text: str) -> str | None:
    script = soup.find("script", attrs={"type": "application/ld+json"})
    if script and script.string:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                loc = data.get("jobLocation")
                if isinstance(loc, dict):
                    addr = loc.get("address", {})
                    if isinstance(addr, dict):
                        locality = addr.get("addressLocality")
                        if locality:
                            return _expand_uk_location(locality)
        except json.JSONDecodeError:
            pass

    location = _extract_location_from_body(text)
    if location:
        return _expand_uk_location(location)
    if "oxford" in text.lower():
        return "Oxford, Oxfordshire, England, United Kingdom"
    return None


def _extract_location_from_title(title: str | None) -> str | None:
    if not title:
        return None
    m = re.search(r"job in (?P<loc>.+?)\s*\|", title, re.IGNORECASE)
    if m:
        return m.group("loc").strip()
    return None


def _extract_location_from_body(text: str) -> str | None:
    for candidate in (
        "Leicester, England, United Kingdom",
        "Oxford, Oxfordshire, England",
        "Belfast, UK",
        "London, England, United Kingdom",
    ):
        if candidate.lower() in text.lower():
            return candidate
    return None


def _expand_uk_location(location: str | None) -> str | None:
    if not location:
        return None
    if "united kingdom" in location.lower() or ", uk" in location.lower():
        return location
    if location.lower() in {"leicester", "belfast", "oxford"}:
        return location
    return f"{location}, United Kingdom"


def _extract_duration_months(text: str) -> int | None:
    lowered = text.lower()
    if any(term in lowered for term in ("12 month", "12-month", "year long", "year-long", "placement year")):
        return 12
    if any(term in lowered for term in ("10 month", "10-month")):
        return 10
    return None


def _extract_duration_text(text: str) -> str | None:
    patterns = (
        r"\d{1,2}\s*[-–]\s*\d{1,2}\s*(?:month|months)",
        r"\d{1,2}\+\s*(?:month|months)",
        r"\d{1,2}\s*(?:month|months)",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            prefix = text[max(0, match.start() - 12):match.start()].lower()
            if "posted" in prefix:
                continue
            return match.group(0)
    if "year long internship" in text.lower():
        match = re.search(r"year long internship[^.\n]*", text, re.IGNORECASE)
        if match:
            value = match.group(0).split("Applications", 1)[0]
            return value.strip()
    return None


def _extract_posted_metadata(soup: BeautifulSoup | None, text: str) -> tuple[str | None, str | None]:
    posted_date = _extract_posted_date(soup, text)
    if posted_date:
        return posted_date, None
    relative = _extract_relative_age_text(text)
    return None, relative


def _extract_posted_date(soup: BeautifulSoup | None, text: str) -> str | None:
    if soup:
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            payload = script.string or script.get_text(" ", strip=True)
            if not payload:
                continue
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                continue
            for item in _iter_job_postings(data):
                date_value = item.get("datePosted")
                if isinstance(date_value, str) and date_value:
                    return date_value[:10]
    for pattern in (
        r"datePosted\W*[:=]\W*\"?(\d{4}-\d{2}-\d{2})",
        r"posted on ([a-z]{3,9} \d{1,2},? \d{4})",
    ):
        m = re.search(pattern, text, re.IGNORECASE)
        if not m:
            continue
        value = m.group(1).replace(",", "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return value
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
    return None


def _iter_job_postings(payload: object):
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            if isinstance(value, (dict, list)):
                yield from _iter_job_postings(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_job_postings(item)


def _extract_relative_age_text(text: str) -> str | None:
    for pattern in (
        r"Posted\s+\d+\+?\s+months?\s+ago",
        r"Posted\s+\d+\+?\s+weeks?\s+ago",
        r"Posted\s+\d+\+?\s+days?\s+ago",
    ):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def _find_apply_url(soup: BeautifulSoup) -> str | None:
    for a in soup.find_all("a", href=True):
        txt = a.get_text(" ", strip=True).lower()
        if "apply" in txt and a["href"]:
            return a["href"]
    return None


def _short_role(role: str) -> str:
    role = role.replace("Software Engineering", "SWE")
    role = role.replace("Software Engineer", "SWE")
    role = role.replace("Placement Student", "Placement")
    role = role.replace("Industrial Placement", "Placement")
    return role


def _split_location(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    loc = location.replace(" | Konecranes", "")
    parts = [part.strip() for part in re.split(r"[,/]+", loc) if part.strip()]
    if not parts:
        return None, None
    city = parts[0]
    region = None
    if len(parts) > 1:
        if parts[1].lower() in {"uk", "united kingdom"}:
            return city, None
        if parts[1].lower() in {"england", "scotland", "wales", "northern ireland"}:
            region = parts[1]
        else:
            region = parts[1]
    return city, region


def _build_notes(text: str, duration_months: int | None, duration_text: str | None = None) -> str | None:
    notes = []
    if duration_text:
        notes.append(duration_text)
    if duration_months:
        notes.append(f"{duration_months}-month placement")
    if "cyber" in text.lower() or "quantum" in text.lower():
        notes.append("Security-related role")
    return "; ".join(notes) if notes else None


def _extract_bae_location(text: str) -> str | None:
    for candidate in ("Portsmouth", "Bristol", "Barrow", "Warton", "Samlesbury", "Farnborough", "Glasgow"):
        if candidate.lower() in text.lower():
            return _expand_uk_location(candidate)
    return None


def _get_source_label(page_url: str) -> str:
    host = urlparse(page_url).netloc.lower()
    if "konecranes" in host:
        return "Konecranes"
    if "accel" in host:
        return "Accel"
    if "crane" in host:
        return "CraneVC"
    return "JobBoard"


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def run() -> None:
    """Module-level entry point used by the package runner."""

    UKIndustrialPlacementsScraper().run()
