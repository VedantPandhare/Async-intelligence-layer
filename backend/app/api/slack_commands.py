"""Slack slash command handler for /standup [trigger|blockers|me|help]."""

import hashlib
import hmac
import time
import uuid

from fastapi import APIRouter, Form, Header, HTTPException, Request
from sqlalchemy import select

from ..config import get_settings
from ..core.logging import get_logger
from ..database import get_db
from ..models.developer import Developer
from ..models.integration import Integration
from ..models.organization import Organization

router = APIRouter(prefix="/slack", tags=["slack-commands"])
settings = get_settings()
logger = get_logger(__name__)


def _verify_slack_signature(body: bytes, timestamp: str, signature: str) -> bool:
    try:
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except ValueError:
        return False
    base = f"v0:{timestamp}:{body.decode()}"
    expected = "v0=" + hmac.new(
        settings.slack_signing_secret.encode(), base.encode(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)


async def _org_id_for_team(team_id: str) -> str | None:
    """Resolve Slack team_id → org_id via the integrations table."""
    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(Integration.provider == "slack")
        )
        for integration in result.scalars():
            if integration.metadata_.get("workspace_id") == team_id:
                return str(integration.org_id)
    return None


@router.post("/commands")
async def slack_command(
    request: Request,
    command: str = Form(...),
    text: str = Form(default=""),
    user_id: str = Form(...),
    team_id: str = Form(...),
    channel_id: str = Form(...),
    x_slack_signature: str | None = Header(None),
    x_slack_request_timestamp: str | None = Header(None),
):
    # Verify request came from Slack
    if settings.slack_signing_secret:
        body = await request.body()
        if not x_slack_signature or not x_slack_request_timestamp:
            raise HTTPException(status_code=401, detail="Missing Slack headers")
        if not _verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    subcommand = text.strip().lower().split()[0] if text.strip() else "help"
    org_id = await _org_id_for_team(team_id)

    if not org_id:
        return {"response_type": "ephemeral", "text": "This workspace is not connected. Visit the dashboard to set up your org."}

    if subcommand == "trigger":
        return await _handle_trigger(org_id)
    elif subcommand == "blockers":
        return await _handle_blockers(org_id)
    elif subcommand == "me":
        return await _handle_me(org_id, user_id)
    else:
        return _handle_help()


async def _handle_trigger(org_id: str) -> dict:
    """Kick off the digest pipeline asynchronously and acknowledge immediately."""
    import asyncio
    from ..agents.graph import pipeline
    from ..agents.persist import persist_pipeline_results
    from ..core.analytics import track
    from datetime import date

    async def _run():
        state = {
            "org_id": org_id, "digest_date": date.today().isoformat(),
            "developer_signals": [], "blockers": [], "conflicts": [],
            "developer_narratives": {}, "sprint_risk": "",
            "final_digest": None, "errors": [], "should_intervene": False,
        }
        result = await pipeline.ainvoke(state)
        await persist_pipeline_results(result)
        track("digest_generated", org_id, {"triggered_by": "slack_command"})

    asyncio.create_task(_run())
    return {
        "response_type": "ephemeral",
        "text": "Pipeline triggered. Digest will appear in your channel shortly.",
    }


async def _handle_blockers(org_id: str) -> dict:
    from ..models.blocker import Blocker

    async with get_db() as db:
        result = await db.execute(
            select(Blocker)
            .where(Blocker.org_id == uuid.UUID(org_id), Blocker.resolved_at.is_(None))
            .order_by(Blocker.detected_at.desc())
            .limit(10)
        )
        blockers = result.scalars().all()

    if not blockers:
        return {"response_type": "in_channel", "text": "✅ No active blockers right now."}

    severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}
    lines = ["*Active Blockers*"]
    for b in blockers:
        emoji = severity_emoji.get(b.severity, "•")
        lines.append(f"{emoji} *{b.severity.upper()}* — {b.description}")

    return {"response_type": "in_channel", "text": "\n".join(lines)}


async def _handle_me(org_id: str, slack_user_id: str) -> dict:
    from datetime import datetime, timedelta, timezone
    from ..models.activity_event import ActivityEvent

    async with get_db() as db:
        dev_result = await db.execute(
            select(Developer).where(
                Developer.org_id == uuid.UUID(org_id),
                Developer.slack_user_id == slack_user_id,
            )
        )
        dev = dev_result.scalar_one_or_none()

        if not dev:
            return {"response_type": "ephemeral", "text": "Your Slack account is not linked to a developer profile."}

        since = datetime.now(timezone.utc) - timedelta(hours=24)
        events_result = await db.execute(
            select(ActivityEvent)
            .where(
                ActivityEvent.developer_id == dev.id,
                ActivityEvent.event_time >= since,
            )
            .order_by(ActivityEvent.event_time.desc())
            .limit(10)
        )
        events = events_result.scalars().all()

    if not events:
        return {"response_type": "ephemeral", "text": "No activity recorded for you in the last 24 hours."}

    lines = [f"*Your last 24h — {dev.name}*"]
    for e in events:
        ts = e.event_time.strftime("%H:%M")
        lines.append(f"`{ts}` [{e.source}] {e.summary}")

    return {"response_type": "ephemeral", "text": "\n".join(lines)}


def _handle_help() -> dict:
    return {
        "response_type": "ephemeral",
        "text": (
            "*Standup Intelligence — commands*\n"
            "`/standup trigger` — run today's digest pipeline now\n"
            "`/standup blockers` — show active blockers for the team\n"
            "`/standup me` — show your own activity in the last 24h\n"
            "`/standup help` — show this message"
        ),
    }
