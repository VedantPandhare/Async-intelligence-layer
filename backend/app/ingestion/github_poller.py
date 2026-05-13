import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select

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


async def poll_github_for_org(org_id: str, since_hours: int = 0) -> dict:
    """
    Poll GitHub for all active developers in the org.
    Returns a summary dict: {developers, fetched, stored, filtered, errors, detail}
    """
    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(
                Integration.org_id == uuid.UUID(org_id),
                Integration.provider == "github",
            )
        )
        integration = result.scalar_one_or_none()
        if not integration or not integration.access_token:
            return {"error": "no_github_integration", "fetched": 0, "stored": 0}

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
        allowed_repos: set[str] = set((org.settings or {}).get("github_repos", [])) if org else set()

    if not developers:
        return {"error": "no_active_developers_with_github_username", "fetched": 0, "stored": 0}

    since = datetime.now(timezone.utc) - timedelta(
        hours=since_hours if since_hours > 0 else 0,
        minutes=0 if since_hours > 0 else 20,
    )

    async with httpx.AsyncClient(
        headers={
            "Authorization": f"token {decrypt_token(integration.access_token)}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    ) as client:
        results = await asyncio.gather(
            *[_poll_developer(client, dev, org_id, since, allowed_repos) for dev in developers],
            return_exceptions=True,
        )

    summary = {
        "developers": [d.github_username for d in developers],
        "allowed_repos": list(allowed_repos),
        "since_iso": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "fetched": 0,
        "stored": 0,
        "filtered": 0,
        "errors": [],
        "detail": [],
    }
    for r in results:
        if isinstance(r, Exception):
            summary["errors"].append(str(r))
        elif isinstance(r, dict):
            summary["fetched"] += r.get("fetched", 0)
            summary["stored"] += r.get("stored", 0)
            summary["filtered"] += r.get("filtered", 0)
            if r.get("error"):
                summary["errors"].append(r["error"])
            summary["detail"].append(r)

    return summary


async def _poll_developer(
    client: httpx.AsyncClient,
    dev: Developer,
    org_id: str,
    since: datetime,
    allowed_repos: set[str] = frozenset(),
) -> dict:
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    dev_id = str(dev.id)
    result = {
        "username": dev.github_username,
        "fetched": 0,
        "stored": 0,
        "filtered": 0,
        "error": None,
        "commits": [],
    }

    events: list[NormalizedEvent] = []

    try:
        from .retry import with_retry
        resp = await with_retry(
            client.get,
            f"{GITHUB_API}/users/{dev.github_username}/events",
            params={"per_page": 50},
        )
        if resp.status_code != 200:
            result["error"] = f"github_api_{resp.status_code}: {resp.text[:200]}"
            logger.warning("github events API non-200", extra={
                "username": dev.github_username, "status": resp.status_code, "body": resp.text[:300],
            })
            return result

        raw_events = resp.json()
        logger.info("github events fetched", extra={"username": dev.github_username, "count": len(raw_events)})

        for event in raw_events:
            etype = event.get("type")
            created = event.get("created_at", "")
            if created < since_iso:
                continue

            repo = event.get("repo", {}).get("name", "")
            if allowed_repos and repo:
                repo_short = repo.split("/")[-1]
                if repo not in allowed_repos and repo_short not in allowed_repos:
                    result["filtered"] += 1
                    if repo not in result.get("filtered_repos", []):
                        result.setdefault("filtered_repos", []).append(repo)
                    continue

            if etype == "PushEvent":
                push_ts = event.get("created_at", "")
                for commit in event.get("payload", {}).get("commits", []):
                    commit["repo"] = repo
                    commit["pushed_at"] = push_ts  # PushEvent commits lack author.date
                    events.append(normalize_github_commit(commit, dev_id, org_id))
                    result["commits"].append({
                        "msg": commit.get("message", "")[:80],
                        "repo": repo,
                        "sha": commit.get("sha", "")[:8],
                    })
                    logger.info("commit queued", extra={
                        "username": dev.github_username, "repo": repo, "msg": commit.get("message", "")[:60],
                    })

            elif etype == "PullRequestEvent":
                pr_payload = event.get("payload", {})
                pr_payload["repo"] = repo
                events.append(normalize_github_pr(pr_payload, dev_id, org_id))

            elif etype == "CheckRunEvent":
                cr_payload = event.get("payload", {})
                cr_payload["repo"] = repo
                events.append(normalize_github_ci_run(cr_payload, dev_id, org_id))

        result["fetched"] = len(events)

    except Exception as exc:
        result["error"] = f"fetch_exception: {exc}"
        logger.warning("github events fetch failed", extra={"username": dev.github_username, "error": str(exc)})
        return result

    if not events:
        return result

    # Store events in their own committed session — embedding is separate so a failing embed
    # never rolls back the event write.
    stored_ids: list[tuple] = []
    try:
        async with get_db() as db:
            for event in events:
                record = await store_event(event, db)
                stored_ids.append((event, record.id))
        result["stored"] = len(stored_ids)
        logger.info("events stored", extra={"username": dev.github_username, "count": len(stored_ids)})
    except Exception as exc:
        result["error"] = f"storage_exception: {exc}"
        logger.warning("event storage failed", extra={"username": dev.github_username, "error": str(exc)})

    # Best-effort embedding in isolated sessions — failures are logged and skipped.
    for event, record_id in stored_ids:
        try:
            async with get_db() as db:
                await embed_and_store_event(event, record_id, db)
        except Exception as exc:
            logger.warning("embed failed", extra={"event_id": str(record_id), "error": str(exc)})

    return result
