"""Live pipelines for pasted people (SPEC §12): scrape -> read -> date -> rank, all DB-backed so a
refresh resumes from the result URL. Pasted people stay private to their pool link."""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app import service as svc
from app.config import settings
from app.db import models as m
from app.ingest.images import download_selected
from app.ingest.pipeline import IngestError, ingest_pair
from app.scoring import core as sc

# One scrape at a time: the free Apify plan allows 5 concurrent actor jobs and each person uses 3.
_apify_sem = asyncio.Semaphore(1)
_live_sem: asyncio.Semaphore | None = None


def live_sem() -> asyncio.Semaphore:
    global _live_sem
    if _live_sem is None:
        _live_sem = asyncio.Semaphore(settings.live_concurrency)
    return _live_sem


async def _set(sm, person_id: int, status: str, note: str | None = None):
    async with sm() as db:
        p = await db.get(m.Person, person_id)
        if p:
            p.status, p.note = status, note
            await db.commit()


async def _phase(sm, pool_id: int, token: str, phase: str, **extra):
    async with sm() as db:
        pool = await db.get(m.Pool, pool_id)
        pool.stats = {**(pool.stats or {}), "phase": phase, **extra}
        await db.commit()
    svc.bus.publish(token, "phase", {"phase": phase, **extra})


async def process_person(sm, gw, token: str, person_id: int, li: str, ig: str, scraper=None) -> bool:
    try:
        await _set(sm, person_id, "scraping", "Scraping public LinkedIn and Instagram")
        svc.bus.publish(token, "person", {"id": person_id, "status": "scraping"})
        async with _apify_sem:
            kw = {"scraper": scraper} if scraper else {}
            out = await ingest_pair(li, ig, **kw)
        async with sm() as db:
            await svc.store_scrape(db, person_id, out["raw"])
            await db.commit()
        note = " ".join(out["messages"]) or None
        await _set(sm, person_id, "reading", note or "Reading the profile")
        svc.bus.publish(token, "person", {"id": person_id, "status": "reading", "note": note})
        images = []
        igc = out["person"]["instagram"]
        if igc and igc["posts"]:
            images = await download_selected(igc["posts"])
        async with sm() as db:
            for ref, data in images:
                db.add(m.Image(person_id=person_id, post_ref=ref, bytes=data, selected=True))
            prof = await svc.build_profile(db, gw, person_id, images, None)
            await db.commit()
        await _set(sm, person_id, "ready", note)
        svc.bus.publish(token, "person", {"id": person_id, "status": "ready", "name": prof["name"], "note": note})
        return True
    except IngestError as e:
        await _set(sm, person_id, "failed", str(e))
        svc.bus.publish(token, "person", {"id": person_id, "status": "failed", "note": str(e)})
    except Exception as e:  # never a bare spinner: say what failed
        msg = f"Something went wrong while reading this profile ({type(e).__name__}). Try again later."
        await _set(sm, person_id, "failed", msg)
        svc.bus.publish(token, "person", {"id": person_id, "status": "failed", "note": msg})
    return False


async def run_live_pool(sm, gw, pool_id: int, token: str, new_ids: list[int], urls: dict[int, tuple[str, str]],
                        demo_ids: list[int] | None = None, frozen: dict | None = None, scraper=None):
    """new_ids: pasted people. demo_ids: frozen Demo-25 members they also date (add-to-demo)."""
    async with live_sem():
        await _phase(sm, pool_id, token, "reading")
        ok = await asyncio.gather(*(process_person(sm, gw, token, pid, *urls[pid], scraper=scraper)
                                    for pid in new_ids))
        good = [pid for pid, k in zip(new_ids, ok) if k]
        everyone = good + list(demo_ids or [])
        if len(everyone) < 2:
            await _phase(sm, pool_id, token, "failed",
                         error="Fewer than two people could be read, so there is nobody to date.")
            return
        async with sm() as db:
            profiles = await svc.load_profiles(db, everyone)
        pairs = [(min(a, b), max(a, b)) for i, a in enumerate(good) for b in everyone if b != a
                 and not (b in good and good.index(b) < i)]
        pairs = list(dict.fromkeys(pairs))
        await _phase(sm, pool_id, token, "dating", total=len(pairs))
        await svc.run_pool_dates(sm, gw, token, pairs, profiles, concurrency=6, plan=settings.live_turn_plan,
                                 samples=settings.live_verdict_samples, turn_route="live")
        await _phase(sm, pool_id, token, "ranking")
        await svc.run_debriefs(sm, gw, good, profiles)
        await _phase(sm, pool_id, token, "done")


async def freeze_pool(sm, pool_id: int):
    """Store the rater stats of a finished pool so later arrivals are scored against them (SPEC §11)."""
    async with sm() as db:
        ids = await svc.pool_members(db, pool_id)
        verdicts, debrief = await svc.load_scoring_inputs(db, ids)
        stats = sc.compute_stats(verdicts, debrief)
        pool = await db.get(m.Pool, pool_id)
        pool.frozen = True
        pool.stats = {**(pool.stats or {}), "frozen_stats": _to_json(stats)}
        await db.commit()


def _to_json(o):
    if isinstance(o, dict):
        return {str(k): _to_json(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_to_json(x) for x in o]
    return o


def from_json_stats(d: dict) -> dict:
    """Inverse of _to_json for the frozen stats: int keys, tuple (mean, sd) values."""
    return {
        "rater_mean_sd": {int(k): tuple(v) for k, v in d["rater_mean_sd"].items()},
        "partner_effect": {int(k): v for k, v in d["partner_effect"].items()},
        "adj_sorted": {int(k): v for k, v in d["adj_sorted"].items()},
    }
