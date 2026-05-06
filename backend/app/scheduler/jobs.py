"""APScheduler job definitions."""

from ..ingestion.github_poller import poll_all_orgs
from ..ingestion.slack_poller import poll_all_orgs_slack


async def github_poll_job() -> None:
    await poll_all_orgs()


async def slack_poll_job() -> None:
    await poll_all_orgs_slack()
