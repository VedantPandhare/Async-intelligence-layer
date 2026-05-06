"""LangChain tools wrapping GitHub REST API — used by agents for RAG lookups."""

import httpx
from langchain_core.tools import tool

from ..config import get_settings

settings = get_settings()


@tool
async def get_pr_details(repo: str, pr_number: int, token: str) -> dict:
    """Fetch full PR details including review status from GitHub API."""
    async with httpx.AsyncClient(
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
        timeout=15,
    ) as client:
        resp = await client.get(f"https://api.github.com/repos/{repo}/pulls/{pr_number}")
        resp.raise_for_status()
        return resp.json()


@tool
async def get_ci_status(repo: str, sha: str, token: str) -> list[dict]:
    """Fetch CI check runs for a given commit SHA."""
    async with httpx.AsyncClient(
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
        timeout=15,
    ) as client:
        resp = await client.get(
            f"https://api.github.com/repos/{repo}/commits/{sha}/check-runs"
        )
        resp.raise_for_status()
        return resp.json().get("check_runs", [])
