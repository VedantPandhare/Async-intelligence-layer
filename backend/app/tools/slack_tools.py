"""Slack tools — stub for Week 2."""

from langchain_core.tools import tool


@tool
async def get_slack_thread(channel: str, thread_ts: str, token: str) -> list[dict]:
    """Fetch all replies in a Slack thread."""
    # TODO Week 2
    return []
