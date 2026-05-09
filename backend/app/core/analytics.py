"""PostHog event tracking — gracefully no-ops when POSTHOG_API_KEY is unset."""

from __future__ import annotations

from ..config import get_settings

_posthog = None


def _get_client():
    global _posthog
    if _posthog is not None:
        return _posthog

    api_key = get_settings().posthog_api_key
    if not api_key:
        return None

    try:
        import posthog as ph
        ph.api_key = api_key
        ph.host = "https://app.posthog.com"
        _posthog = ph
    except ImportError:
        pass  # posthog package not installed — silently skip

    return _posthog


def track(event: str, org_id: str, properties: dict | None = None) -> None:
    """Fire-and-forget event tracking. Never raises."""
    try:
        client = _get_client()
        if client:
            client.capture(
                distinct_id=org_id,
                event=event,
                properties=properties or {},
            )
    except Exception:
        pass
