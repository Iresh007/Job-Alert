from __future__ import annotations

import hashlib
import re
from typing import Dict

from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Fingerprint, Job
from app.utils import canonicalize_url, normalize_company


def url_hash(url: str) -> str:
    normalized = canonicalize_url(url)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def title_fingerprint(title: str) -> str:
    text = re.sub(r"[^a-z0-9 ]", " ", (title or "").lower())
    text = " ".join(text.split())
    return text[:255]


class DedupeEngine:
    def is_duplicate(self, db: Session, job: Dict) -> bool:
        candidate_url_hash = url_hash(job.get("url", ""))
        candidate_title = title_fingerprint(job.get("title", ""))
        candidate_company = normalize_company(job.get("company", ""))

        if not job.get("url") or not job.get("title"):
            return True

        exists = db.scalar(select(Fingerprint).where(Fingerprint.url_hash == candidate_url_hash))
        if exists:
            return True

        prior_titles = db.execute(
            select(Job.title_fingerprint, Job.company).where(Job.company.ilike(f"%{job.get('company', '')}%")).limit(100)
        ).all()
        for prior_title, prior_company in prior_titles:
            if normalize_company(prior_company) != candidate_company:
                continue
            similarity = SequenceMatcher(None, prior_title or "", candidate_title).ratio() * 100
            if similarity >= 92:
                return True

        return False

    def persist_fingerprint(self, db: Session, job: Dict) -> None:
        record = Fingerprint(
            url_hash=url_hash(job.get("url", "")),
            title_fingerprint=title_fingerprint(job.get("title", "")),
            company_normalized=normalize_company(job.get("company", "")),
        )
        db.add(record)

