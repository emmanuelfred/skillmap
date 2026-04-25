import json
import logging
from groq import Groq
from app.core.config import settings
from app.models.schemas import SkillProfile, Opportunity, MatchResult

logger = logging.getLogger("skillmap.match")
client = Groq(api_key=settings.GROQ_API_KEY)


def _keyword_score(talent_skills: list[str], job_skills: list[str]) -> int:
    if not job_skills:
        return 0
    t = [s.lower() for s in talent_skills]
    overlap = sum(1 for js in job_skills if any(js.lower() in ts or ts in js.lower() for ts in t))
    return round((overlap / len(job_skills)) * 100)


class MatchingEngine:
    @staticmethod
    async def match(profile: SkillProfile, opportunities: list[Opportunity]) -> list[MatchResult]:
        if not opportunities:
            return []

        # Step 1: pre-filter top 7 by keyword
        scored = sorted(
            opportunities,
            key=lambda o: _keyword_score(profile.detected_skills, o.required_skills),
            reverse=True
        )[:7]

        if not scored:
            return []

        # Step 2: LLM scoring
        opp_list = json.dumps([{
            "id": o.id, "title": o.title,
            "required_skills": o.required_skills,
            "type": o.type
        } for o in scored])

        prompt = f"""Candidate profile:
- Primary skill: {profile.primary_skill}
- Skills: {', '.join(profile.detected_skills)}
- Level: {profile.experience_level}
- Credibility: {profile.credibility_score}

Opportunities:
{opp_list}

Score each 0-100 and give a 1-sentence explanation.
Return ONLY valid JSON array:
[{{"id": "...", "score": 75, "explanation": "..."}}]"""

        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3,
            )
            text = response.choices[0].message.content.strip()
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            start = text.find("[")
            end = text.rfind("]") + 1
            ratings = json.loads(text[start:end]) if start != -1 else []

            opp_map = {o.id: o for o in scored}
            results = []
            for r in ratings:
                opp = opp_map.get(r.get("id", ""))
                if opp:
                    results.append(MatchResult(
                        opportunity=opp,
                        match_score=max(0, min(100, int(r.get("score", 0)))),
                        explanation=r.get("explanation", "")
                    ))
            return sorted(results, key=lambda x: x.match_score, reverse=True)[:3]

        except Exception as e:
            logger.error(f"Match engine failed: {e}")
            # Fallback: return keyword-scored results
            return [
                MatchResult(
                    opportunity=o,
                    match_score=_keyword_score(profile.detected_skills, o.required_skills),
                    explanation="Based on skill keyword matching"
                )
                for o in scored[:3]
            ]
