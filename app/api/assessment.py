"""
AI Skill Assessment endpoints:
  POST /api/v1/assessment/generate  — generate tailored questions for a skill set
  POST /api/v1/assessment/evaluate  — evaluate answers and return score + feedback

Fixes applied vs v1:
  - temperature raised to 0.95 so questions are different every attempt
  - random seed + topic rotation injected into prompt so model can't repeat itself
  - example JSON removed from prompt (was anchoring the model to same questions)
  - short_answer/code now graded by LLM, not keyword matching
  - topic pool shuffled per request so coverage varies each time
"""

import json
import logging
import random
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from groq import Groq
from app.core.config import settings

logger = logging.getLogger("skillmap.assessment")
router = APIRouter(prefix="/assessment", tags=["assessment"])
client = Groq(api_key=settings.GROQ_API_KEY)


# ── Schemas ────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    primary_skill: str
    extracted_skills: list[str] = []
    experience_level: str = "Beginner"
    num_questions: int = 8


class Question(BaseModel):
    id: int
    type: str          # "multiple_choice" | "true_false" | "short_answer" | "code"
    question: str
    options: Optional[list[str]] = None
    correct_answer: Optional[str] = None
    explanation: str
    difficulty: str    # "easy" | "medium" | "hard"
    topic: str


class AssessmentBundle(BaseModel):
    skill: str
    level: str
    questions: list[Question]
    time_limit_minutes: int


class AnswerSubmission(BaseModel):
    question_id: int
    answer: str


class EvaluateRequest(BaseModel):
    primary_skill: str
    experience_level: str
    questions: list[Question]
    answers: list[AnswerSubmission]


class QuestionResult(BaseModel):
    question_id: int
    question: str
    your_answer: str
    correct_answer: str
    is_correct: bool
    explanation: str
    topic: str


class AssessmentResult(BaseModel):
    overall_score: int
    grade: str
    badge: str
    total_questions: int
    correct_answers: int
    time_taken_seconds: Optional[int] = None
    skill_breakdown: list[dict]
    results: list[QuestionResult]
    strengths: list[str]
    weak_areas: list[str]
    recommendation: str


# ── Topic pools per domain ─────────────────────────────────────────────────
# Injected into the prompt so the model covers different angles each attempt.

TOPIC_POOLS: dict[str, list[str]] = {
    "react": ["hooks", "component lifecycle", "state management", "context API", "performance optimisation",
               "React Router", "error boundaries", "custom hooks", "reconciliation", "refs & forwarding refs",
               "code splitting", "suspense", "testing with React Testing Library", "server components"],
    "python": ["list comprehensions", "decorators", "generators", "async/await", "OOP & dunder methods",
               "error handling", "type hints", "standard library", "virtual environments", "memory management",
               "functional programming", "file I/O", "data structures", "testing with pytest"],
    "javascript": ["closures", "event loop", "promises & async/await", "prototypal inheritance", "ES6+ syntax",
                   "DOM manipulation", "fetch API", "modules", "error handling", "scope & hoisting",
                   "destructuring", "iterators & generators", "WeakMap/WeakSet", "Web APIs"],
    "node": ["event loop", "streams", "buffers", "child processes", "clustering", "Express middleware",
             "error handling", "environment variables", "npm ecosystem", "authentication", "REST vs GraphQL",
             "testing with Jest", "file system", "TCP/HTTP internals"],
    "data": ["data cleaning", "pandas", "NumPy", "visualisation", "SQL queries", "statistical concepts",
             "feature engineering", "model evaluation", "overfitting", "cross-validation",
             "time series", "aggregation", "joins", "outlier detection"],
    "design": ["typography", "colour theory", "layout & grids", "Figma components", "user research",
               "usability testing", "accessibility", "design systems", "prototyping", "wireframing",
               "interaction design", "information architecture", "design handoff", "responsive design"],
    "marketing": ["SEO", "paid ads", "email marketing", "content strategy", "analytics",
                  "A/B testing", "social media", "conversion rate optimisation", "copywriting",
                  "brand strategy", "influencer marketing", "marketing funnels", "customer segmentation"],
}

def _get_topic_pool(skill: str) -> list[str]:
    """Return a shuffled topic pool for the skill, falling back to a generic set."""
    skill_lower = skill.lower()
    for key, pool in TOPIC_POOLS.items():
        if key in skill_lower:
            shuffled = pool[:]
            random.shuffle(shuffled)
            return shuffled
    # Generic fallback topics
    generic = [
        "core concepts", "best practices", "common pitfalls", "tooling & environment",
        "debugging techniques", "performance", "security considerations", "testing",
        "real-world application", "edge cases", "collaboration & code review",
        "documentation", "version control", "deployment",
    ]
    random.shuffle(generic)
    return generic


# ── Helpers ────────────────────────────────────────────────────────────────

def _safe_json_list(text: str) -> list:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    start = text.find("[")
    end = text.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON array found")
    return json.loads(text[start:end])


