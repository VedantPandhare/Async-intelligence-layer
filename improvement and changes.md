# Async Standup Intelligence Layer
## Full Technical Implementation & System Architecture Plan

---

## 1. Project Overview

The Async Standup Intelligence Layer is a multi-agent SaaS system that **replaces daily standups entirely**. It passively observes developer behavior signals across GitHub, Slack, and Jira/Linear throughout the day, infers real blockers from behavioral patterns (not self-reporting), and delivers a team digest every morning — zero meetings, zero forms.

**Core insight:** Behavior is more honest than self-reporting. A developer who has pushed 5 failing commits and gone silent in Slack is more visibly blocked than one who says "no blockers" in a standup.

---

## 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ASYNC STANDUP INTELLIGENCE LAYER                  │
│                                                                           │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                 │
│  │   GitHub API  │   │  Slack API   │   │ Jira/Linear  │  ← Data Sources │
│  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘                 │
│         │                  │                   │                          │
│         └──────────────────┼───────────────────┘                         │
│                            ▼                                              │
│              ┌─────────────────────────┐                                 │
│              │   Signal Ingestion Layer │   ← FastAPI webhooks + polling  │
│              │   (15-min cron + hooks)  │                                 │
│              └────────────┬────────────┘                                 │
│                           ▼                                              │
│              ┌─────────────────────────┐                                 │
│              │   Activity Normalizer   │   ← Unified event schema         │
│              │   PostgreSQL + Redis    │                                  │
│              └────────────┬────────────┘                                 │
│                           ▼                                              │
│         ┌─────────────────────────────────────────┐                     │
│         │           LANGGRAPH PIPELINE             │                     │
│         │                                          │                     │
│         │  ┌──────────┐  ┌──────────┐  ┌────────┐ │                     │
│         │  │ Signal   │→ │ Blocker  │→ │ Dep    │ │                     │
│         │  │Collector │  │Inference │  │Conflict│ │                     │
│         │  └──────────┘  └──────────┘  └────────┘ │                     │
│         │                                    │      │                     │
│         │  ┌──────────┐  ┌──────────┐        │      │                     │
│         │  │Narrative │← │ Digest   │←───────┘      │                     │
│         │  │ Writer   │  │Assembler │               │                     │
│         │  └──────────┘  └──────────┘               │                     │
│         │        │                                   │                     │
│         │        ▼                                   │                     │
│         │  ┌──────────┐                             │                     │
│         │  │Interventi│                             │                     │
│         │  │on Agent  │                             │                     │
│         │  └──────────┘                             │                     │
│         └─────────────────────────────────────────┘                     │
│                           │                                              │
│              ┌────────────┴────────────┐                                 │
│              │     Output Layer        │                                 │
│              │  Slack digest + pings   │                                 │
│              │  Email + Web dashboard  │                                 │
│              └─────────────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Database Schema

### PostgreSQL Tables

```sql
-- Organizations / teams
CREATE TABLE organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    digest_time TIME DEFAULT '09:00:00',       -- when to send daily digest
    timezone VARCHAR(50) DEFAULT 'UTC',
    settings JSONB DEFAULT '{}'               -- quiet hours, tone prefs, etc.
);

-- Developers in each org
CREATE TABLE developers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    github_username VARCHAR(100),
    slack_user_id VARCHAR(100),
    jira_account_id VARCHAR(100),
    email VARCHAR(255),
    role VARCHAR(100),                         -- eng, lead, manager
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Raw activity events (normalized from all sources)
CREATE TABLE activity_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    developer_id UUID REFERENCES developers(id) ON DELETE CASCADE,
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    source VARCHAR(50) NOT NULL,               -- 'github' | 'slack' | 'jira' | 'linear'
    event_type VARCHAR(100) NOT NULL,          -- 'commit' | 'pr_open' | 'pr_review' | 'message' | 'ticket_update'
    event_time TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,                    -- raw normalized event data
    embedding vector(1536),                    -- for semantic search (pgvector)
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_activity_developer_time ON activity_events(developer_id, event_time DESC);
CREATE INDEX idx_activity_org_time ON activity_events(org_id, event_time DESC);
CREATE INDEX idx_activity_source ON activity_events(source, event_type);

-- Daily digests
CREATE TABLE digests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    digest_date DATE NOT NULL,
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    content JSONB NOT NULL,                    -- full structured digest
    markdown_output TEXT,                      -- final rendered digest
    slack_ts VARCHAR(100),                     -- slack message timestamp for threading
    delivered BOOLEAN DEFAULT FALSE,
    UNIQUE(org_id, digest_date)
);

-- Inferred blockers
CREATE TABLE blockers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    developer_id UUID REFERENCES developers(id),
    org_id UUID REFERENCES organizations(id),
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    blocker_type VARCHAR(100),                 -- 'ci_failure' | 'pr_stalled' | 'silence' | 'repeated_question'
    severity VARCHAR(20),                      -- 'low' | 'medium' | 'high' | 'critical'
    description TEXT,
    signals JSONB,                             -- which activity events triggered this
    intervention_sent BOOLEAN DEFAULT FALSE,
    intervention_at TIMESTAMPTZ,
    intervention_content TEXT
);

-- Dependency conflicts between developers
CREATE TABLE dep_conflicts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id),
    developer_a_id UUID REFERENCES developers(id),
    developer_b_id UUID REFERENCES developers(id),
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    conflict_type VARCHAR(100),                -- 'same_file' | 'same_api' | 'same_service'
    details JSONB,
    resolved BOOLEAN DEFAULT FALSE
);

-- Integration credentials per org
CREATE TABLE integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES organizations(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL,             -- 'github' | 'slack' | 'jira' | 'linear'
    access_token TEXT,                         -- encrypted
    refresh_token TEXT,                        -- encrypted
    webhook_secret TEXT,
    metadata JSONB DEFAULT '{}',               -- org_id, workspace_id, etc.
    connected_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(org_id, provider)
);
```

### Qdrant Collection (Vector Store)

```python
# Collection: "activity_embeddings"
# Stores semantic embeddings of all activity events
# Used by the Code Explorer and Blocker Inference agents for RAG

collection_config = {
    "name": "activity_embeddings",
    "vectors": {
        "size": 1536,         # text-embedding-3-small
        "distance": "Cosine"
    },
    "payload_schema": {
        "developer_id": "keyword",
        "org_id": "keyword",
        "event_type": "keyword",
        "source": "keyword",
        "event_time": "datetime",
        "summary": "text"      # human-readable event summary
    }
}
```

---

## 4. Directory Structure

```
standup-intelligence/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI app entry point
│   │   ├── config.py                  # settings, env vars
│   │   ├── database.py                # SQLAlchemy async engine
│   │   │
│   │   ├── api/
│   │   │   ├── auth.py                # OAuth endpoints
│   │   │   ├── webhooks/
│   │   │   │   ├── github.py          # GitHub webhook receiver
│   │   │   │   ├── slack.py           # Slack Events API receiver
│   │   │   │   └── jira.py            # Jira webhook receiver
│   │   │   ├── orgs.py                # Org management
│   │   │   ├── developers.py          # Dev profile endpoints
│   │   │   └── digests.py             # Digest history + manual trigger
│   │   │
│   │   ├── ingestion/
│   │   │   ├── normalizer.py          # Raw events → unified schema
│   │   │   ├── github_poller.py       # 15-min GitHub polling
│   │   │   ├── slack_poller.py        # 15-min Slack polling
│   │   │   └── embedder.py            # OpenAI embeddings for events
│   │   │
│   │   ├── agents/
│   │   │   ├── graph.py               # LangGraph pipeline definition
│   │   │   ├── state.py               # AgentState TypedDict
│   │   │   ├── signal_collector.py    # Agent 1: query + aggregate signals
│   │   │   ├── blocker_inference.py   # Agent 2: detect real blockers
│   │   │   ├── dep_conflict.py        # Agent 3: cross-dev conflicts
│   │   │   ├── narrative_writer.py    # Agent 4: write digest prose
│   │   │   ├── digest_assembler.py    # Agent 5: assemble final digest
│   │   │   └── intervention.py        # Agent 6: proactive pings
│   │   │
│   │   ├── tools/
│   │   │   ├── github_tools.py        # LangChain tools wrapping GitHub API
│   │   │   ├── slack_tools.py         # LangChain tools for Slack
│   │   │   ├── jira_tools.py          # LangChain tools for Jira/Linear
│   │   │   └── vector_tools.py        # RAG tools over activity embeddings
│   │   │
│   │   ├── scheduler/
│   │   │   ├── jobs.py                # APScheduler job definitions
│   │   │   └── runner.py              # Digest trigger + org loop
│   │   │
│   │   ├── delivery/
│   │   │   ├── slack_delivery.py      # Format + send digest to Slack
│   │   │   └── email_delivery.py      # Email digest fallback
│   │   │
│   │   └── models/
│   │       ├── organization.py
│   │       ├── developer.py
│   │       ├── activity_event.py
│   │       ├── digest.py
│   │       └── blocker.py
│   │
│   ├── migrations/                    # Alembic migrations
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/                          # Next.js dashboard
│   ├── app/
│   │   ├── (auth)/
│   │   │   └── login/page.tsx
│   │   ├── (dashboard)/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx               # Today's digest
│   │   │   ├── history/page.tsx       # Past digests
│   │   │   ├── developers/page.tsx    # Dev profiles + signals
│   │   │   ├── blockers/page.tsx      # Active blockers
│   │   │   └── settings/page.tsx      # Integrations + config
│   │   └── api/
│   │       └── auth/[...nextauth]/    # NextAuth
│   ├── components/
│   │   ├── DigestCard.tsx
│   │   ├── DeveloperTimeline.tsx
│   │   ├── BlockerAlert.tsx
│   │   └── SignalFeed.tsx
│   └── package.json
│
├── docker-compose.yml
└── README.md
```

---

## 5. LangGraph Agent Pipeline

### AgentState Definition

