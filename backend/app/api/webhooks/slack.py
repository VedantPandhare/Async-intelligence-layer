"""Slack Events API webhook receiver — handles url_verification and message events."""

import hashlib
import hmac
import time
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from ...config import get_settings
from ...core.logging import get_logger
from ...database import get_db
from ...ingestion.embedder import embed_and_store_event
from ...ingestion.normalizer import normalize_slack_message, store_event
from ...models.developer import Developer

router = APIRouter(tags=["webhooks"])
settings = get_settings()
logger = get_logger(__name__)


def _verify_slack_signature(
    body: bytes,
    timestamp: str,
    signature: str,
    signing_secret: str,
) -> bool:
    # Reject requests older than 5 minutes (replay protection)
    try:
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except ValueError:
        return False

    base = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(
        signing_secret.encode(), base.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


@router.post("/webhooks/slack/{org_id}")
async def slack_webhook(
    org_id: str,
    request: Request,
    x_slack_signature: str | None = Header(None),
    x_slack_request_timestamp: str | None = Header(None),
):
    body = await request.body()

    # Verify signing secret if configured
    if settings.slack_signing_secret and x_slack_signature and x_slack_request_timestamp:
        if not _verify_slack_signature(
            body,
            x_slack_request_timestamp,
            x_slack_signature,
            settings.slack_signing_secret,
        ):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = await request.json()
    event_type = payload.get("type")

    # Slack URL verification challenge (sent once when configuring Events API)
    if event_type == "url_verification":
        return {"challenge": payload["challenge"]}

    if event_type != "event_callback":
        return {"status": "ignored"}

    event = payload.get("event", {})
    slack_event_type = event.get("type")

    # Only process user messages (not bot messages)
    if slack_event_type != "message" or event.get("subtype"):
        return {"status": "ok"}

    slack_user_id = event.get("user")
    if not slack_user_id:
        return {"status": "ok"}

    # Resolve developer by slack_user_id
    org_uuid = uuid.UUID(org_id)
    async with get_db() as db:
        result = await db.execute(
            select(Developer).where(
                Developer.org_id == org_uuid,
                Developer.slack_user_id == slack_user_id,
                Developer.is_active.is_(True),
            )
        )
        dev = result.scalar_one_or_none()

    if not dev:
        return {"status": "ok"}

    raw = {
        **event,
        "channel_name": event.get("channel", "unknown"),
    }

    async with get_db() as db:
        normalized = normalize_slack_message(raw, str(dev.id), org_id)
        record = await store_event(normalized, db)
        try:
            await embed_and_store_event(normalized, record.id, db)
        except Exception as exc:
            logger.warning("embed failed", extra={"event_id": str(record.id), "error": str(exc)})

    return {"status": "ok"}
