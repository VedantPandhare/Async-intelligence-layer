"""Jira webhook receiver — handles issue update events."""

import uuid

from fastapi import APIRouter, Request
from sqlalchemy import select

from ...database import get_db
from ...ingestion.embedder import embed_and_store_event
from ...ingestion.normalizer import normalize_jira_issue, store_event
from ...models.developer import Developer

router = APIRouter(tags=["webhooks"])


@router.post("/webhooks/jira/{org_id}")
async def jira_webhook(org_id: str, request: Request):
    payload = await request.json()

    event_type = payload.get("webhookEvent", "")
    if "issue" not in event_type:
        return {"status": "ignored"}

    issue = payload.get("issue", {})
    fields = issue.get("fields", {})

    # Try to resolve developer by Jira accountId on the assignee
    assignee = fields.get("assignee") or {}
    account_id = assignee.get("accountId")
    if not account_id:
        return {"status": "ok"}

    org_uuid = uuid.UUID(org_id)
    async with get_db() as db:
        result = await db.execute(
            select(Developer).where(
                Developer.org_id == org_uuid,
                Developer.jira_account_id == account_id,
                Developer.is_active.is_(True),
            )
        )
        dev = result.scalar_one_or_none()

    if not dev:
        return {"status": "ok"}

    async with get_db() as db:
        event = normalize_jira_issue(payload, str(dev.id), org_id)
        record = await store_event(event, db)
        try:
            await embed_and_store_event(event, record.id, db)
        except Exception as exc:
            print(f"[jira_webhook] embed failed: {exc}")

    return {"status": "ok"}
