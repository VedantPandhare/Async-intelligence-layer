"""APScheduler job definitions."""

from ..ingestion.github_poller import poll_all_orgs
from ..ingestion.jira_poller import poll_all_orgs_jira
from ..ingestion.slack_poller import poll_all_orgs_slack
from .retention import run_retention_cleanup


async def github_poll_job() -> None:
    await poll_all_orgs()


async def slack_poll_job() -> None:
    await poll_all_orgs_slack()


async def jira_poll_job() -> None:
    await poll_all_orgs_jira()


async def retention_cleanup_job() -> None:
    await run_retention_cleanup()
