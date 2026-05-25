from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .api.router import router
from .config import get_settings
from .core.limiter import limiter
from .core.logging import configure_logging, get_logger
from .database import init_db
from .scheduler.runner import scheduler
logger = get_logger(__name__)
settings = get_settings()

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # HSTS only in production (breaks local HTTP dev)
}


async def _backfill_developers() -> None:
    """Create Developer records for any GitHub integration that has none yet."""
    import uuid
    from sqlalchemy import select
    from .core.encryption import decrypt_token
    from .database import get_db
    from .models.developer import Developer
    from .models.integration import Integration
    import httpx

    try:
        async with get_db() as db:
            result = await db.execute(
                select(Integration).where(Integration.provider == "github")
            )
            integrations = result.scalars().all()

        for integration in integrations:
            org_id = integration.org_id
            async with get_db() as db:
                existing = await db.execute(
                    select(Developer).where(Developer.org_id == org_id)
                )
                if existing.scalars().first():
                    continue  # already has at least one developer

                github_username = (integration.metadata_ or {}).get("github_username", "")
                if not github_username:
                    continue

                try:
                    token = decrypt_token(integration.access_token)
                    async with httpx.AsyncClient(
                        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
                        timeout=10,
                    ) as client:
                        resp = await client.get("https://api.github.com/user")
                        gh = resp.json() if resp.status_code == 200 else {}
                except Exception:
                    gh = {}

                name = gh.get("name") or github_username
                email = gh.get("email") or None

                db.add(Developer(
                    id=uuid.uuid4(),
                    org_id=org_id,
                    name=name,
                    email=email,
                    github_username=github_username,
                    is_active=True,
                ))
                logger.info("backfilled developer", extra={"org_id": str(org_id), "github_username": github_username})
    except Exception as exc:
        logger.warning("developer backfill failed", extra={"error": str(exc)})


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    await init_db()
    await _backfill_developers()
    scheduler.start()
    logger.info("startup complete", extra={"scheduler_running": scheduler.running})
    yield
    scheduler.shutdown(wait=False)
    logger.info("shutdown complete")


app = FastAPI(
    title="Async Standup Intelligence Layer",
    description="Multi-agent system that replaces daily standups with behavioral signal analysis.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS — locked to configured origins (no wildcard in production)
_allowed_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response: Response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers[header] = value
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


app.include_router(router)


@app.api_route("/health", methods=["GET", "HEAD"])
async def health():
    from datetime import datetime, timezone
    checks: dict[str, str] = {}

    # Database
    try:
        from .database import engine
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"error: {exc}"

    # Redis
    try:
        from .core.redis_client import get_redis
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc}"

    overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
    return {
        "status": overall,
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
