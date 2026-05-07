import uuid
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import get_current_org
from ..database import get_db_dep
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


@router.post("/", status_code=201)
async def create_org(payload: OrgCreate, db: AsyncSession = Depends(get_db_dep)):
    existing = await db.execute(select(Organization).where(Organization.slug == payload.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug already taken")

    from datetime import time
    h, m = (int(x) for x in payload.digest_time.split(":")[:2])
    org = Organization(
        id=uuid.uuid4(),
        name=payload.name,
        slug=payload.slug,
        digest_time=time(h, m),
        timezone=payload.timezone,
    )
    db.add(org)
    await db.flush()
    await schedule_digest_for_org(str(org.id), payload.digest_time, payload.timezone)
    return {"id": str(org.id), "slug": org.slug}


@router.get("/{org_id}/settings")
async def get_settings(org_id: str, db: AsyncSession = Depends(get_db_dep)):
    result = await db.execute(select(Organization).where(Organization.id == uuid.UUID(org_id)))
    org = result.scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Org not found")
    return {
        "id": str(org.id),
        "name": org.name,
        "slug": org.slug,
        "digest_time": org.digest_time.strftime("%H:%M"),
        "timezone": org.timezone,
        "settings": org.settings,
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
    if payload.slack_channel:
        org.settings = {**org.settings, "slack_channel": payload.slack_channel}

    await db.flush()

    tz = payload.timezone or org.timezone
    dt = payload.digest_time or org.digest_time.strftime("%H:%M")
    await schedule_digest_for_org(org_id, dt, tz)

    return {"status": "updated"}


@router.post("/{org_id}/retention/run", status_code=202)
async def trigger_retention(
    org_id: str,
    _: str = Depends(get_current_org),
):
    """Manually trigger the 90-day retention cleanup scoped to this org."""
    from ..scheduler.retention import run_retention_cleanup
    counts = await run_retention_cleanup(org_id=org_id)
    return {"status": "ok", "deleted": counts}
