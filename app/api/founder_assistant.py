"""
founder_assistant.py
─────────────────────────────────────────────────────────────
POST /api/v1/founder/analyze
  Takes founder's startup info (stage, industry, budget, goals)
  and returns:
    - Best tools stack by category (with cost)
    - Team structure (roles needed, hiring order)
    - Staff recommendations matched from SkillMap talent DB
    - Budget breakdown
    - Phased action plan
"""

import json
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from groq import Groq
from app.core.config import settings
from app.services.supabase_client import get_db

logger = logging.getLogger("skillmap.founder")
router = APIRouter(prefix="/founder", tags=["founder-assistant"])
client = Groq(api_key=settings.GROQ_API_KEY)


# ── Schemas ────────────────────────────────────────────────────────────────

class FounderInput(BaseModel):
    company_name: str
    industry: str
    stage: str           # "idea" | "mvp" | "early-revenue" | "scaling"
    description: str     # What the company does
    goal: str            # Primary goal right now
    budget_usd: int      # Monthly budget in USD
    team_size: int       # Current team size (including founders)
    location: str = ""   # Company location / market


class ToolRecommendation(BaseModel):
    name: str
    category: str
    purpose: str
    monthly_cost_usd: float
    free_tier: bool
    priority: str        # "essential" | "recommended" | "optional"
    url: str


class RoleRecommendation(BaseModel):
    title: str
    why_needed: str
    hire_order: int      # 1 = hire first
    budget_range_usd: str
    skills_needed: list[str]
    full_time_or_freelance: str


class TalentMatch(BaseModel):
    user_id: str
    name: str
    primary_skill: str
    experience_level: str
    credibility_score: int
    location: str
    skills: list[str]
    fit_reason: str
    role_suggestion: str


class FounderAnalysis(BaseModel):
    summary: str
    budget_breakdown: list[dict]
    total_tool_cost: float
    remaining_for_talent: float
    tools: list[ToolRecommendation]
    roles: list[RoleRecommendation]
    talent_matches: list[TalentMatch]
    action_plan: list[dict]   # [{phase, timeline, actions[]}]
    warnings: list[str]


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_json(text: str, fallback=None):
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > 0:
            return json.loads(text[start:end])
    except Exception:
        pass
    return fallback


def _fetch_available_talent() -> list[dict]:
    """Fetch available talents from Supabase."""
    try:
        db = get_db()
        result = db.table("talents").select(
            "user_id, primary_skill, extracted_skills, experience_level, credibility_score"
        ).eq("available", True).limit(50).execute()

        talents = result.data or []

        # Get profiles for names and locations
        if talents:
            ids = [t["user_id"] for t in talents]
            profiles = db.table("profiles").select(
                "id, name, location"
            ).in_("id", ids).execute()

            profile_map = {p["id"]: p for p in (profiles.data or [])}
            for t in talents:
                p = profile_map.get(t["user_id"], {})
                t["name"] = p.get("name", "Unknown")
                t["location"] = p.get("location", "Remote")

        return talents
    except Exception as e:
        logger.error(f"Could not fetch talent: {e}")
        return []


# ── Main endpoint ──────────────────────────────────────────────────────────

