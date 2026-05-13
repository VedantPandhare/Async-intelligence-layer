import anthropic

from ..config import get_settings
from .state import AgentState

MODEL = "claude-haiku-4-5-20251001"


def _client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)

SYSTEM_PROMPT = """You write brief, friendly Slack DMs to unblock developers.
The message should feel like a helpful colleague checking in — NOT a manager pinging for a status update.
Keep it under 3 sentences. Offer concrete help. Suggest who to talk to. Never be accusatory."""


async def intervention_node(state: AgentState) -> AgentState:
    critical_blockers = [b for b in state.get("blockers", []) if b.get("severity") == "critical"]
    if not critical_blockers:
        return state

    dev_map = {d["developer_id"]: d for d in state.get("developer_signals", [])}
    errors: list[str] = list(state.get("errors", []))

    for blocker in critical_blockers:
        dev = dev_map.get(blocker["developer_id"])
        if not dev:
            continue
        try:
            response = await _client().messages.create(
                model=MODEL,
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": (
                    f"Write a Slack DM to {dev['developer_name']} about this blocker: "
                    f"{blocker['description']}\nSuggested action: {blocker['suggested_action']}"
                )}],
            )
            from ..delivery.slack_delivery import send_slack_dm
            await send_slack_dm(
                developer_id=blocker["developer_id"],
                message=response.content[0].text,
            )
        except Exception as exc:
            errors.append(f"intervention for {blocker['developer_id']}: {exc}")

    return {**state, "errors": errors}
