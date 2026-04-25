"""
AI-powered talent endpoints:
  POST /api/v1/talent/parse-cv   — parse CV file → auto-fill profile fields
  POST /api/v1/talent/screen     — AI screening score + tailored feedback
"""

import json
import logging
import io
from fastapi import APIRouter, HTTPException, UploadFile, File
from groq import Groq
from app.core.config import settings
from app.models.schemas import CVParseResult, ScreeningRequest, ScreeningResult

logger = logging.getLogger("skillmap.talent_ai")
router = APIRouter(prefix="/talent", tags=["talent-ai"])
client = Groq(api_key=settings.GROQ_API_KEY)


def _safe_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON found")
    return json.loads(text[start:end])


@router.post("/parse-cv", response_model=CVParseResult)
async def parse_cv(file: UploadFile = File(...)):
    """
    Parse a CV/resume (PDF or TXT) and extract structured profile data.
    Frontend sends file, backend uses Groq to parse and extract fields.
    """
    allowed = ("application/pdf", "text/plain", "application/octet-stream")
    if file.content_type not in allowed and not (file.filename or "").endswith((".pdf", ".txt")):
        raise HTTPException(status_code=400, detail="Only PDF or TXT files are supported.")

    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum 5MB.")

    # Extract text from PDF or plain text
    if file.filename and file.filename.lower().endswith(".pdf"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                cv_text = "\n".join(
                    page.extract_text() or "" for page in pdf.pages
                ).strip()
        except ImportError:
            raise HTTPException(status_code=500, detail="PDF parsing not available. Please upload a TXT file.")
        except Exception as e:
            logger.error(f"PDF parse error: {e}")
            raise HTTPException(status_code=422, detail="Could not read PDF. Try a plain text (.txt) file instead.")
    else:
        cv_text = content.decode("utf-8", errors="ignore")

    if len(cv_text.strip()) < 50:
        raise HTTPException(status_code=422, detail="CV appears to be empty or unreadable.")

    cv_text = cv_text[:4000]  # Truncate to avoid token overflow

    prompt = f"""You are an expert HR parser for informal and formal economies in the Global South.

Extract a structured talent profile from this CV/resume. Be practical and concrete.
If something is not in the CV, use null — do NOT invent information.

CV TEXT:
{cv_text}

Return ONLY valid JSON with these exact fields:
{{
  "name": "full name or null",
  "location": "city, country or null",
  "description": "2-3 sentence professional summary of what this person does",
  "primary_skill": "their main skill/specialty or null",
  "extracted_skills": ["list", "of", "specific", "skills", "tools", "technologies"],
  "experience_level": "one of: Beginner, Beginner–Intermediate, Intermediate, Intermediate–Advanced, Advanced",
  "career_goals": "what they want next or null",
  "languages": ["languages they speak"],
  "social_links": [{{"label": "GitHub", "url": "https://..."}}],
  "hourly_rate": "estimated market rate like '$15-25/hr' or null"
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.2,
        )
        data = _safe_json(response.choices[0].message.content)
        return CVParseResult(
            name=data.get("name"),
            location=data.get("location"),
            description=data.get("description", ""),
            primary_skill=data.get("primary_skill"),
            extracted_skills=data.get("extracted_skills", []),
            experience_level=data.get("experience_level"),
            career_goals=data.get("career_goals"),
            languages=data.get("languages", []),
            social_links=data.get("social_links", []),
            hourly_rate=data.get("hourly_rate"),
        )
    except Exception as e:
        logger.error(f"CV parse Groq error: {e}")
        raise HTTPException(status_code=500, detail="AI parsing failed. Please try again or fill in manually.")


@router.post("/screen", response_model=ScreeningResult)
async def screen_profile(body: ScreeningRequest):
    """
    AI-powered profile screening.
    Analyzes the talent's full profile and returns scores + actionable feedback
    TAILORED to their specific specialization.
    """
    if not body.description or len(body.description.strip()) < 20:
        raise HTTPException(status_code=400, detail="Profile description is too short to screen.")

    skills_str = ", ".join(body.extracted_skills) if body.extracted_skills else "not specified"
    proof_str = ", ".join([p.get("label", p.get("url", "")) for p in body.proof_links if p.get("url")]) or "none"
    langs_str = ", ".join(body.languages) if body.languages else "not specified"

    prompt = f"""You are a senior talent recruiter specializing in emerging market talent from the Global South.

Perform a detailed screening of this talent profile. Give SPECIFIC, ACTIONABLE feedback
tailored to someone specializing in {body.primary_skill or 'their field'}.

PROFILE:
- Description: {body.description[:1500]}
- Primary Skill: {body.primary_skill or 'not set'}
- Skills: {skills_str}
- Experience Level: {body.experience_level or 'not set'}
- Career Goals: {body.career_goals or 'not set'}
- Proof of Work / Links: {proof_str}
- Languages: {langs_str}
- Expected Rate: {body.hourly_rate or 'not set'}
- Job Type Preference: {body.job_type or 'not set'}

Score each dimension 0-100. Be honest — weak profiles should score low.
Give SPECIFIC advice for {body.primary_skill or 'their field'}, not generic tips.

Return ONLY valid JSON:
{{
  "overall_score": <int 0-100>,
  "profile_completeness": <int 0-100>,
  "market_readiness": <int 0-100>,
  "skill_clarity": <int 0-100>,
  "summary": "<2-3 sentence honest overall assessment specific to their specialty>",
  "strengths": ["<specific strength 1>", "<specific strength 2>", "<specific strength 3>"],
  "improvements": ["<specific actionable step 1>", "<specific actionable step 2>", "<specific actionable step 3>"],
  "recommended_roles": ["<role 1>", "<role 2>", "<role 3>"],
  "salary_insight": "<realistic market rate for their skill level and location context>"
}}"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200,
            temperature=0.3,
        )
        data = _safe_json(response.choices[0].message.content)
        return ScreeningResult(
            overall_score=min(100, max(0, int(data.get("overall_score", 50)))),
            profile_completeness=min(100, max(0, int(data.get("profile_completeness", 50)))),
            market_readiness=min(100, max(0, int(data.get("market_readiness", 50)))),
            skill_clarity=min(100, max(0, int(data.get("skill_clarity", 50)))),
            summary=data.get("summary", ""),
            strengths=data.get("strengths", []),
            improvements=data.get("improvements", []),
            recommended_roles=data.get("recommended_roles", []),
            salary_insight=data.get("salary_insight", ""),
        )
    except Exception as e:
        logger.error(f"Screening Groq error: {e}")
        raise HTTPException(status_code=500, detail="AI screening failed. Please try again.")
