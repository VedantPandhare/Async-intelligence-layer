import hashlib
import hmac
import uuid

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select

from ...database import get_db
from ...ingestion.embedder import embed_and_store_event
from ...ingestion.normalizer import (
    normalize_github_ci_run,
    normalize_github_commit,
    normalize_github_pr,
    store_event,
)
from ...models.developer import Developer
from ...models.integration import Integration

router = APIRouter(tags=["webhooks"])


async def _resolve_developer(email: str, org_id: uuid.UUID):
    async with get_db() as db:
        result = await db.execute(
            select(Developer).where(
                Developer.org_id == org_id,
                Developer.email == email,
            )
        )
        return result.scalar_one_or_none()


@router.post("/webhooks/github/{org_id}")
async def github_webhook(
    org_id: str,
    request: Request,
    x_hub_signature_256: str | None = Header(None),
):
    body = await request.body()

    # Verify HMAC-SHA256 signature
    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(
                Integration.org_id == uuid.UUID(org_id),
                Integration.provider == "github",
            )
        )
        integration = result.scalar_one_or_none()

    if integration and integration.webhook_secret and x_hub_signature_256:
        expected = "sha256=" + hmac.new(
            integration.webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(x_hub_signature_256, expected):
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event", "")
    org_uuid = uuid.UUID(org_id)

    if event_type == "push":
        repo = payload.get("repository", {}).get("full_name", "")
        for commit in payload.get("commits", []):
            author_email = commit.get("author", {}).get("email", "")
            dev = await _resolve_developer(author_email, org_uuid)
            if not dev:
                continue
            commit["repo"] = repo
            async with get_db() as db:
                event = normalize_github_commit(commit, str(dev.id), org_id)
                record = await store_event(event, db)
                await embed_and_store_event(event, record.id, db)

    elif event_type == "pull_request":
        sender_login = payload.get("sender", {}).get("login", "")
        async with get_db() as db:
            result = await db.execute(
                select(Developer).where(
                    Developer.org_id == org_uuid,
                    Developer.github_username == sender_login,
                )
            )
            dev = result.scalar_one_or_none()
        if dev:
            payload["repo"] = payload.get("repository", {}).get("full_name", "")
            async with get_db() as db:
                event = normalize_github_pr(payload, str(dev.id), org_id)
                record = await store_event(event, db)
                await embed_and_store_event(event, record.id, db)

    elif event_type == "check_run":
        sender_login = payload.get("sender", {}).get("login", "")
        async with get_db() as db:
            result = await db.execute(
                select(Developer).where(
                    Developer.org_id == org_uuid,
                    Developer.github_username == sender_login,
                )
            )
            dev = result.scalar_one_or_none()
        if dev:
            payload["repo"] = payload.get("repository", {}).get("full_name", "")
            async with get_db() as db:
                event = normalize_github_ci_run(payload, str(dev.id), org_id)
                record = await store_event(event, db)
                await embed_and_store_event(event, record.id, db)

    return {"status": "ok"}
