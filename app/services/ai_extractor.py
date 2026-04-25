import json
import logging
import re
from groq import Groq
from app.core.config import settings
from app.models.schemas import SkillProfile

logger = logging.getLogger("skillmap.ai")
client = Groq(api_key=settings.GROQ_API_KEY)

DEFAULT_PROFILE = SkillProfile(
    primary_skill="General Skills",
    detected_skills=[],
    experience_level="Beginner",
    suggested_roles=["Entry-level position", "Apprenticeship"],
    credibility_score=40,
)


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
        raise ValueError("No JSON in response")
    return json.loads(text[start:end])


class AIExtractorService:
    @staticmethod
    async def extract(description: str) -> SkillProfile:
        desc = description[:500]  # Token safety

        prompt = f"""You are an expert HR parser for informal economies in the Global South.
Read this person's description and extract their talent profile.

Primary skill MUST be one of: Frontend Development, Backend Development, Mobile Development,
UI/UX Design, Graphic Design, Video Editing, Digital Marketing, Content Creation,
Data & Analytics, Phone Repair, Tailoring, Photography, General Skills.

Experience level MUST be one of: Beginner, Beginner–Intermediate, Intermediate,
Intermediate–Advanced, Advanced.

Description: {desc}

Return ONLY valid JSON:
{{
  "primary_skill": "...",
  "detected_skills": ["skill1", "skill2"],
  "experience_level": "...",
  "suggested_roles": ["role1", "role2"],
  "credibility_score": 50
}}"""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.2,
            )
            data = _safe_json(response.choices[0].message.content)
            return SkillProfile(
                primary_skill=data.get("primary_skill", "General Skills"),
                detected_skills=data.get("detected_skills", []),
                experience_level=data.get("experience_level", "Beginner"),
                suggested_roles=data.get("suggested_roles", []),
                credibility_score=max(30, min(95, int(data.get("credibility_score", 50)))),
            )
        except Exception as e:
            logger.error(f"AI extraction failed: {e}")
            return DEFAULT_PROFILE