@router.post("/analyze", response_model=FounderAnalysis)
async def analyze_startup(body: FounderInput):
    """
    Full AI-powered startup setup analysis.
    Returns tools, team roles, talent matches, and action plan.
    """
    if not body.description or len(body.description) < 10:
        raise HTTPException(status_code=400, detail="Please describe your company.")

    talents = _fetch_available_talent()
    talent_summary = json.dumps([
        {
            "user_id": t["user_id"],
            "name": t.get("name", ""),
            "primary_skill": t.get("primary_skill", ""),
            "skills": (t.get("extracted_skills") or [])[:6],
            "level": t.get("experience_level", ""),
            "credibility": t.get("credibility_score", 0),
            "location": t.get("location", "Remote"),
        }
        for t in talents[:30]
    ], indent=2)

    prompt = f"""You are an elite startup advisor and fractional CTO helping founders in the Global South.

STARTUP PROFILE:
- Company: {body.company_name}
- Industry: {body.industry}
- Stage: {body.stage}
- What they do: {body.description}
- Primary goal: {body.goal}
- Monthly budget: ${body.budget_usd}
- Current team size: {body.team_size}
- Location/Market: {body.location or "Africa/Global South"}

AVAILABLE TALENT ON SKILLMAP (match these to roles):
{talent_summary}

Provide a COMPREHENSIVE startup setup analysis. Be SPECIFIC to their industry and budget.
Do NOT recommend tools they cannot afford. Be realistic about what ${{body.budget_usd}}/month can achieve.

Return ONLY valid JSON:
{{
  "summary": "2-3 sentence honest assessment of their situation and biggest opportunity",

  "budget_breakdown": [
    {{"category": "Tools & Software", "allocated_usd": 150, "percentage": 15}},
    {{"category": "Talent/Freelancers", "allocated_usd": 700, "percentage": 70}},
    {{"category": "Marketing", "allocated_usd": 100, "percentage": 10}},
    {{"category": "Contingency", "allocated_usd": 50, "percentage": 5}}
  ],

  "total_tool_cost": 150.0,
  "remaining_for_talent": 700.0,

  "tools": [
    {{
      "name": "Notion",
      "category": "Project Management",
      "purpose": "Team wiki, roadmap, meeting notes",
      "monthly_cost_usd": 0,
      "free_tier": true,
      "priority": "essential",
      "url": "https://notion.so"
    }}
  ],

  "roles": [
    {{
      "title": "Full Stack Developer",
      "why_needed": "To build and maintain the core product",
      "hire_order": 1,
      "budget_range_usd": "$300-500/month freelance",
      "skills_needed": ["React", "Node.js", "PostgreSQL"],
      "full_time_or_freelance": "freelance"
    }}
  ],

  "talent_matches": [
    {{
      "user_id": "uuid-from-talent-list",
      "name": "Name from talent list",
      "primary_skill": "their primary skill",
      "experience_level": "their level",
      "credibility_score": 75,
      "location": "their location",
      "skills": ["skill1", "skill2"],
      "fit_reason": "Why this specific person fits this startup",
      "role_suggestion": "Which role they should fill"
    }}
  ],

  "action_plan": [
    {{
      "phase": "Week 1-2",
      "timeline": "Immediate",
      "actions": [
        "Set up Notion workspace for team documentation",
        "Post job on SkillMap for key hire"
      ]
    }},
    {{
      "phase": "Month 1",
      "timeline": "Short-term",
      "actions": [
        "Onboard first freelancer",
        "Launch MVP to first 10 users"
      ]
    }}
  ],

  "warnings": [
    "Your budget is tight for {body.industry} — prioritise revenue-generating features first",
    "Avoid hiring full-time staff until you have 3 months of runway"
  ]
}}

RULES:
- Only recommend tools that fit within the budget allocation
- Match talent from the provided list — use their actual user_id, name, skills
- Only match talent whose skills align with the roles needed
- Be specific to {body.industry} and {body.stage} stage
- Give 3-6 tools, 2-4 roles, 3-5 talent matches, 3-4 action phases
- warnings should be honest and specific to their situation"""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=3000,
            temperature=0.3,
        )
        data = _safe_json(response.choices[0].message.content)
        if not data:
            raise ValueError("Invalid JSON from AI")

        # Build tool list
        tools = [
            ToolRecommendation(**t) for t in data.get("tools", [])
            if all(k in t for k in ["name", "category", "purpose", "monthly_cost_usd", "free_tier", "priority", "url"])
        ]

        # Build role list
        roles = [
            RoleRecommendation(**r) for r in data.get("roles", [])
            if all(k in r for k in ["title", "why_needed", "hire_order", "budget_range_usd", "skills_needed", "full_time_or_freelance"])
        ]

        # ── Python-side talent matching (AI hallucinated UUIDs don't work) ──
        # Get role skills from AI analysis
        role_skills_needed = []
        for r in data.get("roles", []):
            role_skills_needed.extend(r.get("skills_needed", []))
        # Also use founder's own description keywords
        all_needed = set(s.lower() for s in role_skills_needed)

        # Score each talent by skill overlap with needed roles
        scored_talents = []
        for t in talents:
            t_skills = set(s.lower() for s in (t.get("extracted_skills") or []))
            t_primary = (t.get("primary_skill") or "").lower()
            # Overlap score
            overlap = len(all_needed & t_skills)
            # Bonus if primary skill is in needed skills
            primary_bonus = 2 if any(t_primary in need or need in t_primary for need in all_needed) else 0
            score = overlap + primary_bonus
            if score > 0 or not all_needed:  # include all if no skills filter
                scored_talents.append((score, t))

        # Sort by score desc, then credibility
        scored_talents.sort(key=lambda x: (x[0], x[1].get("credibility_score", 0)), reverse=True)
        top_talents = [t for _, t in scored_talents[:5]]

        # Ask AI to write fit_reason for each matched talent
        talent_matches = []
        if top_talents:
            match_prompt = f"""For each candidate below, write a SHORT fit_reason (1 sentence max) explaining why they fit 
this {body.industry} startup at {body.stage} stage, and suggest which role they should fill.

Roles needed: {[r.get("title") for r in data.get("roles", [])]}
Startup goal: {body.goal}

Candidates:
{json.dumps([{"name": t.get("name"), "primary_skill": t.get("primary_skill"), "skills": (t.get("extracted_skills") or [])[:5], "level": t.get("experience_level")} for t in top_talents], indent=2)}

Return ONLY valid JSON array:
[{{"name": "...", "fit_reason": "...", "role_suggestion": "..."}}]"""
            
            try:
                mr = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": match_prompt}],
                    max_tokens=600, temperature=0.2,
                )
                mraw = mr.choices[0].message.content.strip()
                if mraw.startswith("```"):
                    mraw = mraw.split("```")[1]
                    if mraw.startswith("json"): mraw = mraw[4:]
                ms = json.loads(mraw[mraw.find("["):mraw.rfind("]")+1])
                match_map = {m.get("name","").lower(): m for m in ms}
            except Exception as e:
                logger.warning(f"Match reason generation failed: {e}")
                match_map = {}

            for t in top_talents:
                t_name = t.get("name", "")
                m_data = match_map.get(t_name.lower(), {})
                talent_matches.append(TalentMatch(
                    user_id=t["user_id"],
                    name=t_name,
                    primary_skill=t.get("primary_skill", ""),
                    experience_level=t.get("experience_level", ""),
                    credibility_score=t.get("credibility_score", 0),
                    location=t.get("location", "Remote"),
                    skills=(t.get("extracted_skills") or [])[:6],
                    fit_reason=m_data.get("fit_reason", f"Strong {t.get('primary_skill','')} skills match your needs"),
                    role_suggestion=m_data.get("role_suggestion", data.get("roles", [{}])[0].get("title", "Key role") if data.get("roles") else "Key role"),
                ))

        return FounderAnalysis(
            summary=data.get("summary", ""),
            budget_breakdown=data.get("budget_breakdown", []),
            total_tool_cost=float(data.get("total_tool_cost", 0)),
            remaining_for_talent=float(data.get("remaining_for_talent", 0)),
            tools=tools,
            roles=roles,
            talent_matches=talent_matches,
            action_plan=data.get("action_plan", []),
            warnings=data.get("warnings", []),
        )

    except Exception as e:
        logger.error(f"Founder analysis failed: {e}")
        raise HTTPException(status_code=500, detail="AI analysis failed. Please try again.")