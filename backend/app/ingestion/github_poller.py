import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..core.encryption import decrypt_token
from ..database import get_db
from ..models.developer import Developer
from ..models.integration import Integration
from .embedder import embed_and_store_event
from .normalizer import (
    NormalizedEvent,
    normalize_github_ci_run,
    normalize_github_commit,
    normalize_github_pr,
    store_event,
)

settings = get_settings()

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
            print(f"[poller] org {integration.org_id} failed: {exc}")


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
            _poll_developer(client, dev, org_id, since)
            for dev in developers
        ]
        await asyncio.gather(*tasks, return_exceptions=True)


async def _poll_developer(
    client: httpx.AsyncClient,
    dev: Developer,
    org_id: str,
    since: datetime,
) -> None:
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    dev_id = str(dev.id)

    events: list[NormalizedEvent] = []

    # --- Commits across all user repos ---
    try:
        resp = await client.get(
            f"{GITHUB_API}/users/{dev.github_username}/events",
            params={"per_page": 50},
        )
        if resp.status_code == 200:
            for event in resp.json():
                etype = event.get("type")
                created = event.get("created_at", "")
                if created < since_iso:
                    continue

                if etype == "PushEvent":
                    repo = event.get("repo", {}).get("name", "")
                    for commit in event.get("payload", {}).get("commits", []):
                        commit["repo"] = repo
                        events.append(normalize_github_commit(commit, dev_id, org_id))

                elif etype == "PullRequestEvent":
                    pr_payload = event.get("payload", {})
                    pr_payload["repo"] = event.get("repo", {}).get("name", "")
                    events.append(normalize_github_pr(pr_payload, dev_id, org_id))

                elif etype == "CheckRunEvent":
                    cr_payload = event.get("payload", {})
                    cr_payload["repo"] = event.get("repo", {}).get("name", "")
                    events.append(normalize_github_ci_run(cr_payload, dev_id, org_id))
    except Exception as exc:
        print(f"[poller] events fetch failed for {dev.github_username}: {exc}")

    if not events:
        return

    async with get_db() as db:
        for event in events:
            record = await store_event(event, db)
            try:
                await embed_and_store_event(event, record.id, db)
            except Exception as exc:
                print(f"[embedder] failed for event {record.id}: {exc}")
