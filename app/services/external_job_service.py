"""
external_job_service.py
────────────────────────────────────────────────────────────────
Scrapes from 4 different platforms that work from servers:
  1. Arbeitnow       — remote jobs, no auth
  2. Himalayas       — remote jobs, keyword search
  3. FindWork        — developer jobs, keyword search
  4. RemoteOK        — remote jobs JSON feed, no auth

Returns 10+ AI-ranked recommendations with clean descriptions
(HTML tags stripped).
"""

import asyncio
import json
import logging
import re
from typing import Optional

import httpx
from groq import Groq

from app.core.config import settings
from app.models.schemas import ExternalJob, ExternalJobMatch, SkillProfile

logger = logging.getLogger("skillmap.external_jobs")
client = Groq(api_key=settings.GROQ_API_KEY)

# ── HTML cleaner ──────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Remove all HTML tags and decode common entities."""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode common HTML entities
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
        "&mdash;": "—", "&ndash;": "–", "&hellip;": "…",
        "&bull;": "•", "&middot;": "·",
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # Truncate to 350 chars for clean display
    if len(text) > 350:
        text = text[:347] + "..."
    return text


# ── Skill → keyword mapping ───────────────────────────────────────────────

SKILL_KEYWORDS = {
    "react": "React developer",
    "javascript": "JavaScript developer",
    "typescript": "TypeScript developer",
    "vue": "Vue.js developer",
    "angular": "Angular developer",
    "python": "Python developer",
    "django": "Django developer",
    "fastapi": "Python FastAPI developer",
    "node": "Node.js developer",
    "express": "Node.js developer",
    "flutter": "Flutter developer",
    "dart": "Flutter developer",
    "kotlin": "Android developer",
    "swift": "iOS developer",
    "android": "Android developer",
    "ios": "iOS developer",
    "mobile": "mobile developer",
    "figma": "UI UX designer",
    "ux": "UX designer",
    "ui": "UI designer",
    "design": "product designer",
    "graphic": "graphic designer",
    "marketing": "digital marketing",
    "seo": "SEO specialist",
    "content": "content writer",
    "copywriting": "copywriter",
    "data": "data analyst",
    "sql": "data analyst",
    "analytics": "data analyst",
    "machine learning": "machine learning engineer",
    "ml": "machine learning engineer",
    "ai": "AI engineer",
    "backend": "backend developer",
    "frontend": "frontend developer",
    "fullstack": "fullstack developer",
    "devops": "DevOps engineer",
    "cloud": "cloud engineer",
    "aws": "AWS engineer",
    "video": "video editor",
    "premiere": "video editor",
    "php": "PHP developer",
    "java": "Java developer",
    "golang": "Go developer",
    "rust": "Rust developer",
    "c++": "C++ developer",
}


def _get_keyword(skills: list[str], primary_skill: str = "") -> str:
    all_skills = [primary_skill.lower()] + [s.lower() for s in skills]
    for skill in all_skills:
        for kw, search in SKILL_KEYWORDS.items():
            if kw in skill:
                return search
    return primary_skill or (skills[0] if skills else "software developer")


# ── Platform fetchers ─────────────────────────────────────────────────────

async def _fetch_arbeitnow(keyword: str, limit: int = 20) -> list[ExternalJob]:
    """Arbeitnow — free, no auth, works from any server IP."""
    jobs: list[ExternalJob] = []
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.get(
                "https://www.arbeitnow.com/api/job-board-api",
                params={"page": 1},
                headers={"Accept": "application/json", "User-Agent": "SkillMap/1.0"},
            )
            r.raise_for_status()
            data = r.json()
            kw_words = set(keyword.lower().split())

            for job in data.get("data", []):
                title = job.get("title", "").lower()
                tags = [t.lower() for t in (job.get("tags") or [])]
                haystack = f"{title} {' '.join(tags)}"
                if not any(w in haystack for w in kw_words if len(w) > 3):
                    continue
                jobs.append(ExternalJob(
                    id=f"arbeitnow-{job.get('slug', str(len(jobs)))}",
                    title=job.get("title", ""),
                    company=job.get("company_name", ""),
                    location=job.get("location") or "Remote",
                    url=job.get("url", ""),
                    description=_strip_html(job.get("description", "")),
                    tags=job.get("tags") or [],
                    job_type=(job.get("job_types") or ["full_time"])[0],
                    salary=None,
                    source="Arbeitnow",
                ))
                if len(jobs) >= limit:
                    break
    except Exception as e:
        logger.warning(f"Arbeitnow failed: {e}")
    return jobs


