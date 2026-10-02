"""Run the Demo-25 batch: every pair dates, then debriefs, then the pool is frozen (SPEC §19 'Batch').
Resumable: finished dates are skipped and unfinished transcripts continue from their last saved turn.

  python -m scripts.run_demo25 --limit-pairs=6        # audit run: a few dates to read first
  python -m scripts.run_demo25                         # the full run (all pairs)
  python -m scripts.run_demo25 --publish               # freeze + make it the public demo (needs consent)

Only people with status 'ready' are included. Prompts must be frozen before the full run: any prompt change
invalidates the cache (SPEC §10)."""
import asyncio
import sys
import time

from sqlalchemy import select, update

from app import jobs, service as svc
from app.config import settings
from app.db import models as m
from app.db.session import Session
from app.llm.gateway import DbCache, build_default_gateway

NAME = "Demo-25"


async def main():
    t0 = time.time()
    lim = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit-pairs=")), None)
    publish = "--publish" in sys.argv
    gw = build_default_gateway(DbCache(Session))
    async with Session() as db:
        people = (await db.execute(select(m.Person).where(m.Person.status == "ready", m.Person.public.is_(False) | m.Person.public.is_(True))
                                   .order_by(m.Person.id))).scalars().all()
        # exclude the synthetic fixtures (their URLs are fake)
        people = [p for p in people if "/in/" in p.linkedin_url and not p.linkedin_url.endswith(
            ("meera-iyer", "arjun-nair", "zoya-khan", "rohan-desai", "sana-mirza", "kabir-malhotra", "tara-dsouza", "vikram-rao"))]
        ids = [p.id for p in people]
        pool = (await db.execute(select(m.Pool).where(m.Pool.name == NAME))).scalar_one_or_none()
        if not pool:
            pool = await svc.create_pool(db, NAME, ids)
            pool.stats = {"phase": "dating"}
        await db.commit()
        token, pool_id = pool.token, pool.id
        profiles = await svc.load_profiles(db, ids)
    pairs = svc.round_robin(ids)
    if lim:
        pairs = pairs[:lim]
    print(f"{len(ids)} people, {len(pairs)} pairs, pool token={token}", flush=True)

    for round_ in (1, 2):  # second pass retries dates whose verdicts failed
        tally = await svc.run_pool_dates(Session, gw, token, pairs, profiles, concurrency=8,
                                         plan=settings.turn_plan, samples=settings.verdict_samples)
        print(f"[{time.time() - t0:.0f}s] pass {round_}: {tally} spend=${gw.spend_usd:.4f} "
              f"calls={ {k: v['calls'] for k, v in gw.usage.items() if v['calls']} }", flush=True)
        if not tally["failed"]:
            break
    if lim:
        print("limited audit run: skipping debriefs and freeze")
        return
    await svc.run_debriefs(Session, gw, ids, profiles)
    print(f"[{time.time() - t0:.0f}s] debriefs done", flush=True)
    async with Session() as db:
        p = await db.get(m.Pool, pool_id)
        p.stats = {**(p.stats or {}), "phase": "done"}
        await db.commit()
    if publish:
        await jobs.freeze_pool(Session, pool_id)
        async with Session() as db:
            await db.execute(update(m.Pool).where(m.Pool.name.like("[SYNTHETIC]%")).values(frozen=False))
            await db.execute(update(m.Person).where(m.Person.id.in_(ids)).values(public=True))
            await db.commit()
        print("published: Demo-25 frozen and set public; synthetic pool unpublished")
    print(f"done in {time.time() - t0:.0f}s  spend=${gw.spend_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
