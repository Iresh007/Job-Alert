from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone
from typing import Dict, List

from app.scrapers.base import BaseScraper, browser_context


BOARD_SOURCES = [
    {
        "name": "LinkedIn",
        "template": "https://www.linkedin.com/jobs/search/?keywords={query}&location={location}&f_TPR=r86400&position=1&pageNum=0",
        "domain_filter": "linkedin.com/jobs/view",
    },
    {
        "name": "Naukri",
        "template": "https://www.naukri.com/{query}-jobs-in-{location}",
        "domain_filter": "naukri.com/job-listings",
    },
    {
        "name": "Indeed",
        "template": "https://in.indeed.com/jobs?q={query}&l={location}",
        "domain_filter": "indeed.com/viewjob",
    },
    {
        "name": "Glassdoor",
        "template": "https://www.glassdoor.co.in/Job/jobs.htm?sc.keyword={query}&locT=C&locId=115&locKeyword={location}",
        "domain_filter": "glassdoor",
    },
    {
        "name": "Foundit",
        "template": "https://www.foundit.in/srp/results?query={query}&locations={location}",
        "domain_filter": "foundit.in",
    },
]


def _build_url(template: str, role: str, location: str) -> str:
    query = urllib.parse.quote_plus(role)
    loc = urllib.parse.quote_plus(location)
    return template.format(query=query, location=loc)


def _empty_job() -> Dict:
    return {
        "job_id": "",
        "title": "",
        "company": "",
        "location": "",
        "url": "",
        "description": "",
        "skills": [],
        "posted_time": datetime.now(timezone.utc),
        "experience_required": "",
        "company_type": "unknown",
        "source": "",
        "recruiter_name": "",
    }


class BoardScraper(BaseScraper):
    source_name = "Boards"

    async def scrape(self, roles: List[str], locations: List[str]) -> List[dict]:
        records: List[dict] = []
        try:
            async with browser_context() as ctx:
                page = await ctx.new_page()
                for source in BOARD_SOURCES:
                    for role in roles:
                        for location in locations:
                            url = _build_url(source["template"], role, location)
                            try:
                                await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                                await page.wait_for_timeout(2000)
                                records.extend(await self._collect_links(page, source, role, location))
                                for _ in range(1):
                                    next_link = page.get_by_role("link", name="Next")
                                    if await next_link.count() == 0:
                                        break
                                    await next_link.first.click(timeout=5000)
                                    await page.wait_for_timeout(2000)
                                    records.extend(await self._collect_links(page, source, role, location))
                            except Exception:
                                continue
                await page.close()
        except Exception:
            return []
        return records

    async def _collect_links(self, page, source: dict, role: str, location: str) -> List[dict]:
        items = await page.eval_on_selector_all(
            "a[href]",
            """
            elements => elements
              .map(el => ({ href: el.href || '', text: (el.textContent || '').trim() }))
              .filter(item => item.href && item.text && item.text.length > 8)
            """,
        )
        results: List[dict] = []
        seen = set()
        for item in items:
            href = item.get("href", "")
            text = item.get("text", "")
            if source["domain_filter"] not in href:
                continue
            key = (href, text)
            if key in seen:
                continue
            seen.add(key)
            record = _empty_job()
            record.update(
                {
                    "job_id": f"{source['name'].lower()}-{abs(hash(href))}",
                    "title": text[:250],
                    "company": "Unknown",
                    "location": location,
                    "url": href,
                    "description": text,
                    "source": source["name"],
                }
            )
            if role.lower() in text.lower() or "engineer" in text.lower():
                results.append(record)
        return results
