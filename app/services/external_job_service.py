"""
external_job_service.py
────────────────────────────────────────────────────────────────
Fetches live remote jobs from free public job-board APIs
(Remotive + Jobicy — no API keys required) and uses Groq AI
to score each job against a talent's extracted profile.

Plugs into the existing MatchingEngine pipeline without
modifying any existing service.
"""

import asyncio
import json
import logging
from typing import Optional

import httpx
from groq import Groq

from app.core.config import settings
from app.models.schemas import ExternalJob, ExternalJobMatch, SkillProfile

logger = logging.getLogger("skillmap.external_jobs")
client = Groq(api_key=settings.GROQ_API_KEY)

# ── Free job-board endpoints (no auth required) ───────────────────────────

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
JOBICY_URL   = "https://jobicy.com/api/v2/remote-jobs"

# Category map: map broad skill → Remotive category slug
SKILL_TO_CATEGORY = {
    "react": "software-dev",
    "javascript": "software-dev",
    "python": "software-dev",
    "node": "software-dev",
    "flutter": "software-dev",
    "mobile": "software-dev",
    "figma": "design",
    "ux": "design",
    "ui": "design",
    "design": "design",
    "marketing": "marketing",
    "seo": "marketing",
    "content": "marketing",
    "social media": "marketing",
    "data": "data",
    "sql": "data",
    "analytics": "data",
    "video": "all-other",
    "writing": "writing",
    "copywriting": "writing",
}


def _pick_remotive_category(skills: list[str]) -> str:
    for skill in [s.lower() for s in skills]:
        for keyword, category in SKILL_TO_CATEGORY.items():
            if keyword in skill:
                return category
    return "all-other"


async def _fetch_remotive(category: str, limit: int = 30) -> list[ExternalJob]:
    jobs: list[ExternalJob] = []
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get(
                REMOTIVE_URL,
                params={"category": category, "limit": limit},
            )
            r.raise_for_status()
            data = r.json()
            for job in data.get("jobs", []):
                jobs.append(ExternalJob(
                    id=f"remotive-{job.get('id', '')}",
                    title=job.get("title", ""),
                    company=job.get("company_name", ""),
                    location=job.get("candidate_required_location") or "Remote",
                    url=job.get("url", ""),
                    description=(job.get("description") or "")[:600],
                    tags=job.get("tags") or [],
                    job_type=job.get("job_type", "full_time"),
                    salary=job.get("salary"),
                    source="Remotive",
                ))
    except Exception as e:
        logger.warning(f"Remotive fetch failed: {e}")
    return jobs


async def _fetch_jobicy(count: int = 20) -> list[ExternalJob]:
    jobs: list[ExternalJob] = []
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            r = await http.get(JOBICY_URL, params={"count": count})
            r.raise_for_status()
            data = r.json()
            for job in data.get("jobs", []):
                jobs.append(ExternalJob(
                    id=f"jobicy-{job.get('id', '')}",
                    title=job.get("jobTitle", ""),
                    company=job.get("companyName", ""),
                    location=job.get("jobGeo") or "Remote",
                    url=job.get("url", ""),
                    description=(job.get("jobExcerpt") or "")[:600],
                    tags=job.get("jobIndustry") or [],
                    job_type=job.get("jobType") or "full_time",
                    salary=job.get("annualSalaryMin"),
                    source="Jobicy",
                ))
    except Exception as e:
        logger.warning(f"Jobicy fetch failed: {e}")
    return jobs


def _keyword_prefilter(
    jobs: list[ExternalJob],
    skills: list[str],
    min_overlap: int = 1,
) -> list[ExternalJob]:
    """
    Fast keyword filter before hitting the AI.
    Keeps jobs whose title or description shares at least `min_overlap`
    words with the talent's skill set.
    """
    skill_tokens = {s.lower() for s in skills}
    filtered = []
    for job in jobs:
        haystack = f"{job.title} {job.description} {' '.join(job.tags)}".lower()
        if any(tok in haystack for tok in skill_tokens):
            filtered.append(job)
    # Always return at least 10 jobs even if overlap is poor, so AI has material
    if len(filtered) < 10:
        filtered = jobs[:10]
    return filtered[:25]  # Cap — we send max 25 to Groq


