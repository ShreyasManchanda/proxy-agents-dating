"""End-to-end run on SYNTHETIC fixtures with the real LLMs and the real database.
Run: python -m scripts.run_synthetic [n_people] [turn_plan like 2,2,2] [verdict_samples]
Creates a pool named "[SYNTHETIC] dev" and prints its token. Never ship these people."""
import asyncio
import sys
import time

from app import service as svc
from app.db.session import Session
from app.ingest.apify import ScrapeResult
from app.llm.gateway import build_default_gateway
from fixtures.synthetic import all_people


async def main(n: int, plan, samples):
    t0 = time.time()
    from app.llm.gateway import DbCache
    gw = build_default_gateway(DbCache(Session))
    people = all_people()[:n]
    async with Session() as db:
        ids = []
        for p in people:
            row = await svc.get_or_create_person(db, p["linkedin_url"], p["instagram_url"])
            await svc.store_scrape(db, row.id, [
                ScrapeResult("ig", "synthetic", True, p["ig"]), ScrapeResult("li", "synthetic", True, p["li"]),
                ScrapeResult("li_posts", "synthetic", True, p["li_posts"])])
            ids.append(row.id)
        await db.commit()
    print(f"[{time.time() - t0:.0f}s] stored {n} people")
    if "fresh" in sys.argv:  # drop earlier (shorter) dev dates among these people so they rerun in full
        from sqlalchemy import delete
        from app.db import models as m
        async with Session() as db:
            await db.execute(delete(m.Date).where(m.Date.a_id.in_(ids), m.Date.b_id.in_(ids)))
            await db.execute(delete(m.Debrief).where(m.Debrief.from_id.in_(ids)))
            await db.commit()

    async def prof(pid, name):
        async with Session() as db:
            await svc.build_profile(db, gw, pid, None, name)
            await db.commit()
    await asyncio.gather(*(prof(i, p["name"]) for i, p in zip(ids, people)))
    print(f"[{time.time() - t0:.0f}s] profiles built  spend=${gw.spend_usd:.4f}")

    async with Session() as db:
        profiles = await svc.load_profiles(db, ids)
        pool = await svc.create_pool(db, "[SYNTHETIC] dev", ids)
        await db.commit()
        token = pool.token
    pairs = svc.round_robin(ids)
    print(f"pool token={token} pairs={len(pairs)}")
    tally = await svc.run_pool_dates(Session, gw, token, pairs, profiles, concurrency=6, plan=plan, samples=samples)
    print(f"[{time.time() - t0:.0f}s] dates {tally}  spend=${gw.spend_usd:.4f}")
    await svc.run_debriefs(Session, gw, ids, profiles)
    async with Session() as db:
        res = await svc.compute_rankings(db, ids)
    names = {i: profiles[i]["name"] for i in ids}
    for a, rows in res["rankings"].items():
        print(f"\n{names[a]}:")
        for r in rows:
            print(f"  #{r['rank']} {names[r['target']]:16} final={r['final']:.2f} own={r['own']:.2f} "
                  f"their={r['their_own']:.2f} {r['tag']}" + (f"  CONFLICT {[c['topic'] for c in r['conflicts']]}" if r['conflicts'] else ""))
    print("\nhypothesis:", res["hypothesis"])
    print("usage:", {k: v for k, v in gw.usage.items() if v["calls"]}, f"spend=${gw.spend_usd:.4f}",
          f"total {time.time() - t0:.0f}s")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    plan = tuple(int(x) for x in sys.argv[2].split(",")) if len(sys.argv) > 2 else (2, 2, 2)
    samples = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    asyncio.run(main(n, plan, samples))
