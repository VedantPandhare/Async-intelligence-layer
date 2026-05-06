import uuid
from datetime import date

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .jobs import github_poll_job, slack_poll_job

scheduler = AsyncIOScheduler(timezone="UTC")


def start_scheduler() -> None:
    scheduler.add_job(github_poll_job, "interval", minutes=15, id="github_poller", replace_existing=True)
    scheduler.add_job(slack_poll_job, "interval", minutes=15, id="slack_poller", replace_existing=True)
    scheduler.start()


async def schedule_digest_for_org(org_id: str, digest_time: str, timezone: str) -> None:
    """Register a per-org daily digest job. Called when an org is onboarded or settings change."""
    hour, minute = (int(x) for x in digest_time.split(":")[:2])

    async def _run_digest():
        from ..agents.graph import pipeline
        from ..database import get_db
        from ..models.digest import Digest

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

        async with get_db() as db:
            digest = Digest(
                id=uuid.uuid4(),
                org_id=uuid.UUID(org_id),
                digest_date=date.today(),
                content=result,
                markdown_output=result.get("final_digest", ""),
            )
            db.add(digest)

        if result.get("final_digest"):
            from ..delivery.slack_delivery import send_digest_to_channel
            await send_digest_to_channel(org_id, result["final_digest"])

    scheduler.add_job(
        _run_digest,
        "cron",
        hour=hour,
        minute=minute,
        timezone=timezone,
        id=f"digest_{org_id}",
        replace_existing=True,
    )
