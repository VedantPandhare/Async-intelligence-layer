import json
import re

import anthropic

from ..config import get_settings
from .state import AgentState

MODEL = "claude-haiku-4-5-20251001"


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)

SYSTEM_PROMPT = """You write developer digest summaries the way a senior engineer would describe a colleague's day to the rest of the team.

Rules:
- 2-3 sentences per developer
- Interpret the commits — describe WHAT was built or changed, not just list the commit message text.
  Example: instead of "committed 'Add styled HTML contact form'", write "built a styled contact form on the frontend"
- Group related commits into a single work area description. If someone pushed 3 README updates, say "updated the README" once, not three times.
- Name the repo (from commits_today[].repo) so readers know the context
- Mention PRs or CI failures only if present — skip the sentence entirely if not
- Do NOT mention velocity, baselines, pace comparisons, silence hours, or data quality
- Do NOT pad with phrases like "indicating sustained output", "showing active engagement", "it appears", "seems to be"
- If commits_today is empty and prs_opened is empty: write exactly "No activity today."
- Tone: one engineer telling another what their teammate shipped — specific, human, zero corporate fluff"""


async def narrative_writer_node(state: AgentState) -> AgentState:
    errors: list[str] = list(state.get("errors", []))

    if not state.get("developer_signals"):
        return {**state, "developer_narratives": {}, "sprint_risk": "No activity data available."}

    user_msg = f"""Summarise each developer's day based on their actual commits and PRs.

Interpret the work — describe what was built or changed, not just the commit message text.
Use the repo name from commits_today[].repo and derive meaning from commits_today[].message.
2-3 sentences max. No velocity, no pace analysis.

Developer signals:
{json.dumps(state["developer_signals"], indent=2)}

Blockers (mention only if present):
{json.dumps(state.get("blockers", []), indent=2)}

Return JSON only:
{{
  "developer_summaries": {{
    "<developer_id>": "<2-3 sentence summary describing what was built>"
  }},
  "sprint_risk": "<1 sentence: CI failures or blockers if any, otherwise 'No blockers.'>"
}}"""

    try:
        response = await _client().messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        content = response.content[0].text
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            result = json.loads(match.group()) if match else {}

        raw_narratives = result.get("developer_summaries", {})
        sprint_risk = result.get("sprint_risk", "Sprint risk could not be assessed.")

        # LLMs sometimes use developer_name or github_username as key instead of UUID
        signals = state.get("developer_signals", [])
        name_to_id = {s["developer_name"]: s["developer_id"] for s in signals}
        github_to_id = {s["github_username"]: s["developer_id"] for s in signals if s.get("github_username")}
        narratives: dict[str, str] = {}
        for key, summary in raw_narratives.items():
            resolved = name_to_id.get(key) or github_to_id.get(key) or key
            narratives[resolved] = summary

    except Exception as exc:
        errors.append(f"narrative_writer: {exc}")
        narratives = {}
        sprint_risk = "Unable to assess sprint risk."

    return {**state, "developer_narratives": narratives, "sprint_risk": sprint_risk, "errors": errors}
