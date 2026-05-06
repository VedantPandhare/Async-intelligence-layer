"""Jira webhook receiver — stub for Week 2."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/jira/{org_id}")
async def jira_webhook(org_id: str, request: Request):
    # TODO Week 2: verify JWT, normalize Jira issue events
    return {"status": "ok"}
