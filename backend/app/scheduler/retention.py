"""Nightly job that deletes activity_events older than EVENT_RETENTION_DAYS (default 90)."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from ..config import get_settings
from ..core.logging import get_logger
from ..database import get_db
from ..models.activity_event import ActivityEvent
from ..models.blocker import Blocker
from ..models.dep_conflict import DepConflict
from ..models.digest import Digest

settings = get_settings()
logger = get_logger(__name__)


async def run_retention_cleanup(org_id: str | None = None) -> dict:
    """
    Deletes rows older than EVENT_RETENTION_DAYS.
    Pass org_id to scope cleanup to one org; omit for global nightly run.

    Cleans:
    - activity_events  — hard delete
    - resolved blockers — hard delete
    - resolved dep_conflicts — hard delete
    - old digests — strips content JSON, keeps markdown
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.event_retention_days)
    counts: dict[str, int] = {}

    # Build optional org filter
    org_uuid = uuid.UUID(org_id) if org_id else None

    async with get_db() as db:
        # activity_events
        stmt = delete(ActivityEvent).where(ActivityEvent.event_time < cutoff)
        if org_uuid:
            stmt = stmt.where(ActivityEvent.org_id == org_uuid)
        result = await db.execute(stmt)
        counts["activity_events"] = result.rowcount

        # resolved blockers
        stmt = delete(Blocker).where(
            Blocker.detected_at < cutoff,
            Blocker.resolved_at.isnot(None),
        )
        if org_uuid:
            stmt = stmt.where(Blocker.org_id == org_uuid)
        result = await db.execute(stmt)
        counts["blockers"] = result.rowcount

        # resolved dep_conflicts
        stmt = delete(DepConflict).where(
            DepConflict.detected_at < cutoff,
            DepConflict.resolved.is_(True),
        )
        if org_uuid:
            stmt = stmt.where(DepConflict.org_id == org_uuid)
        result = await db.execute(stmt)
        counts["dep_conflicts"] = result.rowcount

        # digests — strip content JSON, keep markdown
        digest_stmt = select(Digest).where(Digest.generated_at < cutoff)
        if org_uuid:
            digest_stmt = digest_stmt.where(Digest.org_id == org_uuid)
        old_digests = await db.execute(digest_stmt)
        stripped = 0
        for digest in old_digests.scalars():
            if digest.content:
                digest.content = {}
                stripped += 1
        counts["digests_stripped"] = stripped

    scope = f"org={org_id}" if org_id else "global"
    logger.info("retention cleanup complete", extra={"scope": scope, **counts})
    return counts
