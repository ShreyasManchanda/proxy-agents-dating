import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api.routes import router
from app.db import models as m
from app.db.session import Session
from app.llm.gateway import DbCache, build_default_gateway


async def prewarm(app: FastAPI):
    """Published (frozen) pools never change, so compute every page the demo needs once at start-up and keep
    it in memory. The first visitor then gets instant pages, and nothing here calls an LLM."""
    await asyncio.sleep(2)
    try:
        async with Session() as db:
            tokens = [t for (t,) in (await db.execute(select(m.Pool.token).where(m.Pool.frozen.is_(True)))).all()]
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://warm", timeout=120) as c:
            for t in tokens:
                pool = (await c.get(f"/api/pools/{t}")).json()
                dates = (await c.get(f"/api/pools/{t}/dates")).json()
                await c.get(f"/api/pools/{t}/diagnostics")
                for w in range(21):  # every slider position
                    await c.get(f"/api/pools/{t}/rankings?own_weight={w / 20:.2f}")
                for person in pool.get("people", []):
                    await c.get(f"/api/pools/{t}/people/{person['id']}")
                for d in dates:
                    await c.get(f"/api/pools/{t}/dates/{d['id']}")
    except Exception:  # warming is best-effort, never a reason to fail start-up
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.sm = Session
    app.state.gw = build_default_gateway(DbCache(Session))
    task = asyncio.create_task(prewarm(app))
    yield
    task.cancel()


app = FastAPI(title="Agentic Dating", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"ok": True}


_dist = Path(__file__).resolve().parent.parent / "web" / "dist"
if _dist.is_dir():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        """Single-page app: any non-API path serves index.html (client-side routing)."""
        f = _dist / path
        return FileResponse(f if path and f.is_file() else _dist / "index.html")
