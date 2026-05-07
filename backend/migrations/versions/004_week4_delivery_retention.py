"""week4: Block Kit formatter, quiet hours, email delivery, retention cleanup

Revision ID: 004
Revises: 003
Create Date: 2026-05-07

All Week 4 additions are Python-only:
- delivery/block_kit.py        — Slack Block Kit rich formatter
- delivery/slack_delivery.py   — quiet hours enforcement, Block Kit integration,
                                  email fallback on Slack failure, decrypt tokens
- delivery/email_delivery.py   — full SendGrid implementation with HTML conversion
- scheduler/retention.py       — 90-day nightly cleanup (activity_events, blockers,
                                  dep_conflicts, digest content JSON)
- scheduler/jobs.py            — retention_cleanup_job registered at 03:00 UTC
- scheduler/runner.py          — Block Kit blocks passed to send_digest_to_channel
- api/orgs.py                  — POST /{org_id}/retention/run manual trigger
- config.py                    — sendgrid_api_key, email_from, event_retention_days
- .env.example                 — SENDGRID_API_KEY, EMAIL_FROM, EVENT_RETENTION_DAYS
- requirements.txt             — sendgrid==6.11.0 added

No schema changes required.
"""
from typing import Sequence, Union

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
