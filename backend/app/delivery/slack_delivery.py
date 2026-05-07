import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from ..config import get_settings
from ..core.encryption import decrypt_token
from ..core.logging import get_logger
from ..database import get_db
from ..models.developer import Developer
from ..models.integration import Integration

settings = get_settings()
logger = get_logger(__name__)


async def _get_slack_client(org_id: str):
    from slack_sdk.web.async_client import AsyncWebClient

    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(
                Integration.org_id == uuid.UUID(org_id),
                Integration.provider == "slack",
            )
        )
        integration = result.scalar_one_or_none()

    raw_token = (
        decrypt_token(integration.access_token)
        if integration and integration.access_token
        else settings.slack_bot_token
    )
    return AsyncWebClient(token=raw_token)


def _is_quiet_hours(org_settings: dict) -> bool:
    """Return True if the current UTC time falls within the org's configured quiet hours."""
    quiet = org_settings.get("quiet_hours")
    if not quiet:
        return False
    try:
        tz_offset = org_settings.get("quiet_hours_tz_offset", 0)
        now_hour = (datetime.now(timezone.utc).hour + tz_offset) % 24
        start = int(quiet.get("start", 22))
        end = int(quiet.get("end", 8))
        if start > end:  # overnight window e.g. 22–8
            return now_hour >= start or now_hour < end
        return start <= now_hour < end
    except Exception:
        return False


async def send_digest_to_channel(
    org_id: str,
    markdown: str,
    blocks: list | None = None,
) -> str | None:
    """Post the digest to the org's configured Slack channel using Block Kit if provided.
    Falls back to email if Slack is not connected. Returns Slack thread ts."""
    from ..models.organization import Organization

    async with get_db() as db:
        result = await db.execute(
            select(Organization).where(Organization.id == uuid.UUID(org_id))
        )
        org = result.scalar_one_or_none()

    if not org:
        return None

    channel = org.settings.get("slack_channel", "#general")

    try:
        client = await _get_slack_client(org_id)
        kwargs: dict = {"channel": channel, "text": markdown, "mrkdwn": True}
        if blocks:
            kwargs["blocks"] = blocks
        resp = await client.chat_postMessage(**kwargs)
        return resp.get("ts")
    except Exception as exc:
        logger.warning("slack delivery failed — falling back to email", extra={"org_id": org_id, "error": str(exc)})
        from .email_delivery import send_digest_email
        await send_digest_email(org_id, markdown)
        return None


async def send_slack_dm(developer_id: str, message: str) -> bool:
    """Send a DM to a developer (used by intervention agent).
    Respects quiet hours — returns False if message was suppressed."""
    async with get_db() as db:
        result = await db.execute(
            select(Developer).where(Developer.id == uuid.UUID(developer_id))
        )
        dev = result.scalar_one_or_none()

    if not dev or not dev.slack_user_id:
        return False

    # Check quiet hours before sending DM
    from ..models.organization import Organization
    async with get_db() as db:
        org_result = await db.execute(
            select(Organization).where(Organization.id == dev.org_id)
        )
        org = org_result.scalar_one_or_none()

    if org and _is_quiet_hours(org.settings):
        logger.info("DM suppressed — quiet hours", extra={"developer_id": developer_id})
        return False

    try:
        client = await _get_slack_client(str(dev.org_id))
        await client.chat_postMessage(channel=dev.slack_user_id, text=message)
        return True
    except Exception as exc:
        logger.warning("slack DM failed", extra={"developer_id": developer_id, "error": str(exc)})
        return False
