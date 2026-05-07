# Async Standup Intelligence Layer

> **Replace daily standups entirely.** A multi-agent AI system that passively observes developer behavior across GitHub, Slack, and Jira — then delivers an intelligent team digest every morning. Zero meetings, zero forms.

---

## Why This Exists

Daily standups have a fundamental flaw: **developers self-report**. Someone with 5 failing CI runs and 4 hours of Slack silence will still say "no blockers" in a standup because they don't want to look stuck, don't realize they're blocked, or simply forgot.

This system flips the model. Instead of asking developers what they did, it **observes what actually happened** — commits, PR review lag, CI failure patterns, Slack question frequency — and infers real blockers from behavioral signals.

```
Before: "How's the auth PR going?"  →  "Almost done" (it's been 3 days, 0 reviews)
After:  🔴 Alex: PR #142 open 3 days, 0 reviews. Sent Slack question about OAuth twice.
        Suggested action: tag @backend-lead for review.
```

### Impact for Dev Teams

| Problem | What we solve |
|---------|--------------|
| Hidden blockers surface too late | Detected within hours, not days |
| Standups waste 15–30 min/day | Async digest takes 2 minutes to read |
| Manager doesn't know who's stuck | Behavioral signals, not self-reporting |
| Cross-team conflicts caught in review | File overlap detected before merge |
| Sprint health only visible at retro | Daily sprint risk assessment |

---

## How It Works

```
GitHub  ──┐
Slack   ──┼──▶  Signal Ingestion  ──▶  PostgreSQL + Qdrant
Jira    ──┘     (webhooks + 15-min      (activity events +
                 polling)                vector embeddings)
                                               │
                                               ▼
                              ┌────────────────────────────┐
                              │     LangGraph Pipeline      │
                              │                             │
                              │  1. Signal Collector        │
                              │  2. Blocker Inference  ◀── Claude Sonnet 4
                              │  3. Dependency Conflict     │
                              │  4. Narrative Writer   ◀── Claude Sonnet 4
                              │  5. Digest Assembler        │
                              │  6. Intervention Agent ◀── Claude Sonnet 4
                              └────────────────────────────┘
                                               │
                              ┌────────────────┴──────────────┐
                              │         Output Layer           │
                              │  Slack digest + DMs + REST API │
                              └────────────────────────────────┘
```

### The 6-Agent Pipeline

| Agent | What it does |
|-------|-------------|
| **Signal Collector** | Queries 24h of activity events per developer, computes velocity delta, silence hours |
| **Blocker Inference** | Claude analyzes signal *combinations* — 3 CI failures + silence = real blocker |
| **Dep Conflict Detector** | Finds developer pairs touching the same files/services |
| **Narrative Writer** | Claude writes 2–3 sentence human-sounding summaries per developer |
| **Digest Assembler** | Pure Python — formats the final Slack digest, sets intervention flag |
| **Intervention Agent** | If critical blockers exist, Claude writes friendly Slack DMs |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend API** | FastAPI (Python 3.12), async/await throughout |
| **Database** | PostgreSQL 16 + pgvector extension |
| **Cache** | Redis 7 |
| **Vector Store** | Qdrant (semantic search over activity events) |
| **LLM — Agents** | Claude Sonnet 4 via Anthropic SDK |
| **LLM — Embeddings** | HuggingFace Inference API (`BAAI/bge-base-en-v1.5`, 768-dim, **free**) |
| **Agent Framework** | LangGraph + LangChain |
| **Scheduling** | APScheduler (15-min pollers + per-org digest cron) |
| **Integrations** | GitHub REST API, Slack Events API, Jira webhooks |
| **Token Security** | Fernet symmetric encryption for stored OAuth tokens |
| **ORM / Migrations** | SQLAlchemy 2.0 async + Alembic |
| **Containerization** | Docker Compose |
| **Frontend** *(Week 6)* | Next.js + TypeScript + TailwindCSS |

---

## Project Structure

