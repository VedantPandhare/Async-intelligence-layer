from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models.activity_event import ActivityEvent


@dataclass
class NormalizedEvent:
    developer_id: str
    org_id: str
    source: str           # 'github' | 'slack' | 'jira' | 'linear'
    event_type: str       # 'commit' | 'pr_open' | 'pr_review' | 'ci_run' | 'message' | 'ticket_update'
    event_time: datetime
    payload: dict[str, Any]
    summary: str          # human-readable string used for embedding


def normalize_github_commit(raw: dict, developer_id: str, org_id: str) -> NormalizedEvent:
    commit_data = raw.get("commit", raw)
    author = commit_data.get("author", {})
    # PushEvent commits have no author.date — fall back to the event's created_at (pushed_at)
    date_str = author.get("date") or raw.get("pushed_at") or raw.get("committed_date", "")

    try:
        event_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        event_time = datetime.utcnow()

    message = commit_data.get("message", "")
    files = [f["filename"] for f in raw.get("files", [])]

    return NormalizedEvent(
        developer_id=developer_id,
        org_id=org_id,
        source="github",
        event_type="commit",
        event_time=event_time,
        payload={
            "sha": raw.get("sha", "")[:8],
            "message": message[:200],
            "files_changed": files,
            "additions": raw.get("stats", {}).get("additions", 0),
            "deletions": raw.get("stats", {}).get("deletions", 0),
            "repo": raw.get("repo", ""),
        },
        summary=f"Committed: {message[:100]}",
    )


def normalize_github_pr(raw: dict, developer_id: str, org_id: str) -> NormalizedEvent:
    action = raw.get("action", "opened")
    pr = raw.get("pull_request", raw)
    title = pr.get("title", "")

    try:
        event_time = datetime.fromisoformat(
            pr.get("created_at", pr.get("updated_at", "")).replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        event_time = datetime.utcnow()

    event_type = "pr_review" if action in ("review_requested", "reviewed") else "pr_open"

    return NormalizedEvent(
        developer_id=developer_id,
        org_id=org_id,
        source="github",
        event_type=event_type,
        event_time=event_time,
        payload={
            "pr_number": pr.get("number"),
            "title": title[:200],
            "action": action,
            "state": pr.get("state", "open"),
            "repo": raw.get("repo", ""),
            "reviews_count": pr.get("review_comments", 0),
            "days_open": (
                (datetime.utcnow() - event_time.replace(tzinfo=None)).days
                if event_time else 0
            ),
        },
        summary=f"PR {action}: {title[:100]}",
    )


def normalize_github_ci_run(raw: dict, developer_id: str, org_id: str) -> NormalizedEvent:
    check_run = raw.get("check_run", raw)
    status = check_run.get("conclusion") or check_run.get("status", "unknown")

    try:
        event_time = datetime.fromisoformat(
            check_run.get("completed_at", check_run.get("started_at", "")).replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        event_time = datetime.utcnow()

    return NormalizedEvent(
        developer_id=developer_id,
        org_id=org_id,
        source="github",
        event_type="ci_run",
        event_time=event_time,
        payload={
            "name": check_run.get("name", "CI"),
            "status": status,
            "conclusion": check_run.get("conclusion"),
            "repo": raw.get("repo", ""),
            "head_sha": check_run.get("head_sha", "")[:8],
        },
        summary=f"CI run {status}: {check_run.get('name', 'CI')}",
    )


def normalize_slack_message(raw: dict, developer_id: str, org_id: str) -> NormalizedEvent:
    try:
        event_time = datetime.fromtimestamp(float(raw.get("ts", 0)))
    except (ValueError, TypeError):
        event_time = datetime.utcnow()

    text = raw.get("text", "")

    return NormalizedEvent(
        developer_id=developer_id,
        org_id=org_id,
        source="slack",
        event_type="message",
        event_time=event_time,
        payload={
            "channel": raw.get("channel", ""),
            "channel_name": raw.get("channel_name", "unknown"),
            "text_length": len(text),
            "has_question": "?" in text,
            "thread_reply": bool(raw.get("thread_ts")),
        },
        summary=f"Slack message in #{raw.get('channel_name', 'unknown')}",
    )


def normalize_jira_issue(raw: dict, developer_id: str, org_id: str) -> NormalizedEvent:
    issue = raw.get("issue", raw)
    fields = issue.get("fields", {})
    changelog = raw.get("changelog", {})

    try:
        event_time = datetime.fromisoformat(
            fields.get("updated", "").replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        event_time = datetime.utcnow()

    status = fields.get("status", {}).get("name", "unknown")
    title = fields.get("summary", "")

    return NormalizedEvent(
        developer_id=developer_id,
        org_id=org_id,
        source="jira",
        event_type="ticket_update",
        event_time=event_time,
        payload={
            "issue_key": issue.get("key", ""),
            "title": title[:200],
            "status": status,
            "changelog": changelog,
        },
        summary=f"Ticket {issue.get('key', '')}: {title[:80]} → {status}",
    )


async def store_event(event: NormalizedEvent, db: AsyncSession) -> ActivityEvent:
    """Persist a NormalizedEvent to activity_events table, skipping exact duplicates."""
    import uuid as _uuid
    from datetime import timezone as _tz
    from sqlalchemy import select as sa_select
    from ..models.activity_event import ActivityEvent as AE

    # Ensure event_time is timezone-aware (DB column is TIMESTAMPTZ)
    et = event.event_time
    if et.tzinfo is None:
        et = et.replace(tzinfo=_tz.utc)

    # Dedup: commits use SHA (timestamps from PushEvent are unreliable); others use time
    sha = event.payload.get("sha", "") if event.event_type == "commit" else ""
    if sha:
        existing = await db.execute(
            sa_select(AE).where(
                AE.developer_id == _uuid.UUID(event.developer_id),
                AE.source == event.source,
                AE.event_type == event.event_type,
                AE.payload["sha"].astext == sha,
            )
        )
    else:
        existing = await db.execute(
            sa_select(AE).where(
                AE.developer_id == _uuid.UUID(event.developer_id),
                AE.event_type == event.event_type,
                AE.event_time == et,
                AE.source == event.source,
            )
        )
    dupe = existing.scalar_one_or_none()
    if dupe:
        return dupe

    record = ActivityEvent(
        id=_uuid.uuid4(),
        developer_id=_uuid.UUID(event.developer_id),
        org_id=_uuid.UUID(event.org_id),
        source=event.source,
        event_type=event.event_type,
        event_time=et,
        payload=event.payload,
        summary=event.summary,
    )
    db.add(record)
    await db.flush()
    return record