async def _ai_rank_jobs(
    profile: SkillProfile,
    jobs: list[ExternalJob],
    primary_skill: Optional[str] = None,
    experience_level: Optional[str] = None,
) -> list[ExternalJobMatch]:
    """
    Send up to 25 pre-filtered jobs to Groq for scoring.
    Returns ranked ExternalJobMatch list (score ≥ 40 only).
    """
    if not jobs:
        return []

    jobs_payload = [
        {
            "idx": i,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "tags": j.tags,
            "snippet": j.description[:300],
        }
        for i, j in enumerate(jobs)
    ]

    prompt = f"""You are a talent-matching AI for an African workforce platform.

TALENT PROFILE:
- Primary skill: {primary_skill or profile.primary_skill}
- All skills: {', '.join(profile.detected_skills)}
- Experience level: {experience_level or profile.experience_level}
- Suggested roles: {', '.join(profile.suggested_roles)}

EXTERNAL JOBS (JSON array):
{json.dumps(jobs_payload, indent=2)}

For each job, output a score 0–100 indicating how well it fits the talent.
Consider: skill overlap, seniority fit, role alignment.

Return ONLY valid JSON array — no prose, no markdown:
[
  {{"idx": 0, "score": 85, "reason": "Strong React match, junior-friendly"}},
  {{"idx": 1, "score": 40, "reason": "Partial overlap on design tools"}},
  ...
]
Include ALL jobs. Score 0 if completely irrelevant."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        scores: list[dict] = json.loads(raw)
    except Exception as e:
        logger.error(f"Groq ranking error: {e}")
        # Fallback: return top 5 unscored
        return [
            ExternalJobMatch(job=jobs[i], match_score=50, reason="Keyword match")
            for i in range(min(5, len(jobs)))
        ]

    results: list[ExternalJobMatch] = []
    for s in scores:
        idx = s.get("idx")
        score = int(s.get("score", 0))
        reason = s.get("reason", "")
        if idx is not None and 0 <= idx < len(jobs) and score >= 40:
            results.append(ExternalJobMatch(
                job=jobs[idx],
                match_score=score,
                reason=reason,
            ))

    results.sort(key=lambda x: x.match_score, reverse=True)
    return results[:10]  # Top 10 only


async def find_external_matches(
    profile: SkillProfile,
    primary_skill: Optional[str] = None,
    experience_level: Optional[str] = None,
) -> list[ExternalJobMatch]:
    """
    Main entry point called by the endpoint.
    1. Fetches jobs from Remotive + Jobicy in parallel
    2. Keyword pre-filters to reduce noise
    3. AI scores remaining jobs against profile
    4. Returns top matches (score ≥ 40), sorted descending
    """
    category = _pick_remotive_category(profile.detected_skills)

    # Fetch both sources concurrently
    remotive_jobs, jobicy_jobs = await asyncio.gather(
        _fetch_remotive(category, limit=30),
        _fetch_jobicy(count=20),
    )

    all_jobs = remotive_jobs + jobicy_jobs
    logger.info(f"Fetched {len(all_jobs)} external jobs ({len(remotive_jobs)} Remotive, {len(jobicy_jobs)} Jobicy)")

    if not all_jobs:
        logger.warning("No external jobs fetched — both sources unavailable")
        return []

    filtered = _keyword_prefilter(all_jobs, profile.detected_skills)
    logger.info(f"After keyword filter: {len(filtered)} jobs sent to AI ranking")

    matches = await _ai_rank_jobs(profile, filtered, primary_skill, experience_level)
    logger.info(f"AI returned {len(matches)} scored matches")
    return matches
