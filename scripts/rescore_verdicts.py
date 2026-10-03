"""Re-score existing dates with the current verdict prompt (transcripts are NOT regenerated).

  python -m scripts.rescore_verdicts --dry --limit=10   # calibration: print stats, write nothing
  python -m scripts.rescore_verdicts                    # replace every verdict, then redo the debriefs

Only the blind verdict calls and the per-person debrief rankings are redone, so this is cheap (about $0.5)."""
import asyncio
import statistics as st
import sys
import time

from sqlalchemy import delete, select

from app import service as svc
from app.config import settings
from app.dating.runner import Person as DatePerson, _verdict
from app.db import models as m
from app.db.session import Session
from app.llm.gateway import DbCache, build_default_gateway


async def main():
    t0 = time.time()
    dry = "--dry" in sys.argv
    lim = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), None)
    gw = build_default_gateway(DbCache(Session))
    async with Session() as db:
        pool = (await db.execute(select(m.Pool).where(m.Pool.name == "Demo-25"))).scalar_one()
        ids = await svc.pool_members(db, pool.id)
        profiles = await svc.load_profiles(db, ids)
        dates = (await db.execute(select(m.Date).where(m.Date.a_id.in_(ids), m.Date.b_id.in_(ids),
                                                       m.Date.status == "done").order_by(m.Date.id))).scalars().all()
    if lim:
        dates = dates[:lim]
    print(f"{len(dates)} dates, dry={dry}", flush=True)
    sem = asyncio.Semaphore(6)
    stats = {"comp": [], "yes": 0, "n": 0, "failed": 0}

    async def one(d):
        async with sem:
            new = {}
            for rater in (d.a_id, d.b_id):
                me = DatePerson(rater, profiles[rater]["name"], profiles[rater]["persona_card"])
                got = [v for s in range(settings.verdict_samples) if (v := await _verdict(gw, me, d.transcript, s, settings))]
                if not got:
                    stats["failed"] += 1
                    return
                new[rater] = got
            for rater, vs in new.items():
                for v in vs:
                    stats["comp"].append(sum(v["scores"].values()) / 6)
                stats["yes"] += vs[0]["second_date"]
                stats["n"] += 1
            if dry:
                return
            async with Session() as db:
                await db.execute(delete(m.Verdict).where(m.Verdict.date_id == d.id))
                for rater, vs in new.items():
                    target = d.b_id if rater == d.a_id else d.a_id
                    for k, v in enumerate(vs):
                        db.add(m.Verdict(date_id=d.id, from_id=rater, to_id=target, sample_idx=k, scores=v["scores"],
                                         second_date=v["second_date"], reason=v["reason"], quote=v["quote"]))
                await db.commit()
    await asyncio.gather(*(one(d) for d in dates))
    c = stats["comp"]
    print(f"[{time.time() - t0:.0f}s] composite mean={st.mean(c):.2f} sd={st.pstdev(c):.2f} min={min(c):.1f} max={max(c):.1f} | "
          f"second_date yes {stats['yes']}/{stats['n']} | failed dates={stats['failed']} | spend=${gw.spend_usd:.4f}", flush=True)
    if not dry:
        await svc.run_debriefs(Session, gw, ids, profiles)
        print(f"[{time.time() - t0:.0f}s] debriefs redone, spend=${gw.spend_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
