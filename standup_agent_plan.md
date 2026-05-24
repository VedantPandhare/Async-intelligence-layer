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

### Week 8 — Beta
- [ ] Deploy to Railway (backend) + Vercel (frontend)
- [ ] Recruit 2–3 real engineering teams
- [ ] Instrument with PostHog for usage analytics
- [ ] Iterate on digest quality from real feedback

---

## 14. Deployment (Production)

```
Railway.app (Backend)
  └── FastAPI service
  └── PostgreSQL (managed)
  └── Redis (managed)
  └── Background worker (scheduler + pollers)

Qdrant Cloud (Free tier → paid at scale)

Vercel (Frontend)
  └── Next.js app
  └── Edge functions for auth

Cloudflare (Optional)
  └── DDoS protection
  └── Webhook proxy for reliability
```

Total infra cost for MVP: ~$20–40/month before you have paying customers.

---

## 15. Privacy & Trust Principles

1. **No message content stored** — only metadata (message sent, channel, has_question boolean)
2. **Developer-first view** — each dev can see their own signals dashboard
3. **Opt-out per developer** — any dev can turn off their monitoring
4. **Data retention policy** — raw events purged after 90 days
5. **No manager-only views** — all digest data visible to the whole team
6. **Explicit consent** — team lead must get team buy-in before activating
