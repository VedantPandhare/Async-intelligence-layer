"""JWT token creation and verification, plus FastAPI dependency for protected routes."""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from ..config import get_settings

_bearer = HTTPBearer(auto_error=True)
_ALGORITHM = "HS256"
_TOKEN_TTL_HOURS = 24


def create_access_token(org_id: str, expires_hours: int = _TOKEN_TTL_HOURS) -> str:
    payload = {
        "sub": org_id,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=expires_hours),
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
