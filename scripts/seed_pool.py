"""Load the real pool from a spreadsheet, validate it, and optionally ingest it (SPEC §17, §18).

  python -m scripts.seed_pool datings.xlsx            # dry run: clean + validate + write pool.csv
  python -m scripts.seed_pool pool.csv --ingest       # scrape + read everyone (costs Apify credit)
  ... --confirm-consent                                # mark people public (visible to judges)

pool.csv and the spreadsheet are gitignored: they hold real people's links and must never be committed.
Columns: instagram, linkedin (a pasted page title like "Name (@handle) • Instagram photos" is accepted).
"""
import asyncio
import csv
import re
import sys
from pathlib import Path

from app.ingest.urls import BadUrl, normalize_instagram, normalize_linkedin

HANDLE_IN_TITLE = re.compile(r"\(@([A-Za-z0-9._]{1,30})\)")


def clean_instagram(cell: str) -> str:
    cell = (cell or "").strip()
    m = HANDLE_IN_TITLE.search(cell)
    if m and "instagram.com" not in cell:
        cell = f"https://www.instagram.com/{m.group(1)}"
    return normalize_instagram(cell)


def read_rows(path: Path) -> list[dict]:
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        import openpyxl
        ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        head = [str(h or "").strip().lower() for h in rows[0]]
        return [dict(zip(head, [("" if c is None else str(c)) for c in r])) for r in rows[1:] if any(r)]
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def validate(rows: list[dict]) -> tuple[list[dict], list[str]]:
    good, problems, seen_li, seen_ig = [], [], set(), set()
    for n, r in enumerate(rows, 2):
        try:
            ig = clean_instagram(r.get("instagram") or r.get("instagram_url") or "")
            li = normalize_linkedin(r.get("linkedin") or r.get("linkedin_url") or "")
        except BadUrl as e:
            problems.append(f"row {n}: {e}")
            continue
        if li in seen_li or ig in seen_ig:
            problems.append(f"row {n}: duplicate person ({li})")
            continue
        seen_li.add(li)
        seen_ig.add(ig)
        good.append({"instagram_url": ig, "linkedin_url": li, "consent": (r.get("consent") or "").strip()})
    return good, problems


async def ingest(people: list[dict], confirm_consent: bool, retry_failed: bool = False):
    from sqlalchemy import select
    from app.db import models as m
    from app import service as svc
    from app.db.session import Session
    from app.jobs import process_person
    from app.llm.gateway import DbCache, build_default_gateway

    gw = build_default_gateway(DbCache(Session))
    ids, urls = [], {}
    async with Session() as db:
        for p in people:
            row = await svc.get_or_create_person(db, p["linkedin_url"], p["instagram_url"], public=confirm_consent)
            row.public = confirm_consent
            ids.append(row.id)
            urls[row.id] = (p["linkedin_url"], p["instagram_url"])
        await db.commit()
    if retry_failed:  # skip people who are already ready (saves Apify credit)
        async with Session() as db:
            rows = (await db.execute(select(m.Person.id, m.Person.status).where(m.Person.id.in_(ids)))).all()
        ids = [i for i, st in rows if st != "ready"]
    print(f"{len(ids)} people to process; scraping and reading (Apify is limited to one person at a time)...")
    done = 0
    gate = asyncio.Semaphore(3)  # bounded: the database pooler allows only a few clients

    async def one(pid):
        nonlocal done
        async with gate:
            ok = await process_person(Session, gw, "seed", pid, *urls[pid])
        done += 1
        print(f"  [{done}/{len(ids)}] person {pid} {'ready' if ok else 'FAILED'}  llm_spend=${gw.spend_usd:.4f}", flush=True)
        return ok
    results = await asyncio.gather(*(one(i) for i in ids))
    print(f"ready={sum(results)} failed={len(results) - sum(results)}  llm_spend=${gw.spend_usd:.4f}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0] if args else "datings.xlsx")
    good, problems = validate(read_rows(path))
    print(f"{path}: {len(good)} valid people, {len(problems)} problems")
    for p in problems:
        print("  PROBLEM", p)
    for i, p in enumerate(good, 1):
        print(f"  {i:2}. {p['linkedin_url'].split('/in/')[1]:34} {p['instagram_url'].split('.com/')[1]}")
    if path.suffix.lower() != ".csv" or path.name != "pool.csv":
        with open("pool.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["linkedin_url", "instagram_url", "consent"])
            w.writeheader()
            w.writerows(good)
        print("wrote pool.csv (gitignored)")
    if "--ingest" in sys.argv:
        if problems:
            print("Fix the problems above before ingesting.")
            return
        lim = next((int(a.split("=")[1]) for a in sys.argv if a.startswith("--limit=")), None)
        asyncio.run(ingest(good[:lim] if lim else good, "--confirm-consent" in sys.argv, "--retry-failed" in sys.argv))


if __name__ == "__main__":
    main()
