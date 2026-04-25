"""
external_jobs_endpoint.py
────────────────────────────────────────────────────────────────
Standalone FastAPI router for AI-powered external job matching.

Mount in your main app with:
    from app.api.external_jobs_endpoint import router as external_jobs_router
    app.include_router(external_jobs_router, prefix="/api/v1")

Does NOT modify endpoints.py — it is purely additive.
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.schemas import (
    ExternalJobsRequest,
    ExternalJobsResponse,
    SkillProfile,
)
from app.services.external_job_service import find_external_matches

logger = logging.getLogger("skillmap.external_jobs_endpoint")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/talent", tags=["external-jobs"])


@router.post("/external-jobs", response_model=ExternalJobsResponse)
@limiter.limit("6/minute")
async def get_external_job_matches(request: Request, body: ExternalJobsRequest):
    """
    Fetch live external jobs from Remotive + Jobicy and score them
    against the talent's profile using Groq AI.

    Accepts either:
      - A pre-built SkillProfile (from /process-talent response)
      - OR raw fields (primary_skill + detected_skills) to build one on the fly

    Returns top matched external jobs with AI-generated match scores.
    """
    # Build a SkillProfile from the request
    if body.profile:
        profile = body.profile
    elif body.primary_skill and body.detected_skills:
        profile = SkillProfile(
            primary_skill=body.primary_skill,
            detected_skills=body.detected_skills,
            experience_level=body.experience_level or "Intermediate",
            suggested_roles=[body.primary_skill],
            credibility_score=50,
        )
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'profile' or both 'primary_skill' and 'detected_skills'.",
        )

    if not profile.detected_skills:
        raise HTTPException(
            status_code=400,
            detail="Profile has no detected skills — cannot match external jobs.",
        )

    try:
        matches = await find_external_matches(
            profile=profile,
            primary_skill=body.primary_skill or profile.primary_skill,
            experience_level=body.experience_level or profile.experience_level,
        )
        return ExternalJobsResponse(
            matches=matches,
            total=len(matches),
            sources=["Remotive", "Jobicy"],
        )
    except Exception as e:
        logger.error(f"external-jobs failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="External job search temporarily unavailable. Please try again.",
        )
