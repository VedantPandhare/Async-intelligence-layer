import json
import re

import anthropic

from ..config import get_settings
from .state import AgentState

MODEL = "claude-haiku-4-5-20251001"


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)

SYSTEM_PROMPT = """You write developer digest summaries the way a senior engineer would describe a colleague's recent work to the rest of the team.

Rules:
- 3-4 sentences per developer
- Sentence 1: Describe WHAT was built or changed — interpret the work, don't just re-state the commit message. Say "built a styled contact form" not "committed 'Add styled HTML contact form'". Name the repo.
- Sentence 2: List the actual commit messages as a reference, formatted like: Commits: "Add styled HTML contact form", "Update README"
- Sentence 3: If there are PRs, CI failures, or blockers — mention them. Otherwise skip.
- Sentence 4 (optional): Any relevant follow-up context — what might come next, or what area of the product this affects.
- Do NOT mention velocity, baselines, pace comparisons, silence hours, or data quality issues
- Do NOT pad with "indicating sustained output", "showing active engagement", "it appears", "seems to be"
- If commits_today is empty and prs_opened is empty: write exactly "No activity today."
- Tone: a knowledgeable teammate explaining what got shipped — specific, useful, zero corporate filler"""


async def narrative_writer_node(state: AgentState) -> AgentState:
    errors: list[str] = list(state.get("errors", []))

    if not state.get("developer_signals"):
        return {**state, "developer_narratives": {}, "sprint_risk": "No activity data available."}

    user_msg = f"""Write a digest summary for each developer based on their recent commits and PRs.

For each developer:
- Interpret what they built (don't just list commit messages) — use commits_today[].message and commits_today[].repo
- Then list the raw commit messages on a second sentence: Commits: "msg1", "msg2"
- 3-4 sentences total. No velocity or pace analysis.

Developer signals:
{json.dumps(state["developer_signals"], indent=2)}

Blockers (mention only if present):
{json.dumps(state.get("blockers", []), indent=2)}

Return JSON only:
{{
  "developer_summaries": {{
    "<developer_id>": "<3-4 sentence summary>"
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