```
Async_layer/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry + lifespan
│   │   ├── config.py            # Pydantic settings from .env
│   │   ├── database.py          # Async SQLAlchemy engine + session
│   │   ├── core/
│   │   │   └── encryption.py    # Fernet token encryption
│   │   ├── models/              # SQLAlchemy ORM (6 tables)
│   │   ├── ingestion/
│   │   │   ├── normalizer.py    # Raw events → NormalizedEvent schema
│   │   │   ├── github_poller.py # 15-min GitHub Events API polling
│   │   │   ├── slack_poller.py  # 15-min Slack conversations.history
│   │   │   └── embedder.py      # HuggingFace embeddings + Qdrant upsert
│   │   ├── agents/
│   │   │   ├── graph.py         # LangGraph pipeline definition
│   │   │   ├── state.py         # AgentState TypedDicts
│   │   │   └── *.py             # 6 agent node implementations
│   │   ├── api/
│   │   │   ├── auth.py          # OAuth2 connect + callback endpoints
│   │   │   ├── orgs.py          # Org management
│   │   │   ├── developers.py    # Developer profiles + timeline
│   │   │   ├── digests.py       # Digest history + manual trigger
│   │   │   └── webhooks/        # GitHub (full), Slack, Jira receivers
│   │   ├── scheduler/
│   │   │   └── runner.py        # APScheduler — pollers + digest cron
│   │   └── delivery/
│   │       └── slack_delivery.py
│   ├── migrations/              # Alembic async migrations
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml
├── .env.example                 # ← copy this to .env and fill in keys
└── standup_agent_plan.md        # Full technical specification
```

---

## Setup Guide

### Prerequisites
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Python 3.12+ (only needed if running outside Docker)
- Git

---

### Step 1 — Clone and configure environment

```bash
git clone https://github.com/VedantPandhare/Async-intelligence-layer.git
cd Async-intelligence-layer

# Copy the example env file
cp .env.example .env
```

Now open `.env` and fill in the required keys (see table below).

---

### Step 2 — Required API Keys

