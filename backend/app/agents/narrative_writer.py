import json
import re

import anthropic

from ..config import get_settings
from .state import AgentState

MODEL = "claude-haiku-4-5-20251001"


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)

SYSTEM_PROMPT = """You write detailed, honest, human-sounding developer summaries
for a team digest. You are writing for the team — not for management surveillance.

Rules:
- Each developer summary: 4-5 sentences
- Sentence 1: What they worked on — name the EXACT repo and quote/paraphrase the actual commit message(s)
- Sentence 2: Describe the scope of the work — mention files changed, additions/deletions if available, or what area of the codebase was touched
- Sentence 3: Note their velocity — are they above or below their usual pace? (commit_velocity_delta > 0.3 = strong, < -0.3 = slow)
- Sentence 4: Flag any blockers, CI failures, or silence concerns if present; if none, note what's going well
- Sentence 5 (optional): Any coordination note — PRs opened, reviews given, tickets updated
- Tone: like a senior engineer summarizing a colleague's week — specific, direct, no filler
- ALWAYS use the exact repo name and exact commit message text from commits_today[].message and commits_today[].repo
- If commits_today is empty but prs_opened is not, lead with the PR title and repo instead
- Flag blockers with emoji: 🔴 critical, 🟡 attention needed, ✅ going well
- Never say "it appears" or "seems to be" — state it plainly
- Never say "No activity" when commits_today or prs_opened has data
- Never mention surveillance or that you're watching behavior"""


async def narrative_writer_node(state: AgentState) -> AgentState:
    errors: list[str] = list(state.get("errors", []))

    if not state.get("developer_signals"):
        return {**state, "developer_narratives": {}, "sprint_risk": "No activity data available."}

    user_msg = f"""Write detailed summaries for these developers based on their actual activity.

Developer signals — commits_today[].message = real commit messages, commits_today[].repo = repo name,
commits_today[].files_changed = list of files, commits_today[].additions / .deletions = line counts.
Use ALL of this data to write a specific, grounded summary. Do not make anything up.

Developer signals:
{json.dumps(state["developer_signals"], indent=2)}

Inferred blockers:
{json.dumps(state.get("blockers", []), indent=2)}

Dependency conflicts:
{json.dumps(state.get("conflicts", []), indent=2)}

Write 4-5 sentences per developer. Lead with the actual repo name and commit message.
If files_changed lists specific files, mention 1-2 of them. Note velocity trend.

Also write a 2-sentence sprint risk assessment covering the whole team.

Return JSON only:
{{
  "developer_summaries": {{
    "<developer_id>": "<4-5 sentence summary with specific repo, commit messages, file details>"
  }},
  "sprint_risk": "<2 sentence overall team risk assessment>"
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