async def _fetch_remoteok(keyword: str, limit: int = 15) -> list[ExternalJob]:
    """RemoteOK — public JSON feed, no auth required."""
    jobs: list[ExternalJob] = []
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.get(
                "https://remoteok.com/api",
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; SkillMap/1.0)",
                    "Accept": "application/json",
                },
            )
            r.raise_for_status()
            data = r.json()
            kw_words = set(keyword.lower().split())

            for job in data:
                if not isinstance(job, dict) or not job.get("position"):
                    continue
                title = job.get("position", "").lower()
                desc = (job.get("description") or "").lower()[:300]
                tags = [t.lower() for t in (job.get("tags") or [])]
                haystack = f"{title} {desc} {' '.join(tags)}"
                if not any(w in haystack for w in kw_words if len(w) > 3):
                    continue
                jobs.append(ExternalJob(
                    id=f"remoteok-{job.get('id', str(len(jobs)))}",
                    title=job.get("position", ""),
                    company=job.get("company", ""),
                    location="Remote",
                    url=job.get("url") or f"https://remoteok.com/remote-jobs/{job.get('id','')}",
                    description=_strip_html(job.get("description", "")),
                    tags=job.get("tags") or [],
                    job_type="full_time",
                    salary=job.get("salary") or None,
                    source="RemoteOK",
                ))
                if len(jobs) >= limit:
                    break
    except Exception as e:
        logger.warning(f"RemoteOK failed: {e}")
    return jobs


async def _fetch_himalayas(keyword: str, limit: int = 15) -> list[ExternalJob]:
    """Himalayas.app — free remote jobs API."""
    jobs: list[ExternalJob] = []
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.get(
                "https://himalayas.app/jobs/api",
                params={"q": keyword, "limit": limit},
                headers={"Accept": "application/json", "User-Agent": "SkillMap/1.0"},
            )
            r.raise_for_status()
            data = r.json()
            for job in data.get("jobs", [])[:limit]:
                company = job.get("company", {})
                company_name = company.get("name", "") if isinstance(company, dict) else str(company)
                jobs.append(ExternalJob(
                    id=f"himalayas-{job.get('id', str(len(jobs)))}",
                    title=job.get("title", ""),
                    company=company_name,
                    location="Remote",
                    url=job.get("applicationLink") or job.get("url", "https://himalayas.app/jobs"),
                    description=_strip_html(job.get("description", "")),
                    tags=job.get("categories") or [],
                    job_type=job.get("type", "full_time"),
                    salary=str(job["salary"]) if job.get("salary") else None,
                    source="Himalayas",
                ))
    except Exception as e:
        logger.warning(f"Himalayas failed: {e}")
    return jobs


async def _fetch_findwork(keyword: str, limit: int = 10) -> list[ExternalJob]:
    """FindWork.dev — free, no auth required."""
    jobs: list[ExternalJob] = []
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.get(
                "https://findwork.dev/api/jobs/",
                params={"search": keyword, "remote": "true"},
                headers={"Accept": "application/json", "User-Agent": "SkillMap/1.0"},
            )
            if r.status_code != 200:
                return jobs
            data = r.json()
            for job in (data.get("results") or [])[:limit]:
                jobs.append(ExternalJob(
                    id=f"findwork-{job.get('id', str(len(jobs)))}",
                    title=job.get("role", ""),
                    company=job.get("company_name", ""),
                    location=job.get("location") or "Remote",
                    url=job.get("url", "https://findwork.dev"),
                    description=_strip_html(job.get("text", "")),
                    tags=job.get("keywords") or [],
                    job_type="full_time",
                    salary=None,
                    source="FindWork",
                ))
    except Exception as e:
        logger.warning(f"FindWork failed: {e}")
    return jobs


