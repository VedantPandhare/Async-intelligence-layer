"""Slack poller — polls message counts per developer every 15 minutes.
Full implementation in Week 2; this stub wires the scheduler entry point.
"""

from ..database import get_db
from ..models.integration import Integration
from sqlalchemy import select


async def poll_all_orgs_slack() -> None:
    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(Integration.provider == "slack")
        )
        integrations = result.scalars().all()

    for integration in integrations:
        try:
            await poll_slack_for_org(str(integration.org_id))
        except Exception as exc:
            print(f"[slack_poller] org {integration.org_id} failed: {exc}")


async def poll_slack_for_org(org_id: str) -> None:
    # TODO Week 2: implement Slack conversations.history polling
    pass
