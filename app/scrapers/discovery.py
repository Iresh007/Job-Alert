from __future__ import annotations

import asyncio
from typing import Dict, List

from app.config import settings
from app.scrapers.ats_scrapers import AshbyScraper, GreenhouseScraper, LeverScraper, SmartRecruitersScraper, WorkdayScraper
from app.scrapers.board_scrapers import BoardScraper


class SourceDiscoveryService:
    def __init__(self, source_catalog: dict) -> None:
        self.source_catalog = source_catalog or {}

    async def fetch_all(self, roles: List[str], locations: List[str]) -> List[dict]:
        greenhouse = GreenhouseScraper().scrape(self.source_catalog.get("greenhouse", []), roles, locations)
        lever = LeverScraper().scrape(self.source_catalog.get("lever", []), roles, locations)
        smartrecruiters = SmartRecruitersScraper().scrape(self.source_catalog.get("smartrecruiters", []), roles, locations)
        workday = WorkdayScraper().scrape(self.source_catalog.get("workday", []), roles, locations)
        ashby = AshbyScraper().scrape(self.source_catalog.get("ashby", []), roles, locations)
        tasks = [greenhouse, lever, smartrecruiters, workday, ashby]
        if settings.enable_board_scrapers:
            tasks.append(BoardScraper().scrape(roles, locations))

        batches = await asyncio.gather(*tasks, return_exceptions=True)
        flattened: List[dict] = []
        for batch in batches:
            if isinstance(batch, Exception):
                continue
            flattened.extend(batch)
        return flattened
