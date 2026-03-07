from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from app.utils import hours_since


STACK_KEYWORDS = [
    "azure databricks",
    "databricks",
    "snowflake",
    "azure data factory",
    "adls",
    "adls gen2",
    "pyspark",
    "spark",
    "sql",
]

ARCH_KEYWORDS = ["data vault", "data vault 2.0", "medallion", "bronze", "silver", "gold"]
CLOUD_KEYWORDS = ["azure", "aws", "gcp"]
CICD_KEYWORDS = ["jenkins", "azure devops", "github actions", "ci/cd"]
RECRUITER_HINTS = ["recruiter", "talent", "hiring manager"]


@dataclass
class ScoreResult:
    interview_probability: float
    salary_fit_probability: float
    stack_match: float
    is_super_priority: bool
    is_ultra_low_competition: bool
    apply_within_6_hours: bool


class ScoringEngine:
    def _is_target_role(self, title: str) -> bool:
        tl = (title or "").lower()
        if any(term in tl for term in ["data engineer", "databricks", "azure data", "snowflake"]):
            return True
        return "data" in tl and "engineer" in tl and "manager" not in tl

    def _ratio(self, text: str, keywords: List[str]) -> float:
        text_lower = (text or "").lower()
        if not keywords:
            return 0
        hits = sum(1 for keyword in keywords if keyword in text_lower)
        return min((hits / len(keywords)) * 100, 100)

    def _company_type_score(self, company_type: str) -> float:
        value = (company_type or "").lower()
        if any(token in value for token in ["product", "startup", "funded"]):
            return 100
        if "service" in value or "consult" in value:
            return 55
        return 65

    def _freshness_score(self, posted_time) -> float:
        age_hours = hours_since(posted_time)
        if age_hours <= 6:
            return 100
        if age_hours <= 24:
            return 85
        if age_hours <= 72:
            return 65
        if age_hours <= 168:
            return 45
        return 20

    def _role_clarity_score(self, title: str) -> float:
        tl = (title or "").lower()
        if "data engineer" in tl:
            return 100
        if "engineer" in tl and ("data" in tl or "analytics" in tl):
            return 80
        return 40

    def _recruiter_visibility_score(self, job: Dict) -> float:
        recruiter = (job.get("recruiter_name") or "").lower()
        description = (job.get("description") or "").lower()
        if recruiter:
            return 100
        if any(hint in description for hint in RECRUITER_HINTS):
            return 70
        return 35

    def estimate_salary_fit(self, job: Dict) -> float:
        text = " ".join(
            [
                job.get("title", ""),
                job.get("description", ""),
                " ".join(job.get("skills", []) or []),
                job.get("experience_required", ""),
            ]
        ).lower()

        score = 45.0
        score += 20.0 * (self._ratio(text, STACK_KEYWORDS) / 100)
        score += 10.0 * (self._ratio(text, ARCH_KEYWORDS) / 100)
        score += 10.0 * (self._ratio(text, CICD_KEYWORDS) / 100)
        score += 15.0 if any(x in text for x in ["3+", "3 years", "4 years", "2-5", "3-5"]) else 0.0
        return min(score, 100)

    def score(self, job: Dict, preferred_skills: List[str] | None = None) -> ScoreResult:
        combined_text = " ".join(
            [
                job.get("title", ""),
                job.get("description", ""),
                " ".join(job.get("skills", []) or []),
                job.get("experience_required", ""),
            ]
        )
        title = job.get("title", "")
        target_role = self._is_target_role(title)
        preferred = [item.strip().lower() for item in (preferred_skills or []) if item and item.strip()]
        preferred_effective = [item for item in preferred if len(item) >= 2]

        effective_stack_keywords = list(dict.fromkeys(STACK_KEYWORDS + preferred_effective))
        stack_match = self._ratio(combined_text, effective_stack_keywords)
        if preferred_effective:
            stack_match = max(stack_match, self._ratio(combined_text, preferred_effective))
        title_lower = title.lower()
        explicit_target_title = any(term in title_lower for term in ["data engineer", "databricks", "azure data", "snowflake"])
        if "databricks" in title_lower or "snowflake" in title_lower or "azure data" in title_lower:
            stack_match = max(stack_match, 92)
        elif "data engineer" in title_lower:
            stack_match = max(stack_match, 82)
        elif target_role:
            stack_match = max(stack_match, 75)

        architecture_match = self._ratio(combined_text, ARCH_KEYWORDS)
        if target_role:
            architecture_match = max(architecture_match, 60)
        if explicit_target_title:
            architecture_match = max(architecture_match, 70)

        cloud_match = self._ratio(combined_text, CLOUD_KEYWORDS)
        if target_role:
            cloud_match = max(cloud_match, 60)
        if explicit_target_title:
            cloud_match = max(cloud_match, 70)

        cicd_match = self._ratio(combined_text, CICD_KEYWORDS)
        if target_role:
            cicd_match = max(cicd_match, 55)
        if explicit_target_title:
            cicd_match = max(cicd_match, 65)

        company_type_score = self._company_type_score(job.get("company_type", "unknown"))
        freshness_score = self._freshness_score(job.get("posted_time"))
        role_clarity_score = self._role_clarity_score(title)
        recruiter_score = self._recruiter_visibility_score(job)

        interview_probability = (
            stack_match * 0.35
            + architecture_match * 0.15
            + cloud_match * 0.10
            + cicd_match * 0.10
            + company_type_score * 0.10
            + freshness_score * 0.10
            + role_clarity_score * 0.05
            + recruiter_score * 0.05
        )

        salary_fit = self.estimate_salary_fit(job)

        age_hours = hours_since(job.get("posted_time"))
        is_super = age_hours <= 6 and interview_probability >= 80 and stack_match >= 80
        is_ultra = age_hours <= 3

        return ScoreResult(
            interview_probability=round(interview_probability, 2),
            salary_fit_probability=round(salary_fit, 2),
            stack_match=round(stack_match, 2),
            is_super_priority=is_super,
            is_ultra_low_competition=is_ultra,
            apply_within_6_hours=is_super,
        )
