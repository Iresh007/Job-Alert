from __future__ import annotations

import asyncio
import random
from contextlib import asynccontextmanager
from typing import Any

import httpx
from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from app.config import settings


USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
]


class BaseScraper:
    source_name = "base"

    def __init__(self) -> None:
        self.timeout = settings.request_timeout_seconds
        self.retries = settings.max_retries

    async def fetch_json(self, url: str, method: str = "GET", json_payload: dict | None = None) -> Any:
        proxy = settings.proxy_server or None
        for attempt in range(1, self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, proxy=proxy, follow_redirects=True) as client:
                    response = await client.request(method, url, json=json_payload, headers={"User-Agent": random.choice(USER_AGENTS)})
                    response.raise_for_status()
                    return response.json()
            except Exception:
                if attempt >= self.retries:
                    return None
                await asyncio.sleep(1.2 * attempt)
        return None

    async def fetch_text(self, url: str) -> str:
        proxy = settings.proxy_server or None
        for attempt in range(1, self.retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout, proxy=proxy, follow_redirects=True) as client:
                    response = await client.get(url, headers={"User-Agent": random.choice(USER_AGENTS)})
                    response.raise_for_status()
                    return response.text
            except Exception:
                if attempt >= self.retries:
                    return ""
                await asyncio.sleep(1.2 * attempt)
        return ""


@asynccontextmanager
async def browser_context() -> BrowserContext:
    playwright: Playwright = await async_playwright().start()
    launch_args = {"headless": settings.scrape_headless}
    if settings.proxy_server:
        launch_args["proxy"] = {"server": settings.proxy_server}
    browser: Browser = await playwright.chromium.launch(**launch_args)
    context = await browser.new_context(user_agent=random.choice(USER_AGENTS))
    try:
        yield context
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()
