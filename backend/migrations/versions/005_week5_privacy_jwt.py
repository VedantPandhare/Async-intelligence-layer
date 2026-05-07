"""week5: Privacy controls, JWT authentication, Redis OAuth state, structured logging

Revision ID: 005
Revises: 004
Create Date: 2026-05-07

All Week 5 additions are Python-only (no schema changes):
- core/redis_client.py        — shared async Redis client singleton
- core/security.py            — JWT creation/verification, get_current_org dependency
- core/logging.py             — structured JSON logging via python-json-logger
- api/auth.py                 — OAuth CSRF state moved from in-memory dict to Redis (TTL 600s)
                                 POST /auth/token endpoint issues 24-hour JWTs
- api/developers.py           — PATCH /{org_id}/{dev_id}/opt-out  sets is_active=False
                                 PATCH /{org_id}/{dev_id}/opt-in   sets is_active=True
                                 POST /{org_id} protected by get_current_org
- api/digests.py              — POST /{org_id}/trigger protected by get_current_org
                                 PATCH /blockers/{id}/resolve protected by get_current_org
- api/orgs.py                 — PATCH /{org_id}/settings protected by get_current_org
                                 POST /{org_id}/retention/run protected by get_current_org
- main.py                     — configure_logging() called on startup
- requirements.txt            — python-json-logger==2.0.7 added

No schema changes required.
"""
from typing import Sequence, Union

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