```python
# backend/app/agents/state.py
from typing import TypedDict, List, Optional, Dict, Any
from datetime import date

class DeveloperSignals(TypedDict):
    developer_id: str
    developer_name: str
    github_username: str
    commits_today: List[Dict]
    prs_opened: List[Dict]
    prs_reviewed: List[Dict]
    ci_failures: List[Dict]
    slack_messages_count: int
    last_slack_message_at: Optional[str]
    tickets_updated: List[Dict]
    files_touched: List[str]
    commit_velocity_delta: float    # vs 7-day average
    silence_hours: float            # hours since last any activity

class InferredBlocker(TypedDict):
    developer_id: str
    blocker_type: str               # 'ci_failure' | 'pr_stalled' | 'silence' | 'dependency_wait'
    severity: str                   # 'low' | 'medium' | 'high' | 'critical'
    description: str
    signals: List[str]              # evidence
    suggested_action: str

class DependencyConflict(TypedDict):
    developer_a: str
    developer_b: str
    conflict_type: str
    files_or_services: List[str]
    risk: str

class AgentState(TypedDict):
    org_id: str
    digest_date: str
    # Populated by signal_collector
    developer_signals: List[DeveloperSignals]
    # Populated by blocker_inference
    blockers: List[InferredBlocker]
    # Populated by dep_conflict
    conflicts: List[DependencyConflict]
    # Populated by narrative_writer
    developer_narratives: Dict[str, str]    # dev_id → prose summary
    sprint_risk: str
    # Populated by digest_assembler
    final_digest: Optional[str]
    # Control
    errors: List[str]
    should_intervene: bool
```

### LangGraph Pipeline Definition

```python
# backend/app/agents/graph.py
from langgraph.graph import StateGraph, END
from .state import AgentState
from .signal_collector import signal_collector_node
from .blocker_inference import blocker_inference_node
from .dep_conflict import dep_conflict_node
from .narrative_writer import narrative_writer_node
from .digest_assembler import digest_assembler_node
from .intervention import intervention_node

def should_intervene(state: AgentState) -> str:
    """Conditional edge: only run intervention if critical blockers exist."""
    critical = [b for b in state["blockers"] if b["severity"] == "critical"]
    return "intervention" if critical else "end"

def build_pipeline() -> StateGraph:
    graph = StateGraph(AgentState)

    # Add all nodes
    graph.add_node("signal_collector", signal_collector_node)
    graph.add_node("blocker_inference", blocker_inference_node)
    graph.add_node("dep_conflict", dep_conflict_node)
    graph.add_node("narrative_writer", narrative_writer_node)
    graph.add_node("digest_assembler", digest_assembler_node)
    graph.add_node("intervention", intervention_node)

    # Linear flow
    graph.set_entry_point("signal_collector")
    graph.add_edge("signal_collector", "blocker_inference")
    graph.add_edge("blocker_inference", "dep_conflict")
    graph.add_edge("dep_conflict", "narrative_writer")
    graph.add_edge("narrative_writer", "digest_assembler")

    # Conditional: only intervene if critical blockers
    graph.add_conditional_edges(
        "digest_assembler",
        should_intervene,
        {"intervention": "intervention", "end": END}
    )
    graph.add_edge("intervention", END)

    return graph.compile()

pipeline = build_pipeline()
```

### Agent 1: Signal Collector

```python
# backend/app/agents/signal_collector.py
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from .state import AgentState, DeveloperSignals
from ..database import get_db
from ..models import ActivityEvent, Developer
from datetime import datetime, timedelta
import json

llm = ChatAnthropic(model="claude-sonnet-4-20250514", max_tokens=2000)

async def signal_collector_node(state: AgentState) -> AgentState:
    """
    Queries the database for all activity events in the past 24h,
    aggregates them per developer, and enriches with behavioral metrics.
    """
    org_id = state["org_id"]
    since = datetime.utcnow() - timedelta(hours=24)

    async with get_db() as db:
        developers = await db.query(Developer).filter_by(
            org_id=org_id, is_active=True
        ).all()

        developer_signals = []
        for dev in developers:
            events = await db.query(ActivityEvent).filter(
                ActivityEvent.developer_id == dev.id,
                ActivityEvent.event_time >= since
            ).order_by(ActivityEvent.event_time.desc()).all()

            # Aggregate by event type
            commits = [e.payload for e in events if e.event_type == "commit"]
            ci_failures = [e.payload for e in events
                          if e.event_type == "ci_run" and e.payload.get("status") == "failed"]
            slack_msgs = [e for e in events if e.source == "slack"]

            # Calculate commit velocity delta vs 7-day average
            week_ago = datetime.utcnow() - timedelta(days=7)
            past_week_commits = await db.query(ActivityEvent).filter(
                ActivityEvent.developer_id == dev.id,
                ActivityEvent.event_type == "commit",
                ActivityEvent.event_time >= week_ago
            ).count()
            avg_daily_commits = past_week_commits / 7
            velocity_delta = (len(commits) - avg_daily_commits) / max(avg_daily_commits, 1)

            # Time since last any activity
            last_event = events[0] if events else None
            silence_hours = 0.0
            if last_event:
                silence_hours = (datetime.utcnow() - last_event.event_time).seconds / 3600

            developer_signals.append(DeveloperSignals(
                developer_id=str(dev.id),
                developer_name=dev.name,
                github_username=dev.github_username or "",
                commits_today=commits,
                prs_opened=[e.payload for e in events if e.event_type == "pr_open"],
                prs_reviewed=[e.payload for e in events if e.event_type == "pr_review"],
                ci_failures=ci_failures,
                slack_messages_count=len(slack_msgs),
                last_slack_message_at=slack_msgs[0].event_time.isoformat() if slack_msgs else None,
                tickets_updated=[e.payload for e in events if e.source in ("jira", "linear")],
                files_touched=list(set(
                    f for c in commits for f in c.get("files_changed", [])
                )),
                commit_velocity_delta=velocity_delta,
                silence_hours=silence_hours
            ))

    return {**state, "developer_signals": developer_signals}
```

### Agent 2: Blocker Inference

```python
# backend/app/agents/blocker_inference.py
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from .state import AgentState, InferredBlocker
import json

llm = ChatAnthropic(model="claude-sonnet-4-20250514", max_tokens=3000)

BLOCKER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are an expert engineering team observer. Your job is to detect 
real blockers from behavioral signals — NOT self-reported status.

A blocker is inferred when you see COMBINATIONS of signals, never one signal alone.
Strong blocker patterns:
- 3+ consecutive CI failures on same files + no new commits in 2h = likely stuck on a hard bug
- PR open > 2 days with 0 reviews + developer sent question in Slack = waiting on reviewer
- Commit velocity dropped >60% vs baseline + silence > 4h during work hours = blocked or context-switching
- Same Slack question asked 2+ times in a day = unresolved dependency or knowledge gap
- Ticket in "In Progress" for >3 days with no commits touching related files = estimation problem or hidden blocker

For each developer, return a JSON array of blockers. If no blocker, return empty array.
Severity: critical (blocks sprint), high (blocks today), medium (slows work), low (minor friction).

Return ONLY valid JSON. No prose."""),
    ("human", """Analyze these developer signals for org {org_id} on {digest_date}:

{signals_json}

Return JSON array of blockers:
[{{
  "developer_id": "...",
  "blocker_type": "ci_failure|pr_stalled|silence|dependency_wait|estimation_problem",
  "severity": "critical|high|medium|low",
  "description": "Plain English explanation of what the blocker is",
  "signals": ["list", "of", "evidence"],
  "suggested_action": "Who should do what to unblock"
}}]""")
])

async def blocker_inference_node(state: AgentState) -> AgentState:
    chain = BLOCKER_PROMPT | llm

    response = await chain.ainvoke({
        "org_id": state["org_id"],
        "digest_date": state["digest_date"],
        "signals_json": json.dumps(state["developer_signals"], indent=2)
    })

    try:
        blockers = json.loads(response.content)
    except json.JSONDecodeError:
        # LLM returned prose — extract JSON from it
        import re
        match = re.search(r'\[.*\]', response.content, re.DOTALL)
        blockers = json.loads(match.group()) if match else []

    return {**state, "blockers": blockers}
```

### Agent 3: Dependency Conflict Detector

```python
# backend/app/agents/dep_conflict.py
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from .state import AgentState
import json
from itertools import combinations

llm = ChatAnthropic(model="claude-sonnet-4-20250514", max_tokens=2000)

DEP_CONFLICT_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You detect dependency conflicts between developers working in parallel.
A conflict exists when two devs are touching the same files, API endpoints, DB tables, 
or services in ways that will likely cause merge conflicts or integration issues.

Return JSON array only. Empty array if no conflicts."""),
    ("human", """Check these developer pairs for conflicts:

{pairs_json}

Return:
[{{
  "developer_a": "name",
  "developer_b": "name",  
  "conflict_type": "same_file|same_api|same_service|same_schema",
  "files_or_services": ["list of overlapping items"],
  "risk": "Will conflict on merge|May conflict|Low risk but coordinate"
}}]""")
])

async def dep_conflict_node(state: AgentState) -> AgentState:
    signals = state["developer_signals"]

    # Build pairs with their files_touched for comparison
    pairs = []
    for a, b in combinations(signals, 2):
        overlap = set(a["files_touched"]) & set(b["files_touched"])
        if overlap:  # only LLM-check pairs with actual file overlap
            pairs.append({
                "dev_a": a["developer_name"],
                "dev_b": b["developer_name"],
                "shared_files": list(overlap),
                "dev_a_tickets": [t.get("title") for t in a["tickets_updated"]],
                "dev_b_tickets": [t.get("title") for t in b["tickets_updated"]],
            })

    if not pairs:
        return {**state, "conflicts": []}

    chain = DEP_CONFLICT_PROMPT | llm
    response = await chain.ainvoke({"pairs_json": json.dumps(pairs, indent=2)})

    try:
        conflicts = json.loads(response.content)
    except:
        conflicts = []

    return {**state, "conflicts": conflicts}
```

### Agent 4: Narrative Writer

