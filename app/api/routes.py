"""HTTP API (SPEC §14). A pool is addressed by an unguessable token in the URL: that token is the access control."""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app import jobs, service as svc
from app.config import settings
from app.db import models as m
from app.ingest.urls import BadUrl, normalize_instagram, normalize_linkedin

router = APIRouter(prefix="/api")

LIVE_RUN_DAILY_CAP = int(os.getenv("LIVE_RUN_DAILY_CAP", "12"))
_runs = {"day": date.today(), "n": 0}
_hits: dict[str, deque] = defaultdict(deque)
_tasks: set[asyncio.Task] = set()


def _paste_enabled() -> bool:
    return os.getenv("PASTE_ENABLED", "true").lower() != "false"  # kill switch: demo stays browsable


def _runs_left() -> int:
    if _runs["day"] != date.today():
        _runs.update(day=date.today(), n=0)
    return max(0, LIVE_RUN_DAILY_CAP - _runs["n"])


def _rate_limit(request: Request, per_hour: int = 6):
    ip = (request.headers.get("x-forwarded-for") or request.client.host or "?").split(",")[0].strip()
    q, now = _hits[ip], time.time()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= per_hour:
        raise HTTPException(429, "Too many runs from your connection this hour. Please try again later.")
    q.append(now)


_cache: dict[tuple, tuple[float, object]] = {}


async def cached(pool: m.Pool, key: tuple, build, ttl: float = 600.0):
    """Frozen (published) pools are immutable, so their responses are cached in memory. Live pools never are."""
    if not pool.frozen:
        return await build()
    k = (pool.token, *key)
    hit = _cache.get(k)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    val = await build()
    _cache[k] = (time.time(), val)
    return val


def _hit(token: str, key: tuple, ttl: float = 600.0):
    """Fast path: a cached answer for a published pool needs no database round trip at all."""
    hit = _cache.get((token, *key))
    return hit[1] if hit and time.time() - hit[0] < ttl else None


def sm(request: Request):
    return request.app.state.sm


async def _pool(db, token: str) -> m.Pool:
    pool = (await db.execute(select(m.Pool).where(m.Pool.token == token))).scalar_one_or_none()
    if not pool:
        raise HTTPException(404, "Pool not found")
    return pool


class Pair(BaseModel):
    linkedin: str
    instagram: str


class PoolIn(BaseModel):
    pairs: list[Pair]
    add_to_demo: bool = False


@router.get("/config")
async def config(request: Request):
    async with sm(request)() as db:
        demo = (await db.execute(select(m.Pool).where(m.Pool.frozen.is_(True)).order_by(m.Pool.id))).scalars().first()
    return {"paste_enabled": _paste_enabled(), "live_runs_left": _runs_left(), "live_pool_max": settings.live_pool_max,
            "demo_token": demo.token if demo else None, "demo_name": demo.name if demo else None}


@router.post("/pools")
async def create_pool(body: PoolIn, request: Request):
    if not _paste_enabled():
        raise HTTPException(503, "Pasting new links is switched off right now. The demo is still browsable.")
    if _runs_left() <= 0:
        raise HTTPException(429, "Today's live runs are used up. The demo is still available; try again tomorrow.")
    if not body.pairs:
        raise HTTPException(400, "Add at least one LinkedIn + Instagram pair.")
    if len(body.pairs) > settings.live_pool_max:
        raise HTTPException(400, f"At most {settings.live_pool_max} people per run.")
    if not body.add_to_demo and len(body.pairs) < 2:
        raise HTTPException(400, "Add at least two people, or choose to join the 25-person demo.")
    cleaned = []
    for i, p in enumerate(body.pairs, 1):
        try:
            cleaned.append((normalize_linkedin(p.linkedin), normalize_instagram(p.instagram)))
        except BadUrl as e:
            raise HTTPException(400, f"Person {i}: {e}")
    if len(set(cleaned)) != len(cleaned):
        raise HTTPException(400, "The same person appears twice.")
    _rate_limit(request)
    _runs["n"] += 1
    s = sm(request)
    async with s() as db:
        demo_ids, frozen = [], None
        if body.add_to_demo:
            demo = (await db.execute(select(m.Pool).where(m.Pool.frozen.is_(True)).order_by(m.Pool.id))).scalars().first()
            if not demo:
                raise HTTPException(503, "The demo pool isn't ready yet.")
            demo_ids = await svc.pool_members(db, demo.id)
            frozen = jobs.from_json_stats(demo.stats["frozen_stats"]) if demo.stats and demo.stats.get("frozen_stats") else None
        new_ids, urls = [], {}
        for li, ig in cleaned:
            existing = (await db.execute(select(m.Person).where(m.Person.linkedin_url == li,
                                                               m.Person.instagram_url == ig))).scalar_one_or_none()
            if existing and existing.public:
                raise HTTPException(400, "That person is part of the public demo already.")
            # a pasted person is private to this run: always a fresh row, so deleting it removes only their data
            row = m.Person(linkedin_url=li, instagram_url=ig, public=False, status="pending")
            db.add(row)
            await db.flush()
            new_ids.append(row.id)
            urls[row.id] = (li, ig)
        pool = await svc.create_pool(db, "Your run", new_ids + demo_ids)
        pool.stats = {"phase": "queued", "add_to_demo": body.add_to_demo, "new_ids": new_ids,
                      "frozen_ref": bool(frozen)}
        await db.commit()
        token, pool_id = pool.token, pool.id
    task = asyncio.create_task(jobs.run_live_pool(s, request.app.state.gw, pool_id, token, new_ids, urls,
                                                  demo_ids, frozen))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"token": token}


