"""OAuth2 callback handlers for GitHub, Slack, and Jira integrations.
Exposes JWT issuance, refresh token rotation, and revocation endpoints.
"""

import secrets
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select

from ..config import get_settings
from ..core.analytics import track
from ..core.encryption import encrypt_token
from ..core.limiter import limiter
from ..core.logging import get_logger
from ..core.redis_client import get_redis
from ..core.security import (
    create_access_token,
    create_refresh_token,
    revoke_refresh_token,
    rotate_refresh_token,
    verify_api_key,
)
from ..database import get_db
from ..models.integration import Integration
from ..models.organization import Organization

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger = get_logger(__name__)

_STATE_TTL = 600  # seconds


# ─── JWT issuance ─────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    org_id: str
    secret: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/token")
@limiter.limit("5/minute")
async def issue_token(request: Request, payload: TokenRequest):
    """Exchange org_id + API key (or master secret in dev) for a 15-min JWT + 7-day refresh token."""
    async with get_db() as db:
        result = await db.execute(
            select(Organization).where(Organization.id == uuid.UUID(payload.org_id))
        )
        org = result.scalar_one_or_none()

    if not org:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    stored_hash: str | None = org.settings.get("api_key_hash")

    if stored_hash:
        # Per-org API key is set — validate against stored hash
        if not verify_api_key(payload.secret, stored_hash):
            logger.warning("failed auth attempt", extra={"org_id": payload.org_id, "ip": request.client.host if request.client else "unknown"})
            raise HTTPException(status_code=401, detail="Invalid credentials")
    else:
        # No per-org key yet — fall back to master secret (dev mode)
        if payload.secret != settings.secret_key:
            raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(org.id.__str__())
    refresh_token = await create_refresh_token(str(org.id))
    track("user_login", str(org.id), {"org_slug": org.slug})

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 900,  # 15 minutes
        "refresh_token": refresh_token,
    }


@router.post("/refresh")
async def refresh_token_endpoint(payload: RefreshRequest):
    """Rotate a refresh token — returns a new access token and a new refresh token.
    The old refresh token is invalidated immediately (one-time use)."""
    result = await rotate_refresh_token(payload.refresh_token)
    if not result:
        raise HTTPException(status_code=401, detail="Refresh token invalid or expired")
    access_token, new_refresh = result
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": 900,
        "refresh_token": new_refresh,
    }


@router.post("/revoke")
async def revoke_token_endpoint(payload: RefreshRequest):
    """Revoke a refresh token — effectively logs out the session."""
    await revoke_refresh_token(payload.refresh_token)
    return {"status": "revoked"}


# ─── GitHub ───────────────────────────────────────────────────────────────────

@router.get("/github/connect/{org_id}")
async def github_connect(org_id: str):
    state = secrets.token_urlsafe(32)
    redis = get_redis()
    await redis.setex(f"oauth_state:{state}", _STATE_TTL, org_id)
    url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={settings.github_client_id}"
        f"&scope=repo,read:org"
        f"&state={state}"
    )
    return {"authorization_url": url}


@router.get("/github/callback")
async def github_callback(code: str, state: str = Query(...)):
    org_id = await _pop_state(state)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        data = resp.json()

    access_token = data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail=f"GitHub OAuth failed: {data}")

    await _upsert_integration(
        org_id=org_id,
        provider="github",
        access_token=access_token,
        metadata={"scope": data.get("scope", "")},
    )
    track("integration_connected", org_id, {"provider": "github"})
    return {"status": "connected", "provider": "github", "org_id": org_id}


# ─── Slack ────────────────────────────────────────────────────────────────────

@router.get("/slack/connect/{org_id}")
async def slack_connect(org_id: str):
    state = secrets.token_urlsafe(32)
    redis = get_redis()
    await redis.setex(f"oauth_state:{state}", _STATE_TTL, org_id)
    scopes = "channels:history,channels:read,chat:write,users:read,im:write"
    url = (
        f"https://slack.com/oauth/v2/authorize"
        f"?client_id={settings.github_client_id}"
        f"&scope={scopes}"
        f"&state={state}"
    )
    return {"authorization_url": url}


@router.get("/slack/callback")
async def slack_callback(code: str, state: str = Query(...)):
    org_id = await _pop_state(state)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "code": code,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    if not data.get("ok"):
        raise HTTPException(status_code=400, detail=f"Slack OAuth failed: {data.get('error')}")

    access_token = data["access_token"]
    workspace_id = data.get("team", {}).get("id")

    await _upsert_integration(
        org_id=org_id,
        provider="slack",
        access_token=access_token,
        metadata={"workspace_id": workspace_id, "team_name": data.get("team", {}).get("name")},
    )
    track("integration_connected", org_id, {"provider": "slack"})
    return {"status": "connected", "provider": "slack", "org_id": org_id}


# ─── Jira ─────────────────────────────────────────────────────────────────────

@router.get("/jira/connect/{org_id}")
async def jira_connect(org_id: str):
    state = secrets.token_urlsafe(32)
    redis = get_redis()
    await redis.setex(f"oauth_state:{state}", _STATE_TTL, org_id)
    url = (
        f"https://auth.atlassian.com/authorize"
        f"?audience=api.atlassian.com"
        f"&client_id={settings.jira_client_id}"
        f"&scope=read:jira-work"
        f"&redirect_uri={settings.base_url}/auth/jira/callback"
        f"&state={state}"
        f"&response_type=code"
        f"&prompt=consent"
    )
    return {"authorization_url": url}


@router.get("/jira/callback")
async def jira_callback(code: str, state: str = Query(...)):
    org_id = await _pop_state(state)

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://auth.atlassian.com/oauth/token",
            json={
                "grant_type": "authorization_code",
                "client_id": settings.jira_client_id,
                "client_secret": settings.jira_client_secret,
                "code": code,
                "redirect_uri": f"{settings.base_url}/auth/jira/callback",
            },
        )
        resp.raise_for_status()
        data = resp.json()

    await _upsert_integration(
        org_id=org_id,
        provider="jira",
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token", ""),
        metadata={"expires_in": data.get("expires_in")},
    )
    track("integration_connected", org_id, {"provider": "jira"})
    return {"status": "connected", "provider": "jira", "org_id": org_id}


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _pop_state(state: str) -> str:
    redis = get_redis()
    org_id = await redis.getdel(f"oauth_state:{state}")
    if not org_id:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    return org_id


async def _upsert_integration(
    org_id: str,
    provider: str,
    access_token: str,
    refresh_token: str = "",
    metadata: dict | None = None,
) -> None:
    async with get_db() as db:
        result = await db.execute(
            select(Integration).where(
                Integration.org_id == uuid.UUID(org_id),
                Integration.provider == provider,
            )
        )
        existing = result.scalar_one_or_none()

        enc_access = encrypt_token(access_token)
        enc_refresh = encrypt_token(refresh_token) if refresh_token else None

        if existing:
            existing.access_token = enc_access
            if enc_refresh:
                existing.refresh_token = enc_refresh
            if metadata:
                existing.metadata_ = {**existing.metadata_, **metadata}
        else:
            integration = Integration(
                id=uuid.uuid4(),
                org_id=uuid.UUID(org_id),
                provider=provider,
                access_token=enc_access,
                refresh_token=enc_refresh,
                metadata_=metadata or {},
            )
            db.add(integration)
