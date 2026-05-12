import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..core.encryption import decrypt_token
from ..core.logging import get_logger
from ..database import get_db
from ..models.developer import Developer
from ..models.integration import Integration
from ..models.organization import Organization
from .embedder import embed_and_store_event
from .normalizer import (
    NormalizedEvent,
    normalize_github_ci_run,
    normalize_github_commit,
    normalize_github_pr,
    store_event,
)

settings = get_settings()
logger = get_logger(__name__)

GITHUB_API = "https://api.github.com"


async def poll_all_orgs() -> None:
    """Called by APScheduler every 15 minutes — polls all orgs with GitHub integration."""
    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(Integration.provider == "github")
        )
        integrations = result.scalars().all()

    for integration in integrations:
        try:
            await poll_github_for_org(str(integration.org_id))
        except Exception as exc:
            logger.warning("github poll failed", extra={"org_id": str(integration.org_id), "error": str(exc)})


async def poll_github_for_org(org_id: str) -> None:
    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(
                Integration.org_id == uuid.UUID(org_id),
                Integration.provider == "github",
            )
        )
        integration = result.scalar_one_or_none()
        if not integration or not integration.access_token:
            return

        devs_result = await db.execute(
            select(Developer).where(
                Developer.org_id == uuid.UUID(org_id),
                Developer.is_active.is_(True),
                Developer.github_username.isnot(None),
            )
        )
        developers = devs_result.scalars().all()

        org_result = await db.execute(
            select(Organization).where(Organization.id == uuid.UUID(org_id))
        )
        org = org_result.scalar_one_or_none()
        # If github_repos is set and non-empty, restrict events to those repos only
        allowed_repos: set[str] = set((org.settings or {}).get("github_repos", [])) if org else set()

    since = datetime.now(timezone.utc) - timedelta(minutes=20)

    async with httpx.AsyncClient(
        headers={
            "Authorization": f"token {decrypt_token(integration.access_token)}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    ) as client:
        tasks = [
            _poll_developer(client, dev, org_id, since, allowed_repos)
            for dev in developers
        ]
        await asyncio.gather(*tasks, return_exceptions=True)


async def _poll_developer(
    client: httpx.AsyncClient,
    dev: Developer,
    org_id: str,
    since: datetime,
    allowed_repos: set[str] = frozenset(),
) -> None:
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    dev_id = str(dev.id)

    events: list[NormalizedEvent] = []

    try:
        from .retry import with_retry
        resp = await with_retry(
            client.get,
            f"{GITHUB_API}/users/{dev.github_username}/events",
            params={"per_page": 50},
        )
        if resp.status_code == 200:
            for event in resp.json():
                etype = event.get("type")
                created = event.get("created_at", "")
                if created < since_iso:
                    continue

                repo = event.get("repo", {}).get("name", "")
                # Filter to configured repos when a list is provided
                if allowed_repos and repo and repo not in allowed_repos:
                    continue

                if etype == "PushEvent":
                    for commit in event.get("payload", {}).get("commits", []):
                        commit["repo"] = repo
                        events.append(normalize_github_commit(commit, dev_id, org_id))

                elif etype == "PullRequestEvent":
                    pr_payload = event.get("payload", {})
                    pr_payload["repo"] = repo
                    events.append(normalize_github_pr(pr_payload, dev_id, org_id))

                elif etype == "CheckRunEvent":
                    cr_payload = event.get("payload", {})
                    cr_payload["repo"] = repo
                    events.append(normalize_github_ci_run(cr_payload, dev_id, org_id))
    except Exception as exc:
        logger.warning("github events fetch failed", extra={"username": dev.github_username, "error": str(exc)})

    if not events:
        return

    async with get_db() as db:
        for event in events:
            record = await store_event(event, db)
            try:
                await embed_and_store_event(event, record.id, db)
            except Exception as exc:
                logger.warning("embed failed", extra={"event_id": str(record.id), "error": str(exc)})
