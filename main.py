import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from app.api.endpoints import router as main_router
from app.api.talent_ai import router as talent_router
from app.api.assessment import router as assessment_router
from app.api.external_jobs_endpoint import router as external_jobs_router  # ← NEW

from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("skillmap")

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="SkillMap Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter
app.add_exception_handler(429, _rate_limit_exceeded_handler)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"{request.method} {request.url.path}")
    response = await call_next(request)
    logger.info(f"{request.method} {request.url.path} → {response.status_code}")
    return response

@app.get("/health")
async def health():
    return {"status": "healthy"}

app.include_router(main_router, prefix="/api/v1")
app.include_router(talent_router, prefix="/api/v1")
app.include_router(assessment_router, prefix="/api/v1")
app.include_router(external_jobs_router, prefix="/api/v1")  # ← NEW

@app.on_event("startup")
async def startup():
    logger.info("=" * 60)
    logger.info("SkillMap Backend starting")
    logger.info("Endpoints:")
    logger.info("  /api/v1/process-talent")
    logger.info("  /api/v1/talent/parse-cv")
    logger.info("  /api/v1/talent/screen")
    logger.info("  /api/v1/assessment/generate")
    logger.info("  /api/v1/assessment/evaluate")
    logger.info("  /api/v1/talent/external-jobs    ← NEW")
    logger.info("Swagger UI: http://localhost:8000/docs")
    logger.info("=" * 60)