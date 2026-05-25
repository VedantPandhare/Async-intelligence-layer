"""Slack slash command handler for /standup [trigger|blockers|me|help]."""

import hashlib
import hmac
import time
import uuid
from urllib.parse import parse_qs

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from ..config import get_settings
from ..core.logging import get_logger
from ..database import get_db
from ..models.developer import Developer
from ..models.integration import Integration

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


@router.post("/events")
async def slack_events(
    request: Request,
    x_slack_signature: str | None = Header(None),
    x_slack_request_timestamp: str | None = Header(None),
):
    import json as _json
    body = await request.body()
    payload = _json.loads(body) if body else {}

    # url_verification must be answered before signature check
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    if settings.slack_signing_secret:
        if not x_slack_signature or not x_slack_request_timestamp:
            raise HTTPException(status_code=401, detail="Missing Slack headers")
        if not _verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    if payload.get("type") != "event_callback":
        return {"status": "ignored"}

    team_id = payload.get("team_id", "")
    org_id = await _org_id_for_team(team_id)
    if not org_id:
        return {"status": "unknown_workspace"}

    event = payload.get("event", {})
    if event.get("type") != "message" or event.get("subtype"):
        return {"status": "ok"}

    slack_user_id = event.get("user")
    if not slack_user_id:
        return {"status": "ok"}

    from sqlalchemy import select as _select
    from ..models.developer import Developer
    from ..ingestion.normalizer import normalize_slack_message, store_event
    from ..ingestion.embedder import embed_and_store_event
    import uuid as _uuid

    async with get_db() as db:
        result = await db.execute(
            _select(Developer).where(
                Developer.org_id == _uuid.UUID(org_id),
                Developer.slack_user_id == slack_user_id,
                Developer.is_active.is_(True),
            )
        )
        dev = result.scalar_one_or_none()

    if not dev:
        return {"status": "ok"}

    raw = {**event, "channel_name": event.get("channel", "unknown")}
    async with get_db() as db:
        normalized = normalize_slack_message(raw, str(dev.id), org_id)
        record = await store_event(normalized, db)
        try:
            await embed_and_store_event(normalized, record.id, db)
        except Exception as exc:
            logger.warning("slack embed failed", extra={"error": str(exc)})

    return {"status": "ok"}


@router.post("/commands")
async def slack_command(
    request: Request,
    x_slack_signature: str | None = Header(None),
    x_slack_request_timestamp: str | None = Header(None),
):
    # Read body once — Form() params would consume the stream before body() could read it
    body = await request.body()

    if settings.slack_signing_secret:
        if not x_slack_signature or not x_slack_request_timestamp:
            raise HTTPException(status_code=401, detail="Missing Slack headers")
        if not _verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Parse url-encoded form fields from raw bytes
    fields = parse_qs(body.decode(), keep_blank_values=True)

    def _field(key: str, default: str = "") -> str:
        return fields.get(key, [default])[0]

    text = _field("text")
    user_id = _field("user_id")
    team_id = _field("team_id")
    channel_id = _field("channel_id")

    subcommand = text.strip().lower().split()[0] if text.strip() else "help"
    org_id = await _org_id_for_team(team_id)

    if not org_id:
        return {"response_type": "ephemeral", "text": "This workspace is not connected. Visit the dashboard to set up your org."}

    if subcommand == "trigger":
        return await _handle_trigger(org_id, channel_id)
    elif subcommand == "blockers":
        return await _handle_blockers(org_id)
    elif subcommand == "me":
        return await _handle_me(org_id, user_id)
    else:
        return _handle_help()


def _build_digest_blocks(result: dict) -> list:
    """Convert pipeline result into Slack Block Kit blocks."""
    from datetime import datetime
    now = datetime.utcnow()
    # %-d is Linux-only; build the date string manually so it works on Windows too
    date_str = f"{now.strftime('%A, %B')} {now.day}"

    blocks: list = [
        {"type": "header", "text": {"type": "plain_text", "text": f"Team Digest — {date_str}"}},
        {"type": "divider"},
    ]

    signals = result.get("developer_signals", [])
    narratives = result.get("developer_narratives", {})
    blockers = result.get("blockers", [])
    blocker_map = {b["developer_id"]: b["severity"] for b in blockers}

    if not signals:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "_No developer activity recorded for this period._"},
        })
    else:
        for dev in signals:
            dev_id = dev["developer_id"]
            name = dev["developer_name"]
            narrative = narratives.get(dev_id, "No activity today.")

            severity = blocker_map.get(dev_id)
            if severity == "critical":
                status = "BLOCKER"
            elif severity in ("high", "medium"):
                status = "Attention needed"
            else:
                status = ""

            commit_count = len(dev.get("commits_today", []))
            pr_count = len(dev.get("prs_opened", []))
            meta_parts = []
            if commit_count:
                meta_parts.append(f"{commit_count} commit{'s' if commit_count != 1 else ''}")
            if pr_count:
                meta_parts.append(f"{pr_count} PR{'s' if pr_count != 1 else ''}")
            if status:
                meta_parts.append(f"*{status}*")
            meta_str = "   |   ".join(meta_parts)

            header_line = f"*{name}*"
            if meta_str:
                header_line += f"   {meta_str}"

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"{header_line}\n{narrative}"},
            })
            blocks.append({"type": "divider"})

    sprint_risk = result.get("sprint_risk", "")
    if sprint_risk:
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"Sprint health   |   {sprint_risk}"}],
        })

    return blocks


async def _handle_trigger(org_id: str, channel_id: str) -> dict:
    """Kick off the digest pipeline asynchronously and post result to the invoking channel."""
    import asyncio
    from slack_sdk.web.async_client import AsyncWebClient
    from ..agents.graph import pipeline
    from ..agents.persist import persist_pipeline_results
    from ..core.analytics import track
    from ..core.encryption import decrypt_token
    from ..models.integration import Integration
    from datetime import date

    async def _run():
        try:
            # Poll GitHub first so signal_collector has fresh data
            from ..ingestion.github_poller import poll_github_for_org
            await poll_github_for_org(org_id, since_hours=168)

            state = {
                "org_id": org_id, "digest_date": date.today().isoformat(),
                "developer_signals": [], "blockers": [], "conflicts": [],
                "developer_narratives": {}, "sprint_risk": "",
                "final_digest": None, "errors": [], "should_intervene": False,
            }
            result = await pipeline.ainvoke(state)
            await persist_pipeline_results(result)
            track("digest_generated", org_id, {"triggered_by": "slack_command"})

            blocks = _build_digest_blocks(result)
            fallback_text = result.get("final_digest") or "Team digest — see blocks"

            async with get_db() as db:
                int_result = await db.execute(
                    select(Integration).where(
                        Integration.org_id == uuid.UUID(org_id),
                        Integration.provider == "slack",
                    )
                )
                integration = int_result.scalar_one_or_none()

            token = (
                decrypt_token(integration.access_token)
                if integration and integration.access_token
                else settings.slack_bot_token
            )
            client = AsyncWebClient(token=token)
            await client.chat_postMessage(
                channel=channel_id,
                text=fallback_text,
                blocks=blocks,
            )
        except Exception as exc:
            logger.warning("trigger pipeline failed", extra={"org_id": org_id, "error": str(exc)})

    asyncio.create_task(_run())
    return {
        "response_type": "ephemeral",
        "text": "⏳ Running pipeline — digest will be posted here in ~30 seconds.",
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
