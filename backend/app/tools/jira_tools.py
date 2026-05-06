"""Jira tools — stub for Week 2."""

from langchain_core.tools import tool


@tool
async def get_jira_issue(issue_key: str, domain: str, token: str) -> dict:
    """Fetch a Jira issue by key."""
    # TODO Week 2
    return {}
