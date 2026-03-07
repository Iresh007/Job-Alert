from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def normalize_whitespace(value: str) -> str:
    return " ".join((value or "").split())


def normalize_company(value: str) -> str:
    cleaned = normalize_whitespace((value or "").lower())
    cleaned = re.sub(r"[^a-z0-9 ]", "", cleaned)
    return cleaned.strip()


def canonicalize_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        query = parse_qsl(parsed.query, keep_blank_values=False)
        query = [(k, v) for k, v in query if not k.lower().startswith("utm")]
        query.sort(key=lambda pair: pair[0])
        path = parsed.path.rstrip("/")
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", urlencode(query), ""))
    except Exception:
        return (url or "").strip()


def parse_iso_or_none(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def hours_since(timestamp: datetime | None) -> float:
    if not timestamp:
        return 999.0
    now = datetime.now(timezone.utc)
    ts = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc)
    delta = now - ts
    return max(delta.total_seconds() / 3600.0, 0.0)


def contains_any(text: str, keywords: Iterable[str]) -> bool:
    text_lower = (text or "").lower()
    return any(k.lower() in text_lower for k in keywords)
