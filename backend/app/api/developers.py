import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.encryption import decrypt_token
from ..core.logging import get_logger
from ..core.security import get_current_org
from ..database import get_db_dep
from ..models.activity_event import ActivityEvent
from ..models.developer import Developer
from ..models.integration import Integration
from ..models.organization import Organization

router = APIRouter(prefix="/developers", tags=["developers"])
logger = get_logger(__name__)

GITHUB_API = "https://api.github.com"


class DeveloperCreate(BaseModel):
    name: str
    email: str | None = None
    github_username: str | None = None
    slack_user_id: str | None = None
    jira_account_id: str | None = None
    role: str | None = None


@router.post("/{org_id}", status_code=201)
async def create_developer(
    org_id: str,
    payload: DeveloperCreate,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    dev = Developer(
        id=uuid.uuid4(),
        org_id=uuid.UUID(org_id),
        **payload.model_dump(),
    )
    db.add(dev)
    await db.flush()
    return {"id": str(dev.id), "name": dev.name}


@router.get("/{org_id}")
async def list_developers(org_id: str, db: AsyncSession = Depends(get_db_dep)):
    result = await db.execute(
        select(Developer).where(Developer.org_id == uuid.UUID(org_id), Developer.is_active.is_(True))
    )
    devs = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "email": d.email,
            "github_username": d.github_username,
            "slack_user_id": d.slack_user_id,
            "role": d.role,
        }
        for d in devs
    ]


@router.get("/{org_id}/{dev_id}")
async def get_developer(org_id: str, dev_id: str, db: AsyncSession = Depends(get_db_dep)):
    result = await db.execute(
        select(Developer).where(
            Developer.id == uuid.UUID(dev_id),
            Developer.org_id == uuid.UUID(org_id),
        )
    )
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return {
        "id": str(dev.id),
        "name": dev.name,
        "email": dev.email,
        "github_username": dev.github_username,
        "slack_user_id": dev.slack_user_id,
        "jira_account_id": dev.jira_account_id,
        "role": dev.role,
        "is_active": dev.is_active,
    }


@router.patch("/{org_id}/{dev_id}/opt-out", status_code=200)
async def opt_out(
    org_id: str,
    dev_id: str,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    """Privacy control: exclude this developer from signal collection and digest generation."""
    dev = await _get_dev(org_id, dev_id, db)
    dev.is_active = False
    await db.flush()
    return {"status": "opted_out", "developer_id": dev_id}


@router.patch("/{org_id}/{dev_id}/opt-in", status_code=200)
async def opt_in(
    org_id: str,
    dev_id: str,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    """Re-enable a developer who previously opted out."""
    dev = await _get_dev(org_id, dev_id, db)
    dev.is_active = True
    await db.flush()
    return {"status": "opted_in", "developer_id": dev_id}


@router.get("/{org_id}/{dev_id}/timeline")
async def developer_timeline(
    org_id: str,
    dev_id: str,
    hours: int = 24,
    db: AsyncSession = Depends(get_db_dep),
):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(ActivityEvent)
        .where(
            ActivityEvent.developer_id == uuid.UUID(dev_id),
            ActivityEvent.org_id == uuid.UUID(org_id),
            ActivityEvent.event_time >= since,
        )
        .order_by(ActivityEvent.event_time.desc())
        .limit(100)
    )
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "source": e.source,
            "event_type": e.event_type,
            "event_time": e.event_time.isoformat(),
            "summary": e.summary,
            "payload": e.payload,
        }
        for e in events
    ]


@router.post("/{org_id}/import-github", status_code=200)
async def import_from_github(
    org_id: str,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    """
    Pull GitHub org members and create/skip Developer records.
    Requires GitHub to be connected and github_org to be set in org settings.
    """
    # Get GitHub integration token
    int_result = await db.execute(
        select(Integration).where(
            Integration.org_id == uuid.UUID(org_id),
            Integration.provider == "github",
        )
    )
    integration = int_result.scalar_one_or_none()
    if not integration or not integration.access_token:
        raise HTTPException(status_code=400, detail="GitHub not connected. Connect GitHub first.")

    token = decrypt_token(integration.access_token)

    # Resolve github_org: prefer org settings, fall back to integration metadata
    org_result = await db.execute(
        select(Organization).where(Organization.id == uuid.UUID(org_id))
    )
    org = org_result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")

    github_org = (org.settings or {}).get("github_org") or integration.metadata_.get("github_username")
    if not github_org:
        raise HTTPException(
            status_code=400,
            detail="GitHub org not configured. Set 'GitHub Org' in Settings first.",
        )

    gh_headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Fetch org members
    async with httpx.AsyncClient(headers=gh_headers, timeout=30) as client:
        resp = await client.get(
            f"{GITHUB_API}/orgs/{github_org}/members",
            params={"per_page": 100},
        )
        if resp.status_code == 404:
            raise HTTPException(
                status_code=400,
                detail=f"GitHub org '{github_org}' not found or the token lacks read:org access.",
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"GitHub API error: {resp.status_code}")
        members = resp.json()

    imported: list[dict] = []
    skipped: list[str] = []

    async with httpx.AsyncClient(headers=gh_headers, timeout=30) as client:
        for member in members:
            username: str = member.get("login", "")
            if not username:
                continue

            # Skip if already exists for this org
            existing = await db.execute(
                select(Developer).where(
                    Developer.org_id == uuid.UUID(org_id),
                    Developer.github_username == username,
                )
            )
            if existing.scalar_one_or_none():
                skipped.append(username)
                continue

            # Fetch public user profile for name + email
            name = username
            email: str | None = None
            try:
                user_resp = await client.get(f"{GITHUB_API}/users/{username}")
                if user_resp.status_code == 200:
                    user_data = user_resp.json()
                    name = user_data.get("name") or username
                    email = user_data.get("email") or None
            except Exception as exc:
                logger.warning("github user detail fetch failed", extra={"username": username, "error": str(exc)})

            dev = Developer(
                id=uuid.uuid4(),
                org_id=uuid.UUID(org_id),
                name=name,
                email=email,
                github_username=username,
            )
            db.add(dev)
            imported.append({"name": name, "github_username": username})

    await db.flush()
    logger.info(
        "github import complete",
        extra={"org_id": org_id, "imported": len(imported), "skipped": len(skipped)},
    )
    return {
        "imported": len(imported),
        "skipped": len(skipped),
        "developers": imported,
    }


@router.get("/{org_id}/github-orgs")
async def list_github_orgs(
    org_id: str,
    db: AsyncSession = Depends(get_db_dep),
):
    """Return the GitHub orgs visible to this workspace's connected token (from integration metadata)."""
    result = await db.execute(
        select(Integration).where(
            Integration.org_id == uuid.UUID(org_id),
            Integration.provider == "github",
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        return {"orgs": []}
    orgs = integration.metadata_.get("github_orgs", [])
    return {"orgs": orgs}


async def _get_dev(org_id: str, dev_id: str, db: AsyncSession) -> Developer:
    result = await db.execute(
        select(Developer).where(
            Developer.id == uuid.UUID(dev_id),
            Developer.org_id == uuid.UUID(org_id),
        )
    )
    dev = result.scalar_one_or_none()
    if not dev:
        raise HTTPException(status_code=404, detail="Developer not found")
    return dev
