"""OAuth callback stubs — full implementation in Week 7."""

from fastapi import APIRouter

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/github/callback")
async def github_callback(code: str, state: str | None = None):
    # TODO Week 7: exchange code for token, store in integrations table
    return {"status": "not_implemented"}


@router.get("/slack/callback")
async def slack_callback(code: str, state: str | None = None):
    # TODO Week 7
    return {"status": "not_implemented"}


@router.get("/jira/callback")
async def jira_callback(code: str, state: str | None = None):
    # TODO Week 7
    return {"status": "not_implemented"}
