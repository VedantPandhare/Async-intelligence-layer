"""week2: no schema changes — Slack/Jira integrations, OAuth, encryption added at Python layer

Revision ID: 002
Revises: 001
Create Date: 2026-05-06

"""
from typing import Sequence, Union

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # All Week 2 changes are Python-only (Slack poller, Jira webhook, OAuth flows,
    # Fernet encryption, DepConflict ORM model). The dep_conflicts table was already
    # created in migration 001.
    pass


def downgrade() -> None:
    pass
