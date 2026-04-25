# SkillMap Backend Technical Plan

## 1. Architecture Overview
While the MVP frontend is Streamlit, extracting the AI logic into a separate FastAPI backend enables better separation of concerns, scalability, and an easier transition to future roadmaps (e.g., mobile apps, Next.js frontend, real databases).

- **Framework**: FastAPI (high performance, built-in Swagger UI for easy testing).
- **Validation**: Pydantic v2 (robust data modeling and typed AI outputs).
- **Intelligence Layer**: Grok API via the official `xai` package or `openai` standard client. We will use system prompts with strict JSON formatting instructions to ensure structured outputs from Grok.
- **Data Storage**: Supabase (PostgreSQL) for scalable database storage. We will use the `supabase` Python client to query opportunities and store generated profiles.
  - **`opportunities` table schema**: `id` (uuid), `type` (text), `title` (text), `required_skills` (text[]), `location` (text), `description` (text), `created_at` (timestamp).

## 2. File Structure
```text
skillmap_backend/
├── main.py                     # FastAPI app bootstrap and routing
├── requirements.txt            # Python dependencies
├── .env                        # Environment variables (GROK_API_KEY, SUPABASE_URL, SUPABASE_KEY)
├── app/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── endpoints.py        # API Routes (e.g., /process-talent)
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py           # Settings and env var management
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py          # Pydantic models (Input, Profile, Opportunity, Match)
│   ├── services/
│   │   ├── __init__.py
│   │   ├── ai_extractor.py     # AI logic for unstructured text -> structured profile
│   │   ├── match_engine.py     # Logic for grading profile against opportunities
│   │   ├── supabase_client.py  # Supabase connection and database queries
```

## 3. Data Models (Pydantic / `app/models/schemas.py`)
These models define the contract between the Streamlit frontend, the AI layer, and the backend engine.

```python
from pydantic import BaseModel, Field
from typing import List, Optional

# --- Request Models ---
class UserInputPayload(BaseModel):
    description: str = Field(..., description="Free-text skill description")
    location: Optional[str] = None
    proof_link: Optional[str] = None

# --- Core Domain Models ---
class SkillProfile(BaseModel):
    primary_skill: str
    detected_skills: List[str]
    experience_level: str = Field(description="Beginner, Intermediate, Expert")
    suggested_roles: List[str]
    credibility_score: int = Field(ge=0, le=100, description="AI confidence score")

class Opportunity(BaseModel):
    id: str
    type: str  # job, gig, training
    title: str
    required_skills: List[str]
    location: Optional[str]
    description: str

# --- Response Models ---
class MatchResult(BaseModel):
    opportunity: Opportunity
    match_score: int  # 0 to 100
    explanation: str  # Short AI explanation of why it's a match

class ProcessingResponse(BaseModel):
    profile: SkillProfile
    matches: List[MatchResult]
```

## 4. API Endpoints (`app/api/endpoints.py`)

For the MVP, we only need a single orchestration endpoint to minimize frontend-backend chatter, plus an optional helper endpoint.
**Crucial Component – Async Handling**: FastAPI + External APIs + DB means async matters. Use `async def` endpoints and async calls for Grok (via `httpx` or async wrappers) and Supabase to ensure your app stays fast under load.

### `POST /api/v1/process-talent`
- **Purpose**: Consumes the raw text description, runs extraction, runs matching against the static dataset, and returns everything to the Streamlit UI in one go.
- **Security & Abuse Protection**: Add basic rate limiting per IP (e.g., 10 req/min using `slowapi`) to prevent Grok cost abuse and scraping.
- **Input**: `UserInputPayload`
- **Output**: `ProcessingResponse`
- **Data Flow**:
  1. Await `AIExtractorService.extract(payload.description)`
  2. Fetch opportunities from Supabase using your async client. **Important**: Always apply `LIMIT 20` and simple filtering (e.g., skill tags or location) natively via SQL/Supabase to avoid dumping an entire table into memory.
  3. Await `MatchingEngine.match(extracted_profile, opportunities)` executing the hybrid logic.
  4. **System-wide Fallback**: Catch overarching exceptions. If BOTH extraction and matching fail, do NOT crash. Return an empty matches array with a clean UI message: *"System temporarily unavailable, try again."*
  5. Return the combined dictionary to the user (and optionally log the profile to Supabase).

