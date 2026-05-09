import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.graph import pipeline
from ..agents.persist import persist_pipeline_results
from ..core.analytics import track
from ..core.security import get_current_org
from ..database import get_db_dep
from ..models.digest import Digest

router = APIRouter(prefix="/digests", tags=["digests"])


@router.get("/{org_id}")
async def list_digests(org_id: str, limit: int = 10, db: AsyncSession = Depends(get_db_dep)):
    result = await db.execute(
        select(Digest)
        .where(Digest.org_id == uuid.UUID(org_id))
        .order_by(Digest.digest_date.desc())
        .limit(limit)
    )
    digests = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "digest_date": d.digest_date.isoformat(),
            "generated_at": d.generated_at.isoformat(),
            "delivered": d.delivered,
            "markdown_output": d.markdown_output,
        }
        for d in digests
    ]


@router.get("/{org_id}/today")
async def get_today_digest(org_id: str, db: AsyncSession = Depends(get_db_dep)):
    result = await db.execute(
        select(Digest).where(
            Digest.org_id == uuid.UUID(org_id),
            Digest.digest_date == date.today(),
        )
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail="No digest generated yet for today")
    return {
        "id": str(digest.id),
        "digest_date": digest.digest_date.isoformat(),
        "markdown_output": digest.markdown_output,
        "content": digest.content,
        "delivered": digest.delivered,
    }


@router.post("/{org_id}/trigger", status_code=202)
async def trigger_digest(
    org_id: str,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    """Manually kick off the LangGraph pipeline for testing."""
    initial_state = {
        "org_id": org_id,
        "digest_date": date.today().isoformat(),
        "developer_signals": [],
        "blockers": [],
        "conflicts": [],
        "developer_narratives": {},
        "sprint_risk": "",
        "final_digest": None,
        "errors": [],
        "should_intervene": False,
    }
    result = await pipeline.ainvoke(initial_state)

    await persist_pipeline_results(result)

    digest = Digest(
        id=uuid.uuid4(),
        org_id=uuid.UUID(org_id),
        digest_date=date.today(),
        content=result,
        markdown_output=result.get("final_digest", ""),
    )
    db.add(digest)
    await db.flush()

    blockers_found = len(result.get("blockers", []))
    track("digest_generated", org_id, {
        "blockers_found": blockers_found,
        "conflicts_found": len(result.get("conflicts", [])),
        "has_errors": bool(result.get("errors")),
        "triggered_manually": True,
    })
    if blockers_found:
        track("blocker_detected", org_id, {"count": blockers_found})

    return {
        "id": str(digest.id),
        "markdown_output": digest.markdown_output,
        "blockers_found": blockers_found,
        "conflicts_found": len(result.get("conflicts", [])),
        "errors": result.get("errors", []),
    }


@router.get("/{org_id}/blockers")
async def list_blockers(org_id: str, db: AsyncSession = Depends(get_db_dep)):
    from ..models.blocker import Blocker
    result = await db.execute(
        select(Blocker)
        .where(Blocker.org_id == uuid.UUID(org_id), Blocker.resolved_at.is_(None))
        .order_by(Blocker.detected_at.desc())
    )
    blockers = result.scalars().all()
    return [
        {
            "id": str(b.id),
            "developer_id": str(b.developer_id),
            "severity": b.severity,
            "blocker_type": b.blocker_type,
            "description": b.description,
            "detected_at": b.detected_at.isoformat(),
            "intervention_sent": b.intervention_sent,
        }
        for b in blockers
    ]


@router.patch("/blockers/{blocker_id}/resolve")
async def resolve_blocker(
    blocker_id: str,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    from datetime import datetime, timezone
    from ..models.blocker import Blocker
    result = await db.execute(select(Blocker).where(Blocker.id == uuid.UUID(blocker_id)))
    blocker = result.scalar_one_or_none()
    if not blocker:
        raise HTTPException(status_code=404, detail="Blocker not found")
    blocker.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return {"status": "resolved"}
