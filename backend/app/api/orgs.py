import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import generate_api_key, get_current_org, hash_api_key
from ..database import get_db_dep
from ..models.integration import Integration
from ..models.organization import Organization
from ..scheduler.runner import schedule_digest_for_org

router = APIRouter(prefix="/org", tags=["organizations"])


class OrgCreate(BaseModel):
    name: str
    slug: str
    digest_time: str = "09:00"
    timezone: str = "UTC"


class OrgSettings(BaseModel):
    digest_time: str | None = None
    timezone: str | None = None
    slack_channel: str | None = None
    # GitHub configuration
    github_org: str | None = None
    github_repos: list[str] | None = None   # empty list = watch all repos
    # Slack ingestion
    slack_read_channels: list[str] | None = None  # channel names to read from


@router.post("/", status_code=201)
async def create_org(payload: OrgCreate, db: AsyncSession = Depends(get_db_dep)):
    existing = await db.execute(select(Organization).where(Organization.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug already taken")

    from datetime import time
    h, m = (int(x) for x in payload.digest_time.split(":")[:2])

    api_key = generate_api_key()
    org = Organization(
        id=uuid.uuid4(),
        name=payload.name,
        slug=payload.slug,
        digest_time=time(h, m),
        timezone=payload.timezone,
        settings={"api_key_hash": hash_api_key(api_key)},
    )
    db.add(org)
    await db.flush()
    await schedule_digest_for_org(str(org.id), payload.digest_time, payload.timezone)

    # api_key is returned exactly once — the caller must store it
    return {"id": str(org.id), "slug": org.slug, "api_key": api_key}


@router.get("/{org_id}/settings")
async def get_settings(org_id: str, db: AsyncSession = Depends(get_db_dep)):
    result = await db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    public_settings = {k: v for k, v in org.settings.items() if k != "api_key_hash"}
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "digest_time": org.digest_time.strftime("%H:%M"),
        "timezone": org.timezone,
        "settings": public_settings,
    }


@router.patch("/{org_id}/settings")
async def update_settings(
    org_id: str,
    payload: OrgSettings,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    result = await db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")

    if payload.digest_time:
        from datetime import time
        h, m = (int(x) for x in payload.digest_time.split(":")[:2])
        org.digest_time = time(h, m)
    if payload.timezone:
        org.timezone = payload.timezone

    # Merge all JSONB settings fields
    updates: dict = {}
    if payload.slack_channel is not None:
        updates["slack_channel"] = payload.slack_channel
    if payload.github_org is not None:
        updates["github_org"] = payload.github_org.strip()
    if payload.github_repos is not None:
        updates["github_repos"] = [r.strip() for r in payload.github_repos if r.strip()]
    if payload.slack_read_channels is not None:
        updates["slack_read_channels"] = [c.strip().lstrip("#") for c in payload.slack_read_channels if c.strip()]

    if updates:
        org.settings = {**org.settings, **updates}

    await db.flush()

    tz = payload.timezone or org.timezone
    dt = payload.digest_time or org.digest_time.strftime("%H:%M")
    await schedule_digest_for_org(org_id, dt, tz)

    return {"status": "updated"}


@router.get("/{org_id}/integrations")
async def get_integrations(org_id: str, db: AsyncSession = Depends(get_db_dep)):
    """Return connection status for all providers for this org."""
    result = await db.execute(
        select(Integration).where(Integration.org_id == uuid.UUID(org_id))
    )
    integrations = result.scalars().all()
    by_provider = {i.provider: i for i in integrations}

    def _status(provider: str) -> dict:
        i = by_provider.get(provider)
        if not i:
            return {"connected": False}
        return {
            "connected": True,
            "connected_at": i.connected_at.isoformat(),
            "metadata": i.metadata_,
        }

    return {
        "github": _status("github"),
        "slack": _status("slack"),
        "jira": _status("jira"),
    }


@router.delete("/{org_id}/integrations/{provider}", status_code=200)
async def disconnect_integration(
    org_id: str,
    provider: str,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    """Remove a provider integration (revokes stored token)."""
    result = await db.execute(
        select(Integration).where(
            Integration.org_id == uuid.UUID(org_id),
            Integration.provider == provider,
        )
    )
    integration = result.scalar_one_or_none()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    await db.delete(integration)
    await db.flush()
    return {"status": "disconnected", "provider": provider}


@router.post("/{org_id}/api-key/rotate", status_code=200)
async def rotate_api_key(
    org_id: str,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    """Invalidate the current API key and issue a new one. Returned exactly once."""
    result = await db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")

    new_key = generate_api_key()
    org.settings = {**org.settings, "api_key_hash": hash_api_key(new_key)}
    await db.flush()

    return {"api_key": new_key}


@router.post("/{org_id}/retention/run", status_code=202)
async def trigger_retention(
    org_id: str,
    _: str = Depends(get_current_org),
):
    """Manually trigger the 90-day retention cleanup scoped to this org."""
    from ..scheduler.retention import run_retention_cleanup
    counts = await run_retention_cleanup(org_id=org_id)
    return {"status": "ok", "deleted": counts}
