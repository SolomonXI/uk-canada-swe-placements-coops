"""Canadian SWE co-op scraper focused on Toronto, Vancouver, and Calgary."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .base import Scraper
from .utils import generate_listing_id, infer_category_and_ai_focus, upsert_listing

STARTING_URLS = [
    # Real public job pages and boards.
    "https://jobs.lever.co/kepler",
    "https://jobs.lever.co/kabam/ad42a9d4-838d-443e-be94-e18b9097851e",
    "https://jobs.lever.co/waabi/0fd4e30b-9bd1-4b53-9043-6088457363cb",
    "https://jobs.lever.co/acceldata",
    "https://jobs.lever.co/achievers",
    "https://jobs.pointnine.com/companies/clio/jobs/61425836-software-developer-co-op",
]

CITY_REGION_MAP = {
    "toronto": ("Toronto", "Ontario"),
    "vancouver": ("Vancouver", "British Columbia"),
    "burnaby": ("Burnaby", "British Columbia"),
    "calgary": ("Calgary", "Alberta"),
    "kitchener": ("Kitchener", "Ontario"),
    "waterloo": ("Waterloo", "Ontario"),
    "ottawa": ("Ottawa", "Ontario"),
    "halifax": ("Halifax", "Nova Scotia"),
}


class CanadaCoopsScraper(Scraper):
    source_name = "CanadaCoops"

    def run(self) -> None:
        """Fetch live Canadian co-op pages, extract SWE roles, and save them."""

        for url in STARTING_URLS:
            try:
                response = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
            except requests.RequestException as exc:
                print(f"[CA] Skipping {url}: {exc}")
                continue

            soup = BeautifulSoup(response.text, "html.parser")
            listings = list(_parse_source(soup, url))
            if not listings:
                print(f"[CA] No matching SWE co-op found at {url}")
                continue
            for listing in listings:
                upsert_listing(listing)
                print(f"[CA] Upserted {listing['id']}")


def _parse_source(soup: BeautifulSoup, page_url: str) -> Iterable[dict]:
    host = urlparse(page_url).netloc.lower()
    if "jobs.lever.co" in host:
        yield from _parse_lever_source(soup, page_url)
        return
    if "jobs.pointnine.com" in host or "jobs.accel.com" in host or "careers.crane.vc" in host:
        listing = _parse_getro_job(soup, page_url)
        if listing:
            yield listing
        return
    if "tdbank.jobs" in host:
        listing = _parse_td_job(soup, page_url)
        if listing:
            yield listing
        return


def _parse_lever_source(soup: BeautifulSoup, page_url: str) -> Iterable[dict]:
    postings = soup.select("div.posting")
    if postings:
        for posting in postings:
            listing = _parse_lever_board_posting(posting, page_url)
            if listing:
                yield listing
        return

    listing = _parse_lever_job_page(soup, page_url)
    if listing:
        yield listing


def _parse_lever_board_posting(posting, page_url: str) -> dict | None:
    title_tag = posting.find("a", class_="posting-title")
    title = _clean_text(_split_lever_title(title_tag.get_text(" ", strip=True) if title_tag else posting.get_text(" ", strip=True)))
    text = _clean_text(posting.get_text(" ", strip=True))
    if _is_non_swe_title(title, text) or not _looks_like_coop(title, text):
        return None

    category, ai_focus = infer_category_and_ai_focus(title, text)
    if category is None:
        return None

    location = _location_from_text_or_url(text, page_url)
    company = _company_from_lever_page(page_url)
    application_url = title_tag["href"] if title_tag and title_tag.has_attr("href") else page_url
    duration_months = _extract_duration_months(text)
    duration_text = _extract_duration_text(text)
    city, region = _split_canadian_location(location)
    posted_date, posted_age_text = _extract_posted_metadata(None, text)

    return {
        "id": generate_listing_id(company, title or "Co-op", application_url),
        "company": company,
        "role": title,
        "short_role": _short_role(title),
        "type": "coop",
        "category": "SWE",
        "ai_focus": ai_focus,
        "duration_months": duration_months,
        "duration_text": duration_text,
        "country": "Canada",
        "city": city,
        "region": region,
        "locations": [location] if location else [],
        "application_url": application_url,
        "source": _get_source_label(page_url),
        "posted_date": posted_date,
        "posted_age_text": posted_age_text,
        "last_seen_date": _utc_today(),
        "open": True,
        "sponsorship": "Unknown",
        "notes": _build_notes(text, duration_months, duration_text),
    }


def _parse_lever_job_page(soup: BeautifulSoup, page_url: str) -> dict | None:
    title = _first_relevant_heading(soup) or _meta_content(soup, "og:title") or _title_text(soup) or ""
    text = _clean_text(soup.get_text(" ", strip=True))
    if _is_non_swe_title(title, text) or not _looks_like_coop(title, text):
        return None

    category, ai_focus = infer_category_and_ai_focus(title, text)
    if category is None:
        return None

    company = _company_from_lever_page(page_url)
    location = _location_from_text_or_url(text, page_url)
    city, region = _split_canadian_location(location)
    duration_months = _extract_duration_months(text)
    duration_text = _extract_duration_text(text)
    application_url = _find_apply_url(soup) or page_url
    posted_date, posted_age_text = _extract_posted_metadata(soup, text)

    return {
        "id": generate_listing_id(company, title or "Co-op", application_url),
        "company": company,
        "role": title,
        "short_role": _short_role(title),
        "type": "coop",
        "category": "SWE",
        "ai_focus": ai_focus,
        "duration_months": duration_months,
        "duration_text": duration_text,
        "country": "Canada",
        "city": city,
        "region": region,
        "locations": [location] if location else [],
        "application_url": application_url,
        "source": _get_source_label(page_url),
        "posted_date": posted_date,
        "posted_age_text": posted_age_text,
        "last_seen_date": _utc_today(),
        "open": not _looks_closed(text),
        "sponsorship": "Unknown",
        "notes": _build_notes(text, duration_months, duration_text),
    }


def _parse_getro_job(soup: BeautifulSoup, page_url: str) -> dict | None:
    title = _first_relevant_heading(soup) or _title_text(soup) or ""
    text = _clean_text(soup.get_text(" ", strip=True))
    if _is_non_swe_title(title, text) or not _looks_like_coop(title, text):
        return None

    category, ai_focus = infer_category_and_ai_focus(title, text)
    if category is None:
        return None

    company = _company_from_getro_page(soup, page_url)
    location = _location_from_getro_page(soup, text)
    city, region = _split_canadian_location(location)
    duration_months = _extract_duration_months(text)
    duration_text = _extract_duration_text(text)
    posted_date, posted_age_text = _extract_posted_metadata(soup, text)

    return {
        "id": generate_listing_id(company, title or "Co-op", page_url),
        "company": company,
        "role": title,
        "short_role": _short_role(title),
        "type": "coop",
        "category": "SWE",
        "ai_focus": ai_focus,
        "duration_months": duration_months,
        "duration_text": duration_text,
        "country": "Canada",
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
        "notes": _build_notes(text, duration_months, duration_text),
    }


def _parse_td_job(soup: BeautifulSoup, page_url: str) -> dict | None:
    text = _clean_text(soup.get_text(" ", strip=True))
    title = _first_relevant_heading(soup) or _meta_content(soup, "og:title") or _title_text(soup) or ""
    if _is_non_swe_title(title, text) or not _looks_like_coop(title, text):
        return None

    category, ai_focus = infer_category_and_ai_focus(title, text)
    if category is None:
        return None

    company = "TD"
    location = _location_from_text_or_url(text, page_url) or "Toronto, Ontario, Canada"
    city, region = _split_canadian_location(location)
    duration_months = _extract_duration_months(text)
    duration_text = _extract_duration_text(text)
    posted_date, posted_age_text = _extract_posted_metadata(soup, text)
    application_url = _find_apply_url(soup) or page_url

    return {
        "id": generate_listing_id(company, title or "Co-op", application_url),
        "company": company,
        "role": title,
        "short_role": _short_role(title),
        "type": "coop",
        "category": "SWE",
        "ai_focus": ai_focus,
        "duration_months": duration_months,
        "duration_text": duration_text,
        "country": "Canada",
        "city": city,
        "region": region,
        "locations": [location] if location else [],
        "application_url": application_url,
        "source": _get_source_label(page_url),
        "posted_date": posted_date,
        "posted_age_text": posted_age_text,
        "last_seen_date": _utc_today(),
        "open": not _looks_closed(text),
        "sponsorship": "Unknown",
        "notes": _build_notes(text, duration_months, duration_text),
    }


def _looks_like_coop(title: str, text: str) -> bool:
    lowered = f"{title} {text}".lower()
    return any(term in lowered for term in ("co-op", "coop", "co op", "cooperative education", "intern/co-op", "internship/coop"))


def _is_non_swe_title(title: str, text: str) -> bool:
    lowered = f"{title} {text}".lower()
    return "systems engineering" in lowered and "software" not in lowered


def _split_lever_title(text: str) -> str:
    # Lever board titles usually look like: "Role Title Hybrid — Co-op Toronto".
    text = " ".join(text.split())
    match = re.split(r"\s(?:Hybrid|On-site|Remote|Full-time|Full Time)\s[—-]\s", text, maxsplit=1)
    if match:
        return match[0].strip()
    return text.strip()


def _looks_closed(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "no longer accepting applications",
            "applications closed",
            "job is no longer accepting applications",
            "this job is no longer accepting applications",
            "opportunity expired",
        )
    )


def _meta_content(soup: BeautifulSoup, property_name: str) -> str | None:
    tag = soup.find("meta", attrs={"property": property_name}) or soup.find("meta", attrs={"name": property_name})
    if tag and tag.get("content"):
        return tag["content"].strip()
    return None


def _title_text(soup: BeautifulSoup) -> str | None:
    return soup.title.get_text(" ", strip=True) if soup.title else None


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
    skip = {"summary:", "job description", "qualifications", "additional information", "what your team does:"}
    for tag_name in ("h1", "h2", "h3"):
        for tag in soup.find_all(tag_name):
            text = tag.get_text(" ", strip=True)
            lowered = text.lower()
            if text and any(keyword in lowered for keyword in keywords) and lowered not in skip:
                return text
    return _first_heading(soup)


def _clean_text(value: str) -> str:
    return " ".join(value.split())


def _company_from_lever_page(page_url: str) -> str:
    host = urlparse(page_url).netloc.lower()
    if "achievers" in host:
        return "Achievers"
    if "acceldata" in host:
        return "Acceldata"
    if "kabam" in host:
        return "Kabam"
    if "waabi" in host:
        return "Waabi"
    if "magnetforensics" in host:
        return "Magnet Forensics"
    if "pointnine" in host:
        return "Clio"
    if "tdbank" in host:
        return "TD"
    slug = urlparse(page_url).path.strip("/").split("/")[0]
    if slug:
        if slug == "magnetforensics":
            return "Magnet Forensics"
        return slug.replace("-", " ").title()
    return host.split(".")[0].title()


def _company_from_getro_page(soup: BeautifulSoup, page_url: str) -> str:
    img = soup.find("img", alt=True)
    if img and img.get("alt"):
        return img["alt"].strip()
    title = _title_text(soup) or ""
    if "@" in title:
        return title.split("@", 1)[1].split("|")[0].strip()
    return urlparse(page_url).netloc.split(".")[0].title()


def _location_from_lever_page(text: str) -> str | None:
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if any(city in line.lower() for city in CITY_REGION_MAP):
            return _expand_canadian_location(line)
    return None


def _location_from_text_or_url(text: str, page_url: str) -> str | None:
    location = _extract_location_from_text(text)
    if location:
        return _expand_canadian_location(location)
    host = urlparse(page_url).netloc.lower()
    if "tdbank.jobs" in host or "achievers" in host or "pointnine" in host:
        return "Toronto, Ontario, Canada"
    if "acceldata" in host:
        return "Kitchener, Ontario, Canada"
    if "kabam" in host:
        return "Vancouver, British Columbia, Canada"
    if "waabi" in host:
        return "Toronto, Ontario, Canada"
    if "magnetforensics" in host:
        return "Waterloo, Ontario, Canada"
    return None


def _extract_location_from_text(text: str) -> str | None:
    for city in CITY_REGION_MAP:
        if city in text.lower():
            return _expand_canadian_location(city)
    for snippet in (
        "Toronto, ON",
        "Toronto, Ontario",
        "Vancouver, BC",
        "Vancouver, British Columbia",
        "Calgary, AB",
        "Calgary, Alberta",
        "Burnaby, BC",
        "Waterloo, Ontario",
        "Ottawa, Ontario",
        "Halifax, Nova Scotia",
    ):
        if snippet.lower() in text.lower():
            return snippet
    return None


def _expand_canadian_location(value: str) -> str:
    lowered = value.lower()
    if "toronto" in lowered:
        return "Toronto, Ontario, Canada"
    if "vancouver" in lowered:
        return "Vancouver, British Columbia, Canada"
    if "burnaby" in lowered:
        return "Burnaby, British Columbia, Canada"
    if "calgary" in lowered:
        return "Calgary, Alberta, Canada"
    if "kitchener" in lowered:
        return "Kitchener, Ontario, Canada"
    if "waterloo" in lowered:
        return "Waterloo, Ontario, Canada"
    if "ottawa" in lowered:
        return "Ottawa, Ontario, Canada"
    if "halifax" in lowered:
        return "Halifax, Nova Scotia, Canada"
    return value if "canada" in lowered else f"{value}, Canada"


def _split_canadian_location(location: str | None) -> tuple[str | None, str | None]:
    if not location:
        return None, None
    expanded = _expand_canadian_location(location)
    parts = [part.strip() for part in re.split(r",\s*", expanded) if part.strip()]
    if len(parts) >= 3:
        return parts[0], parts[1]
    if len(parts) == 2:
        city = parts[0]
        region = parts[1] if parts[1] != "Canada" else None
        return city, region
    if parts:
        city = parts[0]
        region = CITY_REGION_MAP.get(city.lower(), (None, None))[1]
        return city, region
    return None, None


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
                            return _expand_canadian_location(locality)
        except json.JSONDecodeError:
            pass

    location = _extract_location_from_text(text)
    if location:
        return _expand_canadian_location(location)
    return None


def _extract_duration_months(text: str) -> int | None:
    lowered = text.lower()
    match = re.search(r"(\d{1,2})\s*[- ]?month", lowered)
    if match:
        return int(match.group(1))
    if "co-op" in lowered or "coop" in lowered:
        if "4 month" in lowered:
            return 4
        if "8 month" in lowered:
            return 8
        if "12 month" in lowered:
            return 12
        if "16 month" in lowered:
            return 16
    return None


def _extract_duration_text(text: str) -> str | None:
    patterns = (
        r"\(\d{1,2}\s*[-–]\s*\d{1,2}\s*(?:month|months)\)",
        r"\(\d{1,2}\+\s*(?:month|months)\)",
        r"\d{1,2}\s*[-–]\s*\d{1,2}\s*(?:month|months)",
        r"\d{1,2}\+\s*(?:month|months)",
        r"\d{1,2}\s*(?:month|months)",
    )
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            prefix = text[max(0, m.start() - 12):m.start()].lower()
            if "posted" in prefix:
                continue
            return m.group(0).strip("()")
    if "year long internship" in text.lower():
        m = re.search(r"year long internship[^.\n]*", text, re.IGNORECASE)
        if m:
            value = m.group(0).split("Applications", 1)[0]
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
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(0).strip()
    return None


def _find_apply_url(soup: BeautifulSoup) -> str | None:
    for a in soup.find_all("a", href=True):
        txt = a.get_text(" ", strip=True).lower()
        if "apply" in txt and a["href"]:
            return a["href"]
    return None


def _short_role(role: str) -> str:
    return (
        role.replace("Software Engineering", "SWE")
        .replace("Software Developer", "SWE")
        .replace("Software Engineer", "SWE")
        .replace("Intern/Co-op", "Co-op")
    )


def _build_notes(text: str, duration_months: int | None, duration_text: str | None = None) -> str | None:
    notes = []
    if duration_text:
        notes.append(duration_text)
    if duration_months:
        notes.append(f"{duration_months}-month co-op")
    if "ai" in text.lower() or "machine learning" in text.lower():
        notes.append("AI-related role")
    return "; ".join(notes) if notes else None


def _get_source_label(page_url: str) -> str:
    host = urlparse(page_url).netloc.lower()
    if "lever.co" in host:
        return "Lever"
    if "pointnine" in host:
        return "PointNine"
    if "tdbank.jobs" in host:
        return "TDBank"
    if "acceldata" in host:
        return "Acceldata"
    if "achievers" in host:
        return "Achievers"
    return "JobBoard"


def _utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _looks_closed(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "no longer accepting applications",
            "applications closed",
            "job is no longer accepting applications",
            "this job is no longer accepting applications",
            "opportunity expired",
        )
    )


def _looks_like_coop(title: str, text: str) -> bool:
    lowered = f"{title} {text}".lower()
    return any(term in lowered for term in ("co-op", "coop", "co op", "cooperative education", "intern/co-op", "internship/coop"))


def run() -> None:
    """Module-level entry point used by the package runner."""

    CanadaCoopsScraper().run()
