"""OAuth2 callback handlers for GitHub, Slack, and Jira integrations.
Also exposes POST /auth/token for API consumers to exchange org credentials for a JWT.
"""

import secrets
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select

from ..config import get_settings
from ..core.encryption import encrypt_token
from ..core.redis_client import get_redis
from ..core.security import create_access_token
from ..database import get_db
from ..models.integration import Integration

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

_STATE_TTL = 600  # seconds


# ─── JWT token issuance ────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    org_id: str
    secret: str


@router.post("/token")
async def issue_token(payload: TokenRequest):
    """Exchange org_id + master secret for a 24-hour JWT.

    In production this is replaced by full per-org API keys (Week 7).
    """
    if payload.secret != settings.secret_key:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(payload.org_id)
    return {"access_token": token, "token_type": "bearer", "expires_in": 86400}


# ─── GitHub ───────────────────────────────────────────────────────────────────

@router.get("/github/connect/{org_id}")
async def github_connect(org_id: str):
    """Generate GitHub OAuth URL for the org to initiate the flow."""
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
        f"&scope=read:jira-data"
        f"&redirect_uri=http://localhost:8000/auth/jira/callback"
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
                "redirect_uri": "http://localhost:8000/auth/jira/callback",
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
    return {"status": "connected", "provider": "jira", "org_id": org_id}


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _pop_state(state: str) -> str:
    """Retrieve and delete the org_id stored for this OAuth state token."""
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
    """Insert or update an integration row with encrypted tokens."""
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
