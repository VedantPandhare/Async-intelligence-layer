import json
import re

import anthropic

from ..config import get_settings
from .state import AgentState, InferredBlocker

MODEL = "claude-haiku-4-5-20251001"


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)

SYSTEM_PROMPT = """You are an expert engineering team observer. Your job is to detect
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

Return ONLY valid JSON. No prose."""


async def blocker_inference_node(state: AgentState) -> AgentState:
    if not state.get("developer_signals"):
        return {**state, "blockers": []}

    errors: list[str] = list(state.get("errors", []))

    user_msg = f"""Analyze these developer signals for org {state["org_id"]} on {state["digest_date"]}:

{json.dumps(state["developer_signals"], indent=2)}

Return JSON array of blockers:
[{{
  "developer_id": "...",
  "blocker_type": "ci_failure|pr_stalled|silence|dependency_wait|estimation_problem",
  "severity": "critical|high|medium|low",
  "description": "Plain English explanation of what the blocker is",
  "signals": ["list", "of", "evidence"],
  "suggested_action": "Who should do what to unblock"
}}]"""

    try:
        response = await _client().messages.create(
            model=MODEL,
            max_tokens=3000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        content = response.content[0].text
        try:
            blockers: list[InferredBlocker] = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", content, re.DOTALL)
            blockers = json.loads(match.group()) if match else []

    except Exception as exc:
        errors.append(f"blocker_inference: {exc}")
        blockers = []

    return {**state, "blockers": blockers, "errors": errors}
