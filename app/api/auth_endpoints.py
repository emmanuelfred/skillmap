"""
Auth webhook endpoints — called by Supabase Auth webhooks
to send branded emails via Gmail SMTP.

Set these in Supabase Dashboard → Auth → Hooks:
  - Send email hook → POST http://your-backend/api/v1/auth/webhook/email

Or call them directly from your frontend after signup/reset.
"""

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, EmailStr
from typing import Literal, Optional
import logging
import hmac
import hashlib

from app.core.config import settings
from app.services.email_service import (
    send_verification_email,
    send_password_reset_email,
    send_welcome_email,
)

logger = logging.getLogger("skillmap.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request models ─────────────────────────────────────────────────────────

class WelcomeEmailRequest(BaseModel):
    email: EmailStr
    name: str
    role: Literal["talent", "employer"]


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    name: str
    confirm_url: str


class ResetEmailRequest(BaseModel):
    email: EmailStr
    name: str
    reset_url: str


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.post("/send-welcome")
async def send_welcome(payload: WelcomeEmailRequest):
    """
    Called from frontend after email is confirmed.
    Sends a branded welcome email.
    """
    ok = send_welcome_email(payload.email, payload.name, payload.role)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send welcome email")
    return {"status": "sent"}


@router.post("/send-verification")
async def send_verification(payload: VerifyEmailRequest):
    """
    Optional: override Supabase's default verification email with a branded one.
    Requires disabling Supabase's built-in mailer.
    """
    ok = send_verification_email(payload.email, payload.name, payload.confirm_url)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send verification email")
    return {"status": "sent"}


@router.post("/send-reset")
async def send_reset(payload: ResetEmailRequest):
    """
    Optional: override Supabase's default password reset email with a branded one.
    """
    ok = send_password_reset_email(payload.email, payload.name, payload.reset_url)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to send reset email")
    return {"status": "sent"}


@router.get("/health")
async def auth_health():
    return {"status": "ok", "smtp_user": settings.GMAIL_USER}
