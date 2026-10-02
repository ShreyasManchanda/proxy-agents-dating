"""Reliability diagnostics for a finished pool (SPEC section 11). Run after the batch:

  python -m scripts.diagnostics            # test-retest on 10% of verdicts + order swap on 10 dates

Writes the numbers to pool.stats["diagnostics"], which the About-the-results panel shows.
Consistency is measurable here; correctness is not, and the panel says so."""
import asyncio
import random
import time

from sqlalchemy import select

from app import service as svc
from app.config import settings
from app.dating.runner import Person as DatePerson, _verdict, run_date
from app.db import models as m
from app.db.session import Session
from app.llm.gateway import DbCache, build_default_gateway
from app.scoring.core import order_bias, pearson


def composite(scores: dict) -> float:
    return sum(scores.values()) / max(1, len(scores))


async def main():
    t0 = time.time()
    rnd = random.Random(20261002)  # fixed seed: the same dates are re-tested every time
    gw = build_default_gateway(DbCache(Session))
    async with Session() as db:
        pool = (await db.execute(select(m.Pool).where(m.Pool.name == "Demo-25"))).scalar_one()
        ids = await svc.pool_members(db, pool.id)
        profiles = await svc.load_profiles(db, ids)
        dates = (await db.execute(select(m.Date).where(m.Date.a_id.in_(ids), m.Date.b_id.in_(ids),
                                                       m.Date.status == "done").order_by(m.Date.id))).scalars().all()
        verdicts = (await db.execute(select(m.Verdict).where(m.Verdict.date_id.in_([d.id for d in dates]),
                                                             m.Verdict.sample_idx == 0))).scalars().all()
    by_date = {d.id: d for d in dates}
    print(f"{len(dates)} finished dates, {len(verdicts)} verdicts", flush=True)

    # 1. test-retest: re-ask the verdict question for a random 10% and correlate with the original
    n = max(10, int(len(verdicts) * settings.retest_fraction))
    pick = rnd.sample(verdicts, min(n, len(verdicts)))

    async def redo(v):
        d = by_date[v.date_id]
        me = DatePerson(v.from_id, profiles[v.from_id]["name"], profiles[v.from_id]["persona_card"])
        out = await _verdict(gw, me, d.transcript, sample=97, cfg=settings)  # fresh cache key, same prompt
        return (composite(v.scores), composite(out["scores"])) if out else None
    pairs = [x for x in await asyncio.gather(*(redo(v) for v in pick)) if x]
    retest_r = pearson([a for a, _ in pairs], [b for _, b in pairs])
    drift = sum(abs(a - b) for a, b in pairs) / len(pairs) if pairs else None
    print(f"[{time.time() - t0:.0f}s] test-retest: n={len(pairs)} r={retest_r} mean |diff|={drift}", flush=True)

    # 2. order swap: replay ORDERSWAP_SAMPLE dates with the other agent speaking first
    sample = rnd.sample(dates, min(settings.orderswap_sample, len(dates)))
    orig, swapped = [], []

    async def swap(d):
        a, b = d.a_id, d.b_id
        first_orig = d.transcript[0]["speaker"]
        res = await run_date(gw, DatePerson(a, profiles[a]["name"], profiles[a]["persona_card"]),
                             DatePerson(b, profiles[b]["name"], profiles[b]["persona_card"]),
                             plan=settings.turn_plan, samples=1, first_override=(b if first_orig == a else a))
        vs = [v for v in verdicts if v.date_id == d.id]
        if not vs or not all(res.verdicts.get(p) for p in (a, b)):
            return None
        o = sum(composite(v.scores) for v in vs) / len(vs)
        w = sum(composite(res.verdicts[p][0]["scores"]) for p in (a, b)) / 2
        return o, w
    for r in await asyncio.gather(*(swap(d) for d in sample)):
        if r:
            orig.append(r[0]); swapped.append(r[1])
    shift = order_bias(orig, swapped)
    swap_r = pearson(orig, swapped)
    print(f"[{time.time() - t0:.0f}s] order swap: n={len(orig)} mean shift={shift} r={swap_r}", flush=True)

    async with Session() as db:
        p = await db.get(m.Pool, pool.id)
        p.stats = {**(p.stats or {}), "diagnostics": {
            "test_retest": {"n": len(pairs), "r": retest_r, "mean_abs_diff": drift},
            "order_swap": {"n": len(orig), "mean_shift": shift, "r": swap_r},
            "run_at": time.strftime("%Y-%m-%d")}}
        await db.commit()
    print(f"saved. spend=${gw.spend_usd:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
