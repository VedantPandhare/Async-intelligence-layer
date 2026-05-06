"""Slack Events API webhook receiver — stub for Week 2."""

import hashlib
import hmac
import time

from fastapi import APIRouter, Header, HTTPException, Request

from ...config import get_settings

router = APIRouter(tags=["webhooks"])
settings = get_settings()


@router.post("/webhooks/slack/{org_id}")
async def slack_webhook(
    org_id: str,
    request: Request,
    x_slack_signature: str | None = Header(None),
    x_slack_request_timestamp: str | None = Header(None),
):
    body = await request.body()

    # Verify Slack signing secret
    if settings.slack_signing_secret and x_slack_signature and x_slack_request_timestamp:
        base = f"v0:{x_slack_request_timestamp}:{body.decode()}"
        expected = "v0=" + hmac.new(
            settings.slack_signing_secret.encode(), base.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(x_slack_signature, expected):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    payload = await request.json()

    # URL verification challenge (Slack requires this on first setup)
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    # TODO Week 2: handle message events, normalize, store
    return {"status": "ok"}
