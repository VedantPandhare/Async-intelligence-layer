"""Shared async Redis client — initialized once at module level."""

import redis.asyncio as aioredis

from ..config import get_settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        settings = get_settings()
        kwargs: dict = {"decode_responses": True}
        if settings.redis_url.startswith("rediss://"):
            kwargs["ssl_cert_reqs"] = None
        _redis = aioredis.from_url(settings.redis_url, **kwargs)
    return _redis