```python
# backend/app/agents/narrative_writer.py
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from .state import AgentState
import json

llm = ChatAnthropic(model="claude-sonnet-4-20250514", max_tokens=4000)

NARRATIVE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You write concise, honest, human-sounding developer summaries 
for a team digest. You are writing for the team — not for management surveillance.

Rules:
- Each developer summary: 2-3 sentences MAX
- Lead with what they accomplished, then flag issues
- Use specific details (PR names, file names, ticket titles) — no vague generalities
- Tone: like a senior engineer summarizing a colleague's day — respectful, direct
- Flag blockers with emoji: 🔴 critical, 🟡 attention needed
- Flag good progress with: ✅
- Never say "it appears" or "seems to be" — state it plainly
- Never mention surveillance or that you're watching behavior"""),
    ("human", """Write summaries for these developers.

Developer signals:
{signals_json}

Inferred blockers:
{blockers_json}

Dependency conflicts:
{conflicts_json}

Also write a 1-sentence sprint risk assessment at the end.

Return JSON:
{{
  "developer_summaries": {{
    "<developer_id>": "<2-3 sentence summary>"
  }},
  "sprint_risk": "<1 sentence overall risk>"
}}""")
])

async def narrative_writer_node(state: AgentState) -> AgentState:
    chain = NARRATIVE_PROMPT | llm
    response = await chain.ainvoke({
        "signals_json": json.dumps(state["developer_signals"], indent=2),
        "blockers_json": json.dumps(state["blockers"], indent=2),
        "conflicts_json": json.dumps(state["conflicts"], indent=2),
    })

    try:
        result = json.loads(response.content)
        narratives = result["developer_summaries"]
        sprint_risk = result["sprint_risk"]
    except:
        narratives = {}
        sprint_risk = "Unable to assess sprint risk."

    return {**state, "developer_narratives": narratives, "sprint_risk": sprint_risk}
```

### Agent 5: Digest Assembler

```python
# backend/app/agents/digest_assembler.py
from .state import AgentState
from datetime import datetime

def digest_assembler_node(state: AgentState) -> AgentState:
    """
    Pure Python (no LLM needed) — assembles the final Slack-formatted digest
    from all agent outputs.
    """
    lines = []
    date_str = datetime.utcnow().strftime("%A, %B %-d")

    lines.append(f"*🗓 Team Digest — {date_str}*\n")

    # Per-developer summaries
    for dev in state["developer_signals"]:
        dev_id = dev["developer_id"]
        narrative = state["developer_narratives"].get(dev_id, "No activity recorded.")
        lines.append(f"*{dev['developer_name']}* — {narrative}")

    lines.append("")

    # Dependency conflicts
    if state["conflicts"]:
        lines.append("*⚠️ Coordination needed*")
        for c in state["conflicts"]:
            lines.append(
                f"› {c['developer_a']} × {c['developer_b']}: "
                f"{c['risk']} — `{'`, `'.join(c['files_or_services'][:3])}`"
            )
        lines.append("")

    # Sprint risk
    lines.append(f"*Sprint health:* {state['sprint_risk']}")

    final_digest = "\n".join(lines)

    return {**state, "final_digest": final_digest, "should_intervene": bool(
        [b for b in state["blockers"] if b["severity"] == "critical"]
    )}
```

### Agent 6: Intervention Agent

```python
# backend/app/agents/intervention.py
from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate
from .state import AgentState
from ..delivery.slack_delivery import send_slack_dm
import json

llm = ChatAnthropic(model="claude-sonnet-4-20250514", max_tokens=1000)

INTERVENTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You write brief, friendly Slack DMs to unblock developers.
The message should feel like a helpful colleague checking in — NOT a manager pinging for a status update.
Keep it under 3 sentences. Offer help. Suggest who to talk to. Never be accusatory."""),
    ("human", "Write a Slack DM to {developer_name} about this blocker: {blocker_description}\nSuggested action: {suggested_action}")
])

async def intervention_node(state: AgentState) -> AgentState:
    critical_blockers = [b for b in state["blockers"] if b["severity"] == "critical"]

    # Map dev_id → name
    dev_map = {d["developer_id"]: d for d in state["developer_signals"]}

    chain = INTERVENTION_PROMPT | llm

    for blocker in critical_blockers:
        dev = dev_map.get(blocker["developer_id"])
        if not dev:
            continue

        response = await chain.ainvoke({
            "developer_name": dev["developer_name"],
            "blocker_description": blocker["description"],
            "suggested_action": blocker["suggested_action"]
        })

        # Send DM via Slack API
        await send_slack_dm(
            developer_id=blocker["developer_id"],
            message=response.content
        )

    return state
```

---

## 6. Signal Ingestion Layer

### Unified Event Schema

```python
# backend/app/ingestion/normalizer.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

@dataclass
class NormalizedEvent:
    developer_id: str
    org_id: str
    source: str          # 'github' | 'slack' | 'jira' | 'linear'
    event_type: str
    event_time: datetime
    payload: Dict[str, Any]
    summary: str         # human-readable string for embedding

# GitHub commit → NormalizedEvent
def normalize_github_commit(raw: dict, developer_id: str, org_id: str) -> NormalizedEvent:
    return NormalizedEvent(
        developer_id=developer_id,
        org_id=org_id,
        source="github",
        event_type="commit",
        event_time=datetime.fromisoformat(raw["commit"]["author"]["date"]),
        payload={
            "sha": raw["sha"][:8],
            "message": raw["commit"]["message"][:200],
            "files_changed": [f["filename"] for f in raw.get("files", [])],
            "additions": raw["stats"]["additions"],
            "deletions": raw["stats"]["deletions"],
        },
        summary=f"Committed: {raw['commit']['message'][:100]}"
    )

# Slack message → NormalizedEvent
def normalize_slack_message(raw: dict, developer_id: str, org_id: str) -> NormalizedEvent:
    return NormalizedEvent(
        developer_id=developer_id,
        org_id=org_id,
        source="slack",
        event_type="message",
        event_time=datetime.fromtimestamp(float(raw["ts"])),
        payload={
            "channel": raw.get("channel"),
            "text_length": len(raw.get("text", "")),
            "has_question": "?" in raw.get("text", ""),
            "thread_reply": bool(raw.get("thread_ts")),
        },
        summary=f"Slack message in #{raw.get('channel_name', 'unknown')}"
    )
```

### GitHub Poller

```python
# backend/app/ingestion/github_poller.py
import httpx
from datetime import datetime, timedelta
from .normalizer import normalize_github_commit, normalize_github_pr, normalize_ci_run
from ..database import get_db
from ..models import ActivityEvent, Developer, Integration
import asyncio

async def poll_github_for_org(org_id: str):
    """Polls GitHub API for all developers in an org. Runs every 15 minutes."""
    async with get_db() as db:
        integration = await db.query(Integration).filter_by(
            org_id=org_id, provider="github"
        ).first()

        if not integration:
            return

        developers = await db.query(Developer).filter_by(
            org_id=org_id, is_active=True
        ).all()

        since = datetime.utcnow() - timedelta(minutes=20)  # 5min overlap for safety

        async with httpx.AsyncClient(
            headers={"Authorization": f"token {integration.access_token}"}
        ) as client:
            tasks = [poll_developer(client, dev, org_id, since, db) for dev in developers]
            await asyncio.gather(*tasks, return_exceptions=True)


async def poll_developer(client, dev, org_id, since, db):
    # Commits
    commits_url = f"https://api.github.com/repos/{dev.github_username}"
    # ... fetch commits, PRs, CI runs
    # normalize and upsert into activity_events
    pass
```

### Webhook Receiver (GitHub)

```python
# backend/app/api/webhooks/github.py
from fastapi import APIRouter, Request, HTTPException, Header
import hmac, hashlib
from ...ingestion.normalizer import normalize_github_commit
from ...ingestion.embedder import embed_and_store_event
from ...database import get_db

router = APIRouter()

@router.post("/webhooks/github/{org_id}")
async def github_webhook(
    org_id: str,
    request: Request,
    x_hub_signature_256: str = Header(None)
):
    body = await request.body()

    # Verify webhook signature
    async with get_db() as db:
        integration = await db.query(Integration).filter_by(
            org_id=org_id, provider="github"
        ).first()
        expected = "sha256=" + hmac.new(
            integration.webhook_secret.encode(),
            body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(x_hub_signature_256, expected):
            raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event")

    # Route to appropriate normalizer
    if event_type == "push":
        for commit in payload.get("commits", []):
            developer = await resolve_developer(commit["author"]["email"], org_id)
            if developer:
                event = normalize_github_commit(commit, developer.id, org_id)
                await embed_and_store_event(event)

    return {"status": "ok"}
```

---

## 7. Scheduler — Daily Digest Trigger

```python
# backend/app/scheduler/runner.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from ..agents.graph import pipeline
from ..agents.state import AgentState
from ..database import get_db
from ..models import Organization
from ..delivery.slack_delivery import deliver_digest
from datetime import date

scheduler = AsyncIOScheduler()

async def run_digest_for_org(org_id: str):
    """Runs the full LangGraph pipeline for one org and delivers the digest."""
    initial_state = AgentState(
        org_id=org_id,
        digest_date=date.today().isoformat(),
        developer_signals=[],
        blockers=[],
        conflicts=[],
        developer_narratives={},
        sprint_risk="",
        final_digest=None,
        errors=[],
        should_intervene=False
    )

    try:
        final_state = await pipeline.ainvoke(initial_state)

        if final_state["final_digest"]:
            await deliver_digest(org_id, final_state["final_digest"])

            # Persist to DB
            async with get_db() as db:
                await db.execute("""
                    INSERT INTO digests (org_id, digest_date, content, markdown_output, delivered)
                    VALUES ($1, $2, $3, $4, true)
                    ON CONFLICT (org_id, digest_date) DO UPDATE
                    SET markdown_output = EXCLUDED.markdown_output
                """, org_id, date.today(),
                    json.dumps(final_state),
                    final_state["final_digest"]
                )

    except Exception as e:
        print(f"Pipeline error for org {org_id}: {e}")


async def schedule_all_orgs():
    """On startup, read all orgs and schedule their digests at their configured time."""
    async with get_db() as db:
        orgs = await db.query(Organization).filter_by(is_active=True).all()

    for org in orgs:
        # org.digest_time is a TIME in org.timezone
        scheduler.add_job(
            run_digest_for_org,
            CronTrigger(
                hour=org.digest_time.hour,
                minute=org.digest_time.minute,
                timezone=org.timezone
            ),
            args=[str(org.id)],
            id=f"digest_{org.id}",
            replace_existing=True
        )

scheduler.start()
```

---

## 8. Delivery Layer

