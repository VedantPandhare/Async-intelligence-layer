from datetime import datetime

from .state import AgentState


def digest_assembler_node(state: AgentState) -> AgentState:
    now = datetime.utcnow()
    date_str = f"{now.strftime('%A, %B')} {now.day}"

    sections: list[str] = []
    sections.append(f"## 🗓 Team Digest — {date_str}")

    signals = state.get("developer_signals", [])
    narratives = state.get("developer_narratives", {})
    blockers = state.get("blockers", [])
    blocker_map: dict[str, str] = {b["developer_id"]: b["severity"] for b in blockers}

    if not signals:
        sections.append("_No developer activity recorded for this period._")
    else:
        dev_blocks: list[str] = []
        for dev in signals:
            dev_id = dev["developer_id"]
            narrative = narratives.get(dev_id, "No summary available.")

            severity = blocker_map.get(dev_id)
            if severity == "critical":
                icon = "🔴"
            elif severity == "high":
                icon = "🟠"
            elif severity == "medium":
                icon = "🟡"
            else:
                commits = dev.get("commits_today", [])
                icon = "✅" if commits else "⚪"

            commit_count = len(dev.get("commits_today", []))
            pr_count = len(dev.get("prs_opened", []))
            meta_parts = []
            if commit_count:
                meta_parts.append(f"{commit_count} commit{'s' if commit_count != 1 else ''}")
            if pr_count:
                meta_parts.append(f"{pr_count} PR{'s' if pr_count != 1 else ''} opened")
            meta = f"  \n*{', '.join(meta_parts)}*" if meta_parts else ""

            dev_blocks.append(f"### {icon} {dev['developer_name']}\n{narrative}{meta}")

        sections.append("\n\n---\n\n".join(dev_blocks))

    conflicts = state.get("conflicts", [])
    if conflicts:
        conflict_lines = ["### ⚠️ Coordination Needed"]
        for c in conflicts:
            overlap = c.get("files_or_services", [])[:3]
            overlap_str = ", ".join(f"`{f}`" for f in overlap)
            conflict_lines.append(
                f"**{c['developer_a']}** × **{c['developer_b']}**: {c['risk']}"
                + (f" — {overlap_str}" if overlap_str else "")
            )
        sections.append("\n".join(conflict_lines))

    sprint_risk = state.get("sprint_risk", "")
    if sprint_risk:
        sections.append(f"---\n\n**Sprint health:** {sprint_risk}")

    final_digest = "\n\n".join(sections)

    has_critical = any(b.get("severity") == "critical" for b in blockers)
    return {**state, "final_digest": final_digest, "should_intervene": has_critical}
