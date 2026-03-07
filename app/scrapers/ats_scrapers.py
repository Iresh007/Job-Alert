from __future__ import annotations

import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Dict, List

from app.scrapers.base import BaseScraper
from app.utils import parse_iso_or_none


INDIA_LOCATION_HINTS = [
    "india",
    "bangalore",
    "bengaluru",
    "hyderabad",
    "pune",
    "gurgaon",
    "noida",
    "mumbai",
    "chennai",
]

REMOTE_HINTS = ["remote", "work from home", "anywhere"]


def _clean_text(value: str) -> str:
    text = unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def _role_match(title: str, roles: List[str]) -> bool:
    title_lower = (title or "").lower()
    if "manager" in title_lower:
        return False
    normalized_roles = [item.lower() for item in roles]
    explicit_terms = [
        "data engineer",
        "databricks engineer",
        "azure data engineer",
        "snowflake data engineer",
        "snowflake developer",
    ]
    if any(term in title_lower for term in explicit_terms):
        return True
    if "data" in title_lower and "engineer" in title_lower:
        return True
    return any(role in title_lower for role in normalized_roles)


def _location_match(location: str, allowed: List[str]) -> bool:
    loc = (location or "").lower()
    if not loc:
        return True
    allowed_lower = [item.lower() for item in allowed]
    if any(item in loc for item in allowed_lower):
        return True
    if "india" in allowed_lower and any(hint in loc for hint in INDIA_LOCATION_HINTS):
        return True
    if "remote" in allowed_lower and any(hint in loc for hint in REMOTE_HINTS):
        return True
    return False


def _base_job() -> Dict[str, Any]:
    return {
        "job_id": "",
        "title": "",
        "company": "",
        "location": "",
        "url": "",
        "description": "",
        "skills": [],
        "posted_time": None,
        "experience_required": "",
        "company_type": "unknown",
        "source": "",
        "recruiter_name": "",
    }


class GreenhouseScraper(BaseScraper):
    source_name = "Greenhouse"

    async def scrape(self, companies: List[str], roles: List[str], locations: List[str]) -> List[dict]:
        results: List[dict] = []
        for company in companies:
            url = f"https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true"
            payload = await self.fetch_json(url)
            if not payload or "jobs" not in payload:
                continue
            for job in payload.get("jobs", []):
                title = job.get("title", "")
                location = (job.get("location") or {}).get("name", "")
                if not _role_match(title, roles) or not _location_match(location, locations):
                    continue
                entry = _base_job()
                entry.update(
                    {
                        "job_id": f"gh-{company}-{job.get('id', '')}",
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": job.get("absolute_url", ""),
                        "description": _clean_text(job.get("content", "")),
                        "posted_time": parse_iso_or_none(job.get("updated_at")),
                        "source": self.source_name,
                    }
                )
                results.append(entry)
        return results


class LeverScraper(BaseScraper):
    source_name = "Lever"

    async def scrape(self, companies: List[str], roles: List[str], locations: List[str]) -> List[dict]:
        results: List[dict] = []
        for company in companies:
            url = f"https://api.lever.co/v0/postings/{company}?mode=json"
            payload = await self.fetch_json(url)
            if not isinstance(payload, list):
                continue
            for job in payload:
                title = job.get("text", "")
                location = (job.get("categories") or {}).get("location", "")
                if not _role_match(title, roles) or not _location_match(location, locations):
                    continue
                created_ms = job.get("createdAt")
                posted = datetime.fromtimestamp(created_ms / 1000, tz=timezone.utc) if isinstance(created_ms, (int, float)) else None
                entry = _base_job()
                entry.update(
                    {
                        "job_id": f"lever-{company}-{job.get('id', '')}",
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": job.get("applyUrl", ""),
                        "description": _clean_text(job.get("descriptionPlain", "") or job.get("description", "")),
                        "posted_time": posted,
                        "source": self.source_name,
                    }
                )
                results.append(entry)
        return results


