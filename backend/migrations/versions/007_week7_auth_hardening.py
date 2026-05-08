"""week7: JWT auth hardening, per-org API keys, refresh token rotation, CORS lockdown

Revision ID: 007
Revises: 006
Create Date: 2026-05-08

All Week 7 additions are Python-only (no schema changes):

Authentication hardening:
- core/security.py          — access tokens reduced to 15-min TTL
                               generate_api_key() / hash_api_key() / verify_api_key()
                               create_refresh_token() stores opaque token in Redis (7-day TTL)
                               rotate_refresh_token() atomically swaps old → new pair (getdel)
                               revoke_refresh_token() deletes from Redis
- core/limiter.py           — shared slowapi Limiter instance (200/min default)
- api/auth.py               — POST /auth/token now validates per-org hashed API key
                               (falls back to SECRET_KEY if no key set — dev mode)
                               POST /auth/refresh  — rotate refresh token
                               POST /auth/revoke   — logout / invalidate session
                               POST /auth/token rate-limited to 5/minute per IP
- api/orgs.py               — POST /org/ generates API key at creation, returns plaintext once
                               POST /{org_id}/api-key/rotate — invalidate + reissue key
                               GET /{org_id}/settings strips api_key_hash from public response

Infrastructure hardening:
- main.py                   — CORS lockdown: allow_origins from CORS_ORIGINS env var (no wildcard)
                               Security headers middleware: X-Content-Type-Options, X-Frame-Options,
                               X-XSS-Protection, Referrer-Policy, HSTS (production only)
- config.py                 — cors_origins: str = "http://localhost:3000,http://localhost:8000"
- .env.example              — CORS_ORIGINS documented

Frontend:
- frontend/lib/api.ts       — automatic token refresh on 401 with single in-flight promise guard
- frontend/lib/auth.ts      — clearAuth() also removes refresh_token from localStorage
- frontend/app/login/       — stores refresh_token from /auth/token response

No schema changes required.
"""
from typing import Sequence, Union

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
