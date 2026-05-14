import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..agents.graph import pipeline
from ..agents.persist import persist_pipeline_results
from ..core.analytics import track
from ..core.security import get_current_org
from ..database import get_db_dep
from ..models.digest import Digest

router = APIRouter(prefix="/digests", tags=["digests"])


@router.get("/{org_id}")
async def list_digests(org_id: str, limit: int = 10, db: AsyncSession = Depends(get_db_dep)):
    result = await db.execute(
        select(Digest)
        .where(Digest.org_id == uuid.UUID(org_id))
        .order_by(Digest.digest_date.desc())
        .limit(limit)
    )
    digests = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "digest_date": d.digest_date.isoformat(),
            "generated_at": d.generated_at.isoformat(),
            "delivered": d.delivered,
            "markdown_output": d.markdown_output,
        }
        for d in digests
    ]


@router.get("/{org_id}/today")
async def get_today_digest(org_id: str, db: AsyncSession = Depends(get_db_dep)):
    result = await db.execute(
        select(Digest).where(
            Digest.org_id == uuid.UUID(org_id),
            Digest.digest_date == date.today(),
        )
    )
    digest = result.scalar_one_or_none()
    if not digest:
        raise HTTPException(status_code=404, detail="No digest generated yet for today")
    return {
        "id": str(digest.id),
        "digest_date": digest.digest_date.isoformat(),
        "generated_at": digest.generated_at.isoformat() if digest.generated_at else None,
        "markdown_output": digest.markdown_output,
        "content": digest.content,
        "delivered": digest.delivered,
    }