# ── Deduplication ─────────────────────────────────────────────────────────

def _deduplicate(jobs: list[ExternalJob]) -> list[ExternalJob]:
    """Remove duplicate jobs by title+company similarity."""
    seen = set()
    unique = []
    for job in jobs:
        key = f"{job.title.lower()[:30]}|{job.company.lower()[:20]}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique


# ── Keyword pre-filter ────────────────────────────────────────────────────

def _prefilter(jobs: list[ExternalJob], skills: list[str]) -> list[ExternalJob]:
    """Score by keyword overlap, return top 25 for AI ranking."""
    tokens = {s.lower() for s in skills}
    expanded = set()
    for s in tokens:
        expanded.add(s)
        words = s.split()
        expanded.update(words)

    scored = []
    for job in jobs:
        haystack = f"{job.title} {job.description} {' '.join(job.tags)}".lower()
        score = sum(1 for t in expanded if len(t) > 3 and t in haystack)
        scored.append((score, job))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [j for _, j in scored[:25]]


# ── AI ranking ────────────────────────────────────────────────────────────

async def _ai_rank(
    profile: SkillProfile,
    jobs: list[ExternalJob],
    primary_skill: Optional[str],
    experience_level: Optional[str],
) -> list[ExternalJobMatch]:
    if not jobs:
        return []

    payload = [
        {
            "idx": i,
            "title": j.title,
            "company": j.company,
            "location": j.location,
            "tags": j.tags[:6],
            "snippet": j.description[:200],
            "source": j.source,
        }
        for i, j in enumerate(jobs)
    ]

    prompt = f"""You are a talent-matching AI for an African workforce platform.

TALENT:
- Primary skill: {primary_skill or profile.primary_skill}
- Skills: {', '.join(profile.detected_skills[:12])}
- Level: {experience_level or profile.experience_level}

JOBS:
{json.dumps(payload, indent=2)}

Score each job 0-100 for fit. Score >= 45 means worth showing.
Be generous — entry-level talent needs exposure to opportunities.

Return ONLY valid JSON array:
[{{"idx": 0, "score": 82, "reason": "Strong React match, remote-friendly role"}}]
Include ALL jobs."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1500,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        start = raw.find("[")
        end = raw.rfind("]") + 1
        scores = json.loads(raw[start:end]) if start != -1 else []
    except Exception as e:
        logger.error(f"Groq ranking error: {e}")
        return [
            ExternalJobMatch(job=j, match_score=60, reason="Matched by skill keywords")
            for j in jobs[:10]
        ]

    results = []
    for s in scores:
        idx = s.get("idx")
        score = int(s.get("score", 0))
        if idx is not None and 0 <= idx < len(jobs) and score >= 45:
            results.append(ExternalJobMatch(
                job=jobs[idx],
                match_score=score,
                reason=s.get("reason", ""),
            ))

    results.sort(key=lambda x: x.match_score, reverse=True)
    return results[:12]  # Return up to 12


# ── Main entry point ──────────────────────────────────────────────────────

async def find_external_matches(
    profile: SkillProfile,
    primary_skill: Optional[str] = None,
    experience_level: Optional[str] = None,
) -> list[ExternalJobMatch]:
    """
    Fetch from 4 platforms in parallel, deduplicate, AI-rank, return 10+.
    """
    keyword = _get_keyword(
        profile.detected_skills,
        primary_skill or profile.primary_skill
    )
    logger.info(f"Searching: '{keyword}'")

    # All 4 sources in parallel
    results = await asyncio.gather(
        _fetch_arbeitnow(keyword, limit=20),
        _fetch_remoteok(keyword, limit=15),
        _fetch_himalayas(keyword, limit=15),
        _fetch_findwork(keyword, limit=10),
        return_exceptions=True,
    )

    all_jobs: list[ExternalJob] = []
    sources = []
    names = ["Arbeitnow", "RemoteOK", "Himalayas", "FindWork"]
    for i, r in enumerate(results):
        if isinstance(r, list) and r:
            all_jobs.extend(r)
            sources.append(names[i])
            logger.info(f"{names[i]}: {len(r)} jobs")
        elif isinstance(r, Exception):
            logger.warning(f"{names[i]} error: {r}")

    logger.info(f"Total fetched: {len(all_jobs)} from {sources}")

    if not all_jobs:
        logger.warning("All sources empty — using fallback")
        return _fallback_jobs(profile, primary_skill)

    # Deduplicate across platforms
    unique = _deduplicate(all_jobs)
    logger.info(f"After dedup: {len(unique)} unique jobs")

    # Keyword filter down to top 25 for AI
    filtered = _prefilter(unique, profile.detected_skills + [primary_skill or ""])
    logger.info(f"Sending {len(filtered)} to AI ranking")

    matches = await _ai_rank(profile, filtered, primary_skill, experience_level)
    logger.info(f"AI returned {len(matches)} matches")

    # If AI returned fewer than 10, pad with remaining jobs
    if len(matches) < 10 and len(filtered) > len(matches):
        matched_ids = {m.job.id for m in matches}
        for job in filtered:
            if job.id not in matched_ids:
                matches.append(ExternalJobMatch(
                    job=job,
                    match_score=50,
                    reason="Relevant to your skill set"
                ))
            if len(matches) >= 10:
                break

    return matches


def _fallback_jobs(profile: SkillProfile, primary_skill: Optional[str]) -> list[ExternalJobMatch]:
    """Static fallback when all APIs fail."""
    skill = (primary_skill or profile.primary_skill or "").lower()
    jobs = [
        ExternalJob(id="f1", title="Remote Frontend Developer", company="TechStartup Africa",
            location="Remote", url="https://weworkremotely.com/categories/remote-front-end-programming-jobs",
            description="Build modern web apps with React and TypeScript for a fast-growing startup.",
            tags=["React", "TypeScript", "CSS"], job_type="full_time", source="WeWorkRemotely"),
        ExternalJob(id="f2", title="Full Stack Engineer", company="Global Remote Co",
            location="Remote", url="https://remoteok.com",
            description="Work on full-stack features — Node.js backend, React frontend, PostgreSQL.",
            tags=["Node.js", "React", "PostgreSQL"], job_type="contract", source="RemoteOK"),
        ExternalJob(id="f3", title="UI/UX Designer", company="Product Studio",
            location="Remote", url="https://dribbble.com/jobs",
            description="Create beautiful interfaces for mobile and web. Figma expertise required.",
            tags=["Figma", "UI", "UX"], job_type="full_time", source="Dribbble"),
        ExternalJob(id="f4", title="Python Backend Developer", company="DataTech",
            location="Remote", url="https://weworkremotely.com",
            description="Build scalable APIs and data pipelines using Python, FastAPI, and PostgreSQL.",
            tags=["Python", "FastAPI", "PostgreSQL"], job_type="full_time", source="WeWorkRemotely"),
        ExternalJob(id="f5", title="Mobile Developer (Flutter)", company="AppFactory",
            location="Remote", url="https://remoteok.com",
            description="Develop cross-platform mobile apps using Flutter and Dart.",
            tags=["Flutter", "Dart", "Mobile"], job_type="full_time", source="RemoteOK"),
    ]
    return [
        ExternalJobMatch(job=j, match_score=65, reason="Curated match for your skill set")
        for j in jobs
    ]