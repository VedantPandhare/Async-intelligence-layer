import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..database import get_db
from ..models.activity_event import ActivityEvent
from ..models.developer import Developer
from .state import AgentState, DeveloperSignals


async def signal_collector_node(state: AgentState) -> AgentState:
    """
    Queries 24h of activity events for all active developers in the org,
    aggregates per-developer behavioral metrics, and returns DeveloperSignals.
    """
    org_id = uuid.UUID(state["org_id"])
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    errors: list[str] = list(state.get("errors", []))

    try:
        async with get_db() as db:
            devs_result = await db.execute(
                select(Developer).where(
                    Developer.org_id == org_id,
                    Developer.is_active.is_(True),
                )
            )
            developers = devs_result.scalars().all()

            developer_signals: list[DeveloperSignals] = []

            for dev in developers:
                # All events in last 24h
                events_result = await db.execute(
                    select(ActivityEvent)
                    .where(
                        ActivityEvent.developer_id == dev.id,
                        ActivityEvent.event_time >= since,
                    )
                    .order_by(ActivityEvent.event_time.desc())
                )
                events = events_result.scalars().all()

                commits = [e.payload for e in events if e.event_type == "commit"]
                prs_opened = [e.payload for e in events if e.event_type == "pr_open"]
                prs_reviewed = [e.payload for e in events if e.event_type == "pr_review"]
                ci_failures = [
                    e.payload for e in events
                    if e.event_type == "ci_run" and e.payload.get("status") in ("failure", "failed")
                ]
                slack_msgs = [e for e in events if e.source == "slack"]
                tickets = [e.payload for e in events if e.source in ("jira", "linear")]

                files_touched: list[str] = list(
                    {f for c in commits for f in c.get("files_changed", [])}
                )

                # Commit velocity delta vs 7-day average
                week_count_result = await db.execute(
                    select(func.count()).where(
                        ActivityEvent.developer_id == dev.id,
                        ActivityEvent.event_type == "commit",
                        ActivityEvent.event_time >= week_ago,
                    )
                )
                past_week_commits = week_count_result.scalar() or 0
                avg_daily = past_week_commits / 7
                velocity_delta = (len(commits) - avg_daily) / max(avg_daily, 1)

                # Hours of silence
                last_event = events[0] if events else None
                if last_event and last_event.event_time:
                    last_ts = last_event.event_time
                    if last_ts.tzinfo is None:
                        last_ts = last_ts.replace(tzinfo=timezone.utc)
                    silence_hours = (datetime.now(timezone.utc) - last_ts).total_seconds() / 3600
                else:
                    silence_hours = 24.0

                developer_signals.append(
                    DeveloperSignals(
                        developer_id=str(dev.id),
                        developer_name=dev.name,
                        github_username=dev.github_username or "",
                        commits_today=commits,
                        prs_opened=prs_opened,
                        prs_reviewed=prs_reviewed,
                        ci_failures=ci_failures,
                        slack_messages_count=len(slack_msgs),
                        last_slack_message_at=(
                            slack_msgs[0].event_time.isoformat() if slack_msgs else None
                        ),
                        tickets_updated=tickets,
                        files_touched=files_touched,
                        commit_velocity_delta=round(velocity_delta, 3),
                        silence_hours=round(silence_hours, 2),
                    )
                )

    except Exception as exc:
        errors.append(f"signal_collector: {exc}")
        developer_signals = []

    return {**state, "developer_signals": developer_signals, "errors": errors}