@router.post("/{org_id}/trigger", status_code=202)
async def trigger_digest(
    org_id: str,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    """Manually kick off the LangGraph pipeline for testing."""
    initial_state = {
        "org_id": org_id,
        "digest_date": date.today().isoformat(),
        "developer_signals": [],
        "blockers": [],
        "conflicts": [],
        "developer_narratives": {},
        "sprint_risk": "",
        "final_digest": None,
        "errors": [],
        "should_intervene": False,
    }
    poll_summary: dict = {}
    try:
        from ..ingestion.github_poller import poll_github_for_org
        poll_summary = await poll_github_for_org(org_id, since_hours=48)
    except Exception as exc:
        poll_summary = {"error": str(exc)}

    try:
        result = await pipeline.ainvoke(initial_state)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {exc}")

    await persist_pipeline_results(result)

    from datetime import datetime, timezone
    today = date.today()
    existing = await db.execute(
        select(Digest).where(
            Digest.org_id == uuid.UUID(org_id),
            Digest.digest_date == today,
        )
    )
    digest = existing.scalar_one_or_none()
    if digest:
        digest.content = result
        digest.markdown_output = result.get("final_digest", "")
        digest.generated_at = datetime.now(timezone.utc)
    else:
        digest = Digest(
            id=uuid.uuid4(),
            org_id=uuid.UUID(org_id),
            digest_date=today,
            content=result,
            markdown_output=result.get("final_digest", ""),
        )
        db.add(digest)
    await db.flush()

    blockers_found = len(result.get("blockers", []))
    track("digest_generated", org_id, {
        "blockers_found": blockers_found,
        "conflicts_found": len(result.get("conflicts", [])),
        "has_errors": bool(result.get("errors")),
        "triggered_manually": True,
    })
    if blockers_found:
        track("blocker_detected", org_id, {"count": blockers_found})

    return {
        "id": str(digest.id),
        "markdown_output": digest.markdown_output,
        "blockers_found": blockers_found,
        "conflicts_found": len(result.get("conflicts", [])),
        "errors": result.get("errors", []),
        "poll_summary": poll_summary,
    }


@router.post("/{org_id}/test-poll")
async def test_poll(org_id: str):
    """Run the full poller for this org and return step-by-step results."""
    from datetime import datetime, timedelta, timezone
    from ..database import get_db
    from ..models.developer import Developer
    from ..models.integration import Integration
    from ..core.encryption import decrypt_token
    import httpx as _httpx
    import uuid as _uuid
    from sqlalchemy import select as _sel

    steps = []

    async with get_db() as db:
        # Get integration
        ir = await db.execute(_sel(Integration).where(
            Integration.org_id == _uuid.UUID(org_id),
            Integration.provider == "github",
        ))
        integration = ir.scalar_one_or_none()
        if not integration:
            return {"error": "no github integration"}

        token = decrypt_token(integration.access_token)
        steps.append({"step": "token_decrypted", "ok": bool(token)})

        # Get org settings
        from ..models.organization import Organization
        or_ = await db.execute(_sel(Organization).where(Organization.id == _uuid.UUID(org_id)))
        org = or_.scalar_one_or_none()
        allowed_repos = set((org.settings or {}).get("github_repos", [])) if org else set()
        steps.append({"step": "allowed_repos", "value": list(allowed_repos)})

        # Get developers
        dr = await db.execute(_sel(Developer).where(
            Developer.org_id == _uuid.UUID(org_id),
            Developer.is_active.is_(True),
            Developer.github_username.isnot(None),
        ))
        devs = dr.scalars().all()
        steps.append({"step": "developers", "count": len(devs), "names": [d.github_username for d in devs]})

    since = datetime.now(timezone.utc) - timedelta(days=7)
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    steps.append({"step": "since_iso", "value": since_iso})

    stored_total = 0
    async with _httpx.AsyncClient(
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
        timeout=30,
    ) as client:
        for dev in devs:
            resp = await client.get(
                f"https://api.github.com/users/{dev.github_username}/events",
                params={"per_page": 50},
            )
            raw_events = resp.json() if resp.status_code == 200 else []
            push_events = [e for e in raw_events if e.get("type") == "PushEvent"]
            commits_raw = []
            for ev in push_events:
                repo = ev.get("repo", {}).get("name", "")
                created = ev.get("created_at", "")
                if created < since_iso:
                    continue
                if allowed_repos and repo:
                    repo_short = repo.split("/")[-1]
                    if repo not in allowed_repos and repo_short not in allowed_repos:
                        steps.append({"step": "filtered_out", "repo": repo, "allowed": list(allowed_repos)})
                        continue
                for c in ev.get("payload", {}).get("commits", []):
                    commits_raw.append({"sha": c.get("sha", "")[:8], "msg": c.get("message", "")[:60], "repo": repo})

            steps.append({"step": "commits_to_store", "dev": dev.github_username, "count": len(commits_raw), "commits": commits_raw})

            # Try storing
            from ..ingestion.normalizer import normalize_github_commit, store_event
            from ..database import get_db as _get_db
            for c in commits_raw:
                c["repo"] = c["repo"]
                raw_c = {"sha": c["sha"], "message": c["msg"], "author": {}}
                raw_c["repo"] = c["repo"]
                ne = normalize_github_commit(raw_c, str(dev.id), org_id)
                try:
                    async with _get_db() as store_db:
                        rec = await store_event(ne, store_db)
                    stored_total += 1
                    steps.append({"step": "stored", "sha": c["sha"], "id": str(rec.id)})
                except Exception as e:
                    steps.append({"step": "store_failed", "sha": c["sha"], "error": str(e)})

    return {"stored_total": stored_total, "steps": steps}


@router.post("/{org_id}/test-insert")
async def test_insert(org_id: str):
    """Directly insert one test activity_event row — proves DB write works independent of poller."""
    from datetime import datetime, timezone
    from ..database import get_db
    from ..models.activity_event import ActivityEvent
    from ..models.developer import Developer
    from sqlalchemy import select as _sel
    import uuid as _uuid

    try:
        async with get_db() as db:
            # Get any active developer to use as FK
            result = await db.execute(
                _sel(Developer).where(
                    Developer.org_id == _uuid.UUID(org_id),
                    Developer.is_active.is_(True),
                ).limit(1)
            )
            dev = result.scalar_one_or_none()
            if not dev:
                return {"ok": False, "error": "No active developer found"}

            record = ActivityEvent(
                id=_uuid.uuid4(),
                developer_id=dev.id,
                org_id=_uuid.UUID(org_id),
                source="github",
                event_type="commit",
                event_time=datetime.now(timezone.utc),
                payload={"sha": "test", "message": "test insert", "repo": "test/test"},
                summary="Test insert to verify DB write works",
            )
            db.add(record)
            await db.flush()
        return {"ok": True, "inserted_id": str(record.id), "developer": dev.name}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.delete("/{org_id}/cleanup-test-data")
async def cleanup_test_data(org_id: str):
    """Delete all fake activity_events inserted by test-insert (repo='test/test')."""
    from ..database import get_db
    from ..models.activity_event import ActivityEvent
    from sqlalchemy import delete as _delete
    import uuid as _uuid

    try:
        async with get_db() as db:
            result = await db.execute(
                _delete(ActivityEvent).where(
                    ActivityEvent.org_id == _uuid.UUID(org_id),
                    ActivityEvent.payload["repo"].astext == "test/test",
                ).returning(ActivityEvent.id)
            )
            deleted = result.fetchall()
        return {"ok": True, "deleted_count": len(deleted)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/{org_id}/diagnose")
async def diagnose(org_id: str, db: AsyncSession = Depends(get_db_dep)):
    """Full diagnostic: developers, event counts, LLM test, pipeline errors."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func
    from ..models.developer import Developer
    from ..models.activity_event import ActivityEvent
    from ..models.integration import Integration

    since_24h = datetime.now(timezone.utc) - timedelta(hours=24)

    # 1. Developers
    devs_result = await db.execute(
        select(Developer).where(Developer.org_id == uuid.UUID(org_id))
    )
    devs = devs_result.scalars().all()
    dev_rows = []
    for d in devs:
        count_result = await db.execute(
            select(func.count()).where(
                ActivityEvent.developer_id == d.id,
                ActivityEvent.event_time >= since_24h,
            )
        )
        total_result = await db.execute(
            select(func.count()).where(ActivityEvent.developer_id == d.id)
        )
        dev_rows.append({
            "id": str(d.id),
            "name": d.name,
            "github_username": d.github_username,
            "is_active": d.is_active,
            "events_24h": count_result.scalar(),
            "events_total": total_result.scalar(),
        })

    # 2. GitHub integration
    gh_result = await db.execute(
        select(Integration).where(
            Integration.org_id == uuid.UUID(org_id),
            Integration.provider == "github",
        )
    )
    gh = gh_result.scalar_one_or_none()
    github_info = {
        "connected": gh is not None,
        "github_username": gh.metadata_.get("github_username") if gh else None,
        "scope": gh.metadata_.get("scope") if gh else None,
    }

    # 2b. Test raw GitHub events API with the stored token
    raw_github_events = []
    poll_result = {"status": "skipped", "error": None}
    try:
        from ..core.encryption import decrypt_token
        import httpx as _httpx
        if gh:
            token = decrypt_token(gh.access_token)
            async with _httpx.AsyncClient(timeout=10) as _c:
                for dev_row in dev_rows:
                    if dev_row["github_username"]:
                        r = await _c.get(
                            f"https://api.github.com/users/{dev_row['github_username']}/events",
                            headers={"Authorization": f"token {token}"},
                            params={"per_page": 10},
                        )
                        raw_github_events.append({
                            "username": dev_row["github_username"],
                            "status": r.status_code,
                            "events": [
                                {"type": e.get("type"), "created_at": e.get("created_at", "")[:16], "repo": e.get("repo", {}).get("name")}
                                for e in (r.json() if r.status_code == 200 else [])
                            ],
                        })
    except Exception as e:
        poll_result["error"] = f"raw github check: {e}"

    try:
        from ..ingestion.github_poller import poll_github_for_org
        await poll_github_for_org(org_id, since_hours=48)
        poll_result["status"] = "ok"
    except Exception as e:
        poll_result["status"] = "error"
        poll_result["error"] = str(e)

    # Re-count events after polling
    after_counts = {}
    for d in devs:
        c = await db.execute(
            select(func.count()).where(ActivityEvent.developer_id == d.id)
        )
        after_counts[d.name] = c.scalar()

    # 3. Quick LLM test
    llm_ok = False
    llm_error = None
    try:
        import anthropic
        from ..config import get_settings as _gs
        client = anthropic.AsyncAnthropic(api_key=_gs().anthropic_api_key)
        r = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": "Say OK"}],
        )
        llm_ok = r.content[0].text.strip() != ""
    except Exception as e:
        llm_error = str(e)

    # 4. Run pipeline and capture full state
    from datetime import date as date_type
    initial_state = {
        "org_id": org_id,
        "digest_date": date_type.today().isoformat(),
        "developer_signals": [],
        "blockers": [],
        "conflicts": [],
        "developer_narratives": {},
        "sprint_risk": "",
        "final_digest": None,
        "errors": [],
        "should_intervene": False,
    }
    pipeline_state = None
    pipeline_error = None
    try:
        pipeline_state = await pipeline.ainvoke(initial_state)
    except Exception as e:
        pipeline_error = str(e)

    return {
        "developers": dev_rows,
        "events_after_poll": after_counts,
        "raw_github_events": raw_github_events,
        "poll_result": poll_result,
        "github": github_info,
        "llm_ok": llm_ok,
        "llm_error": llm_error,
        "pipeline_errors": pipeline_state.get("errors", []) if pipeline_state else [],
        "pipeline_exception": pipeline_error,
        "developer_signals_count": len(pipeline_state.get("developer_signals", [])) if pipeline_state else 0,
        "narratives": pipeline_state.get("developer_narratives", {}) if pipeline_state else {},
        "sprint_risk": pipeline_state.get("sprint_risk", "") if pipeline_state else "",
    }


@router.get("/{org_id}/blockers")
async def list_blockers(org_id: str, db: AsyncSession = Depends(get_db_dep)):
    from ..models.blocker import Blocker
    result = await db.execute(
        select(Blocker)
        .where(Blocker.org_id == uuid.UUID(org_id), Blocker.resolved_at.is_(None))
        .order_by(Blocker.detected_at.desc())
    )
    blockers = result.scalars().all()
    return [
        {
            "id": str(b.id),
            "developer_id": str(b.developer_id),
            "severity": b.severity,
            "blocker_type": b.blocker_type,
            "description": b.description,
            "detected_at": b.detected_at.isoformat(),
            "intervention_sent": b.intervention_sent,
        }
        for b in blockers
    ]


@router.patch("/blockers/{blocker_id}/resolve")
async def resolve_blocker(
    blocker_id: str,
    db: AsyncSession = Depends(get_db_dep),
    _: str = Depends(get_current_org),
):
    from datetime import datetime, timezone
    from ..models.blocker import Blocker
    result = await db.execute(select(Blocker).where(Blocker.id == uuid.UUID(blocker_id)))
    blocker = result.scalar_one_or_none()
    if not blocker:
        raise HTTPException(status_code=404, detail="Blocker not found")
    blocker.resolved_at = datetime.now(timezone.utc)
    await db.flush()
    return {"status": "resolved"}
