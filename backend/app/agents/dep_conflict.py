import json
import re
from itertools import combinations

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from .state import AgentState, DependencyConflict

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
}}]"""),
])


async def dep_conflict_node(state: AgentState) -> AgentState:
    signals = state.get("developer_signals", [])
    errors: list[str] = list(state.get("errors", []))

    if len(signals) < 2:
        return {**state, "conflicts": []}

    pairs = []
    for a, b in combinations(signals, 2):
        overlap = set(a["files_touched"]) & set(b["files_touched"])
        if overlap:
            pairs.append({
                "dev_a": a["developer_name"],
                "dev_b": b["developer_name"],
                "shared_files": list(overlap),
                "dev_a_tickets": [t.get("title") for t in a["tickets_updated"]],
                "dev_b_tickets": [t.get("title") for t in b["tickets_updated"]],
            })

    if not pairs:
        return {**state, "conflicts": []}

    try:
        chain = DEP_CONFLICT_PROMPT | llm
        response = await chain.ainvoke({"pairs_json": json.dumps(pairs, indent=2)})

        content = response.content
        try:
            conflicts: list[DependencyConflict] = json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\[.*\]", content, re.DOTALL)
            conflicts = json.loads(match.group()) if match else []

    except Exception as exc:
        errors.append(f"dep_conflict: {exc}")
        conflicts = []

    return {**state, "conflicts": conflicts, "errors": errors}
