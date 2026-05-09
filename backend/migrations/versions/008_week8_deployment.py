"""week8: deployment infrastructure, analytics, Slack slash commands, production support

Revision ID: 008
Revises: 007
Create Date: 2026-05-09

All Week 8 additions are Python-only (no schema changes):

Deployment infrastructure:
- render.yaml               — Render Web Service (uvicorn) + Background Worker (run_worker.py)
                               Web service buildCommand: pip install + alembic upgrade head
                               All env vars marked sync: false (set in Render dashboard)
- backend/run_worker.py     — Standalone asyncio entry point for Render Background Worker
                               Loads all orgs, registers per-org digest crons, runs APScheduler
                               forever without an HTTP server
- frontend/vercel.json      — Vercel deployment config: framework nextjs, security headers,
                               /api/* rewrites to production backend URL

Qdrant Cloud support:
- config.py                 — Added qdrant_url, qdrant_api_key, base_url, frontend_url,
                               posthog_api_key fields
- ingestion/embedder.py     — get_qdrant_client() checks QDRANT_URL first (Qdrant Cloud),
                               falls back to QDRANT_HOST:QDRANT_PORT for local Docker

Analytics (PostHog):
- core/analytics.py         — Fire-and-forget PostHog wrapper; no-op when POSTHOG_API_KEY unset
                               track(event, org_id, properties) used throughout
- api/auth.py               — track("user_login") after token issuance
                               track("integration_connected", provider=...) after each OAuth callback
- api/digests.py            — track("digest_generated") after pipeline trigger
                               track("blocker_detected") for each new blocker found
- api/slack_commands.py     — track("digest_generated", triggered_by="slack_command")

Slack slash commands:
- api/slack_commands.py     — POST /slack/commands handler for /standup [trigger|blockers|me|help]
                               HMAC-SHA256 signature verification (300-second replay window)
                               team_id → org_id resolution via integrations table
                               /standup trigger  — asyncio.create_task pipeline run, immediate ack
                               /standup blockers — list active (unresolved) blockers with severity emoji
                               /standup me       — developer's last 24h activity feed
                               /standup help     — usage message
- api/router.py             — slack_commands_router included at /slack prefix

Enhanced health check:
- main.py                   — GET /health now probes DB (SELECT 1) and Redis (ping())
                               Returns {"status": "ok"|"degraded", "checks": {...}, "timestamp": ...}

Documentation:
- .env.example              — Full production env vars documented with Neon/Upstash/Qdrant Cloud
                               examples as comments; added QDRANT_URL, QDRANT_API_KEY, BASE_URL,
                               FRONTEND_URL, POSTHOG_API_KEY

No schema changes required.
"""
from typing import Sequence, Union

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
