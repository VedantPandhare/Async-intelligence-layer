"""week3: Jira poller, retry logic, rate limiting, blocker+conflict persistence

Revision ID: 003
Revises: 002
Create Date: 2026-05-07

All Week 3 additions are Python-only:
- ingestion/jira_poller.py    — active 15-min Jira REST polling
- ingestion/retry.py          — exponential backoff for all HTTP calls
- agents/persist.py           — saves blockers + dep_conflicts to DB post-pipeline
- main.py                     — slowapi rate limiting (200 req/min default)
- scheduler/runner.py         — stores slack_ts + delivered flag on digest row
- requirements.txt            — slowapi==0.1.9 added

No schema changes required (all tables were created in migration 001).
"""
from typing import Sequence, Union

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
