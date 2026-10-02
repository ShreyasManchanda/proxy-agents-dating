"""Rebuild profiles for people already scraped (no Apify spend). Observer calls are served from the LLM cache.
  python -m scripts.rebuild_profiles            # everyone ready, real people only
  python -m scripts.rebuild_profiles --empty    # only profiles with no valid claims
"""
import asyncio
import sys

from sqlalchemy import select

from app import service as svc
from app.db import models as m
from app.db.session import Session
from app.llm.gateway import DbCache, build_default_gateway

SYNTHETIC = ("meera-iyer", "arjun-nair", "zoya-khan", "rohan-desai", "sana-mirza", "kabir-malhotra", "tara-dsouza", "vikram-rao")


async def main():
    gw = build_default_gateway(DbCache(Session))
    async with Session() as db:
        ps = (await db.execute(select(m.Person).where(m.Person.status == "ready").order_by(m.Person.id))).scalars().all()
        ps = [p for p in ps if not p.linkedin_url.endswith(SYNTHETIC)]
        profs = await svc.load_profiles(db, [p.id for p in ps])
    todo = [p.id for p in ps if "--empty" not in sys.argv
            or sum(len(profs[p.id].get(g) or []) for g in ("needs", "hobbies", "interests", "values")) == 0]
    print(f"rebuilding {len(todo)} profiles", flush=True)
    gate = asyncio.Semaphore(3)

    async def one(pid):
        async with gate:
            async with Session() as db:
                prof = await svc.build_profile(db, gw, pid, None, None)
                await db.commit()
            n = sum(len(prof[g]) for g in ("needs", "hobbies", "interests", "values"))
            print(f"  person {pid}: claims={n} conf={prof['overall_confidence']:.2f} flags={[f for f in prof['source_flags'] if f.startswith('synthesis')]}", flush=True)
    await asyncio.gather(*(one(i) for i in todo))
    print(f"spend=${gw.spend_usd:.4f}")


asyncio.run(main())
