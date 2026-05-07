"""Persists LangGraph pipeline output (blockers, dep_conflicts) to the database."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models.blocker import Blocker
from ..models.dep_conflict import DepConflict
from ..models.developer import Developer
from .state import AgentState


async def persist_pipeline_results(state: AgentState) -> None:
    """
    Called after pipeline.ainvoke() completes.
    Saves inferred blockers and dependency conflicts to the DB.
    Skips rows that would be exact duplicates of unresolved ones detected today.
    """
    org_id = uuid.UUID(state["org_id"])
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_db() as db:
        # Build a name → UUID map for developers
        devs_result = await db.execute(
            select(Developer).where(Developer.org_id == org_id)
        )
        developers = devs_result.scalars().all()
        name_to_id = {d.name: d.id for d in developers}
        id_to_uuid = {str(d.id): d.id for d in developers}

        await _persist_blockers(db, state, org_id, id_to_uuid, today_start, now)
        await _persist_conflicts(db, state, org_id, name_to_id, today_start, now)


async def _persist_blockers(
    db: AsyncSession,
    state: AgentState,
    org_id: uuid.UUID,
    id_to_uuid: dict,
    today_start: datetime,
    now: datetime,
) -> None:
    for b in state.get("blockers", []):
        dev_uuid = id_to_uuid.get(b.get("developer_id"))
        if not dev_uuid:
            continue

        # Skip if an identical unresolved blocker was already logged today
        existing = await db.execute(
            select(Blocker).where(
                Blocker.developer_id == dev_uuid,
                Blocker.org_id == org_id,
                Blocker.blocker_type == b.get("blocker_type"),
                Blocker.resolved_at.is_(None),
                Blocker.detected_at >= today_start,
            )
        )
        if existing.scalar_one_or_none():
            continue

        blocker = Blocker(
            id=uuid.uuid4(),
            developer_id=dev_uuid,
            org_id=org_id,
            detected_at=now,
            blocker_type=b.get("blocker_type"),
            severity=b.get("severity"),
            description=b.get("description"),
            signals={"evidence": b.get("signals", []), "suggested_action": b.get("suggested_action")},
        )
        db.add(blocker)


async def _persist_conflicts(
    db: AsyncSession,
    state: AgentState,
    org_id: uuid.UUID,
    name_to_id: dict,
    today_start: datetime,
    now: datetime,
) -> None:
    for c in state.get("conflicts", []):
        dev_a_id = name_to_id.get(c.get("developer_a"))
        dev_b_id = name_to_id.get(c.get("developer_b"))
        if not dev_a_id or not dev_b_id:
            continue

        # Skip if already recorded today between the same pair
        existing = await db.execute(
            select(DepConflict).where(
                DepConflict.org_id == org_id,
                DepConflict.developer_a_id == dev_a_id,
                DepConflict.developer_b_id == dev_b_id,
                DepConflict.resolved.is_(False),
                DepConflict.detected_at >= today_start,
            )
        )
        if existing.scalar_one_or_none():
            continue

        conflict = DepConflict(
            id=uuid.uuid4(),
            org_id=org_id,
            developer_a_id=dev_a_id,
            developer_b_id=dev_b_id,
            detected_at=now,
            conflict_type=c.get("conflict_type"),
            details={
                "files_or_services": c.get("files_or_services", []),
                "risk": c.get("risk"),
            },
        )
        db.add(conflict)
