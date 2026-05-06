import json
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from .state import AgentState, InferredBlocker

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
}}]"""),
])


async def blocker_inference_node(state: AgentState) -> AgentState:
    if not state.get("developer_signals"):
        return {**state, "blockers": []}

    errors: list[str] = list(state.get("errors", []))

    try:
        chain = BLOCKER_PROMPT | llm
        response = await chain.ainvoke({
            "org_id": state["org_id"],
            "digest_date": state["digest_date"],
            "signals_json": json.dumps(state["developer_signals"], indent=2),
        })

        content = response.content
        try:
            blockers: list[InferredBlocker] = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", content, re.DOTALL)
            blockers = json.loads(match.group()) if match else []

    except Exception as exc:
        errors.append(f"blocker_inference: {exc}")
        blockers = []

    return {**state, "blockers": blockers, "errors": errors}
