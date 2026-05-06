import json
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from .state import AgentState

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
}}"""),
])


async def narrative_writer_node(state: AgentState) -> AgentState:
    errors: list[str] = list(state.get("errors", []))

    if not state.get("developer_signals"):
        return {**state, "developer_narratives": {}, "sprint_risk": "No activity data available."}

    try:
        chain = NARRATIVE_PROMPT | llm
        response = await chain.ainvoke({
            "signals_json": json.dumps(state["developer_signals"], indent=2),
            "blockers_json": json.dumps(state.get("blockers", []), indent=2),
            "conflicts_json": json.dumps(state.get("conflicts", []), indent=2),
        })

        content = response.content
        try:
            result = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            result = json.loads(match.group()) if match else {}

        narratives = result.get("developer_summaries", {})
        sprint_risk = result.get("sprint_risk", "Sprint risk could not be assessed.")

    except Exception as exc:
        errors.append(f"narrative_writer: {exc}")
        narratives = {}
        sprint_risk = "Unable to assess sprint risk."

    return {**state, "developer_narratives": narratives, "sprint_risk": sprint_risk, "errors": errors}