```python
# backend/app/delivery/slack_delivery.py
from slack_sdk.web.async_client import AsyncWebClient
from ..database import get_db
from ..models import Integration, Developer

async def deliver_digest(org_id: str, digest_markdown: str):
    """Posts the daily digest to the team's configured Slack channel."""
    async with get_db() as db:
        integration = await db.query(Integration).filter_by(
            org_id=org_id, provider="slack"
        ).first()

        org = await db.query(Organization).get(org_id)
        channel_id = org.settings.get("digest_channel_id", "#engineering")

    client = AsyncWebClient(token=integration.access_token)

    # Convert markdown to Slack mrkdwn (minor formatting adjustments)
    slack_text = digest_markdown.replace("**", "*")

    response = await client.chat_postMessage(
        channel=channel_id,
        text=slack_text,
        unfurl_links=False
    )

    return response["ts"]  # save for threading follow-ups


async def send_slack_dm(developer_id: str, message: str):
    """Sends a proactive DM to a blocked developer."""
    async with get_db() as db:
        dev = await db.query(Developer).get(developer_id)
        integration = await db.query(Integration).filter_by(
            org_id=dev.org_id, provider="slack"
        ).first()

    client = AsyncWebClient(token=integration.access_token)
    await client.chat_postMessage(
        channel=dev.slack_user_id,  # DM by sending to user ID
        text=message
    )
```

---

## 9. Environment Variables

```bash
# backend/.env

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/standup_db
REDIS_URL=redis://localhost:6379

# Vector Store
QDRANT_URL=http://localhost:6333
QDRANT_API_KEY=your_key

# LLM
ANTHROPIC_API_KEY=sk-ant-...

# Embeddings
OPENAI_API_KEY=sk-...          # for text-embedding-3-small

# Encryption (for stored tokens)
ENCRYPTION_KEY=your_32_byte_key

# App
SECRET_KEY=your_jwt_secret
ENVIRONMENT=development
BASE_URL=https://yourapp.com
```

---

## 10. Docker Compose (Development)

```yaml
# docker-compose.yml
version: '3.9'

services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/standup_db
      - REDIS_URL=redis://redis:6379
      - QDRANT_URL=http://qdrant:6333
    depends_on:
      - db
      - redis
      - qdrant
    volumes:
      - ./backend:/app
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

  frontend:
    build: ./frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost:8000
    volumes:
      - ./frontend:/app

  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: standup_db
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage

volumes:
  postgres_data:
  qdrant_data:
```

---

## 11. API Endpoints

```
Authentication
  POST   /auth/github/callback         OAuth GitHub installation
  POST   /auth/slack/callback           OAuth Slack installation
  POST   /auth/jira/callback            OAuth Jira installation

Webhooks (inbound)
  POST   /webhooks/github/{org_id}      GitHub push/PR/CI events
  POST   /webhooks/slack/{org_id}       Slack Events API
  POST   /webhooks/jira/{org_id}        Jira issue updates

Digests
  GET    /digests/{org_id}              List past digests
  GET    /digests/{org_id}/today        Today's digest
  POST   /digests/{org_id}/trigger      Manually trigger digest run
  GET    /digests/{org_id}/{date}       Specific date digest

Developers
  GET    /developers/{org_id}           List all developers
  GET    /developers/{org_id}/{dev_id}  Developer profile + signals
  GET    /developers/{org_id}/{dev_id}/timeline  24h activity timeline

Blockers
  GET    /blockers/{org_id}             Active blockers
  PATCH  /blockers/{blocker_id}/resolve Mark blocker resolved

Organization
  GET    /org/{org_id}/settings         Get settings
  PATCH  /org/{org_id}/settings         Update digest time, timezone, etc.
```

---

## 12. Cost Estimation

| Component                    | Per 10-dev team/day | Per 100-dev team/day |
|------------------------------|---------------------|----------------------|
| Groq API (Llama 3.3 70B)     | ~$0.003             | ~$0.022              |
| Embeddings (sentence-transf.) | $0 (runs locally)  | $0 (runs locally)    |
| Qdrant Cloud (free tier)     | $0                  | $0                   |
| Upstash Redis (free tier)    | $0                  | ~$0.01               |
| Neon Postgres (free tier)    | $0                  | ~$0.02               |
| **Total/day**                | **~$0.003**         | **~$0.05**           |
| **Total/month**              | **~$0.10**          | **~$1.50**           |

At $15/seat/month pricing → near 100% gross margin at any scale.
Groq free tier (14,400 req/day) covers ~1,000 teams before you pay a cent.

---

## 13. Week-by-Week Build Plan

### Week 1 — Data foundation
- [ ] Set up PostgreSQL with pgvector + Qdrant + Redis via Docker Compose
- [ ] Build GitHub API poller (commits, PRs, CI runs per developer)
- [ ] Build normalizer for GitHub events → unified schema
- [ ] Store events in activity_events table
- [ ] Basic FastAPI scaffolding with org/developer CRUD

### Week 2 — More signals + LangGraph skeleton
- [ ] Slack Events API integration (message metadata only — no message text stored)
- [ ] Jira/Linear API poller for ticket updates
- [ ] LangGraph pipeline skeleton with AgentState
- [ ] Signal Collector agent (pure DB queries, no LLM yet)
- [ ] Embeddings pipeline: events → Qdrant

### Week 3 — Core agents
- [ ] Blocker Inference agent with prompt engineering + JSON output
- [ ] Dependency Conflict agent
- [ ] Test both agents against real activity data
- [ ] Tune blocker detection thresholds (avoid false positives)

### Week 4 — Narrative + delivery
- [ ] Narrative Writer agent
- [ ] Digest Assembler (pure Python)
- [ ] Slack delivery integration
- [ ] APScheduler cron setup — org-level digest scheduling
- [ ] First real digest sent to a test team

