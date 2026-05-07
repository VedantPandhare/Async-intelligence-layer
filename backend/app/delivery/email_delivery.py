"""Email delivery via SendGrid — fallback when Slack is not connected."""

import uuid

import httpx
from sqlalchemy import select

from ..config import get_settings
from ..core.logging import get_logger
from ..database import get_db
from ..models.organization import Organization

settings = get_settings()
logger = get_logger(__name__)

SENDGRID_API = "https://api.sendgrid.com/v3/mail/send"


async def send_digest_email(org_id: str, markdown: str) -> bool:
    """Send the digest as a plain-text email to all developers in the org.
    Returns True on success."""
    sendgrid_key = getattr(settings, "sendgrid_api_key", "")
    from_email = getattr(settings, "email_from", "digest@standup.ai")

    if not sendgrid_key:
        logger.info("sendgrid key not set — skipping email", extra={"org_id": org_id})
        return False

    async with get_db() as db:
        org_result = await db.execute(
            select(Organization).where(Organization.id == uuid.UUID(org_id))
        )
        org = org_result.scalar_one_or_none()

        from ..models.developer import Developer
        devs_result = await db.execute(
            select(Developer).where(
                Developer.org_id == uuid.UUID(org_id),
                Developer.is_active.is_(True),
                Developer.email.isnot(None),
            )
        )
        developers = devs_result.scalars().all()

    if not developers or not org:
        return False

    personalizations = [
        {"to": [{"email": dev.email}]} for dev in developers if dev.email
    ]
    if not personalizations:
        return False

    html_body = _markdown_to_html(markdown)

    payload = {
        "personalizations": personalizations,
        "from": {"email": from_email, "name": "Async Standup Intelligence"},
        "subject": f"Team Digest — {org.name}",
        "content": [
            {"type": "text/plain", "value": markdown},
            {"type": "text/html", "value": html_body},
        ],
    }

    try:
        async with httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {sendgrid_key}",
                "Content-Type": "application/json",
            },
            timeout=15,
        ) as client:
            resp = await client.post(SENDGRID_API, json=payload)
            if resp.status_code in (200, 202):
                logger.info("digest email sent", extra={"org_id": org_id, "recipients": len(personalizations)})
                return True
            logger.warning("sendgrid error", extra={"org_id": org_id, "status": resp.status_code, "body": resp.text[:200]})
            return False
    except Exception as exc:
        logger.error("email delivery failed", extra={"org_id": org_id, "error": str(exc)})
        return False


def _markdown_to_html(markdown: str) -> str:
    """Minimal Slack-markdown → HTML conversion for email."""
    import re

    html = markdown
    # Bold: *text* → <strong>text</strong>
    html = re.sub(r"\*(.+?)\*", r"<strong>\1</strong>", html)
    # Italic: _text_ → <em>text</em>
    html = re.sub(r"_(.+?)_", r"<em>\1</em>", html)
    # Code: `text` → <code>text</code>
    html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
    # Newlines → <br>
    html = html.replace("\n", "<br>\n")

    return f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:700px;margin:auto;padding:24px">
{html}
</body></html>"""
