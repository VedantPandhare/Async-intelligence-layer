from typing import Any, Optional, TypedDict


class DeveloperSignals(TypedDict):
    developer_id: str
    developer_name: str
    github_username: str
    commits_today: list[dict]
    prs_opened: list[dict]
    prs_reviewed: list[dict]
    ci_failures: list[dict]
    slack_messages_count: int
    last_slack_message_at: Optional[str]
    tickets_updated: list[dict]
    files_touched: list[str]
    commit_velocity_delta: float   # vs 7-day average (negative = slower)
    silence_hours: float           # hours since last any activity


class InferredBlocker(TypedDict):
    developer_id: str
    blocker_type: str    # 'ci_failure' | 'pr_stalled' | 'silence' | 'dependency_wait' | 'estimation_problem'
    severity: str        # 'low' | 'medium' | 'high' | 'critical'
    description: str
    signals: list[str]
    suggested_action: str


class DependencyConflict(TypedDict):
    developer_a: str
    developer_b: str
    conflict_type: str
    files_or_services: list[str]
    risk: str


class AgentState(TypedDict):
    org_id: str
    digest_date: str
    developer_signals: list[DeveloperSignals]
    blockers: list[InferredBlocker]
    conflicts: list[DependencyConflict]
    developer_narratives: dict[str, str]   # dev_id → prose summary
    sprint_risk: str
    final_digest: Optional[str]
    errors: list[str]
    should_intervene: bool