### Week 5 — Intervention + polish
- [ ] Intervention agent with DM drafting
- [ ] Quiet hours logic (don't ping at 11pm)
- [ ] GitHub webhook receivers (real-time, supplement polling)
- [ ] Error handling, retries, LangGraph checkpointing

### Week 6 — Web dashboard
- [ ] Next.js project setup with NextAuth
- [ ] Today's digest page
- [ ] Developer timeline view
- [ ] Active blockers page
- [ ] Settings: integrations, digest time, timezone

### Week 7 — Hardening
- [ ] OAuth flows for GitHub App, Slack App, Jira
- [ ] Token encryption at rest
- [ ] Rate limit handling for all APIs
- [ ] Privacy controls: opt-out per developer
- [ ] Onboarding flow for new orgs

### Week 8 — Beta Launch (Updated)

#### Day 1–2: Infrastructure Setup (all free tier)
- [ ] Create accounts: Render, Vercel, Neon, Upstash, Qdrant Cloud, Groq, UptimeRobot, Cloudflare
- [ ] Provision Neon Postgres — copy `DATABASE_URL`, run Alembic migrations
- [ ] Provision Upstash Redis — copy `REDIS_URL`
- [ ] Provision Qdrant Cloud cluster — create `activity_embeddings` collection
- [ ] Buy domain (~₹800/yr on Namecheap), point to Cloudflare nameservers
- [ ] Configure Cloudflare DNS: `api.yourdomain.com` → Render, `app.yourdomain.com` → Vercel

#### Day 3: Deploy Backend to Render
- [ ] Add `render.yaml` to repo root (see section 14)
- [ ] Connect GitHub repo to Render dashboard
- [ ] Create two services from `render.yaml`:
  - `standup-api` (Web Service — FastAPI)
  - `standup-worker` (Background Worker — APScheduler + LangGraph)
- [ ] Set all env vars in Render dashboard (GROQ_API_KEY, DATABASE_URL, REDIS_URL, etc.)
- [ ] Verify: hit `https://api.yourdomain.com/health` → returns `{"status": "ok"}`
- [ ] Set up UptimeRobot: monitor `https://api.yourdomain.com/health` every 10 minutes (prevents Render sleep)

#### Day 4: Deploy Frontend to Vercel
- [ ] `cd frontend && vercel --prod`
- [ ] Set env vars in Vercel dashboard: `NEXT_PUBLIC_API_URL`, `NEXTAUTH_SECRET`, `NEXTAUTH_URL`
- [ ] Configure custom domain `app.yourdomain.com` in Vercel settings
- [ ] Verify: onboarding wizard loads, OAuth redirects work end-to-end

#### Day 5: Register Slack App + GitHub App (Production)
- [ ] Create Slack App at api.slack.com/apps
  - Set OAuth redirect URL: `https://api.yourdomain.com/auth/slack/callback`
  - Enable Events API: `https://api.yourdomain.com/webhooks/slack/{org_id}`
  - Request scopes: `channels:history`, `users:read`, `chat:write`, `im:write`
  - Submit for Slack App Directory review (takes 1–5 days — submit early)
- [ ] Create GitHub App at github.com/settings/apps
  - Set webhook URL: `https://api.yourdomain.com/webhooks/github/{org_id}`
  - Request permissions: `contents:read`, `pull_requests:read`, `checks:read`, `statuses:read`
  - Generate private key, store as `GITHUB_APP_PRIVATE_KEY` env var

#### Day 6: End-to-End Testing
- [ ] Install your own Slack App in a test workspace
- [ ] Connect GitHub — authorize your own repos
- [ ] Let it run for 24 hours, collecting real signals
- [ ] Manually trigger digest: `POST /digests/{org_id}/trigger`
- [ ] Verify digest appears in Slack with correct format
- [ ] Test intervention: manually create a critical blocker record, verify DM sends
- [ ] Check Groq rate limits are not being hit (dashboard.groq.com)
- [ ] Stress test: simulate 10 developers' worth of events, ensure pipeline completes < 3 min

#### Day 7–8: First Real Beta Teams
- [ ] Write a 90-second Loom video showing the digest appearing in Slack — use your own test workspace
- [ ] Reach out personally to 3–5 engineering team leads you know (warm outreach beats cold)
- [ ] Message template: *"I built something that replaces your daily standup with an AI digest. 5-min install, try it free for a month. Here's the demo: [loom link]"*
- [ ] Onboard each team manually — be present on a call, watch them install it, take notes on every friction point
- [ ] Set up PostHog (free tier) for event tracking: digest_generated, blocker_detected, user_login, integration_connected
- [ ] Create a private Slack channel or WhatsApp group with beta teams for feedback

#### Ongoing (Week 8 → Week 10): Iteration Loop
- [ ] Read every digest your system generates for beta teams — manually verify accuracy
- [ ] Tune blocker inference thresholds based on false positives reported by real devs
- [ ] Add a "👍 / 👎" reaction to each digest post in Slack — track thumbs ratio as your north star metric
- [ ] Fix the top 3 friction points from beta onboarding before doing any broader launch
- [ ] Aim for: at least 1 beta team that says "we cancelled our standup meeting because of this"

---

## 14. Deployment — Complete Zero-Cost Production Stack

### Architecture on Render

```
┌─────────────────────────────────────────────────────────────┐
│                    PRODUCTION INFRA ($0/month)               │
│                                                              │
│  Cloudflare (DNS + SSL + DDoS)                              │
│       │                          │                           │
│  api.yourdomain.com         app.yourdomain.com              │
│       │                          │                           │
│  Render Web Service          Vercel                          │
│  [standup-api]               [Next.js dashboard]            │
│  FastAPI + webhooks          Static + SSR                   │
│  Free tier (sleeps*)                                         │
│       │                                                      │
│  Render Background Worker                                    │
│  [standup-worker]                                           │
│  APScheduler + LangGraph                                    │
│  Free tier (NEVER sleeps ✓)                                 │
│       │                                                      │
│  ┌────┴──────────────────────────────────┐                  │
│  │           External Services            │                  │
│  │  Neon Postgres    → primary DB         │                  │
│  │  Upstash Redis    → job queue          │                  │
│  │  Qdrant Cloud     → vector store       │                  │
│  │  Groq API         → LLM inference      │                  │
│  │  UptimeRobot      → keep-alive pinger  │                  │
│  └────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
* UptimeRobot pings every 10min to prevent Render sleep
```

### render.yaml

```yaml
services:

  # ── Web Service: FastAPI (webhooks, auth, REST API) ──────────
  - type: web
    name: standup-api
    runtime: python
    rootDir: backend
    buildCommand: pip install -r requirements.txt && alembic upgrade head
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    plan: free
    healthCheckPath: /health
    envVars:
      - key: DATABASE_URL
        sync: false                   # set manually in Render dashboard
      - key: REDIS_URL
        sync: false
      - key: QDRANT_URL
        sync: false
      - key: QDRANT_API_KEY
        sync: false
      - key: GROQ_API_KEY
        sync: false
      - key: GROQ_MODEL_HEAVY
        value: llama-3.3-70b-versatile
      - key: GROQ_MODEL_FAST
        value: llama-3.1-8b-instant
      - key: SLACK_CLIENT_ID
        sync: false
      - key: SLACK_CLIENT_SECRET
        sync: false
      - key: SLACK_SIGNING_SECRET
        sync: false
      - key: GITHUB_APP_ID
        sync: false
      - key: GITHUB_APP_PRIVATE_KEY
        sync: false
      - key: ENCRYPTION_KEY
        sync: false
      - key: SECRET_KEY
        sync: false
      - key: ENVIRONMENT
        value: production
      - key: BASE_URL
        value: https://api.yourdomain.com

  # ── Background Worker: Scheduler + LangGraph pipeline ────────
  - type: worker
    name: standup-worker
    runtime: python
    rootDir: backend
    buildCommand: pip install -r requirements.txt
    startCommand: python -m app.scheduler.runner
    plan: free
    envVars:
      - key: DATABASE_URL
        sync: false
      - key: REDIS_URL
        sync: false
      - key: QDRANT_URL
        sync: false
      - key: QDRANT_API_KEY
        sync: false
      - key: GROQ_API_KEY
        sync: false
      - key: GROQ_MODEL_HEAVY
        value: llama-3.3-70b-versatile
      - key: GROQ_MODEL_FAST
        value: llama-3.1-8b-instant
      - key: SLACK_BOT_TOKEN
        sync: false
      - key: ENCRYPTION_KEY
        sync: false
      - key: ENVIRONMENT
        value: production
```

### Free Tier Services — Limits & When to Upgrade

| Service | Free Limit | Upgrade Trigger | Paid Cost |
|---------|-----------|-----------------|-----------|
| Render Web Service | 750 hrs/month, sleeps | 10+ active orgs | $7/mo (Starter) |
| Render Worker | 750 hrs/month, no sleep | Never (worker doesn't sleep) | — |
| Neon Postgres | 0.5GB storage, 1 project | DB hits 400MB | $19/mo |
| Upstash Redis | 10,000 cmds/day | High webhook volume | $0.2/100k cmds |
| Qdrant Cloud | 1GB, 1 cluster | Vector store hits 800MB | $25/mo |
| Groq API | 14,400 req/day | 100+ active teams | ~$0.004/day/team |
| Vercel | 100GB bandwidth | Massive traffic | $20/mo |
| UptimeRobot | 50 monitors | Never for this project | — |
| Cloudflare | Unlimited on free | Never for basic use | — |

**Total at MVP (0–10 teams): $0/month**
**Total at growth (10–50 teams): ~$26–50/month**
**Total at scale (50–200 teams): ~$100–200/month vs $3,000–30,000 MRR**

### Environment Variables — Complete List

```bash
# backend/.env (development) / Render dashboard (production)

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.neon.tech/standup_db?sslmode=require

# Cache & Queue
REDIS_URL=rediss://default:xxx@xxx.upstash.io:6379

# Vector Store
QDRANT_URL=https://xxx.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key

# LLM — Groq (replaces Claude)
GROQ_API_KEY=gsk_xxx
GROQ_MODEL_HEAVY=llama-3.3-70b-versatile    # blocker inference, narrative writer
GROQ_MODEL_FAST=llama-3.1-8b-instant        # signal collector, dep conflict, intervention

# Embeddings — local, free (replaces OpenAI)
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5      # runs on CPU via sentence-transformers

# Slack App
SLACK_CLIENT_ID=xxx
SLACK_CLIENT_SECRET=xxx
SLACK_SIGNING_SECRET=xxx
SLACK_BOT_TOKEN=xoxb-xxx

# GitHub App
GITHUB_APP_ID=xxx
GITHUB_APP_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----\nxxx\n-----END RSA PRIVATE KEY-----
GITHUB_WEBHOOK_SECRET=xxx

# Security
ENCRYPTION_KEY=your_32_byte_hex_key         # for encrypting stored OAuth tokens
SECRET_KEY=your_jwt_secret                   # for session tokens

# App
ENVIRONMENT=production
BASE_URL=https://api.yourdomain.com
FRONTEND_URL=https://app.yourdomain.com

# Analytics
POSTHOG_API_KEY=phc_xxx                      # PostHog free tier
```

### Health Check Endpoint

```python
# backend/app/main.py
from fastapi import FastAPI
from datetime import datetime

app = FastAPI()

@app.get("/health")
async def health():
    """UptimeRobot and Render health check endpoint."""
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }
```

---

## 15. Slack App — Full Implementation

The Slack App is the **primary interface** of the product. It handles OAuth installation, receives events, posts the daily digest with rich Block Kit formatting, and responds to slash commands.

### 15.1 Slack App Manifest (api.slack.com/apps)

Create your app using this manifest — paste it directly into the Slack App config UI:

```yaml
display_information:
  name: Standup Intelligence
  description: Replaces your daily standup with an AI-powered team digest
  background_color: "#1a1a2e"

features:
  bot_user:
    display_name: Standup AI
    always_online: true
  slash_commands:
    - command: /standup
      url: https://api.yourdomain.com/slack/commands
      description: Standup Intelligence commands
      usage_hint: "[trigger | blockers | me | help]"
      should_escape: false

oauth_config:
  redirect_urls:
    - https://api.yourdomain.com/auth/slack/callback
  scopes:
    bot:
      - channels:history       # read message metadata
      - channels:read          # list channels
      - chat:write             # post digest messages
      - im:write               # send DMs to developers
      - users:read             # resolve user profiles
      - users:read.email       # match Slack users to GitHub users
      - team:read              # get workspace info

settings:
  event_subscriptions:
    request_url: https://api.yourdomain.com/webhooks/slack/{org_id}
    bot_events:
      - message.channels       # message activity (metadata only)
      - app_mention            # @Standup AI mentions
  interactivity:
    is_enabled: true
    request_url: https://api.yourdomain.com/slack/interactions
  org_deploy_enabled: false
  socket_mode_enabled: false
```

### 15.2 Slack OAuth Flow

```python
# backend/app/api/auth.py
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
import httpx
from ..database import get_db
from ..models import Organization, Integration
from cryptography.fernet import Fernet
import os, secrets

router = APIRouter()
fernet = Fernet(os.environ["ENCRYPTION_KEY"].encode())

@router.get("/auth/slack")
async def slack_auth_start(request: Request):
    """Step 1 — redirect user to Slack OAuth."""
    state = secrets.token_urlsafe(16)
    # Store state in Redis with 10min TTL to prevent CSRF
    await redis.setex(f"oauth_state:{state}", 600, "pending")

    params = {
        "client_id": os.environ["SLACK_CLIENT_ID"],
        "scope": "channels:history,channels:read,chat:write,im:write,users:read,users:read.email,team:read",
        "redirect_uri": f"{os.environ['BASE_URL']}/auth/slack/callback",
        "state": state,
    }
    url = "https://slack.com/oauth/v2/authorize?" + "&".join(f"{k}={v}" for k, v in params.items())
    return RedirectResponse(url)


@router.get("/auth/slack/callback")
async def slack_auth_callback(code: str, state: str):
    """Step 2 — exchange code for token, save integration."""
    # Verify state
    stored = await redis.get(f"oauth_state:{state}")
    if not stored:
        return RedirectResponse(f"{os.environ['FRONTEND_URL']}/error?msg=invalid_state")

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        resp = await client.post("https://slack.com/api/oauth.v2.access", data={
            "client_id": os.environ["SLACK_CLIENT_ID"],
            "client_secret": os.environ["SLACK_CLIENT_SECRET"],
            "code": code,
            "redirect_uri": f"{os.environ['BASE_URL']}/auth/slack/callback",
        })
    data = resp.json()

    if not data.get("ok"):
        return RedirectResponse(f"{os.environ['FRONTEND_URL']}/error?msg=slack_auth_failed")

    bot_token = data["access_token"]
    team_id   = data["team"]["id"]
    team_name = data["team"]["name"]

    async with get_db() as db:
        # Create or get org
        org = await db.query(Organization).filter_by(slack_team_id=team_id).first()
        if not org:
            org = Organization(
                name=team_name,
                slug=team_id,
                slack_team_id=team_id
            )
            db.add(org)
            await db.flush()

        # Save encrypted token
        encrypted = fernet.encrypt(bot_token.encode()).decode()
        integration = Integration(
            org_id=org.id,
            provider="slack",
            access_token=encrypted,
            metadata={"team_id": team_id, "team_name": team_name}
        )
        db.add(integration)
        await db.commit()

    # Redirect to onboarding wizard
    return RedirectResponse(f"{os.environ['FRONTEND_URL']}/onboarding?org_id={org.id}&step=github")
```

### 15.3 Slack Webhook Receiver (Events API)

```python
# backend/app/api/webhooks/slack.py
from fastapi import APIRouter, Request, HTTPException
from slack_sdk.signature import SignatureVerifier
from ...ingestion.normalizer import normalize_slack_message
from ...ingestion.embedder import embed_and_store_event
from ...database import get_db
from ...models import Developer, Integration
import os, json

router = APIRouter()
verifier = SignatureVerifier(os.environ["SLACK_SIGNING_SECRET"])

@router.post("/webhooks/slack/{org_id}")
async def slack_events(org_id: str, request: Request):
    body_bytes = await request.body()
    body_str   = body_bytes.decode()

    # Verify Slack signature — mandatory security check
    if not verifier.is_valid_request(body_str, dict(request.headers)):
        raise HTTPException(status_code=403, detail="Invalid Slack signature")

    payload = json.loads(body_str)

    # Slack URL verification challenge (one-time on app setup)
    if payload.get("type") == "url_verification":
        return {"challenge": payload["challenge"]}

    event = payload.get("event", {})
    event_type = event.get("type")

    if event_type == "message":
        # Skip bot messages and message edits
        if event.get("bot_id") or event.get("subtype"):
            return {"ok": True}

        slack_user_id = event.get("user")
        if not slack_user_id:
            return {"ok": True}

        async with get_db() as db:
            dev = await db.query(Developer).filter_by(
                org_id=org_id,
                slack_user_id=slack_user_id
            ).first()

        if dev:
            # Normalize — NOTE: we store metadata ONLY, never message text
            normalized = normalize_slack_message(event, str(dev.id), org_id)
            await embed_and_store_event(normalized)

    elif event_type == "app_mention":
        # Someone @mentioned the bot — acknowledge
        await handle_mention(event, org_id)

    return {"ok": True}


async def handle_mention(event: dict, org_id: str):
    """Respond to @Standup AI mentions in channels."""
    from ...delivery.slack_delivery import send_slack_message
    await send_slack_message(
        org_id=org_id,
        channel=event["channel"],
        text="👋 Use `/standup help` to see what I can do!"
    )
```

### 15.4 Slash Commands Handler

```python
# backend/app/api/slack_commands.py
from fastapi import APIRouter, Request, Form
from slack_sdk.web.async_client import AsyncWebClient
from ..agents.graph import pipeline
from ..agents.state import AgentState
from ..database import get_db
from ..models import Organization, Developer, Blocker, Integration
from ..delivery.slack_delivery import get_slack_client
from datetime import date
import json

router = APIRouter()

@router.post("/slack/commands")
async def slash_command(
    request: Request,
    command: str = Form(...),
    text: str = Form(""),
    user_id: str = Form(...),
    team_id: str = Form(...),
    channel_id: str = Form(...),
    response_url: str = Form(...),
):
    """Handle /standup [subcommand]"""
    subcommand = text.strip().lower()

    async with get_db() as db:
        org = await db.query(Organization).filter_by(slack_team_id=team_id).first()
        if not org:
            return {"text": "❌ Standup AI isn't set up for this workspace yet. Visit app.yourdomain.com to connect."}

    if subcommand == "trigger" or subcommand == "":
        return await cmd_trigger(org, channel_id, user_id)

    elif subcommand == "blockers":
        return await cmd_blockers(org)

    elif subcommand == "me":
        return await cmd_me(org, user_id)

    elif subcommand == "help":
        return cmd_help()

    return {"text": f"Unknown command `{subcommand}`. Try `/standup help`"}


async def cmd_trigger(org, channel_id, user_id):
    """Manually trigger a digest run."""
    # Respond immediately (Slack requires < 3s response)
    # Then run pipeline in background
    import asyncio
    asyncio.create_task(run_and_post_digest(org, channel_id))
    return {
        "response_type": "ephemeral",
        "text": "⚙️ Generating your team digest now... it'll appear in the channel in ~60 seconds."
    }


async def cmd_blockers(org):
    """Show all active blockers."""
    async with get_db() as db:
        blockers = await db.query(Blocker).filter_by(
            org_id=org.id,
            resolved_at=None
        ).order_by(Blocker.severity.desc()).all()

    if not blockers:
        return {"response_type": "in_channel", "text": "✅ No active blockers detected!"}

    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "*🚧 Active blockers*"}}]
    for b in blockers[:10]:
        emoji = "🔴" if b.severity == "critical" else "🟡"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{emoji} *{b.developer_name}* — {b.description}"}
        })

    return {"response_type": "in_channel", "blocks": blocks}


async def cmd_me(org, slack_user_id):
    """Show the requesting developer's own signals."""
    async with get_db() as db:
        dev = await db.query(Developer).filter_by(
            org_id=org.id, slack_user_id=slack_user_id
        ).first()

    if not dev:
        return {"response_type": "ephemeral", "text": "❌ Couldn't find your developer profile. Make sure GitHub is connected."}

    # Pull last 24h signals for this dev
    summary = await get_developer_summary(str(dev.id), str(org.id))
    return {
        "response_type": "ephemeral",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": f"*Your signals for today, {dev.name}:*\n{summary}"}}
        ]
    }


def cmd_help():
    return {
        "response_type": "ephemeral",
        "blocks": [
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Standup AI commands:*"}},
            {"type": "section", "text": {"type": "mrkdwn",
                "text": "`/standup` or `/standup trigger` — Generate today's digest now\n`/standup blockers` — Show all active blockers\n`/standup me` — See your own signals\n`/standup help` — Show this message"
            }}
        ]
    }
```

### 15.5 Slack Block Kit Digest Formatter

This is what makes the digest look professional in Slack — rich cards instead of plain text.

```python
# backend/app/delivery/slack_delivery.py
from slack_sdk.web.async_client import AsyncWebClient
from ..database import get_db
from ..models import Integration, Organization, Developer
from cryptography.fernet import Fernet
import os

fernet = Fernet(os.environ["ENCRYPTION_KEY"].encode())


async def get_slack_client(org_id: str) -> AsyncWebClient:
    async with get_db() as db:
        integration = await db.query(Integration).filter_by(
            org_id=org_id, provider="slack"
        ).first()
    token = fernet.decrypt(integration.access_token.encode()).decode()
    return AsyncWebClient(token=token)


def build_digest_blocks(final_state: dict) -> list:
    """
    Converts the agent pipeline output into Slack Block Kit blocks.
    This is what users actually see every morning.
    """
    from datetime import datetime
    blocks = []

    date_str = datetime.utcnow().strftime("%A, %B %-d")

    # ── Header ────────────────────────────────────────────────
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f"🗓 Team Digest — {date_str}"}
    })
    blocks.append({"type": "divider"})

    # ── Per-developer summaries ────────────────────────────────
    for dev in final_state["developer_signals"]:
        dev_id    = dev["developer_id"]
        narrative = final_state["developer_narratives"].get(dev_id, "No activity recorded.")

        # Find this dev's blocker if any
        dev_blockers = [b for b in final_state["blockers"] if b["developer_id"] == dev_id]
        severity_emoji = ""
        if dev_blockers:
            top = dev_blockers[0]
            severity_emoji = " 🔴" if top["severity"] == "critical" else " 🟡"

        # Build accessory with commit count
        commit_count = len(dev.get("commits_today", []))
        pr_count     = len(dev.get("prs_opened", []))

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{dev['developer_name']}*{severity_emoji}\n{narrative}"
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "View signals"},
                "url": f"{os.environ['FRONTEND_URL']}/developers/{dev_id}",
                "action_id": f"view_dev_{dev_id}"
            }
        })

        # Stats context line
        stats_parts = []
        if commit_count: stats_parts.append(f"📝 {commit_count} commit{'s' if commit_count > 1 else ''}")
        if pr_count:     stats_parts.append(f"🔀 {pr_count} PR{'s' if pr_count > 1 else ''}")
        ci_fails = len(dev.get("ci_failures", []))
        if ci_fails:     stats_parts.append(f"❌ {ci_fails} CI failure{'s' if ci_fails > 1 else ''}")

        if stats_parts:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": " · ".join(stats_parts)}]
            })

    blocks.append({"type": "divider"})

    # ── Dependency conflicts ───────────────────────────────────
    if final_state.get("conflicts"):
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*⚠️ Coordinate today*"}
        })
        for c in final_state["conflicts"][:3]:
            files = ", ".join(f"`{f}`" for f in c["files_or_services"][:3])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"› *{c['developer_a']}* × *{c['developer_b']}* — {files}\n_{c['risk']}_"
                }
            })
        blocks.append({"type": "divider"})

    # ── Sprint health ──────────────────────────────────────────
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": f"*Sprint health:* {final_state.get('sprint_risk', 'No issues detected.')}"}
    })

    # ── Footer actions ─────────────────────────────────────────
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "👍 Accurate"},
                "style": "primary",
                "action_id": "digest_thumbsup",
                "value": "up"
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "👎 Not quite"},
                "action_id": "digest_thumbsdown",
                "value": "down"
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "📊 Full dashboard"},
                "url": f"{os.environ['FRONTEND_URL']}/",
                "action_id": "open_dashboard"
            }
        ]
    })

    return blocks


async def deliver_digest(org_id: str, final_state: dict):
    """Post the daily digest to the team's configured channel."""
    async with get_db() as db:
        org = await db.query(Organization).get(org_id)

    channel_id = org.settings.get("digest_channel_id", "general")
    client      = await get_slack_client(org_id)
    blocks      = build_digest_blocks(final_state)

    response = await client.chat_postMessage(
        channel=channel_id,
        text=f"🗓 Team Digest — ready",   # fallback for notifications
        blocks=blocks
    )
    return response["ts"]


async def send_slack_dm(developer_id: str, message: str):
    """Send a proactive DM to a blocked developer."""
    async with get_db() as db:
        dev = await db.query(Developer).get(developer_id)

    client = await get_slack_client(str(dev.org_id))

    # Open DM channel then post
    dm = await client.conversations_open(users=[dev.slack_user_id])
    channel = dm["channel"]["id"]

    await client.chat_postMessage(
        channel=channel,
        text=message,
        blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": message}},
            {"type": "context", "elements": [
                {"type": "mrkdwn", "text": "From Standup AI · _This is an automated observation, not a manager alert_"}
            ]}
        ]
    )


async def send_slack_message(org_id: str, channel: str, text: str):
    client = await get_slack_client(org_id)
    await client.chat_postMessage(channel=channel, text=text)


# ── Interaction handler (thumbs up/down feedback) ──────────────
async def handle_interaction(payload: dict):
    """Process Block Kit button clicks — thumbs up/down on digest."""
    action_id = payload["actions"][0]["action_id"]
    user_id   = payload["user"]["id"]
    team_id   = payload["team"]["id"]

    if action_id in ("digest_thumbsup", "digest_thumbsdown"):
        value = payload["actions"][0]["value"]
        # Store feedback in PostHog or DB
        await store_digest_feedback(team_id, user_id, value)
```

### 15.6 Slack Interaction Handler Endpoint

```python
# backend/app/api/slack_interactions.py
from fastapi import APIRouter, Request, Form
from slack_sdk.signature import SignatureVerifier
from ..delivery.slack_delivery import handle_interaction
import json, os

router = APIRouter()
verifier = SignatureVerifier(os.environ["SLACK_SIGNING_SECRET"])

@router.post("/slack/interactions")
async def slack_interactions(request: Request, payload: str = Form(...)):
    """Handles Block Kit button clicks, modal submissions."""
    body_bytes = await request.body()
    if not verifier.is_valid_request(body_bytes.decode(), dict(request.headers)):
        return {"error": "invalid signature"}

    data = json.loads(payload)
    await handle_interaction(data)
    return {}   # Empty 200 — Slack expects immediate response
```

---

## 16. Web Interface — Full Implementation

The web app handles onboarding, settings, and the developer dashboard. Built with Next.js 14 (App Router) + Tailwind CSS + NextAuth.

### 16.1 Project Setup

```bash
cd frontend
npx create-next-app@latest . --typescript --tailwind --app --src-dir
npm install next-auth @auth/prisma-adapter swr date-fns lucide-react
```

### 16.2 NextAuth Configuration

```typescript
// frontend/src/app/api/auth/[...nextauth]/route.ts
import NextAuth from "next-auth"
import GithubProvider from "next-auth/providers/github"
import type { NextAuthOptions } from "next-auth"

export const authOptions: NextAuthOptions = {
  providers: [
    GithubProvider({
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
      authorization: {
        params: { scope: "read:user user:email" }
      }
    }),
  ],
  callbacks: {
    async session({ session, token }) {
      // Attach org_id from our backend to the session
      if (token.org_id) session.org_id = token.org_id as string
      return session
    },
    async jwt({ token, account }) {
      if (account) {
        // Exchange GitHub token for our app session
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/session`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ github_token: account.access_token })
        })
        const data = await res.json()
        token.org_id = data.org_id
      }
      return token
    }
  },
  pages: {
    signIn: "/login",
    error:  "/error",
  }
}