| Key | Where to get it | Required? |
|-----|----------------|-----------|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com) → API Keys | **Yes** |
| `HF_TOKEN` | [huggingface.co](https://huggingface.co) → Settings → Access Tokens → New token (Read) | **Yes** |
| `GITHUB_CLIENT_ID` + `GITHUB_CLIENT_SECRET` | GitHub → Settings → Developer settings → OAuth Apps → New OAuth App | For GitHub integration |
| `GITHUB_WEBHOOK_SECRET` | Any random string — paste it into GitHub webhook config | For GitHub webhooks |
| `SLACK_BOT_TOKEN` | [api.slack.com/apps](https://api.slack.com/apps) → Create App → OAuth & Permissions → `xoxb-...` | For Slack integration |
| `SLACK_SIGNING_SECRET` | Same Slack App page → Basic Information → Signing Secret | For Slack webhooks |
| `JIRA_CLIENT_ID` + `JIRA_CLIENT_SECRET` | [developer.atlassian.com](https://developer.atlassian.com) → OAuth 2.0 Apps | For Jira integration |

**Minimum to get started:** `ANTHROPIC_API_KEY` + `HF_TOKEN` — the system runs without integrations, you can trigger digests manually via the API.

Also generate these two security keys:

```bash
# Generate SECRET_KEY
python -c "import secrets; print(secrets.token_hex(32))"

# Generate ENCRYPTION_KEY (Fernet format)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Paste the outputs into `SECRET_KEY` and `ENCRYPTION_KEY` in `.env`.

---

### Step 3 — Start infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL (with pgvector), Redis, Qdrant, and the FastAPI backend.

Check everything is running:
```bash
docker compose ps
```

---

### Step 4 — Run database migrations

```bash
docker compose exec backend alembic upgrade head
```

This creates all 7 tables: `organizations`, `developers`, `activity_events`, `digests`, `blockers`, `dep_conflicts`, `integrations`.

---

### Step 5 — Verify the API is running

```
GET http://localhost:8000/health
→ {"status": "ok", "version": "0.1.0"}

GET http://localhost:8000/docs
→ Swagger UI with all endpoints
```

---

### Step 6 — Create your first org and developer (manual test)

```bash
# Create an org
curl -X POST http://localhost:8000/org/ \
  -H "Content-Type: application/json" \
  -d '{"name": "My Team", "slug": "my-team", "digest_time": "09:00", "timezone": "Asia/Kolkata"}'

# Add a developer (use the org_id from above)
curl -X POST http://localhost:8000/developers/{org_id} \
  -H "Content-Type: application/json" \
  -d '{"name": "Vedant", "email": "you@example.com", "github_username": "VedantPandhare"}'

# Manually trigger a digest pipeline run
curl -X POST http://localhost:8000/digests/{org_id}/trigger
```

---

### Step 7 — Connect GitHub (optional)

1. Create a GitHub OAuth App at `github.com/settings/developers`
   - Homepage URL: `http://localhost:8000`
   - Callback URL: `http://localhost:8000/auth/github/callback`
2. Add `GITHUB_CLIENT_ID` + `GITHUB_CLIENT_SECRET` to `.env`
3. Visit `GET /auth/github/connect/{org_id}` → follow the authorization URL
4. Add a GitHub webhook pointing to `http://your-domain/webhooks/github/{org_id}`

---

## What's Built (Current Status)

| Week | Feature | Status |
|------|---------|--------|
| **Week 1** | PostgreSQL models, FastAPI, GitHub poller, normalizer, HuggingFace embedder, LangGraph pipeline (all 6 agents), Alembic migrations | ✅ Done |
| **Week 2** | Slack poller, Slack webhook, Jira webhook, OAuth2 flows (GitHub/Slack/Jira), Fernet token encryption | ✅ Done |
| **Week 3** | Blocker inference prompt tuning, Jira Linear poller, rate limiting, retry logic | 🔜 Next |
| **Week 4** | Quiet hours logic, digest delivery polish, email fallback | ⏳ |
| **Week 5** | Privacy controls, per-dev opt-out, 90-day retention policy | ⏳ |
| **Week 6** | Next.js dashboard (digests, developer timelines, blockers, settings) | ⏳ |
| **Week 7** | JWT auth, full production hardening | ⏳ |
| **Week 8** | Railway + Vercel deployment | ⏳ |

---

## API Reference (Key Endpoints)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/org/` | Create org |
| `GET/PATCH` | `/org/{org_id}/settings` | View/update org settings |
| `POST` | `/developers/{org_id}` | Add a developer |
| `GET` | `/developers/{org_id}/{dev_id}/timeline` | Developer activity timeline |
| `GET` | `/digests/{org_id}/today` | Today's digest |
| `POST` | `/digests/{org_id}/trigger` | Manually run the pipeline |
| `GET` | `/digests/{org_id}/blockers` | Active blockers for org |
| `PATCH` | `/digests/blockers/{blocker_id}/resolve` | Mark blocker resolved |
| `GET` | `/auth/github/connect/{org_id}` | Start GitHub OAuth |
| `GET` | `/auth/slack/connect/{org_id}` | Start Slack OAuth |
| `POST` | `/webhooks/github/{org_id}` | GitHub webhook receiver |
| `POST` | `/webhooks/slack/{org_id}` | Slack Events API receiver |
| `POST` | `/webhooks/jira/{org_id}` | Jira webhook receiver |

Full interactive docs: `http://localhost:8000/docs`

---

## Privacy Principles

- **No message content stored** — only metadata (length, has_question, channel)
- **Developer-first visibility** — each developer sees their own signals
- **Per-developer opt-out** — set `is_active = false` to exclude from analysis
- **90-day retention** *(Week 5)* — old events auto-purged
- **No manager-only views** — the digest is shared with the whole team

---

## Cost Estimate

| Team size | Claude (agents) | HuggingFace (embeddings) | Total/day |
|-----------|----------------|--------------------------|-----------|
| 10 devs | ~$0.12 | Free | ~$0.12 |
| 50 devs | ~$0.50 | Free | ~$0.50 |
| 100 devs | ~$1.00 | Free | ~$1.00 |

At `$15/seat/month` pricing: margins are exceptional.

---

## License

MIT
