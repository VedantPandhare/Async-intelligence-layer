"""Jira poller — fetches recently updated issues assigned to tracked developers every 15 min."""

import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

from ..core.encryption import decrypt_token
from ..core.logging import get_logger
from ..database import get_db
from ..models.developer import Developer
from ..models.integration import Integration
from ..models.organization import Organization
from .embedder import embed_and_store_event
from .normalizer import normalize_jira_issue, store_event
from .retry import with_retry

logger = get_logger(__name__)
JIRA_API = "https://api.atlassian.com"


async def poll_all_orgs_jira() -> None:
    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(Integration.provider == "jira")
        )
        integrations = result.scalars().all()

    for integration in integrations:
        try:
            await poll_jira_for_org(str(integration.org_id))
        except Exception as exc:
            logger.warning("jira poll failed", extra={"org_id": str(integration.org_id), "error": str(exc)})


async def poll_jira_for_org(org_id: str) -> None:
    org_uuid = uuid.UUID(org_id)

    async with get_db() as db:
        int_result = await db.execute(
            select(Integration).where(
                Integration.org_id == org_uuid,
                Integration.provider == "jira",
            )
        )
        integration = int_result.scalar_one_or_none()
        if not integration or not integration.access_token:
            return

        devs_result = await db.execute(
            select(Developer).where(
                Developer.org_id == org_uuid,
                Developer.is_active.is_(True),
                Developer.jira_account_id.isnot(None),
            )
        )
        developers = devs_result.scalars().all()

        org_result = await db.execute(
            select(Organization).where(Organization.id == org_uuid)
        )
        org = org_result.scalar_one_or_none()

    if not developers or not org:
        return

    token = decrypt_token(integration.access_token)
    jira_domain = integration.metadata_.get("domain") or org.settings.get("jira_domain", "")
    cloud_id = integration.metadata_.get("cloud_id", "")

    since = datetime.now(timezone.utc) - timedelta(minutes=20)
    since_str = since.strftime("%Y-%m-%d %H:%M")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(headers=headers, timeout=30) as client:
        for dev in developers:
            await _poll_developer_issues(client, dev, org_id, cloud_id, since_str)


async def _poll_developer_issues(
    client: httpx.AsyncClient,
    dev: Developer,
    org_id: str,
    cloud_id: str,
    since_str: str,
) -> None:
    jql = (
        f'assignee = "{dev.jira_account_id}" '
        f'AND updated >= "{since_str}" '
        f'ORDER BY updated DESC'
    )

    url = f"{JIRA_API}/ex/jira/{cloud_id}/rest/api/3/search" if cloud_id else None
    if not url:
        return

    try:
        resp = await with_retry(client.get, url, params={"jql": jql, "maxResults": 50})
        if resp.status_code != 200:
            return

        issues = resp.json().get("issues", [])
        for issue in issues:
            payload = {"issue": issue, "webhookEvent": "jira:issue_updated"}
            async with get_db() as db:
                event = normalize_jira_issue(payload, str(dev.id), org_id)
                record = await store_event(event, db)
                try:
                    await embed_and_store_event(event, record.id, db)
                except Exception as exc:
                    logger.warning("embed failed", extra={"event_id": str(record.id), "error": str(exc)})

    except Exception as exc:
        logger.warning("jira issues fetch failed", extra={"jira_account_id": dev.jira_account_id, "error": str(exc)})
