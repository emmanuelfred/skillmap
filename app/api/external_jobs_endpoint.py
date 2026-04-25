"""
external_jobs_endpoint.py — FIXED
Uses Arbeitnow + Himalayas + FindWork instead of Remotive/Jobicy
(those block server IPs with 403).
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.schemas import ExternalJobsRequest, ExternalJobsResponse, SkillProfile
from app.services.external_job_service import find_external_matches

logger = logging.getLogger("skillmap.external_jobs_endpoint")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter(prefix="/talent", tags=["external-jobs"])


@router.post("/external-jobs", response_model=ExternalJobsResponse)
@limiter.limit("6/minute")
async def get_external_job_matches(request: Request, body: ExternalJobsRequest):
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

    if not profile.detected_skills and not profile.primary_skill:
        raise HTTPException(
            status_code=400,
            detail="Profile has no skills — cannot match external jobs.",
        )

    try:
        matches = await find_external_matches(
            profile=profile,
            primary_skill=body.primary_skill or profile.primary_skill,
            experience_level=body.experience_level or profile.experience_level,
        )

        # Collect unique sources from returned matches
        sources = list(dict.fromkeys(m.job.source for m in matches)) or ["Arbeitnow", "Himalayas"]

        return ExternalJobsResponse(
            matches=matches,
            total=len(matches),
            sources=sources,
        )
    except Exception as e:
        logger.error(f"external-jobs failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="External job search temporarily unavailable. Please try again.",
        )