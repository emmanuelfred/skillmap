import logging
import uuid
from fastapi import APIRouter, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.models.schemas import UserInputPayload, ProcessingResponse, Opportunity
from app.services.ai_extractor import AIExtractorService
from app.services.match_engine import MatchingEngine
from app.services.supabase_client import get_db

logger = logging.getLogger("skillmap.endpoints")
limiter = Limiter(key_func=get_remote_address)
router = APIRouter()


def _fetch_opportunities() -> list[Opportunity]:
    try:
        db = get_db()
        result = db.table("opportunities").select("*").limit(20).execute()
        opps = []
        for row in (result.data or []):
            opps.append(Opportunity(
                id=str(row.get("id", uuid.uuid4())),
                type=row.get("type", "Job"),
                title=row.get("title", ""),
                required_skills=row.get("required_skills", []),
                location=row.get("location"),
                description=row.get("description", ""),
            ))
        return opps
    except Exception as e:
        logger.warning(f"Could not fetch opportunities from DB: {e}")
        return _fallback_opportunities()


def _fallback_opportunities() -> list[Opportunity]:
    """Static fallback opportunities if DB is unavailable."""
    return [
        Opportunity(id="f1", type="Job", title="Junior Frontend Developer", required_skills=["React", "HTML", "CSS", "JavaScript"], location="Remote", description="Build UIs for a Lagos-based fintech startup."),
        Opportunity(id="f2", type="Gig", title="Freelance Video Editor", required_skills=["Premiere Pro", "Color Grading", "Storytelling"], location="Remote", description="Edit short-form content for social media brands."),
        Opportunity(id="f3", type="Training", title="Data Analytics Bootcamp", required_skills=["Excel", "SQL", "Problem Solving"], location="Online", description="8-week intensive — scholarship available for Global South applicants."),
        Opportunity(id="f4", type="Job", title="Social Media Manager", required_skills=["Instagram", "TikTok", "Content Strategy", "Copywriting"], location="Remote", description="Manage social channels for a pan-African e-commerce brand."),
        Opportunity(id="f5", type="Mentorship", title="Tech Mentorship Program", required_skills=["Curiosity", "Communication"], location="Online", description="1:1 mentorship with senior engineers from Google and Meta."),
        Opportunity(id="f6", type="Apprenticeship", title="Mobile App Apprentice", required_skills=["Flutter", "Dart", "Mobile Development"], location="Accra, Ghana", description="6-month paid apprenticeship at a Ghanaian startup."),
    ]


@router.get("/opportunities")
async def get_opportunities():
    return _fetch_opportunities()


@router.post("/process-talent", response_model=ProcessingResponse)
@limiter.limit("10/minute")
async def process_talent(request: Request, payload: UserInputPayload):
    """
    Main endpoint: extract skills from description + match to opportunities.
    Called by the frontend TalentEdit page.
    """
    if not payload.description or len(payload.description.strip()) < 10:
        raise HTTPException(status_code=400, detail="Description is too short.")

    try:
        profile = await AIExtractorService.extract(payload.description)
        opportunities = _fetch_opportunities()
        matches = await MatchingEngine.match(profile, opportunities)
        return ProcessingResponse(profile=profile, matches=matches)
    except Exception as e:
        logger.error(f"process-talent failed: {e}")
        raise HTTPException(status_code=500, detail="Processing temporarily unavailable. Please try again.")
