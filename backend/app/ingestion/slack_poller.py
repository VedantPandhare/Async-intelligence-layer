"""Slack poller — polls message counts per developer every 15 minutes
using conversations.history and users.list APIs.
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from slack_sdk.web.async_client import AsyncWebClient
from sqlalchemy import select

from ..core.encryption import decrypt_token
from ..core.logging import get_logger
from ..database import get_db
from ..models.developer import Developer
from ..models.integration import Integration
from .embedder import embed_and_store_event
from .normalizer import normalize_slack_message, store_event

logger = get_logger(__name__)


async def poll_all_orgs_slack() -> None:
    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(Integration.provider == "slack")
        )
        integrations = result.scalars().all()

    for integration in integrations:
        try:
            await poll_slack_for_org(str(integration.org_id))
        except Exception as exc:
            logger.warning("slack poll failed", extra={"org_id": str(integration.org_id), "error": str(exc)})


async def poll_slack_for_org(org_id: str) -> None:
    org_uuid = uuid.UUID(org_id)

    async with get_db() as db:
        int_result = await db.execute(
            select(Integration).where(
                Integration.org_id == org_uuid,
                Integration.provider == "slack",
            )
        )
        integration = int_result.scalar_one_or_none()
        if not integration or not integration.access_token:
            return

        devs_result = await db.execute(
            select(Developer).where(
                Developer.org_id == org_uuid,
                Developer.is_active.is_(True),
                Developer.slack_user_id.isnot(None),
            )
        )
        developers = devs_result.scalars().all()

    token = decrypt_token(integration.access_token)
    client = AsyncWebClient(token=token)

    since = datetime.now(timezone.utc) - timedelta(minutes=20)
    since_ts = str(since.timestamp())

    # Fetch all public channels the bot has joined
    channels = await _get_channels(client)

    # Build a map of slack_user_id → Developer
    dev_map = {dev.slack_user_id: dev for dev in developers}

    tasks = [
        _poll_channel(client, channel, dev_map, org_id, since_ts)
        for channel in channels
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


async def _get_channels(client: AsyncWebClient) -> list[dict]:
    try:
        resp = await client.conversations_list(
            types="public_channel,private_channel",
            exclude_archived=True,
            limit=200,
        )
        return resp.get("channels", [])
    except Exception as exc:
        logger.warning("conversations_list failed", extra={"error": str(exc)})
        return []


async def _poll_channel(
    client: AsyncWebClient,
    channel: dict,
    dev_map: dict,
    org_id: str,
    oldest: str,
) -> None:
    channel_id = channel["id"]
    channel_name = channel.get("name", channel_id)

    try:
        resp = await client.conversations_history(
            channel=channel_id,
            oldest=oldest,
            limit=200,
        )
    except Exception as exc:
        logger.warning("conversations_history failed", extra={"channel": channel_name, "error": str(exc)})
        return

    messages = resp.get("messages", [])

    for msg in messages:
        user_id = msg.get("user")
        if not user_id or user_id not in dev_map:
            continue

        dev = dev_map[user_id]
        raw = {
            **msg,
            "channel": channel_id,
            "channel_name": channel_name,
        }

        try:
            async with get_db() as db:
                event = normalize_slack_message(raw, str(dev.id), org_id)
                record = await store_event(event, db)
                await embed_and_store_event(event, record.id, db)
        except Exception as exc:
            logger.warning("store/embed failed", extra={"user_id": user_id, "error": str(exc)})
