"""Standalone background worker — runs APScheduler without the FastAPI HTTP server.

Used by the Render Background Worker service so the digest pipeline and pollers
run 24/7 without being subject to Render's free-tier web service sleep behaviour.

Start with:  python run_worker.py
"""

import asyncio
import logging
import sys

# Ensure the backend/ directory is on the path when invoked directly
sys.path.insert(0, ".")

from app.core.logging import configure_logging, get_logger
from app.database import init_db


async def main() -> None:
    configure_logging()
    logger = get_logger("worker")

    logger.info("worker starting — initialising database")
    await init_db()

    # Import scheduler after DB init (avoids premature settings reads)
    from app.scheduler.runner import scheduler, start_scheduler, schedule_digest_for_org
    from app.database import get_db
    from app.models.organization import Organization
    from sqlalchemy import select

    # Register all fixed-interval jobs (pollers + retention)
    start_scheduler()

    # Load every org and register its per-org digest cron
    async with get_db() as db:
        result = await db.execute(select(Organization))
        orgs = result.scalars().all()

    for org in orgs:
        await schedule_digest_for_org(
            str(org.id),
            org.digest_time.strftime("%H:%M"),
            org.timezone,
        )

    logger.info(
        "worker ready",
        extra={"orgs_scheduled": len(orgs), "scheduler_running": scheduler.running},
    )

    # Block forever — APScheduler runs on the event loop
    try:
        while True:
            await asyncio.sleep(3600)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("worker shutting down")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    asyncio.run(main())
