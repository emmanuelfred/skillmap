from pydantic import BaseModel
from typing import Optional, List


# ── EXISTING MODELS (unchanged) ───────────────────────────────────────────

class UserInputPayload(BaseModel):
    description: str
    location: Optional[str] = None
    proof_link: Optional[str] = None


class SkillProfile(BaseModel):
    primary_skill: str
    detected_skills: List[str]
    experience_level: str
    suggested_roles: List[str]
    credibility_score: int


class Opportunity(BaseModel):
    id: str
    type: str
    title: str
    required_skills: List[str]
    location: Optional[str]
    description: str


class MatchResult(BaseModel):
    opportunity: Opportunity
    match_score: int
    explanation: str


class ProcessingResponse(BaseModel):
    profile: SkillProfile
    matches: List[MatchResult]


# CV parsing
class CVParseResult(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    description: str = ""
    primary_skill: Optional[str] = None
    extracted_skills: List[str] = []
    experience_level: Optional[str] = None
    career_goals: Optional[str] = None
    languages: List[str] = []
    social_links: List[dict] = []
    hourly_rate: Optional[str] = None


# AI Screening
class ScreeningRequest(BaseModel):
    description: str
    primary_skill: Optional[str] = None
    extracted_skills: List[str] = []
    experience_level: Optional[str] = None
    career_goals: Optional[str] = None
    proof_links: List[dict] = []
    languages: List[str] = []
    hourly_rate: Optional[str] = None
    job_type: Optional[str] = None


class ScreeningResult(BaseModel):
    overall_score: int
    profile_completeness: int
    market_readiness: int
    skill_clarity: int
    summary: str
    strengths: List[str]
    improvements: List[str]
    recommended_roles: List[str]
    salary_insight: str


# ── NEW MODELS — External Job Matching ───────────────────────────────────
# Added below. Nothing above was changed.

class ExternalJob(BaseModel):
    """A live job pulled from an external job board (Remotive, Jobicy, etc.)"""
    id: str
    title: str
    company: str
    location: str
    url: str
    description: str
    tags: List[str] = []
    job_type: Optional[str] = None   # e.g. "full_time", "contract", "part_time"
    salary: Optional[str] = None     # Raw string from source, may be null
    source: str                       # "Remotive" | "Jobicy"


class ExternalJobMatch(BaseModel):
    """An external job paired with its AI-generated match score."""
    job: ExternalJob
    match_score: int          # 0–100
    reason: str               # One-line AI explanation


class ExternalJobsRequest(BaseModel):
    """
    Request body for POST /api/v1/talent/external-jobs.

    Send either a full SkillProfile (from a prior /process-talent call)
    OR the raw fields — the endpoint will construct one for you.
    """
    profile: Optional[SkillProfile] = None        # preferred: reuse existing profile
    primary_skill: Optional[str] = None            # fallback if no profile
    detected_skills: Optional[List[str]] = None    # fallback if no profile
    experience_level: Optional[str] = None


class ExternalJobsResponse(BaseModel):
    matches: List[ExternalJobMatch]
    total: int
    sources: List[str]   # e.g. ["Remotive", "Jobicy"]