const handler = NextAuth(authOptions)
export { handler as GET, handler as POST }
```

### 16.3 Pages Overview

```
frontend/src/app/
├── (auth)/
│   └── login/page.tsx              ← Sign in with GitHub
├── onboarding/
│   └── page.tsx                    ← 3-step setup wizard
├── (dashboard)/
│   ├── layout.tsx                  ← Sidebar + nav wrapper
│   ├── page.tsx                    ← Today's digest
│   ├── history/page.tsx            ← Past digests
│   ├── developers/
│   │   ├── page.tsx                ← Team overview
│   │   └── [id]/page.tsx           ← Individual dev timeline
│   ├── blockers/page.tsx           ← Active blockers
│   └── settings/page.tsx           ← Integrations + config
```

### 16.4 Login Page

```tsx
// frontend/src/app/(auth)/login/page.tsx
"use client"
import { signIn } from "next-auth/react"
import { Github } from "lucide-react"

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-10 w-full max-w-md text-center">
        <div className="w-12 h-12 bg-indigo-600 rounded-xl flex items-center justify-center mx-auto mb-6">
          <span className="text-2xl">🗓</span>
        </div>
        <h1 className="text-2xl font-semibold text-white mb-2">Standup Intelligence</h1>
        <p className="text-gray-400 text-sm mb-8">
          Replace your daily standup with an AI-powered team digest.
        </p>
        <button
          onClick={() => signIn("github", { callbackUrl: "/onboarding" })}
          className="w-full flex items-center justify-center gap-3 bg-white text-gray-900 font-medium px-6 py-3 rounded-xl hover:bg-gray-100 transition"
        >
          <Github className="w-5 h-5" />
          Continue with GitHub
        </button>
        <p className="text-gray-600 text-xs mt-6">
          By continuing, you agree to our Terms and Privacy Policy.
        </p>
      </div>
    </div>
  )
}
```

### 16.5 Onboarding Wizard (3 Steps)

```tsx
// frontend/src/app/onboarding/page.tsx
"use client"
import { useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { CheckCircle, Github, Slack, Trello } from "lucide-react"

const STEPS = ["Connect GitHub", "Connect Slack", "Configure digest"]

export default function OnboardingPage() {
  const router       = useRouter()
  const params       = useSearchParams()
  const orgId        = params.get("org_id")
  const initialStep  = Number(params.get("step") ?? 0)
  const [step, setStep]         = useState(initialStep)
  const [digestTime, setDigestTime] = useState("09:00")
  const [timezone, setTimezone]     = useState("Asia/Kolkata")
  const [channel, setChannel]       = useState("")
  const [channels, setChannels]     = useState<{id:string,name:string}[]>([])

  const connectGitHub = () => {
    // Redirect to GitHub App installation
    window.location.href =
      `https://github.com/apps/YOUR_GITHUB_APP/installations/new?state=${orgId}`
  }

  const connectSlack = () => {
    window.location.href = `${process.env.NEXT_PUBLIC_API_URL}/auth/slack`
  }

  const fetchChannels = async () => {
    const res  = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/orgs/${orgId}/slack/channels`)
    const data = await res.json()
    setChannels(data.channels)
  }

  const saveConfig = async () => {
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/org/${orgId}/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        digest_time: digestTime,
        timezone,
        digest_channel_id: channel
      })
    })
    router.push("/")
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-lg">

        {/* Step indicators */}
        <div className="flex items-center gap-2 mb-8">
          {STEPS.map((s, i) => (
            <div key={i} className="flex items-center gap-2 flex-1">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-medium
                ${i < step ? "bg-green-500 text-white" : i === step ? "bg-indigo-600 text-white" : "bg-gray-800 text-gray-500"}`}>
                {i < step ? <CheckCircle className="w-4 h-4" /> : i + 1}
              </div>
              <span className={`text-xs ${i === step ? "text-white" : "text-gray-500"}`}>{s}</span>
              {i < STEPS.length - 1 && <div className="flex-1 h-px bg-gray-800" />}
            </div>
          ))}
        </div>

        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8">

          {/* Step 0: GitHub */}
          {step === 0 && (
            <div className="text-center">
              <Github className="w-12 h-12 text-white mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-white mb-2">Connect GitHub</h2>
              <p className="text-gray-400 text-sm mb-6">
                We'll watch commits, PRs, and CI runs — read-only access.
              </p>
              <button onClick={connectGitHub}
                className="w-full bg-indigo-600 text-white py-3 rounded-xl font-medium hover:bg-indigo-700 transition">
                Install GitHub App
              </button>
              <button onClick={() => setStep(1)}
                className="w-full mt-3 text-gray-500 text-sm hover:text-gray-300 transition">
                Skip for now
              </button>
            </div>
          )}

          {/* Step 1: Slack */}
          {step === 1 && (
            <div className="text-center">
              <Slack className="w-12 h-12 text-green-400 mx-auto mb-4" />
              <h2 className="text-xl font-semibold text-white mb-2">Connect Slack</h2>
              <p className="text-gray-400 text-sm mb-6">
                We track message metadata only — never content. The digest posts here daily.
              </p>
              <button onClick={connectSlack}
                className="w-full bg-green-600 text-white py-3 rounded-xl font-medium hover:bg-green-700 transition">
                Add to Slack
              </button>
              <button onClick={() => setStep(2)}
                className="w-full mt-3 text-gray-500 text-sm hover:text-gray-300 transition">
                Skip for now
              </button>
            </div>
          )}

          {/* Step 2: Configure */}
          {step === 2 && (
            <div>
              <h2 className="text-xl font-semibold text-white mb-6">Configure your digest</h2>
              <div className="space-y-4">
                <div>
                  <label className="text-sm text-gray-400 mb-1 block">Digest time</label>
                  <input type="time" value={digestTime}
                    onChange={e => setDigestTime(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-white" />
                </div>
                <div>
                  <label className="text-sm text-gray-400 mb-1 block">Timezone</label>
                  <select value={timezone} onChange={e => setTimezone(e.target.value)}
                    className="w-full bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-white">
                    <option value="Asia/Kolkata">India (IST)</option>
                    <option value="America/New_York">Eastern (ET)</option>
                    <option value="America/Los_Angeles">Pacific (PT)</option>
                    <option value="Europe/London">London (GMT)</option>
                    <option value="UTC">UTC</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm text-gray-400 mb-1 block">Digest Slack channel</label>
                  <div className="flex gap-2">
                    <input type="text" placeholder="#standup or #engineering"
                      value={channel} onChange={e => setChannel(e.target.value)}
                      className="flex-1 bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-white placeholder-gray-600" />
                  </div>
                </div>
                <button onClick={saveConfig}
                  className="w-full bg-indigo-600 text-white py-3 rounded-xl font-medium hover:bg-indigo-700 transition mt-2">
                  Finish setup →
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
```

### 16.6 Dashboard Layout (Sidebar)

```tsx
// frontend/src/app/(dashboard)/layout.tsx
import { getServerSession } from "next-auth"
import { authOptions } from "../api/auth/[...nextauth]/route"
import { redirect } from "next/navigation"
import Link from "next/link"
import { LayoutDashboard, Users, AlertTriangle, History, Settings } from "lucide-react"

const NAV = [
  { href: "/",            icon: LayoutDashboard, label: "Today's digest" },
  { href: "/developers",  icon: Users,            label: "Team"           },
  { href: "/blockers",    icon: AlertTriangle,    label: "Blockers"       },
  { href: "/history",     icon: History,          label: "History"        },
  { href: "/settings",    icon: Settings,         label: "Settings"       },
]

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const session = await getServerSession(authOptions)
  if (!session) redirect("/login")

  return (
    <div className="min-h-screen bg-gray-950 flex">
      {/* Sidebar */}
      <aside className="w-56 bg-gray-900 border-r border-gray-800 flex flex-col p-4 fixed h-full">
        <div className="flex items-center gap-2 mb-8 px-2">
          <div className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center text-sm">🗓</div>
          <span className="text-white font-medium text-sm">Standup AI</span>
        </div>
        <nav className="flex-1 space-y-1">
          {NAV.map(({ href, icon: Icon, label }) => (
            <Link key={href} href={href}
              className="flex items-center gap-3 px-3 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-800 transition text-sm">
              <Icon className="w-4 h-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-gray-800 pt-4">
          <p className="text-gray-500 text-xs px-2">{session.user?.name}</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="ml-56 flex-1 p-8">{children}</main>
    </div>
  )
}
```

### 16.7 Today's Digest Page

```tsx
// frontend/src/app/(dashboard)/page.tsx
"use client"
import useSWR from "swr"
import { useSession } from "next-auth/react"
import { AlertTriangle, RefreshCw, CheckCircle } from "lucide-react"

const fetcher = (url: string) => fetch(url).then(r => r.json())

export default function TodayPage() {
  const { data: session } = useSession()
  const orgId = (session as any)?.org_id

  const { data, isLoading, mutate } = useSWR(
    orgId ? `${process.env.NEXT_PUBLIC_API_URL}/digests/${orgId}/today` : null,
    fetcher
  )

  const triggerDigest = async () => {
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/digests/${orgId}/trigger`, { method: "POST" })
    setTimeout(() => mutate(), 60000) // refresh after 60s
  }

  if (isLoading) return <div className="text-gray-400 text-sm">Loading digest...</div>

  return (
    <div className="max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-white">Today's digest</h1>
          <p className="text-gray-500 text-sm mt-1">{new Date().toLocaleDateString("en-US", { weekday:"long", month:"long", day:"numeric" })}</p>
        </div>
        <button onClick={triggerDigest}
          className="flex items-center gap-2 bg-gray-800 hover:bg-gray-700 text-white text-sm px-4 py-2 rounded-lg transition">
          <RefreshCw className="w-4 h-4" /> Regenerate
        </button>
      </div>

      {!data?.content ? (
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-12 text-center">
          <p className="text-gray-400">No digest yet today.</p>
          <button onClick={triggerDigest}
            className="mt-4 bg-indigo-600 text-white px-6 py-2 rounded-lg text-sm hover:bg-indigo-700 transition">
            Generate now
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Developer cards */}
          {data.content.developer_signals?.map((dev: any) => {
            const narrative = data.content.developer_narratives?.[dev.developer_id] ?? "No activity."
            const blocker = data.content.blockers?.find((b: any) => b.developer_id === dev.developer_id)

            return (
              <div key={dev.developer_id}
                className="bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-700 transition">
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 bg-indigo-900 rounded-full flex items-center justify-center text-sm font-medium text-indigo-300">
                      {dev.developer_name[0]}
                    </div>
                    <div>
                      <p className="text-white font-medium text-sm">{dev.developer_name}</p>
                      <p className="text-gray-400 text-xs">@{dev.github_username}</p>
                    </div>
                  </div>
                  {blocker ? (
                    <span className={`text-xs px-2 py-1 rounded-full font-medium
                      ${blocker.severity === "critical" ? "bg-red-900 text-red-300" : "bg-yellow-900 text-yellow-300"}`}>
                      {blocker.severity === "critical" ? "🔴 Blocked" : "🟡 Attention"}
                    </span>
                  ) : (
                    <CheckCircle className="w-4 h-4 text-green-500 mt-1" />
                  )}
                </div>
                <p className="text-gray-300 text-sm mt-3 leading-relaxed">{narrative}</p>
                <div className="flex gap-4 mt-3 text-xs text-gray-500">
                  {dev.commits_today?.length > 0 && <span>📝 {dev.commits_today.length} commits</span>}
                  {dev.prs_opened?.length  > 0 && <span>🔀 {dev.prs_opened.length} PRs</span>}
                  {dev.ci_failures?.length > 0 && <span className="text-red-400">❌ {dev.ci_failures.length} CI failures</span>}
                </div>
              </div>
            )
          })}

          {/* Sprint risk */}
          {data.content.sprint_risk && (
            <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
              <p className="text-gray-400 text-xs font-medium uppercase tracking-wide mb-1">Sprint health</p>
              <p className="text-gray-300 text-sm">{data.content.sprint_risk}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
```

### 16.8 Settings Page (Integrations + Config)

```tsx
// frontend/src/app/(dashboard)/settings/page.tsx
"use client"
import { useState, useEffect } from "react"
import { useSession } from "next-auth/react"
import { Github, Slack, CheckCircle, XCircle } from "lucide-react"

export default function SettingsPage() {
  const { data: session } = useSession()
  const orgId = (session as any)?.org_id
  const [settings, setSettings] = useState<any>(null)
  const [integrations, setIntegrations] = useState<any>({})
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!orgId) return
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/org/${orgId}/settings`)
      .then(r => r.json()).then(setSettings)
    fetch(`${process.env.NEXT_PUBLIC_API_URL}/org/${orgId}/integrations`)
      .then(r => r.json()).then(setIntegrations)
  }, [orgId])

  const save = async () => {
    setSaving(true)
    await fetch(`${process.env.NEXT_PUBLIC_API_URL}/org/${orgId}/settings`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings)
    })
    setSaving(false)
  }

  if (!settings) return <div className="text-gray-400 text-sm">Loading...</div>

  return (
    <div className="max-w-2xl space-y-6">
      <h1 className="text-xl font-semibold text-white">Settings</h1>

      {/* Integrations */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <h2 className="text-white font-medium mb-4">Integrations</h2>
        <div className="space-y-3">
          {[
            { key: "github", icon: Github,  label: "GitHub",  color: "text-white",       connect: "/auth/github"  },
            { key: "slack",  icon: Slack,   label: "Slack",   color: "text-green-400",   connect: "/auth/slack"   },
          ].map(({ key, icon: Icon, label, color, connect }) => (
            <div key={key} className="flex items-center justify-between py-2">
              <div className="flex items-center gap-3">
                <Icon className={`w-5 h-5 ${color}`} />
                <span className="text-white text-sm">{label}</span>
              </div>
              {integrations[key] ? (
                <div className="flex items-center gap-2 text-green-400 text-xs">
                  <CheckCircle className="w-4 h-4" /> Connected
                </div>
              ) : (
                <a href={`${process.env.NEXT_PUBLIC_API_URL}${connect}`}
                  className="text-xs bg-gray-800 hover:bg-gray-700 text-white px-3 py-1 rounded-lg transition">
                  Connect
                </a>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Digest config */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <h2 className="text-white font-medium mb-4">Digest configuration</h2>
        <div className="space-y-4">
          <div>
            <label className="text-sm text-gray-400 block mb-1">Daily digest time</label>
            <input type="time" value={settings.digest_time ?? "09:00"}
              onChange={e => setSettings({...settings, digest_time: e.target.value})}
              className="bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-white w-full" />
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">Timezone</label>
            <select value={settings.timezone ?? "UTC"}
              onChange={e => setSettings({...settings, timezone: e.target.value})}
              className="bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-white w-full">
              <option value="Asia/Kolkata">India (IST)</option>
              <option value="America/New_York">Eastern (ET)</option>
              <option value="America/Los_Angeles">Pacific (PT)</option>
              <option value="Europe/London">London (GMT)</option>
              <option value="UTC">UTC</option>
            </select>
          </div>
          <div>
            <label className="text-sm text-gray-400 block mb-1">Quiet hours (no DMs between)</label>
            <div className="flex gap-3">
              <input type="time" value={settings.quiet_start ?? "20:00"}
                onChange={e => setSettings({...settings, quiet_start: e.target.value})}
                className="bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-white flex-1" />
              <span className="text-gray-500 self-center">to</span>
              <input type="time" value={settings.quiet_end ?? "09:00"}
                onChange={e => setSettings({...settings, quiet_end: e.target.value})}
                className="bg-gray-800 border border-gray-700 rounded-xl px-4 py-2 text-white flex-1" />
            </div>
          </div>
          <button onClick={save} disabled={saving}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-xl text-sm font-medium transition disabled:opacity-50">
            {saving ? "Saving..." : "Save settings"}
          </button>
        </div>
      </div>

      {/* Privacy controls */}
      <div className="bg-gray-900 border border-gray-800 rounded-2xl p-6">
        <h2 className="text-white font-medium mb-1">Privacy</h2>
        <p className="text-gray-500 text-xs mb-4">Individual developers can opt out at any time.</p>
        <div className="space-y-2">
          {["No message content is ever stored — metadata only",
            "All digest data visible to the whole team, not just managers",
            "Raw activity events purged after 90 days",
            "Any developer can opt out from their profile page"
          ].map(item => (
            <div key={item} className="flex items-center gap-2 text-xs text-gray-400">
              <CheckCircle className="w-3.5 h-3.5 text-green-500 flex-shrink-0" />
              {item}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
```

### 16.9 Frontend Environment Variables

```bash
# frontend/.env.local
NEXT_PUBLIC_API_URL=https://api.yourdomain.com   # your Render backend URL
NEXTAUTH_URL=https://app.yourdomain.com           # your Vercel frontend URL
NEXTAUTH_SECRET=your_random_32_char_secret

# GitHub OAuth App (separate from GitHub App — for user login only)
GITHUB_CLIENT_ID=your_github_oauth_app_client_id
GITHUB_CLIENT_SECRET=your_github_oauth_app_secret
```

> **Note:** Two different GitHub credentials are needed:
> - **GitHub App** (backend) — watches repos for commits/PRs/CI. Set up at github.com/settings/apps.
> - **GitHub OAuth App** (frontend) — logs users into your web dashboard. Set up at github.com/settings/developers.

1. **No message content stored** — only metadata (message sent, channel, has_question boolean)
2. **Developer-first view** — each dev can see their own signals dashboard
3. **Opt-out per developer** — any dev can turn off their monitoring
4. **Data retention policy** — raw events purged after 90 days
5. **No manager-only views** — all digest data visible to the whole team
6. **Explicit consent** — team lead must get team buy-in before activating
