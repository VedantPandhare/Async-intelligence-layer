"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-05-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("digest_time", sa.Time, nullable=False, server_default="09:00:00"),
        sa.Column("timezone", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("settings", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "developers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255)),
        sa.Column("github_username", sa.String(100)),
        sa.Column("slack_user_id", sa.String(100)),
        sa.Column("jira_account_id", sa.String(100)),
        sa.Column("role", sa.String(100)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )

    op.create_table(
        "integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("access_token", sa.Text),
        sa.Column("refresh_token", sa.Text),
        sa.Column("webhook_secret", sa.Text),
        sa.Column("metadata", postgresql.JSON, server_default="{}"),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.UniqueConstraint("org_id", "provider", name="uq_integration_org_provider"),
    )

    op.create_table(
        "activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("developer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSON, nullable=False),
        sa.Column("summary", sa.String(500)),
        sa.Column("embedding", Vector(768)),
        sa.Column("ingested_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("idx_activity_developer_time", "activity_events", ["developer_id", "event_time"])
    op.create_index("idx_activity_org_time", "activity_events", ["org_id", "event_time"])
    op.create_index("idx_activity_source", "activity_events", ["source", "event_type"])

    op.create_table(
        "digests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("digest_date", sa.Date, nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("content", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("markdown_output", sa.Text),
        sa.Column("slack_ts", sa.String(100)),
        sa.Column("delivered", sa.Boolean, nullable=False, server_default="false"),
        sa.UniqueConstraint("org_id", "digest_date", name="uq_digest_org_date"),
    )

    op.create_table(
        "blockers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("developer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("blocker_type", sa.String(100)),
        sa.Column("severity", sa.String(20)),
        sa.Column("description", sa.Text),
        sa.Column("signals", postgresql.JSON),
        sa.Column("intervention_sent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("intervention_at", sa.DateTime(timezone=True)),
        sa.Column("intervention_content", sa.Text),
    )

    op.create_table(
        "dep_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("developer_a_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("developer_b_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("developers.id"), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("conflict_type", sa.String(100)),
        sa.Column("details", postgresql.JSON),
        sa.Column("resolved", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_table("dep_conflicts")
    op.drop_table("blockers")
    op.drop_table("digests")
    op.drop_table("activity_events")
    op.drop_table("integrations")
    op.drop_table("developers")
    op.drop_table("organizations")