class SmartRecruitersScraper(BaseScraper):
    source_name = "SmartRecruiters"

    async def scrape(self, companies: List[str], roles: List[str], locations: List[str]) -> List[dict]:
        results: List[dict] = []
        for company in companies:
            offset = 0
            while True:
                url = (
                    "https://api.smartrecruiters.com/v1/companies/"
                    f"{company}/postings?offset={offset}&limit=100"
                )
                payload = await self.fetch_json(url)
                if not payload or "content" not in payload:
                    break
                postings = payload.get("content", [])
                if not postings:
                    break
                for job in postings:
                    title = job.get("name", "")
                    location = job.get("location", {}).get("city", "") or job.get("location", {}).get("region", "")
                    if not _role_match(title, roles) or not _location_match(location, locations):
                        continue
                    posted = parse_iso_or_none(job.get("releasedDate"))
                    entry = _base_job()
                    posting_id = job.get("id", "")
                    human_url = f"https://jobs.smartrecruiters.com/{company}/{posting_id}" if posting_id else job.get("ref", "")
                    entry.update(
                        {
                            "job_id": f"sr-{company}-{job.get('id', '')}",
                            "title": title,
                            "company": job.get("company", {}).get("name", company),
                            "location": location,
                            "url": human_url,
                            "description": _clean_text(job.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get("text", "")),
                            "posted_time": posted,
                            "source": self.source_name,
                        }
                    )
                    results.append(entry)
                offset += 100
                if len(postings) < 100:
                    break
        return results


class WorkdayScraper(BaseScraper):
    source_name = "Workday"

    async def scrape(self, entries: List[dict], roles: List[str], locations: List[str]) -> List[dict]:
        results: List[dict] = []
        for item in entries:
            offset = 0
            while True:
                search_url = item.get("search_url", "")
                if not search_url:
                    break
                payload = await self.fetch_json(
                    search_url,
                    method="POST",
                    json_payload={"limit": 20, "offset": offset, "searchText": ""},
                )
                if not payload:
                    break
                jobs = payload.get("jobPostings", [])
                if not jobs:
                    break
                for job in jobs:
                    title = job.get("title", "")
                    location = ", ".join(job.get("locationsText", []) or [])
                    if not _role_match(title, roles) or not _location_match(location, locations):
                        continue
                    external_path = job.get("externalPath", "")
                    apply_base = item.get("apply_base", "")
                    apply_url = f"{apply_base}{external_path}" if apply_base and external_path else search_url
                    posted = parse_iso_or_none(job.get("postedOn"))
                    entry = _base_job()
                    entry.update(
                        {
                            "job_id": f"wd-{item.get('name', 'unknown')}-{job.get('bulletFields', [''])[0]}-{offset}",
                            "title": title,
                            "company": item.get("name", "workday-company"),
                            "location": location,
                            "url": apply_url,
                            "description": _clean_text(" ".join(job.get("bulletFields", []))),
                            "posted_time": posted,
                            "source": self.source_name,
                        }
                    )
                    results.append(entry)
                offset += 20
                total = payload.get("total")
                if isinstance(total, int) and offset >= total:
                    break
        return results


class AshbyScraper(BaseScraper):
    source_name = "Ashby"

    async def scrape(self, companies: List[str], roles: List[str], locations: List[str]) -> List[dict]:
        results: List[dict] = []
        href_pattern = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
        for company in companies:
            page = await self.fetch_text(f"https://jobs.ashbyhq.com/{company}")
            if not page:
                continue
            for href, raw_title in href_pattern.findall(page):
                title = _clean_text(raw_title)
                if "/job/" not in href.lower() and "/jobs/" not in href.lower():
                    continue
                if not _role_match(title, roles):
                    continue
                clean_href = href if href.startswith("http") else f"https://jobs.ashbyhq.com{href}"
                loc_match = re.search(r"(india|remote)", title, flags=re.IGNORECASE)
                location = loc_match.group(1) if loc_match else "Remote"
                if not _location_match(location, locations):
                    continue
                entry = _base_job()
                entry.update(
                    {
                        "job_id": f"ashby-{company}-{abs(hash(clean_href))}",
                        "title": title,
                        "company": company,
                        "location": location,
                        "url": clean_href,
                        "description": "",
                        "posted_time": None,
                        "source": self.source_name,
                    }
                )
                results.append(entry)
        return results
