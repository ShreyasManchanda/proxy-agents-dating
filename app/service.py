"""Orchestration over the database: ingest -> extract -> dates -> debrief -> scores.
All LLM access goes through one Gateway; dates are pair-level and reused across pools (SPEC §10, §12)."""
from __future__ import annotations

import asyncio
import json
import secrets
from collections import defaultdict
from collections.abc import Awaitable, Callable

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.baselines.core import baseline_complement, baseline_similarity
from app.config import settings
from app.dating.runner import PROMPT_VERSION, Person as DatePerson, run_date
from app.db import models as m
from app.extract.pipeline import extract_person, load_prompt
from app.ingest.apify import ScrapeResult
from app.llm.gateway import Gateway
from app.llm.util import parse_json
from app.normalize.canonical import normalize_person
from app.scoring import core as sc

Scraper = Callable[[str, str], Awaitable[list[ScrapeResult]]]


# ---------- pub/sub for SSE (in-memory, single process) ----------

class Bus:
    def __init__(self):
        self.subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self.backlog: dict[str, list[dict]] = defaultdict(list)

    def publish(self, token: str, kind: str, data: dict):
        ev = {"kind": kind, **data}
        self.backlog[token] = (self.backlog[token] + [ev])[-400:]
        for q in self.subs[token]:
            q.put_nowait(ev)

    def subscribe(self, token: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        for ev in self.backlog[token]:
            q.put_nowait(ev)
        self.subs[token].append(q)
        return q

    def unsubscribe(self, token: str, q: asyncio.Queue):
        if q in self.subs[token]:
            self.subs[token].remove(q)


bus = Bus()


def scrub_nul(o):
    """Postgres JSONB and text reject the NUL character; scraped text sometimes contains it."""
    if isinstance(o, str):
        return o.replace("\x00", "")
    if isinstance(o, dict):
        return {scrub_nul(k): scrub_nul(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [scrub_nul(v) for v in o]
    return o


# ---------- people ----------

async def get_or_create_person(db: AsyncSession, li_url: str, ig_url: str, public: bool = False) -> m.Person:
    row = (await db.execute(select(m.Person).where(m.Person.linkedin_url == li_url,
                                                   m.Person.instagram_url == ig_url)
                            .order_by(m.Person.id))).scalars().first()
    if row:
        return row
    row = m.Person(linkedin_url=li_url, instagram_url=ig_url, public=public, status="pending")
    db.add(row)
    await db.flush()
    return row


async def store_scrape(db: AsyncSession, person_id: int, results: list[ScrapeResult]):
    await db.execute(delete(m.RawScrape).where(m.RawScrape.person_id == person_id))
    for r in results:
        db.add(m.RawScrape(person_id=person_id, source=r.source, provider=r.provider,
                           payload=scrub_nul(r.payload), ok=r.ok, error=scrub_nul(r.error)))


async def load_canon(db: AsyncSession, person_id: int) -> dict:
    rows = (await db.execute(select(m.RawScrape).where(m.RawScrape.person_id == person_id))).scalars().all()
    by = {r.source: (r.payload if r.ok else None) for r in rows}
    return normalize_person(by.get("ig"), by.get("li"), by.get("li_posts"))


async def build_profile(db: AsyncSession, gw: Gateway, person_id: int,
                        images: list[tuple[str, bytes]] | None = None, name: str | None = None) -> dict:
    canon = await load_canon(db, person_id)
    out = await extract_person(gw, canon, images, name)
    prof = out["profile"]
    prof["observations"] = out["observations"]          # evidence map the UI expands
    prof["persona_card"] = out["persona_card"]
    prof["voice_samples"] = out["voice_samples"]
    prof["name"] = prof["identity"].get("name") or name
    await db.execute(delete(m.Observation).where(m.Observation.person_id == person_id))
    for o in out["observations"]:
        db.add(m.Observation(person_id=person_id, source=o["source"], kind=o["kind"], text=scrub_nul(o["text"]),
                             ref=scrub_nul(o["ref"]), weight=o["weight"], confidence=o["confidence"]))
    await db.execute(delete(m.Profile).where(m.Profile.person_id == person_id))
    _, ver = load_prompt("synthesis")
    db.add(m.Profile(person_id=person_id, version=1, data=scrub_nul(json.loads(json.dumps(prof, default=str))),
                     confidence=prof["overall_confidence"], prompt_version=ver))
    person = await db.get(m.Person, person_id)
    person.display_name = prof["name"]
    person.status = "ready"
    return prof


async def load_profiles(db: AsyncSession, ids: list[int]) -> dict[int, dict]:
    rows = (await db.execute(select(m.Profile).where(m.Profile.person_id.in_(ids)))).scalars().all()
    return {r.person_id: r.data for r in rows}


# ---------- pools ----------

async def create_pool(db: AsyncSession, name: str, person_ids: list[int], frozen: bool = False) -> m.Pool:
    pool = m.Pool(token=secrets.token_urlsafe(16), name=name, frozen=frozen)
    db.add(pool)
    await db.flush()
    for pid in person_ids:
        db.add(m.PoolMember(pool_id=pool.id, person_id=pid))
    return pool


async def pool_members(db: AsyncSession, pool_id: int) -> list[int]:
    rows = (await db.execute(select(m.PoolMember.person_id).where(m.PoolMember.pool_id == pool_id))).all()
    return sorted(r[0] for r in rows)


def round_robin(ids: list[int]) -> list[tuple[int, int]]:
    """Circle method: every round, everyone plays once. Interleaves the grid so that if quota runs
    out the grid is still balanced and rankings are still computable (SPEC §10)."""
    xs = list(ids) + ([None] if len(ids) % 2 else [])
    n, out = len(xs), []
    for _ in range(n - 1):
        for i in range(n // 2):
            a, b = xs[i], xs[n - 1 - i]
            if a is not None and b is not None:
                out.append((min(a, b), max(a, b)))
        xs = [xs[0], xs[-1]] + xs[1:-1]
    return out


# ---------- dates ----------

async def _persist_date(sm: async_sessionmaker, a: int, b: int, gw: Gateway, profiles: dict[int, dict],
                        token: str, plan, samples, turn_route) -> str:
    async with sm() as db:
        row = (await db.execute(select(m.Date).where(m.Date.a_id == a, m.Date.b_id == b))).scalar_one_or_none()
        if row and row.status == "done":
            return "reused"
        if not row:
            row = m.Date(a_id=a, b_id=b, status="running", prompt_version=PROMPT_VERSION, transcript=[])
            db.add(row)
            await db.flush()
        row.status = "running"
        date_id, transcript = row.id, list(row.transcript or [])
        await db.commit()

    pa = DatePerson(a, profiles[a]["name"], profiles[a]["persona_card"])
    pb = DatePerson(b, profiles[b]["name"], profiles[b]["persona_card"])

    async def save(t):
        async with sm() as db2:
            r = await db2.get(m.Date, date_id)
            r.transcript = t
            await db2.commit()

    async def emit(kind, data):
        bus.publish(token, kind, {**data, "date_id": date_id})

    try:
        res = await run_date(gw, pa, pb, transcript, save, emit, plan=plan, samples=samples,
                             turn_route=turn_route)
    except Exception as e:
        async with sm() as db3:
            r = await db3.get(m.Date, date_id)
            r.status = "failed"
            r.metrics = {"error": repr(e)[:300]}
            await db3.commit()
        bus.publish(token, "date_failed", {"date_id": date_id, "a": a, "b": b, "error": repr(e)[:160]})
        return "failed"

    async with sm() as db4:
        await db4.execute(delete(m.Verdict).where(m.Verdict.date_id == date_id))
        for rater, vs in res.verdicts.items():
            target = b if rater == a else a
            for k, v in enumerate(vs):
                db4.add(m.Verdict(date_id=date_id, from_id=rater, to_id=target, sample_idx=k,
                                  scores=v["scores"], second_date=v["second_date"],
                                  reason=v["reason"], quote=v["quote"]))
        r = await db4.get(m.Date, date_id)
        r.transcript = res.transcript
        r.status = "done" if all(res.verdicts.get(p) for p in (a, b)) else "failed"
        r.metrics = {"flags": res.flags}
        await db4.commit()
    return "done" if all(res.verdicts.get(p) for p in (a, b)) else "failed"


async def run_pool_dates(sm: async_sessionmaker, gw: Gateway, token: str, pairs: list[tuple[int, int]],
                         profiles: dict[int, dict], concurrency: int = 6, plan=None, samples=None,
                         turn_route: str | None = "turns") -> dict:
    sem = asyncio.Semaphore(concurrency)
    tally = {"done": 0, "failed": 0, "reused": 0}

    async def one(a, b):
        async with sem:
            r = await _persist_date(sm, a, b, gw, profiles, token, plan, samples, turn_route)
            tally[r] += 1
            bus.publish(token, "progress", {"tally": dict(tally), "total": len(pairs)})
    await asyncio.gather(*(one(a, b) for a, b in pairs))
    return tally


async def run_debriefs(sm: async_sessionmaker, gw: Gateway, ids: list[int], profiles: dict[int, dict]):
    """One call per person ranks its partners using each verdict's one-line reason (SPEC §10)."""
    system, ver = load_prompt("debrief")
    async with sm() as db:
        vs = (await db.execute(select(m.Verdict).where(m.Verdict.from_id.in_(ids), m.Verdict.to_id.in_(ids),
                                                       m.Verdict.sample_idx == 0))).scalars().all()
    by: dict[int, list[m.Verdict]] = defaultdict(list)
    for v in vs:
        by[v.from_id].append(v)

    async def one(pid):
        mine = by.get(pid, [])
        if len(mine) < 2:
            return
        lines = "\n".join(f"partner {v.to_id}: {v.reason}" for v in mine)
        sys_ = system.replace("{{NAME}}", profiles[pid]["name"])
        want = {v.to_id for v in mine}
        for attempt in range(2):
            text, _ = await gw.complete(prompt_version=ver, system=sys_, user=f"<data>\n{lines}\n</data>",
                                        temperature=settings.temp_rank, sample=attempt, json_mode=True,
                                        route="verdict")
            try:
                order = parse_json(text)
                order = order.get("ranking", order) if isinstance(order, dict) else order
                order = [int(str(x).replace("partner", "").strip()) for x in order]
            except Exception:
                continue
            order = list(dict.fromkeys(x for x in order if x in want))
            order += sorted(want - set(order))  # any omitted partner goes last, deterministically
            async with sm() as db:
                await db.execute(delete(m.Debrief).where(m.Debrief.from_id == pid))
                db.add(m.Debrief(from_id=pid, ranking=order))
                await db.commit()
            return
    await asyncio.gather(*(one(p) for p in ids))


# ---------- scoring from the database ----------

async def load_scoring_inputs(db: AsyncSession, ids: list[int]):
    vs = (await db.execute(select(m.Verdict).where(m.Verdict.from_id.in_(ids), m.Verdict.to_id.in_(ids)))).scalars().all()
    verdicts: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for v in vs:
        verdicts[(v.from_id, v.to_id)].append({"scores": v.scores, "second_date": v.second_date})
    ds = (await db.execute(select(m.Debrief).where(m.Debrief.from_id.in_(ids)))).scalars().all()
    debrief = {d.from_id: [x for x in d.ranking if x in ids] for d in ds}
    return dict(verdicts), debrief


def stated_by_topic(profile: dict) -> dict:
    return {s["topic"]: {"value_normalized": s.get("value_normalized"), "quote": s["quote"], "value": s.get("value")}
            for s in profile.get("stated_signals", [])}


async def compute_rankings(db: AsyncSession, ids: list[int], own_weight: float | None = None,
                           frozen: dict | None = None) -> dict:
    verdicts, debrief = await load_scoring_inputs(db, ids)
    profiles = await load_profiles(db, ids)
    own = sc.own_scores(verdicts, debrief, frozen=frozen)
    conflicts = {}
    for (a, b) in own:
        if a < b and a in profiles and b in profiles:
            c = sc.detect_conflicts(stated_by_topic(profiles[a]), stated_by_topic(profiles[b]))
            if c:
                conflicts[(a, b)] = c
    fin = sc.final_scores(own, conflicts, own_weight)
    ranked = sc.rankings(fin)
    # best quoted moment for each directed pair (first verdict sample)
    vs = (await db.execute(select(m.Verdict).where(m.Verdict.from_id.in_(ids), m.Verdict.sample_idx == 0))).scalars().all()
    quotes = {(v.from_id, v.to_id): {"quote": v.quote, "reason": v.reason, "second_date": v.second_date} for v in vs}
    sim = {}
    comp = {}
    for (a, b) in own:
        if a in profiles and b in profiles:
            s1, s2 = baseline_similarity(profiles[a], profiles[b]), baseline_complement(profiles[a], profiles[b])
            if s1 is not None:
                sim[(a, b)] = s1
            if s2 is not None:
                comp[(a, b)] = s2
    hyp = sc.hypothesis_panel({k: v["adj"] for k, v in own.items()}, sim, comp)
    out = {}
    for a, rows in ranked.items():
        out[a] = [{**r, "moment": quotes.get((a, r["target"])), "target_name": profiles.get(r["target"], {}).get("name")}
                  for r in rows]
    return {"rankings": out, "hypothesis": hyp, "n_dates": len(own) // 2}
