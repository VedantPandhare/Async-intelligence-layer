"""JWT tokens, API key hashing, and refresh token rotation via Redis."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from ..config import get_settings

_bearer = HTTPBearer(auto_error=True)
_ALGORITHM = "HS256"
_ACCESS_TTL_MINUTES = 15
_REFRESH_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


# ─── Access tokens ────────────────────────────────────────────────────────────

def create_access_token(org_id: str, expires_minutes: int = _ACCESS_TTL_MINUTES) -> str:
    payload = {
        "sub": org_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, get_settings().jwt_secret, algorithm=_ALGORITHM)


def decode_token(token: str) -> str:
    """Return org_id from a valid JWT, or raise 401."""
    try:
        data = jwt.decode(token, get_settings().jwt_secret, algorithms=[_ALGORITHM])
        org_id: str | None = data.get("sub")
        if not org_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return org_id
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalid or expired: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def get_current_org(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> str:
    """FastAPI dependency — returns the org_id embedded in the Bearer JWT."""
    return decode_token(credentials.credentials)


# ─── Refresh tokens ───────────────────────────────────────────────────────────

async def create_refresh_token(org_id: str) -> str:
    """Mint an opaque refresh token and store it in Redis with a 7-day TTL."""
    from ..core.redis_client import get_redis
    token = secrets.token_urlsafe(48)
    await get_redis().setex(f"refresh:{token}", _REFRESH_TTL_SECONDS, org_id)
    return token


async def rotate_refresh_token(old_token: str) -> tuple[str, str] | None:
    """Atomically swap an old refresh token for a new access + refresh pair.

    Returns (access_token, refresh_token) or None if the token is unknown/expired.
    """
    from ..core.redis_client import get_redis
    org_id: str | None = await get_redis().getdel(f"refresh:{old_token}")
    if not org_id:
        return None
    return create_access_token(org_id), await create_refresh_token(org_id)


async def revoke_refresh_token(token: str) -> bool:
    from ..core.redis_client import get_redis
    return bool(await get_redis().delete(f"refresh:{token}"))


# ─── Per-org API keys ─────────────────────────────────────────────────────────

_KEY_PREFIX = "asi_"


def generate_api_key() -> str:
    """Generate a new plaintext API key. Return to caller once — never store plaintext."""
    return f"{_KEY_PREFIX}{secrets.token_urlsafe(32)}"


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def verify_api_key(key: str, stored_hash: str) -> bool:
    """Constant-time comparison to prevent timing attacks."""
    return hmac.compare_digest(hash_api_key(key), stored_hash)
