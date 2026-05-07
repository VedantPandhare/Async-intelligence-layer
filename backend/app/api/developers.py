import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import get_current_org
from ..database import get_db_dep
from ..models.activity_event import ActivityEvent
from ..models.developer import Developer

router = APIRouter(prefix="/developers", tags=["developers"])


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
