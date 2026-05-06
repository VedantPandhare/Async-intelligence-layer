import json

from langchain_anthropic import ChatAnthropic
from langchain_core.prompts import ChatPromptTemplate

from .state import AgentState

llm = ChatAnthropic(model="claude-sonnet-4-20250514", max_tokens=500)

INTERVENTION_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You write brief, friendly Slack DMs to unblock developers.
The message should feel like a helpful colleague checking in — NOT a manager pinging for a status update.
Keep it under 3 sentences. Offer concrete help. Suggest who to talk to. Never be accusatory."""),
    ("human", "Write a Slack DM to {developer_name} about this blocker: {blocker_description}\nSuggested action: {suggested_action}"),
])


async def intervention_node(state: AgentState) -> AgentState:
    critical_blockers = [b for b in state.get("blockers", []) if b.get("severity") == "critical"]
    if not critical_blockers:
        return state

    dev_map = {d["developer_id"]: d for d in state.get("developer_signals", [])}
    chain = INTERVENTION_PROMPT | llm
    errors: list[str] = list(state.get("errors", []))

    for blocker in critical_blockers:
        dev = dev_map.get(blocker["developer_id"])
        if not dev:
            continue
        try:
            response = await chain.ainvoke({
                "developer_name": dev["developer_name"],
                "blocker_description": blocker["description"],
                "suggested_action": blocker["suggested_action"],
            })
            # Delivery handled by slack_delivery — import here to avoid circular deps
            from ..delivery.slack_delivery import send_slack_dm
            await send_slack_dm(
                developer_id=blocker["developer_id"],
                message=response.content,
            )
        except Exception as exc:
            errors.append(f"intervention for {blocker['developer_id']}: {exc}")

    return {**state, "errors": errors}
