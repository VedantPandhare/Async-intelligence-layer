from datetime import datetime

from .state import AgentState


def digest_assembler_node(state: AgentState) -> AgentState:
    """
    Pure Python — assembles the final Slack-formatted digest from all agent outputs.
    No LLM call needed here.
    """
    lines: list[str] = []
    now = datetime.utcnow()
    date_str = f"{now.strftime('%A, %B')} {now.day}"

    lines.append(f"*🗓 Team Digest — {date_str}*\n")

    signals = state.get("developer_signals", [])
    narratives = state.get("developer_narratives", {})

    if not signals:
        lines.append("_No developer activity recorded for this period._")
    else:
        for dev in signals:
            dev_id = dev["developer_id"]
            narrative = narratives.get(dev_id, "_No summary available._")
            lines.append(f"*{dev['developer_name']}* — {narrative}")

    lines.append("")

    conflicts = state.get("conflicts", [])
    if conflicts:
        lines.append("*⚠️ Coordination needed*")
        for c in conflicts:
            overlap = c.get("files_or_services", [])[:3]
            overlap_str = "`, `".join(overlap)
            lines.append(
                f"› {c['developer_a']} × {c['developer_b']}: "
                f"{c['risk']} — `{overlap_str}`"
            )
        lines.append("")

    sprint_risk = state.get("sprint_risk", "")
    if sprint_risk:
        lines.append(f"*Sprint health:* {sprint_risk}")

    final_digest = "\n".join(lines)

    has_critical = any(
        b.get("severity") == "critical" for b in state.get("blockers", [])
    )

    return {**state, "final_digest": final_digest, "should_intervene": has_critical}
