"""week6: Next.js 14 dashboard frontend

Revision ID: 006
Revises: 005
Create Date: 2026-05-08

All Week 6 additions are frontend-only (no backend schema or code changes):
- frontend/app/layout.tsx             — root Next.js layout
- frontend/app/page.tsx               — root redirect (→ /dashboard or /login)
- frontend/app/login/page.tsx         — JWT login form (org_id + master secret)
- frontend/app/dashboard/layout.tsx   — sidebar navigation layout + AuthGuard
- frontend/app/dashboard/page.tsx     — today's digest with markdown rendering + pipeline trigger
- frontend/app/dashboard/digests/     — digest history list with sidebar selector
- frontend/app/dashboard/blockers/    — active blockers with one-click resolve
- frontend/app/dashboard/developers/  — developer list with opt-out/opt-in toggle
- frontend/app/dashboard/developers/[dev_id]/ — per-developer activity timeline
- frontend/app/dashboard/settings/    — org settings (digest time, timezone, Slack channel)
- frontend/components/                — Nav, AuthGuard, MarkdownRenderer, Spinner
- frontend/lib/api.ts                 — typed apiFetch wrapper with JWT header injection
- frontend/lib/auth.ts                — localStorage token/orgId helpers
- frontend/Dockerfile                 — multi-stage Node 20 image with standalone output
- docker-compose.yml                  — frontend service added on port 3000

No backend schema changes required.
"""
from typing import Sequence, Union

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