def _safe_json_obj(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found")
    return json.loads(text[start:end])


def _grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 75: return "B"
    if score >= 60: return "C"
    if score >= 45: return "D"
    return "F"


def _badge(skill: str, level: str, score: int) -> str:
    if score >= 85:
        return f"✅ Verified {level} {skill} Developer"
    if score >= 65:
        return f"📋 {level} {skill} — Assessed"
    return f"📚 {skill} — Keep Practising"


# ── Question type distribution ─────────────────────────────────────────────

def _build_type_distribution(n: int, is_technical: bool) -> list[str]:
    """
    Return a shuffled list of question types for n questions.
    Technical skills get more code questions; non-technical get more scenario-based.
    """
    if is_technical:
        pool = (
            ["multiple_choice"] * 3 +
            ["true_false"] * 2 +
            ["code"] * 2 +
            ["short_answer"] * 1
        )
    else:
        pool = (
            ["multiple_choice"] * 3 +
            ["true_false"] * 2 +
            ["short_answer"] * 3
        )
    # Cycle the pool to fill n slots, then shuffle
    types = (pool * ((n // len(pool)) + 1))[:n]
    random.shuffle(types)
    return types


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/generate", response_model=AssessmentBundle)
async def generate_assessment(body: GenerateRequest):
    """
    Generate a fully randomised, AI-powered skill assessment.
    Every call produces different questions by:
      1. Using temperature=0.95 (high creativity)
      2. Injecting a unique session seed into the prompt
      3. Rotating which sub-topics are covered each attempt
      4. Not including example questions in the prompt (avoids anchoring)
    """
    if not body.primary_skill:
        raise HTTPException(status_code=400, detail="Primary skill is required.")

    skills_str = ", ".join(body.extracted_skills[:8]) if body.extracted_skills else body.primary_skill
    n = min(max(body.num_questions, 5), 12)

    is_technical = any(k in body.primary_skill.lower() for k in [
        "develop", "data", "analytic", "mobile", "backend", "frontend",
        "engineer", "code", "program", "software", "python", "react",
        "node", "java", "sql", "cloud", "devops", "ml", "ai",
    ])

    # Pick n topics from the shuffled pool — different every call
    topic_pool = _get_topic_pool(body.primary_skill)
    selected_topics = topic_pool[:n]

    # Build question type list — shuffled each time
    type_distribution = _build_type_distribution(n, is_technical)

    # Unique session seed — forces the LLM to treat this as a fresh request
    session_seed = str(uuid.uuid4())[:8]

    # Map types to instructions
    type_instructions = {
        "multiple_choice": 'type "multiple_choice", options array with exactly 4 items formatted as ["A. text", "B. text", "C. text", "D. text"], correct_answer is the single letter e.g. "B"',
        "true_false":      'type "true_false", options array ["True", "False"], correct_answer is "True" or "False"',
        "short_answer":    'type "short_answer", options is null, correct_answer is a concise ideal 1-2 sentence answer',
        "code":            'type "code", options is null, question includes a realistic code snippet inside triple backticks, correct_answer explains what it does or what the bug is in 1-2 sentences',
    }

    question_specs = "\n".join(
        f"  Question {i+1}: topic=\"{selected_topics[i]}\", {type_instructions[type_distribution[i]]}"
        for i in range(n)
    )

    prompt = f"""You are an expert technical assessor. Session: {session_seed}

Generate {n} UNIQUE, VARIED assessment questions for a {body.experience_level}-level {body.primary_skill} practitioner.
Their known tools and skills: {skills_str}

You MUST follow this exact specification — one question per line:
{question_specs}

Additional rules:
- Every question must be genuinely different — no repetition of concepts across questions
- Questions must test PRACTICAL, real-world knowledge — not just definitions
- Calibrate difficulty precisely for {body.experience_level} level
- For code questions: write a real, non-trivial snippet (10-20 lines) in the appropriate language
- Explanations must be informative and teach something, not just restate the answer
- Do NOT copy or paraphrase questions from any previous assessment

Return ONLY a valid JSON array with {n} objects. Each object must have ALL of these fields:
  id (integer starting at 1), type, question, options, correct_answer, explanation, difficulty ("easy"|"medium"|"hard"), topic

Return ONLY the JSON array. No preamble, no markdown, no explanation outside the JSON."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4000,
            temperature=0.95,   # High — ensures different questions every time
            top_p=0.9,
        )
        raw = response.choices[0].message.content
        logger.info(f"Assessment generation raw length: {len(raw)} chars")
        questions_data = _safe_json_list(raw)

        questions = []
        for i, q in enumerate(questions_data[:n]):
            questions.append(Question(
                id=q.get("id", i + 1),
                type=q.get("type", "multiple_choice"),
                question=q.get("question", ""),
                options=q.get("options"),
                correct_answer=q.get("correct_answer", ""),
                explanation=q.get("explanation", ""),
                difficulty=q.get("difficulty", "medium"),
                topic=q.get("topic", selected_topics[i] if i < len(selected_topics) else body.primary_skill),
            ))

        if len(questions) < 3:
            raise ValueError(f"Model returned too few questions: {len(questions)}")

        time_limit = len(questions) * 3  # 3 minutes per question
        return AssessmentBundle(
            skill=body.primary_skill,
            level=body.experience_level,
            questions=questions,
            time_limit_minutes=time_limit,
        )

    except Exception as e:
        logger.error(f"Assessment generation failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate assessment. Please try again.")


@router.post("/evaluate", response_model=AssessmentResult)
async def evaluate_assessment(body: EvaluateRequest):
    """
    Evaluate submitted answers.
    - multiple_choice / true_false: deterministic letter matching
    - short_answer / code: LLM-based semantic evaluation (replaces broken keyword matching)
    """
    if not body.questions or not body.answers:
        raise HTTPException(status_code=400, detail="Questions and answers are required.")

    answer_map = {a.question_id: a.answer for a in body.answers}

    # ── Collect open-ended questions for batch LLM grading ────────────────
    open_ended: list[tuple[Question, str]] = []
    for q in body.questions:
        if q.type in ("short_answer", "code"):
            user_ans = answer_map.get(q.id, "").strip()
            open_ended.append((q, user_ans))

    # Grade all open-ended questions in a single LLM call (cheaper & faster)
    llm_grades: dict[int, bool] = {}
    if open_ended:
        grade_items = [
            {
                "id": q.id,
                "question": q.question[:300],
                "correct_answer": q.correct_answer or "",
                "user_answer": ans,
            }
            for q, ans in open_ended
        ]
        grade_prompt = f"""You are a strict but fair technical assessor grading open-ended answers.

For each item, decide if the user's answer is essentially correct — it doesn't need to be word-perfect,
but it must demonstrate genuine understanding of the concept.

Grade these answers for a {body.experience_level} {body.primary_skill} assessment:

{json.dumps(grade_items, indent=2)}

Return ONLY a JSON array — one object per question, in the same order:
[{{"id": <int>, "is_correct": <true|false>, "reason": "<one sentence why>"}}]

Be strict: vague or off-topic answers are incorrect. Partial credit is not possible."""

        try:
            grade_response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": grade_prompt}],
                max_tokens=800,
                temperature=0.1,  # Low — deterministic grading
            )
            grade_data = _safe_json_list(grade_response.choices[0].message.content)
            for item in grade_data:
                qid = item.get("id")
                if qid is not None:
                    llm_grades[qid] = bool(item.get("is_correct", False))
        except Exception as e:
            logger.warning(f"LLM grading failed, falling back to keyword match: {e}")
            # Fallback: keyword overlap
            for q, user_ans in open_ended:
                correct_lower = (q.correct_answer or "").lower()
                user_lower = user_ans.lower()
                keywords = [w for w in correct_lower.split() if len(w) > 4]
                matches = sum(1 for w in keywords if w in user_lower)
                llm_grades[q.id] = matches >= max(1, len(keywords) * 0.4) if keywords else False

    # ── Score all questions ────────────────────────────────────────────────
    results = []
    topic_scores: dict[str, list[bool]] = {}
    correct_count = 0

    for q in body.questions:
        user_answer = answer_map.get(q.id, "").strip()
        correct = q.correct_answer or ""

        if q.type in ("multiple_choice", "true_false"):
            user_letter = user_answer[0].upper() if user_answer else ""
            correct_letter = correct[0].upper() if correct else ""
            is_correct = user_letter == correct_letter
        else:
            is_correct = llm_grades.get(q.id, False)

        if is_correct:
            correct_count += 1

        topic = q.topic or body.primary_skill
        topic_scores.setdefault(topic, []).append(is_correct)

        results.append(QuestionResult(
            question_id=q.id,
            question=q.question,
            your_answer=user_answer or "(no answer)",
            correct_answer=correct,
            is_correct=is_correct,
            explanation=q.explanation,
            topic=topic,
        ))

    total = len(body.questions)
    score = round((correct_count / total) * 100) if total > 0 else 0

    skill_breakdown = [
        {
            "topic": topic,
            "correct": sum(1 for x in scores if x),
            "total": len(scores),
            "score": round(sum(1 for x in scores if x) / len(scores) * 100),
        }
        for topic, scores in topic_scores.items()
    ]

    strengths = [b["topic"] for b in skill_breakdown if b["score"] >= 70]
    weak_areas = [b["topic"] for b in skill_breakdown if b["score"] < 50]

    if score >= 85:
        rec = f"Excellent! Your {body.primary_skill} skills are strong. Consider applying for senior roles or contributing to open-source projects."
    elif score >= 65:
        rec = f"Good foundation in {body.primary_skill}. Focus on: {', '.join(weak_areas[:2]) or 'advanced topics'} to level up."
    elif score >= 45:
        rec = f"You're on the right track with {body.primary_skill}. Review the weak areas and practise with real projects."
    else:
        rec = f"Keep building your {body.primary_skill} skills. Start with the fundamentals and work through practical tutorials."

    return AssessmentResult(
        overall_score=score,
        grade=_grade(score),
        badge=_badge(body.primary_skill, body.experience_level, score),
        total_questions=total,
        correct_answers=correct_count,
        skill_breakdown=skill_breakdown,
        results=results,
        strengths=strengths,
        weak_areas=weak_areas,
        recommendation=rec,
    )