### `GET /api/v1/opportunities` (Optional)
- **Purpose**: Simply returns the list of opportunities from Supabase so the UI can display stats or allow the user to browse them manually.

## 5. Core Services Implementation

### A. The AI Skill Extraction Engine (`app/services/ai_extractor.py`)
Use the Grok API with structured output prompting. Extract the output using strict JSON instructions to map to your `SkillProfile` model.
- **System Prompt Formulation**: *"You are an expert HR parser for informal economies. Read the user's raw input and extract their primary skill, a list of specific hard/soft skills, an estimated experience level based on context, and recommend realistic job roles for them. Output valid JSON only."*
- **Robust Parsing & Fallback (Critical)**: Because LLMs like Grok are not 100% strict, your Python code must wrap the API call aggressively:
  1. **API Safety**: Set an explicit timeout (5-10 seconds max) and allow 1 retry on connection or parsing failure.
  2. Attempt direct JSON parsing.
  3. If parsing fails, extract the JSON substring using non-greedy Regex (e.g. `\{.*?\}`) or locate the first `{` and last `}` safely.
  4. Retry parsing.
  5. If it still fails, return a safe, default `SkillProfile` to prevent random backend crashes.
- **Cost Control & Caching (Optimization)**:
  - **Token Safety**: Prevent oversized payloads from hitting the LLM by explicitly limiting max input tokens and truncating long descriptions (e.g., max 500 chars) *before* sending to the API.
  - **Caching Layer**: To drastically reduce costs, implement an optional cache. Store `hash(description) -> SkillProfile` in memory or Supabase. Check this cache before firing the API request.

### B. The Opportunity Matching Engine (`app/services/match_engine.py`)
Sending ALL opportunities to an LLM every request is slow, highly expensive, and inconsistent. Instead, implement a **Hybrid Matching Logic**:
- **Step 1 - Pre-filter (Local/Fast)**: Use simple keyword overlap or text scoring to filter the 20 DB opportunities down to the **top 5-7** most relevant ones.
- **Step 2 - LLM Scoring (Smart)**: Send ONLY those 5-7 opportunities to Grok to deeply evaluate the nuance and write explanations.
- **System Prompt**: *"Here is a candidate profile and an array of open opportunities. Evaluate each opportunity and score from 0-100 on how well it fits candidate profile. Provide a 1-sentence explanation. Output valid JSON only."*
- Sort the response by `match_score` and return the final top 3 recommendations.

### C. Observability (Logging and Tracking)
Without logs, you cannot debug production issues effectively. Explicitly implement structured logging for:
- **Request Tracing**: Generate a `request_id` (e.g., UUID) at the start of every API call. Pass this ID explicitly through the extractor, matcher, and all logging events so you can trace the exact pipeline flow when debugging failures.
- Incoming API requests and payload sizes.
- Grok API latency and status codes.
- Parsing failures and occurrences of fallback profile returns.
- Final matching scores generated by the hybrid engine.

## 6. Step-by-Step Execution Plan

1. **Requirements Setup**: `pip install fastapi 'uvicorn[standard]' pydantic httpx openai supabase python-dotenv`.
2. **Database Setup**: Set up Supabase, create an `opportunities` table, and seed it with 10-15 highly varied items.
3. **Data Model Definition**: Translate the PRD requirements into the Pydantic models.
4. **Build the Extractor**: Implement `ai_extractor.py` using async Grok calls and the robust Regex parsing fallback.
5. **Build the Matcher**: Implement `match_engine.py` using the Hybrid Approach (local keyword filter + async LLM scoring).
6. **API Orchestration**: Combine these steps into the async `POST /process-talent` endpoint.
7. **End-to-End Testing**: Launch with `uvicorn main:app --reload`. Navigate to `http://localhost:8000/docs` (the auto-generated Swagger UI). Click "Try it out" and submit *"I repair smartphones and replace screens"*, and verify you receive structured profile data alongside suggested opportunities.
