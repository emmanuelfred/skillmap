"""
Email service using Google SMTP (Gmail).
Handles transactional emails: verification, password reset, welcome.

Requirements in .env:
  GMAIL_USER=you@gmail.com
  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx   # Google App Password (not your login password)
  FRONTEND_URL=http://localhost:5173
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.core.config import settings

logger = logging.getLogger("skillmap.email")


def _send(to: str, subject: str, html: str) -> bool:
    """Low-level SMTP send. Returns True on success."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"SkillMap <{settings.GMAIL_USER}>"
    msg["To"] = to
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(settings.GMAIL_USER, settings.GMAIL_APP_PASSWORD)
            server.sendmail(settings.GMAIL_USER, to, msg.as_string())
        logger.info(f"Email sent → {to} | {subject}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP auth failed — check GMAIL_USER and GMAIL_APP_PASSWORD")
        return False
    except Exception as e:
        logger.error(f"SMTP error sending to {to}: {e}")
        return False


# ── Templates ──────────────────────────────────────────────────────────────

def _base_template(title: str, body: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
      <title>{title}</title>
    </head>
    <body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;">
      <table width="100%" cellpadding="0" cellspacing="0" style="padding:40px 20px;">
        <tr>
          <td align="center">
            <table width="560" cellpadding="0" cellspacing="0"
                   style="background:#1e293b;border-radius:16px;overflow:hidden;border:1px solid #334155;">
              <!-- Header -->
              <tr>
                <td style="background:linear-gradient(135deg,#6366f1,#8b5cf6);padding:32px 40px;">
                  <h1 style="margin:0;color:#fff;font-size:24px;font-weight:800;letter-spacing:-0.5px;">
                    SkillMap
                  </h1>
                  <p style="margin:4px 0 0;color:rgba(255,255,255,0.7);font-size:13px;">
                    AI-powered talent matching
                  </p>
                </td>
              </tr>
              <!-- Body -->
              <tr>
                <td style="padding:40px;">
                  {body}
                </td>
              </tr>
              <!-- Footer -->
              <tr>
                <td style="padding:24px 40px;border-top:1px solid #334155;">
                  <p style="margin:0;color:#64748b;font-size:12px;text-align:center;">
                    © 2025 SkillMap. You're receiving this because you signed up at
                    <a href="{settings.FRONTEND_URL}" style="color:#6366f1;">{settings.FRONTEND_URL}</a>.
                    <br/>If you didn't, you can safely ignore this email.
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>
      </table>
    </body>
    </html>
    """


def _btn(href: str, label: str) -> str:
    return f"""
    <table cellpadding="0" cellspacing="0" style="margin:28px 0;">
      <tr>
        <td style="border-radius:12px;background:linear-gradient(135deg,#6366f1,#8b5cf6);">
          <a href="{href}"
             style="display:inline-block;padding:14px 32px;color:#fff;font-weight:700;
                    font-size:15px;text-decoration:none;border-radius:12px;letter-spacing:0.2px;">
            {label}
          </a>
        </td>
      </tr>
    </table>
    """


# ── Public API ─────────────────────────────────────────────────────────────

def send_verification_email(to: str, name: str, confirm_url: str) -> bool:
    """
    Supabase already sends the verification email by default.
    This is an OPTIONAL branded override — call it from a custom webhook
    if you disable Supabase's built-in mailer.
    """
    body = f"""
    <h2 style="margin:0 0 8px;color:#f1f5f9;font-size:22px;font-weight:800;">
      Verify your email, {name.split()[0]} 👋
    </h2>
    <p style="color:#94a3b8;margin:0 0 4px;font-size:15px;line-height:1.6;">
      You're one step away from joining thousands of talents getting discovered on SkillMap.
      Click the button below to activate your account.
    </p>
    {_btn(confirm_url, "Confirm my email")}
    <p style="color:#64748b;font-size:13px;margin:0;">
      Button not working? Copy and paste this link:<br/>
      <a href="{confirm_url}" style="color:#6366f1;word-break:break-all;">{confirm_url}</a>
    </p>
    <p style="color:#64748b;font-size:12px;margin:24px 0 0;">
      This link expires in <strong style="color:#94a3b8;">24 hours</strong>.
    </p>
    """
    return _send(to, "Confirm your SkillMap email", _base_template("Verify Email", body))


def send_password_reset_email(to: str, name: str, reset_url: str) -> bool:
    body = f"""
    <h2 style="margin:0 0 8px;color:#f1f5f9;font-size:22px;font-weight:800;">
      Reset your password
    </h2>
    <p style="color:#94a3b8;margin:0 0 4px;font-size:15px;line-height:1.6;">
      Hi {name.split()[0]}, we received a request to reset your SkillMap password.
      Click below to choose a new one.
    </p>
    {_btn(reset_url, "Reset my password")}
    <div style="background:#0f172a;border-radius:8px;padding:16px;margin:20px 0;">
      <p style="color:#64748b;font-size:13px;margin:0;">
        ⏰ This link expires in <strong style="color:#94a3b8;">1 hour</strong>.<br/>
        🔒 If you didn't request this, your account is safe — just ignore this email.
      </p>
    </div>
    <p style="color:#64748b;font-size:13px;margin:0;">
      Button not working? Copy and paste:<br/>
      <a href="{reset_url}" style="color:#6366f1;word-break:break-all;">{reset_url}</a>
    </p>
    """
    return _send(to, "Reset your SkillMap password", _base_template("Reset Password", body))


def send_welcome_email(to: str, name: str, role: str) -> bool:
    dashboard_url = f"{settings.FRONTEND_URL}/{role}/dashboard"
    role_tip = (
        "Complete your talent profile so employers can find you — the more detail, the better your matches."
        if role == "talent"
        else "Post your first opportunity and let our AI surface the best-matched candidates for you."
    )
    body = f"""
    <h2 style="margin:0 0 8px;color:#f1f5f9;font-size:22px;font-weight:800;">
      Welcome to SkillMap, {name.split()[0]}! 🎉
    </h2>
    <p style="color:#94a3b8;margin:0 0 16px;font-size:15px;line-height:1.6;">
      Your account is verified and ready to go. {role_tip}
    </p>
    {_btn(dashboard_url, "Go to my dashboard")}
    <p style="color:#64748b;font-size:13px;margin:0;">
      Questions? Just reply to this email — we're here to help.
    </p>
    """
    return _send(to, "Welcome to SkillMap 🚀", _base_template("Welcome", body))
