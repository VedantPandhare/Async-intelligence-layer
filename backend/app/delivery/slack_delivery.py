import uuid

from sqlalchemy import select

from ..config import get_settings
from ..database import get_db
from ..models.developer import Developer
from ..models.integration import Integration

settings = get_settings()


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

    token = integration.access_token if integration else settings.slack_bot_token
    return AsyncWebClient(token=token)


async def send_digest_to_channel(org_id: str, markdown: str) -> str | None:
    """Post the digest to the org's configured Slack channel. Returns thread ts."""
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
        resp = await client.chat_postMessage(channel=channel, text=markdown, mrkdwn=True)
        return resp.get("ts")
    except Exception as exc:
        print(f"[slack_delivery] failed to post digest for org {org_id}: {exc}")
        return None


async def send_slack_dm(developer_id: str, message: str) -> None:
    """Send a DM to a developer (used by intervention agent)."""
    async with get_db() as db:
        result = await db.execute(
            select(Developer).where(Developer.id == uuid.UUID(developer_id))
        )
        dev = result.scalar_one_or_none()

    if not dev or not dev.slack_user_id:
        return

    try:
        client = await _get_slack_client(str(dev.org_id))
        await client.chat_postMessage(channel=dev.slack_user_id, text=message)
    except Exception as exc:
        print(f"[slack_delivery] DM to {developer_id} failed: {exc}")