@router.get("/pools/{token}")
async def get_pool(token: str, request: Request):
    if (h := _hit(token, ("pool",))) is not None:
        return h
    async with sm(request)() as db:
        pool = await _pool(db, token)

        async def build():
            ids = await svc.pool_members(db, pool.id)
            people = (await db.execute(select(m.Person).where(m.Person.id.in_(ids)))).scalars().all()
            profs = await svc.load_profiles_slim(db, ids)
            counts = dict((await db.execute(select(m.Date.status, func.count()).where(
                m.Date.a_id.in_(ids), m.Date.b_id.in_(ids)).group_by(m.Date.status))).all())
            stats = pool.stats or {}
            return {"name": pool.name, "frozen": pool.frozen,
                    "phase": stats.get("phase", "done" if pool.frozen else "queued"),
                    "error": stats.get("error"), "new_ids": stats.get("new_ids", []),
                    "add_to_demo": stats.get("add_to_demo", False),
                    "dates_done": counts.get("done", 0), "dates_failed": counts.get("failed", 0),
                    "dates_total": len(ids) * (len(ids) - 1) // 2,
                    "synthetic": pool.name.startswith("[SYNTHETIC]"),
                    "people": [{"id": p.id, "name": p.display_name or (profs.get(p.id) or {}).get("name"),
                                "status": p.status, "note": p.note,
                                "confidence": (profs.get(p.id) or {}).get("overall_confidence"),
                                "headline": ((profs.get(p.id) or {}).get("work") or {}).get("summary"),
                                "location": ((profs.get(p.id) or {}).get("identity") or {}).get("location")}
                               for p in sorted(people, key=lambda p: p.id)]}
        return await cached(pool, ("pool",), build)


@router.get("/pools/{token}/people/{pid}")
async def get_person(token: str, pid: int, request: Request):
    if (h := _hit(token, ("person", pid))) is not None:
        return h
    async with sm(request)() as db:
        pool = await _pool(db, token)

        async def build():
            if pid not in await svc.pool_members(db, pool.id):
                raise HTTPException(404, "Person not in this pool")
            prof = (await svc.load_profiles(db, [pid])).get(pid)
            person = await db.get(m.Person, pid)
            if not prof:
                return {"id": pid, "status": person.status, "note": person.note, "profile": None}
            prof = {k: v for k, v in prof.items() if k != "persona_card"}  # the date prompt card stays server-side
            return {"id": pid, "status": person.status, "note": person.note, "profile": prof}
        return await cached(pool, ("person", pid), build)


@router.get("/pools/{token}/dates")
async def list_dates(token: str, request: Request):
    if (h := _hit(token, ("dates",))) is not None:
        return h
    async with sm(request)() as db:
        pool = await _pool(db, token)

        async def build():
            ids = await svc.pool_members(db, pool.id)
            ds = (await db.execute(select(m.Date.id, m.Date.a_id, m.Date.b_id, m.Date.status,
                                          func.jsonb_array_length(m.Date.transcript))
                                   .where(m.Date.a_id.in_(ids), m.Date.b_id.in_(ids)))).all()
            vs = (await db.execute(select(m.Verdict.date_id, m.Verdict.scores)
                                   .where(m.Verdict.date_id.in_([d[0] for d in ds])))).all()
            total: dict[int, list[float]] = defaultdict(list)
            for date_id, scores in vs:
                total[date_id].append(sum(scores.values()) / max(1, len(scores)))
            return [{"id": d[0], "a": d[1], "b": d[2], "status": d[3], "turns": d[4] or 0,
                     "score": (sum(total[d[0]]) / len(total[d[0]])) if total.get(d[0]) else None} for d in ds]
        return await cached(pool, ("dates",), build)


@router.get("/pools/{token}/dates/{date_id}")
async def get_date(token: str, date_id: int, request: Request):
    if (h := _hit(token, ("date", date_id))) is not None:
        return h
    async with sm(request)() as db:
        pool = await _pool(db, token)

        async def build():
            ids = await svc.pool_members(db, pool.id)
            d = await db.get(m.Date, date_id)
            if not d or d.a_id not in ids or d.b_id not in ids:
                raise HTTPException(404, "Date not found")
            vs = (await db.execute(select(m.Verdict).where(m.Verdict.date_id == d.id))).scalars().all()
            names = {p.id: p.display_name for p in (await db.execute(
                select(m.Person).where(m.Person.id.in_([d.a_id, d.b_id])))).scalars()}
            return {"id": d.id, "a": d.a_id, "b": d.b_id, "names": names, "status": d.status, "scenario": d.scenario,
                    "transcript": d.transcript, "metrics": d.metrics,
                    "verdicts": [{"from": v.from_id, "to": v.to_id, "sample": v.sample_idx, "scores": v.scores,
                                  "second_date": v.second_date, "reason": v.reason, "quote": v.quote} for v in vs]}
        return await cached(pool, ("date", date_id), build)


@router.get("/pools/{token}/rankings")
async def rankings(token: str, request: Request, own_weight: float = settings.own_weight):
    own_weight = min(1.0, max(0.0, own_weight))
    if (h := _hit(token, ("rank", round(own_weight, 2)))) is not None:
        return h
    async with sm(request)() as db:
        pool = await _pool(db, token)
        ids = await svc.pool_members(db, pool.id)
        frozen = None
        stats = pool.stats or {}
        if stats.get("add_to_demo"):
            demo = (await db.execute(select(m.Pool).where(m.Pool.frozen.is_(True)).order_by(m.Pool.id))).scalars().first()
            if demo and (demo.stats or {}).get("frozen_stats"):
                frozen = jobs.from_json_stats(demo.stats["frozen_stats"])

        async def build():
            res = await svc.compute_rankings(db, ids, own_weight, frozen)
            return {"own_weight": own_weight, "hypothesis": res["hypothesis"], "n_dates": res["n_dates"],
                    "rankings": {str(k): v for k, v in res["rankings"].items()}}
        return await cached(pool, ("rank", round(own_weight, 2)), build)


@router.get("/pools/{token}/diagnostics")
async def diagnostics(token: str, request: Request):
    from collections import defaultdict as dd
    from app.scoring.core import pearson
    if (h := _hit(token, ("diag",))) is not None:
        return h
    async with sm(request)() as db:
        pool = await _pool(db, token)

        async def build():
            ids = await svc.pool_members(db, pool.id)
            res = await svc.compute_rankings(db, ids)
            profs = await svc.load_profiles_slim(db, ids)
            # does a richer profile receive a higher score? reported, never adjusted for (n is small)
            got: dict[int, list[float]] = dd(list)
            for rows in res["rankings"].values():
                for r in rows:
                    got[r["target"]].append(r["own"])
            both = [(profs[i]["richness_score"], sum(v) / len(v)) for i, v in got.items()
                    if i in profs and profs[i].get("richness_score") is not None]
            stored = (pool.stats or {}).get("diagnostics") or {}
            return {"hypothesis": res["hypothesis"], "n_people": len(ids), "n_dates": res["n_dates"],
                    "richness_vs_score": {"r": pearson([a for a, _ in both], [b for _, b in both]), "n": len(both)},
                    "test_retest": stored.get("test_retest"), "order_swap": stored.get("order_swap"),
                    "notes": ["Consistency is measurable here; correctness is not.",
                              "Attraction cannot be measured from two public profiles."]}
        return await cached(pool, ("diag",), build)


@router.get("/pools/{token}/events")
async def events(token: str, request: Request):
    async def gen():
        q = svc.bus.subscribe(token)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    import json
                    yield f"data: {json.dumps(ev, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            svc.bus.unsubscribe(token, q)
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.delete("/pools/{token}/people/{pid}")
async def delete_person(token: str, pid: int, request: Request):
    """Removes the person and everything about them (cascades: scrapes, images, observations, profile,
    dates, verdicts, debrief, pool membership). Only people pasted into this pool can be deleted here."""
    async with sm(request)() as db:
        pool = await _pool(db, token)
        if pid not in (pool.stats or {}).get("new_ids", []):
            raise HTTPException(403, "Only people added in this run can be deleted here.")
        await db.execute(delete(m.Person).where(m.Person.id == pid))
        await db.commit()
    return {"deleted": pid}
